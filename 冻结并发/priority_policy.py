"""Memory admission and pressure response for named cgroup workloads."""
from bisect import bisect_right
from collections import deque
from dataclasses import dataclass
from itertools import permutations
import json
import math
from mmap import PAGESIZE

from memory_prediction import ForecastErrorReserve, HistoricalLookup, MemoryPredictor


@dataclass(frozen=True)
class TaskMemory:
    priority: int
    protected: bool
    running: bool
    current: int
    anon: int
    peak: int | None
    age_s: float | None = None
    phase_floor_s: float | None = None
    phase_ceiling_s: float | None = None
    phase_marker: str | None = None
    freeze_eligible: bool = True

    @property
    def growth(self):
        if self.peak is None:
            return None
        # MemAvailable can already count file cache as reclaimable.
        return max(0, self.peak - self.anon)


def forecast_trajectory(available, forecasts, horizon, confirmation, freeze=()):
    stop = {name: min(horizon, (i + 1) * confirmation) for i, name in enumerate(freeze)}
    paths = {}
    for name, forecast in forecasts.items():
        path = forecast.steps
        if name in stop:
            delay = stop[name]
            prefix = tuple(step for step in path if step[0] <= delay)
            # Bytes charged before confirmation can remain resident.
            path = prefix + ((delay, max(growth for _, growth in prefix)),)
        paths[name] = path
    leads = sorted({0., *(lead for path in paths.values() for lead, _ in path)})
    return tuple((lead, available - sum(path[bisect_right(path, (lead, math.inf)) - 1][1]
                                        for path in paths.values())) for lead in leads)


def forecast_budget(trajectory, reserve):
    minimum = min(available for _, available in trajectory)
    first_risk = next((lead for lead, available in trajectory if available < reserve), None)
    return dict(min_available_bytes=minimum, first_risk_in_s=first_risk)


def choose_freeze(reserve, available, forecasts, trajectory, order, horizon, confirmation, evidence):
    continued = forecast_budget(trajectory, reserve)
    evidence['continued'] = continued
    risk = continued['first_risk_in_s']
    if risk is None:
        return []
    best = []
    best_budget = continued
    for count in range(1, len(order) + 1):
        for group in permutations(order, count):
            budget = forecast_budget(forecast_trajectory(available, forecasts, horizon, confirmation, group), reserve)
            first_risk = budget['first_risk_in_s']
            if first_risk is None:
                evidence.update(reason='forecast_overlap', after_freeze=budget)
                return list(group)
            if first_risk >= risk and budget['min_available_bytes'] > best_budget['min_available_bytes']:
                best, best_budget = list(group), budget
    if best:
        evidence.update(reason='forecast_overlap', after_freeze=best_budget)
    else:
        evidence['reason'] = 'freeze_cannot_mitigate'
    return best


