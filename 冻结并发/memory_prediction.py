"""Forecast memory growth from existing per-task historical envelopes."""

from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
import math
import json
from typing import Protocol

from segmented_scheduler import Curve


@dataclass(frozen=True)
class MemoryPrediction:
    """Right-continuous steps of (seconds ahead, extra bytes above live usage)."""

    # Starts at offset zero. A startup forecast can charge immediately when
    # its planned release is due. The final value holds to the horizon.
    steps: tuple[tuple[float, int], ...]
    phase_range_s: tuple[float, float] | None = None
    match_basis: str | None = None

    def __post_init__(self):
        if (not self.steps or self.steps[0][0] != 0.
                or any(not math.isfinite(lead) or growth < 0 for lead, growth in self.steps)
                or any(left[0] >= right[0] for left, right in zip(self.steps, self.steps[1:]))):
            raise ValueError('prediction steps must start at zero and have increasing offsets')


class MemoryPredictor(Protocol):
    def predict(self, name: str, now: float, age_s: float | None, current_bytes: int,
                horizon_s: float, *, phase_floor_s: float = 0., phase_ceiling_s: float | None = None,
                anonymous_bytes: int | None = None) -> MemoryPrediction | None:
        """Predict continued execution, or return None if the phase is unknown."""
        ...

    def predict_startup(self, name: str, now: float, lead_s: float,
                        horizon_s: float) -> MemoryPrediction | None:
        """Predict absolute new charge from a scheduled release within the horizon."""
        ...


def phase_events(operation, rows):
    """Normalize landmarks emitted by the existing workload scripts."""
    krita_events = {'KRITA_PROCESS', 'PRE_IMPORT_REVIEW_START', 'PRE_IMPORT_REVIEW_DONE',
                    'HIGH_DOCUMENT_SUBMITTED', 'CAPTURE_WINDOW_DONE', 'HIGH_INSTANCE_EXIT',
                    'POST_CLOSE_REVIEW_START'}
    raster_events = {'tile_background_start', 'full_raster_start', 'forward_fft',
                     'frequency_filter', 'inverse_fft', 'residual_and_output'}
    for row in rows:
        if 'monotonic_ns' not in row:
            continue
        if operation == 'foreground_krita':
            key = row.get('kind')
            if key not in krita_events:
                continue
        elif operation == 'raster_fft':
            key = row.get('event')
            if key == 'tile_progress':
                key = f"tile:{row['completed_tiles']}"
            elif key not in raster_events:
                continue
        elif row.get('event_type') == 'phase_start':
            key = row['phase']
        elif row.get('event_type') == 'task_start':
            key = 'task_start'
        else:
            continue
        yield key, row['monotonic_ns']


