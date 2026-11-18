"""Online admission for background cgroups, using observations from this run."""

from collections import deque
from dataclasses import dataclass, fields
import math


MIB = 2**20
FOREGROUND = 'foreground_krita'
OFFSETS = {FOREGROUND: 0, 'xz': 54.63, 'array': 706.27, 'table': 708.31}
PRIORITIES = {'xz': 30, 'array': 20, 'table': 10}


@dataclass(frozen=True)
class Settings:
    sample_interval_s: float = .2
    max_sample_gap_s: float = .6
    stable_s: float = .5
    retry_cooldown_s: float = 1.
    lease_s: float = 1.
    startup_timeout_s: float = 2.
    freeze_timeout_s: float = .5
    watchdog_interval_s: float = .05
    reaction_s: float = 2.5
    reserve_fraction: float = .116
    emergency_bytes: int = 384 * MIB
    step_bytes: int = 128 * MIB
    throttle_margin_bytes: int = 128 * MIB
    recovery_bytes: int = 256 * MIB
    anon_margin_bytes: int = 32 * MIB
    max_retry_extra_bytes: int = 512 * MIB

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            expected = (int,) if field.name.endswith('_bytes') else (int, float)
            if type(value) not in expected or not math.isfinite(value) or value <= 0:
                raise ValueError(f'invalid real-time setting: {field.name}')
        if not self.watchdog_interval_s < self.sample_interval_s < self.max_sample_gap_s < self.lease_s:
            raise ValueError('expected watchdog interval < sample interval < sample gap < lease')
        if self.reaction_s < self.max_sample_gap_s + self.watchdog_interval_s + self.freeze_timeout_s:
            raise ValueError('reaction window must cover sampling, watchdog and freeze confirmation')
        if not 0 < self.reserve_fraction < 1 or self.recovery_bytes <= self.throttle_margin_bytes:
            raise ValueError('invalid reserve or pressure hysteresis')


@dataclass(frozen=True)
class Reading:
    current: int
    anon: int
    high_events: int
    cpu_usec: int
    state: str
    started: bool
    high: int | None = None