class LegacyPriorityPolicy:
    """Reproduce older archives with peak admission, adaptive reserves and soft limits."""
    def __init__(self, reserve, emergency_floor, config, predictor: MemoryPredictor | None = None,
                 *, legacy_live_freeze=False):
        self.reserve = reserve
        self.emergency_floor = emergency_floor
        self.config = config
        self.history = deque()
        self.stable_since = {}
        self.throttled = False
        self.limits = {}
        self.predictor = predictor
        self.legacy_live_freeze = legacy_live_freeze
        self.prediction_config = config.get('freeze_prediction')
        if predictor is not None and self.prediction_config is None:
            raise ValueError('a memory predictor requires freeze_prediction settings')
        if predictor is not None and any(
                not math.isfinite(self.prediction_config[key]) or self.prediction_config[key] <= 0
                for key in ('horizon_s', 'confirmation_s')):
            raise ValueError('a positive prediction horizon and confirmation budget are required')
        self.adaptive = None
        if predictor is not None and 'adaptive_reserve' in self.prediction_config:
            self.adaptive = ForecastErrorReserve(self.prediction_config['adaptive_reserve'], reserve,
                                                 self.prediction_config['horizon_s'])

    def forecast_trajectory(self, available, forecasts, freeze=()):
        return forecast_trajectory(available, forecasts, self.prediction_config['horizon_s'],
                                   self.prediction_config['confirmation_s'], freeze)

    def forecasts(self, now, tasks):
        horizon = self.prediction_config['horizon_s']
        forecasts = {}
        for name, task in sorted(tasks.items()):
            phase = {} if task.phase_floor_s is None else {'phase_floor_s': task.phase_floor_s}
            forecast = self.predictor.predict(name, now, task.age_s, task.current, horizon, **phase)
            if forecast is not None and forecast.steps[-1][0] <= horizon:
                forecasts[name] = forecast
        return forecasts

    def predict_freeze(self, available, active, forecasts, trajectory, freeze_order, evidence):
        evidence['unavailable'] = sorted(active.keys() - forecasts.keys())
        evidence['phases_s'] = {name: list(f.phase_range_s) for name, f in forecasts.items()
                                if f.phase_range_s is not None}
        if evidence['unavailable']:
            evidence['reason'] = 'forecast_unavailable'
            return []

        return choose_freeze(evidence['reserve_bytes'], available, forecasts, trajectory, freeze_order,
                             self.prediction_config['horizon_s'], self.prediction_config['confirmation_s'],
                             evidence)

    def decide(self, now, available, tasks):
        cfg = self.config
        stale = bool(self.history and now - self.history[-1][0] > cfg['max_sample_gap_s'])
        if stale:
            self.stable_since.clear()
        self.history.append((now, available))
        while now - self.history[0][0] > cfg['history_s']:
            self.history.popleft()
        rate = max([0.] + [(past - available) / (now - stamp) for stamp, past in self.history
                           if now - stamp >= cfg['rate_window_s']])
        urgent = self.reserve + int(rate * cfg['rate_multiplier'] * cfg['reaction_s'])
        margin = cfg['headroom_bytes']
        self.throttled = available < urgent + margin * (2 if self.throttled else 1)
        active = {name: task for name, task in tasks.items() if task.running}
        background = {name: task for name, task in active.items() if not task.protected}
        abort = self.emergency_floor is not None and available < self.emergency_floor
        freeze = []
        prediction = None
        trajectory = None
        reserve = self.reserve
        forecasts = {}
        active_forecasts = {}
        if self.adaptive is not None:
            # Use the protected task's stage for both sides of a thaw. Adding
            # a background task does not switch the reserve to a new bucket.
            protected_stage = tuple((name, task.phase_floor_s, None if task.age_s is None else
                                     int(task.age_s // self.adaptive.bucket_s))
                                    for name, task in sorted(active.items()) if task.protected)
            phase = (protected_stage, tuple(sorted(tasks)))
            signature = (phase, tuple(sorted(active)))
            reserve_info = self.adaptive.observe(now, available, phase, signature, stale)
            reserve = reserve_info['reserve_bytes']

        if self.predictor is not None:
            prediction = dict(horizon_s=self.prediction_config['horizon_s'],
                              reserve_bytes=reserve, reason=None)
            if self.adaptive is not None:
                prediction['reserve_calibration'] = reserve_info
                prediction['resume'] = {}
            if abort:
                prediction['reason'] = 'emergency_floor'
            elif background or self.adaptive is not None:
                forecasts = self.forecasts(now, tasks if self.adaptive is not None else active)
                active_forecasts = {name: forecasts[name] for name in active if name in forecasts}
                if active.keys() <= active_forecasts.keys():
                    trajectory = self.forecast_trajectory(available, active_forecasts)
                if background:
                    freeze_order = sorted(background, key=lambda name: (background[name].priority, name))
                    freeze = self.predict_freeze(available, active, active_forecasts, trajectory,
                                                 freeze_order, prediction)
        elif self.legacy_live_freeze:
            # Reproduce runs recorded before prediction-based freezing.
            freeze_order = sorted(background, key=lambda name: (
                background[name].priority, -(background[name].growth or 0), name))
            if abort:
                freeze = freeze_order
            elif available < urgent:
                freeze = freeze_order[:1]

        # A prior is advisory. A workload that outgrows it blocks further
        # admissions while it runs, even when the last sample showed free RAM.
        growth = [task.growth for task in active.values()]
        reliable = all(task.peak is not None and task.current <= task.peak
                       for task in active.values())
        required = {}
        ready = []
        for name, task in tasks.items():
            if task.running or task.protected:
                continue
            if self.adaptive is not None:
                needed = None
                missing = sorted((active.keys() | {name}) - forecasts.keys())
                if missing:
                    prediction['resume'][name] = dict(reason='forecast_unavailable', unavailable=missing)
                else:
                    joint = {**active_forecasts, name: forecasts[name]}
                    minimum = min(value for _, value in self.forecast_trajectory(available, joint))
                    target = reserve + 2 * margin
                    # required_bytes is inclusive. Thaw requires strictly
                    # more projected headroom than the target.
                    needed = target + available - minimum + 1
                    prediction['resume'][name] = dict(
                        reason='insufficient_headroom' if available < needed else 'budget_met',
                        min_available_bytes=minimum, target_available_bytes=target)
            elif reliable and task.peak is not None and task.current <= task.peak:
                needed = urgent + 2 * margin + sum(growth) + task.growth
            elif not active and not any(other.anon > margin for key, other in tasks.items()
                                        if key != name and not other.running):
                # Unknown work can run alone. Keep it out of joint admissions.
                needed = urgent + 2 * margin
            else:
                needed = None
            required[name] = needed
            if (abort or freeze or (self.adaptive is None and self.throttled)
                    or needed is None or available < needed):
                self.stable_since.pop(name, None)
                continue
            since = self.stable_since.setdefault(name, now)
            if now - since >= cfg['resume_stable_s']:
                ready.append(name)
            elif self.adaptive is not None:
                prediction['resume'][name]['reason'] = 'awaiting_stability'
        for name in tuple(self.stable_since):
            if name not in required:
                del self.stable_since[name]
        resume = min(ready, key=lambda name: (-tasks[name].priority, name), default=None)
        if resume is not None:
            self.stable_since.pop(resume)

        self.limits = {name: limit for name, limit in self.limits.items() if name in tasks}
        limits = {}
        if cfg['memory_high']:
            for name in set(background) | ({resume} if resume is not None else set()):
                task = tasks[name]
                limit = task.peak if task.peak is not None and task.current <= task.peak else None
                if self.throttled:
                    target = max(task.anon + cfg['allocation_margin_bytes'], task.current - margin)
                    candidates = [x for x in (limit, self.limits.get(name), target) if x is not None]
                    limit = min(candidates)
                if name not in self.limits or self.limits[name] != limit:
                    limits[name] = limit
            self.limits.update(limits)
        if self.adaptive is not None:
            # Only score the continue-as-is trajectory against the same
            # action, never against measurements following a control change.
            calibration_path = trajectory if active and active.keys() == tasks.keys() else None
            self.adaptive.record(now, signature, calibration_path, bool(abort or freeze or resume or limits))
        decision = dict(available_bytes=available, urgent_bytes=urgent, required_bytes=required,
                        throttle=self.throttled, freeze=freeze, resume=resume, limits=limits, abort=abort)
        if prediction is not None:
            decision['freeze_prediction'] = prediction
        return decision


class PriorityPolicy:
    """One predictive budget for both freeze and thaw, with fixed hysteresis."""

    def __init__(self, config, predictor, *, peak_lookup=None):
        self.predictor = predictor
        self.peak_lookup = predictor if peak_lookup is None else peak_lookup
        self.prediction_config = config['freeze_prediction']
        self.reserve_foreground_peak = self.prediction_config.get('reserve_foreground_peak', False)
        self.horizon = self.prediction_config['horizon_s']
        self.confirmation = self.prediction_config['confirmation_s']
        self.reserve = self.prediction_config['reserve_bytes']
        self.resume_target = self.reserve + self.prediction_config['resume_margin_bytes']
        self.stable_window = config['resume_stable_s']
        self.max_gap = config['max_sample_gap_s']
        self.last_tick = None
        self.stable_since = {}
        if (not 0 < self.reserve < self.resume_target
                or any(not math.isfinite(x) or x <= 0 for x in
                       (self.horizon, self.confirmation, self.stable_window, self.max_gap))):
            raise ValueError('fixed predictive admission requires positive timing and thaw hysteresis')

    def decide(self, now, available, tasks, upcoming=None):
        if self.last_tick is not None and now - self.last_tick > self.max_gap:
            self.stable_since.clear()
        self.last_tick = now
        upcoming = {op: lead for op, lead in (upcoming or {}).items()
                    if op not in tasks and 0 <= lead <= self.horizon}
        forecasts = {}
        for op, task in sorted(tasks.items()):
            if task.protected and self.reserve_foreground_peak:
                # Charge the remaining peak throughout the background window.
                # This stays in the budget for both freezing and thawing.
                prediction = self.peak_lookup.predict_remaining_peak(
                    op, task.current, task.anon, phase_floor_s=task.phase_floor_s or 0.)
            else:
                prediction = self.predictor.predict(op, now, task.age_s, task.current, self.horizon,
                    phase_floor_s=task.phase_floor_s or 0., phase_ceiling_s=task.phase_ceiling_s,
                    anonymous_bytes=task.anon)
            if prediction is not None and prediction.steps[-1][0] <= self.horizon:
                forecasts[op] = prediction
        for op, lead in sorted(upcoming.items()):
            prediction = self.predictor.predict_startup(op, now, lead, self.horizon)
            if prediction is not None and prediction.steps[-1][0] <= self.horizon:
                forecasts[op] = prediction

        active = {op for op, task in tasks.items() if task.running}
        joint = active | upcoming.keys()
        current = {op: forecasts[op] for op in joint if op in forecasts}
        missing = sorted(joint - forecasts.keys())
        order = sorted((op for op in active if not tasks[op].protected and tasks[op].freeze_eligible),
                       key=lambda op: (tasks[op].priority, op))
        evidence = dict(horizon_s=self.horizon, reserve_bytes=self.reserve, reason=None,
                        resume_target_available_bytes=self.resume_target, resume_stable_s=self.stable_window,
                        upcoming_s=upcoming, unavailable=missing, resume={},
                        phases_s={op: list(f.phase_range_s) for op, f in forecasts.items()
                                  if f.phase_range_s is not None},
                        match_basis={op: f.match_basis for op, f in forecasts.items() if f.match_basis})
        if self.reserve_foreground_peak:
            evidence['foreground_peak_growth_bytes'] = {
                op: forecasts[op].steps[0][1] for op in sorted(active & forecasts.keys()) if tasks[op].protected
            }
        freeze = []
        if missing:
            evidence['reason'] = 'forecast_unavailable'
        else:
            trajectory = forecast_trajectory(available, current, self.horizon, self.confirmation)
            freeze = choose_freeze(self.reserve, available, current, trajectory, order,
                                    self.horizon, self.confirmation, evidence)

        required, ready = {}, []
        candidates = {op: task for op, task in tasks.items() if not task.running and not task.protected}
        for op in sorted(candidates):
            unknown = sorted((joint | {op}) - forecasts.keys())
            required[op] = None
            if unknown:
                evidence['resume'][op] = dict(reason='forecast_unavailable', unavailable=unknown)
                self.stable_since.pop(op, None)
                continue
            resumed = {**current, op: forecasts[op]}
            trajectory = forecast_trajectory(available, resumed, self.horizon, self.confirmation)
            budget = forecast_budget(trajectory, self.resume_target)
            minimum = budget['min_available_bytes']
            required[op] = self.resume_target + available - minimum + 1
            check = dict(min_available_bytes=minimum, target_available_bytes=self.resume_target)
            evidence['resume'][op] = check
            if freeze or minimum <= self.resume_target:
                check['reason'] = 'freeze_pending' if freeze else 'insufficient_headroom'
                self.stable_since.pop(op, None)
                continue
            since = self.stable_since.setdefault(op, now)
            check['reason'] = 'awaiting_stability'
            if now - since >= self.stable_window:
                ready.append(op)
        resume = min(ready, key=lambda op: (-tasks[op].priority, op), default=None)
        self.stable_since = {op: since for op, since in self.stable_since.items() if op in candidates}
        if resume is not None:
            evidence['resume'][resume]['reason'] = 'budget_met'
            # Other candidates must establish stability with the new running set.
            self.stable_since.clear()
        return dict(available_bytes=available, required_bytes=required, freeze=freeze,
                    resume=resume, abort=False, freeze_prediction=evidence)


def policy_from_plan(plan, predictor=None, *, replay=False):
    budget = plan['budget']
    config = plan['priority']
    forecast = config.get('freeze_prediction', {})
    if 'reserve_bytes' in forecast:
        if config.get('memory_high') or 'adaptive_reserve' in forecast:
            raise ValueError('fixed predictive mode supports freeze and thaw only')
        if forecast['reserve_bytes'] != budget['reserve_bytes']:
            raise ValueError('fixed reserve differs between the plan and predictive policy')
        lookup = (HistoricalLookup(plan['models'], forecast)
                  if predictor is None or forecast.get('reserve_foreground_peak') else None)
        return PriorityPolicy(config, lookup if predictor is None else predictor, peak_lookup=lookup)
    if not replay:
        raise ValueError('priority execution requires fixed predictive reserve settings')
    floor = budget.get('emergency_floor_bytes', budget['foreground_only_floor_bytes'])
    if predictor is None:
        if 'freeze_prediction' in config:
            predictor = HistoricalLookup(plan['models'], config['freeze_prediction'])
    return LegacyPriorityPolicy(budget['reserve_bytes'], floor, config, predictor,
                                legacy_live_freeze=predictor is None)


def audit_decisions(root, plan, freezes, checkpoint_ns, predictor=None):
    policy = policy_from_plan(plan, predictor, replay=True)
    errors = []
    requests = set()
    max_freeze_ms = 0.
    checkpoints = set()
    transitions = {(event['decision_tick'], event['operation'], event['action']): event
                   for event in freezes if 'decision_tick' in event}
    count = 0
    limit_writes = 0
    last = 0.
    with (root / 'priority_decisions.jsonl').open(encoding='utf-8') as stream:
        for count, line in enumerate(stream, 1):
            row = json.loads(line)
            now = row['monotonic_s']
            tick = row['tick']
            checkpoint = row['checkpoint_ns']
            if tick != count or now <= last:
                errors.append(f'tick {tick}: decision order')
            last = now
            if checkpoint is not None:
                checkpoints.add(checkpoint)
                if now < checkpoint / 1e9 or checkpoint != checkpoint_ns:
                    errors.append(f'tick {tick}: unconfirmed checkpoint')
            tasks = {name: TaskMemory(**task) for name, task in row['tasks'].items()}
            for name, task in tasks.items():
                peak = plan['priority_peaks_bytes'].get(name)
                protected = name == 'foreground_krita'
                if protected and checkpoint is not None:
                    peak = plan.get('priority_checkpoint', {}).get('peak_bytes')
                if (task.peak != peak or task.protected != protected
                    or task.priority != plan['priority']['task_priorities'].get(name, 0)):
                    errors.append(f'tick {tick}: profile differs for {name}')
                phase_floor = None
                if getattr(policy, 'adaptive', None) is not None and protected and checkpoint is not None:
                    phase_floor = plan.get('priority_checkpoint', {}).get('reference_age_s')
                if isinstance(policy, PriorityPolicy):
                    phase_floor = (plan.get('priority_checkpoint', {}).get('reference_age_s')
                                   if protected and checkpoint is not None else None)
                    if phase_floor is not None and (task.phase_floor_s is None or task.phase_floor_s < phase_floor):
                        errors.append(f'tick {tick}: forecast predates checkpoint for {name}')
                elif task.phase_floor_s != phase_floor or (
                        phase_floor is not None and (task.age_s is None or task.age_s < phase_floor)):
                    errors.append(f'tick {tick}: phase boundary differs for {name}')
            if isinstance(policy, PriorityPolicy):
                decision = policy.decide(now, row['decision']['available_bytes'], tasks, row['upcoming_s'])
            else:
                decision = policy.decide(now, row['decision']['available_bytes'], tasks)
            if decision != row['decision'] or decision['abort']:
                errors.append(f'tick {tick}: budget decision differs or emergency floor breached')
            applied = row.get('applied_memory_high', {})
            limits = decision.get('limits', {})
            if applied.keys() != limits.keys():
                errors.append(f'tick {tick}: memory.high writes differ')
            for name, limit in limits.items():
                value = applied.get(name)
                if limit is None:
                    valid = value == 'max'
                else:
                    # cgroup values are rounded to kernel page boundaries.
                    valid = value is not None and value.isdigit() and abs(int(value) - limit) < PAGESIZE
                if not valid:
                    errors.append(f'tick {tick}: invalid memory.high readback for {name}')
            limit_writes += len(applied)
            actions = [(name, 'freeze') for name in decision['freeze']]
            if decision['resume'] is not None:
                actions.append((decision['resume'], 'resume'))
            for name, action in actions:
                key = (tick, name, action)
                event = transitions.get(key)
                # A process may exit after the sample and before a freeze.
                if event is None and action == 'freeze':
                    continue
                if (event is None or event.get('admission') != decision
                    or event['requested_monotonic_ns'] / 1e9 < now):
                    errors.append(f'tick {tick}: missing or mismatched {action} for {name}')
                elif action == 'freeze':
                    max_freeze_ms = max(max_freeze_ms, (event['confirmed_monotonic_ns']
                                                        - event['requested_monotonic_ns']) / 1e6)
                requests.add(key)
    if transitions.keys() - requests or not count:
        errors.append('unexpected freezer transitions or empty decision log')
    return dict(ticks=count, memory_high_writes=limit_writes, max_pressure_freeze_ms=max_freeze_ms,
                confirmed_checkpoints_ns=sorted(checkpoints), errors=errors)