def read_events(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A live workload can still be writing its final line.
                continue


def reference_markers(operation, rows, origin_ns, duration):
    return {key: (stamp-origin_ns)/1e9 for key, stamp in phase_events(operation, rows)
            if 0 <= (stamp-origin_ns)/1e9 < duration}


class HistoricalLookup:
    def __init__(self, models, config):
        self.curves = {name: Curve(model) for name, model in models.items()}
        self.anonymous = {name: Curve(model['anonymous_curve']) for name, model in models.items()
                          if 'anonymous_curve' in model}
        self.phase_search_s = config['phase_search_s']
        self.level_tolerance = config['level_tolerance_bytes']
        self.growth_margin = config.get('growth_margin_bytes', 0)
        if ('default' not in self.phase_search_s
                or any(not math.isfinite(value) or value < 0 for value in self.phase_search_s.values())
                or self.level_tolerance < 0 or self.growth_margin < 0):
            raise ValueError('invalid historical lookup settings')

    def predict(self, name, now, age_s, current_bytes, horizon_s, *, phase_floor_s=0.,
                phase_ceiling_s=None, anonymous_bytes=None):
        curve = self.curves.get(name)
        if curve is None or age_s is None:
            return None
        if anonymous_bytes is not None:
            return self.predict_matched(name, curve, age_s, current_bytes, anonymous_bytes,
                                        horizon_s, phase_floor_s, phase_ceiling_s)

        radius = self.phase_search_s.get(name, self.phase_search_s['default'])
        # The reference envelope is sampled in half-second bins. Keep the
        # observed age's fractional offset when looking at neighbouring bins.
        phases = sorted({max(phase_floor_s, round(age_s + step * .5, 9))
                         for step in range(-int(radius * 2), int(radius * 2) + 1)})
        tolerance = max(self.level_tolerance, current_bytes * .05)
        matched = []
        paths = []
        # The terminal sample reflects cleanup and does not predict live exit.
        last_running = len(curve.times) - 2
        for phase in phases:
            index = bisect_right(curve.times, phase) - 1
            if index > last_running:
                continue
            anchor = curve.values[index]
            if abs(current_bytes - anchor / curve.level_scale) > tolerance:
                continue
            matched.append(phase)
            path = [(0., 0)]
            for i in range(index + 1, last_running + 1):
                lead = round(curve.times[i] - phase, 9)
                if lead > horizon_s:
                    break
                growth = max(0, curve.values[i] - anchor)
                path.append((lead, growth + self.growth_margin if growth else 0))
            paths.append(path)
        if not matched:
            return None

        steps = []
        for lead in sorted({lead for path in paths for lead, _ in path}):
            growth = max(path[bisect_right(path, (lead, math.inf)) - 1][1] for path in paths)
            if not steps or growth != steps[-1][1]:
                steps.append((lead, growth))
        return MemoryPrediction(tuple(steps), (matched[0], matched[-1]))

    def predict_remaining_peak(self, name, current_bytes, anonymous_bytes, *, phase_floor_s=0.):
        """Reserve the highest remaining charge after the last confirmed milestone."""
        curve = self.curves.get(name)
        if curve is None:
            return None
        last_running = curve.times[-2]
        total_peak = curve.maximum(min(phase_floor_s, last_running), last_running)
        growth = max(0, total_peak - current_bytes)
        anon_curve = self.anonymous.get(name)
        if anon_curve is not None:
            last_running = anon_curve.times[-2]
            anon_peak = anon_curve.maximum(min(phase_floor_s, last_running), last_running)
            growth = max(growth, anon_peak - anonymous_bytes)
        if growth:
            growth += self.growth_margin
        return MemoryPrediction(((0., growth),), match_basis='remaining_peak')

    def predict_matched(self, name, curve, age_s, current, anon, horizon, floor, ceiling):
        anon_curve = self.anonymous.get(name)
        level_curve = anon_curve or curve
        level = anon if anon_curve else current
        radius = self.phase_search_s.get(name, self.phase_search_s['default'])
        ceiling = min(ceiling if ceiling is not None else curve.duration, curve.duration)
        origin = min(ceiling, max(floor, age_s))
        phases = sorted({min(ceiling, max(floor, round(origin + step * .5, 9)))
                         for step in range(-int(radius * 2), int(radius * 2) + 1)})
        phases = [p for p in phases if p < curve.duration]
        if not phases or (ceiling == curve.duration and age_s-radius >= ceiling):
            # An overrun has no known release time. Bound the remaining
            # charge with the observed peak from the last confirmed stage.
            growth = max(0, curve.maximum(min(floor, curve.duration), curve.duration) - anon)
            if growth:
                growth += self.growth_margin
            return MemoryPrediction(((0., growth),), match_basis='reference_peak_bound')
        tolerance = max(self.level_tolerance, level * .05)
        matched = [p for p in phases if abs(level_curve.value(p) / level_curve.level_scale - level) <= tolerance]
        basis = ('anonymous' if anon_curve else 'total') if matched else 'phase_envelope'
        phases = matched or phases
        paths = []
        for phase in phases:
            anchor = curve.value(phase)
            anon_anchor = min(anon, anon_curve.value(phase)) if anon_curve else 0
            leads = {0.}
            for track in (curve, anon_curve):
                if track is not None:
                    start = bisect_right(track.times, phase)
                    stop = min(len(track.times) - 1, bisect_right(track.times, phase + horizon))
                    leads.update(round(t - phase, 9) for t in track.times[start:stop])
            path = []
            for lead in sorted(leads):
                at = round(phase + lead, 9)
                total_growth = curve.value(min(at, curve.times[-2])) - anchor
                anon_growth = (anon_curve.value(min(at, anon_curve.times[-2])) - anon_anchor
                               if anon_curve else 0)
                growth = max(0, total_growth, anon_growth)
                path.append((lead, growth + self.growth_margin if growth else 0))
            paths.append(path)
        result = []
        for lead in sorted({lead for path in paths for lead, _ in path}):
            growth = max(path[bisect_right(path, (lead, math.inf)) - 1][1] for path in paths)
            if not result or result[-1][1] != growth:
                result.append((lead, growth))
        return MemoryPrediction(tuple(result), (phases[0], phases[-1]), basis)

    def predict_startup(self, name, now, lead_s, horizon_s):
        curve = self.curves.get(name)
        if curve is None or not 0 <= lead_s <= horizon_s:
            return None
        lead_s = round(lead_s, 9)
        steps = [(0., 0)] if lead_s > 0 else []
        for age, value in curve.points[:-1]:
            lead = round(lead_s + age, 9)
            if lead > horizon_s:
                break
            steps.append((lead, value + self.growth_margin if value else 0))
        return MemoryPrediction(tuple(steps), match_basis='planned_start')


@dataclass
class ErrorWindow:
    started_s: float
    signature: tuple
    trajectory: tuple
    max_error_bytes: int = 0
    sampled: bool = False


class ForecastErrorReserve:
    """Learn one-sided residuals from completed, uninterrupted forecast windows."""

    def __init__(self, config, cold_reserve, horizon_s):
        self.base = config['base_bytes']
        self.minimum_windows = config['min_windows']
        self.bucket_s = config['phase_bucket_s']
        if (type(self.base) is not int or self.base < 0
                or type(self.minimum_windows) is not int or not 1 <= self.minimum_windows <= 64
                or not math.isfinite(self.bucket_s) or self.bucket_s <= 0):
            raise ValueError('invalid adaptive prediction reserve settings')
        self.cold_reserve = max(self.base, cold_reserve)
        self.horizon_s = horizon_s
        self.windows = defaultdict(lambda: deque(maxlen=64))
        self.pending = None

    def observe(self, now, available, phase, signature, stale):
        window = self.pending
        if window is not None:
            elapsed = now - window.started_s
            if stale or signature != window.signature:
                self.pending = None
            else:
                if 0 < elapsed <= self.horizon_s:
                    predicted = window.trajectory[bisect_right(window.trajectory, (elapsed, math.inf)) - 1][1]
                    window.max_error_bytes = max(window.max_error_bytes, predicted - available)
                    window.sampled = True
                if elapsed >= self.horizon_s:
                    if window.sampled:
                        self.windows[phase].append(window.max_error_bytes)
                    self.pending = None

        errors = self.windows.get(phase, ())
        if len(errors) < self.minimum_windows:
            margin = max(self.cold_reserve - self.base, max(errors, default=0))
            source = 'cold_start'
        else:
            margin = sorted(errors)[math.ceil(.95 * len(errors)) - 1]
            source = 'phase_p95'
        return dict(base_bytes=self.base, error_margin_bytes=margin,
                    reserve_bytes=self.base + margin, windows=len(errors), source=source)

    def record(self, now, signature, trajectory, changed):
        if changed:
            self.pending = None
        elif self.pending is None and trajectory:
            self.pending = ErrorWindow(now, signature, trajectory)