class RealtimePolicy:
    def __init__(self, settings, memtotal, priorities=None):
        self.settings = settings
        self.priorities = PRIORITIES if priorities is None else priorities
        self.reserve = math.ceil(memtotal * settings.reserve_fraction)
        if not settings.emergency_bytes < self.reserve < memtotal:
            raise ValueError('emergency floor must be below the reserve for this host')
        self.history = deque()
        self.stable_since = None
        self.resume_since = {}
        self.previous = {}
        self.pressure = False
        self.retry_extra = {}

    def reset_stability(self):
        self.stable_since = None
        self.resume_since.clear()

    def thresholds(self, now, available):
        cfg = self.settings
        if self.history and now - self.history[-1][0] > cfg.max_sample_gap_s:
            self.reset_stability()
            self.history.clear()
            self.previous = {}
        self.history.append((now, available))
        while now - self.history[0][0] > 10:
            self.history.popleft()
        rate = max((max(0, past - available) / (now - stamp)
                    for stamp, past in self.history if now - stamp >= 1), default=0)
        short_drop = max((left - right for (_, left), (stamp, right)
                          in zip(self.history, list(self.history)[1:]) if now - stamp <= 1), default=0)
        urgent = self.reserve + max(short_drop, math.ceil(rate * 1.5 * cfg.reaction_s))
        return urgent, rate, short_drop

    def decide(self, now, available, readings, frozen_since):
        cfg = self.settings
        urgent, rate, short_drop = self.thresholds(now, available)
        recovery = urgent + cfg.recovery_bytes
        if available < urgent + cfg.throttle_margin_bytes:
            self.pressure = True
        elif available >= recovery:
            self.pressure = False

        if available < recovery:
            self.reset_stability()
        elif self.stable_since is None:
            self.stable_since = now
        stable = self.stable_since is not None and now - self.stable_since >= cfg.stable_s

        running = {name: reading for name, reading in readings.items()
                   if name in self.priorities and reading.state == 'RUNNING'}
        # MemAvailable already credits some cache. Allow for its replacement by
        # anonymous pages before assuming there is spare room below a soft limit.
        running_growth = {name: max(0, reading.high - reading.anon) for name, reading in running.items()}
        started = [name for name, reading in running.items() if reading.started]
        prior = self.previous
        self.previous = readings
        decision = dict(available_bytes=available, urgent_bytes=urgent, recovery_bytes=recovery,
                        rate_bytes_s=rate, short_drop_bytes=short_drop, pressure=self.pressure,
                        stable=stable, freeze=None, resume=None, resume_budget_since_s=None, renew=[], limits={},
                        running_growth_bytes=running_growth, resume_required_bytes={}, resume_since_s={},
                        retry_extra_bytes=dict(self.retry_extra), abort=False)
        if available < cfg.emergency_bytes:
            decision['abort'] = True
            return decision
        if available < urgent:
            decision['freeze'] = min(started, key=self.priorities.__getitem__, default=None)
            return decision

        decision['renew'] = started
        if self.pressure:
            for name, reading in running.items():
                target = max(reading.anon + cfg.anon_margin_bytes,
                             reading.current - cfg.throttle_margin_bytes)
                if target <= reading.high - cfg.anon_margin_bytes:
                    decision['limits'][name] = target
        else:
            shared_growth = sum(running_growth.values())
            self.admit_resume(now, decision, readings, frozen_since, shared_growth, len(started) == len(running))
            if decision['resume'] is None and stable:
                self.expand(decision, running, prior, shared_growth)
        return decision

    def admit_resume(self, now, decision, readings, frozen_since, shared_growth, all_started):
        cfg = self.settings
        if not all_started:
            self.resume_since.clear()
            return
        required = decision['resume_required_bytes']
        base = decision['recovery_bytes'] + shared_growth
        for name in frozen_since:
            row = readings[name]
            requested_limit = row.current + cfg.step_bytes
            required[name] = base + requested_limit - row.anon + self.retry_extra.get(name, 0)
        self.resume_since = {name: self.resume_since.get(name, now) for name, need in required.items()
                             if decision['available_bytes'] >= need}
        decision['resume_since_s'] = dict(self.resume_since)
        ready = [name for name, since in self.resume_since.items()
                 if now - since >= cfg.stable_s and now - frozen_since[name] >= cfg.retry_cooldown_s]
        if ready:
            name = max(ready, key=self.priorities.__getitem__)
            decision.update(resume=name, resume_budget_since_s=self.resume_since[name])
            decision['limits'][name] = readings[name].current + cfg.step_bytes

    def expand(self, decision, running, prior, shared_growth):
        cfg = self.settings
        if decision['available_bytes'] < decision['recovery_bytes'] + shared_growth + cfg.step_bytes:
            return
        for name in sorted(running, key=self.priorities.__getitem__, reverse=True):
            row = running[name]
            before = prior.get(name, row)
            if row.started and (row.high_events > before.high_events
                                or row.current >= row.high - cfg.anon_margin_bytes):
                decision['limits'][name] = row.high + cfg.step_bytes
                return

    def record_pressure_freeze(self, name, readings, previous):
        """Apply retry headroom when recent anonymous growth implicates the victim."""
        cfg = self.settings
        victim = readings[name]
        growth = victim.anon - previous.get(name, victim).anon
        foreground = readings.get(FOREGROUND)
        foreground_growth = 0 if foreground is None else (
            foreground.anon - previous.get(FOREGROUND, foreground).anon)
        other_growth = max((row.anon - previous.get(other, row).anon for other, row in readings.items()
                            if other in self.priorities and other != name and row.state == 'RUNNING'), default=0)
        if growth >= max(cfg.anon_margin_bytes, foreground_growth, other_growth):
            self.retry_extra[name] = min(cfg.max_retry_extra_bytes,
                                         self.retry_extra.get(name, 0) + cfg.step_bytes)
        self.reset_stability()
