"""Memory admission and pressure response for named cgroup workloads."""
from collections import deque
from dataclasses import dataclass
import json
from mmap import PAGESIZE
import os


@dataclass(frozen=True)
class TaskMemory:
    priority: int
    protected: bool
    running: bool
    current: int
    anon: int
    peak: int | None

    @property
    def growth(self):
        if self.peak is None:
            return None
        # MemAvailable can already count file cache as reclaimable.
        return max(0, self.peak - self.anon)


class PriorityPolicy:
    def __init__(self, reserve, emergency_floor, config):
        self.reserve = reserve
        self.emergency_floor = emergency_floor
        self.config = config
        self.history = deque()
        self.stable_since = {}
        self.throttled = False
        self.limits = {}

    def decide(self, now, available, tasks):
        cfg = self.config
        if self.history and now - self.history[-1][0] > cfg['max_sample_gap_s']:
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
        freeze = sorted(background, key=lambda name: (
            background[name].priority, -(background[name].growth or 0), name))
        if not abort:
            freeze = freeze[:1] if available < urgent else []

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
            if reliable and task.peak is not None and task.current <= task.peak:
                needed = urgent + 2 * margin + sum(growth) + task.growth
            elif not active and not any(other.anon > margin for key, other in tasks.items()
                                        if key != name and not other.running):
                # Unknown work can run alone. Keep it out of joint admissions.
                needed = urgent + 2 * margin
            else:
                needed = None
            required[name] = needed
            if abort or freeze or self.throttled or needed is None or available < needed:
                self.stable_since.pop(name, None)
                continue
            since = self.stable_since.setdefault(name, now)
            if now - since >= cfg['resume_stable_s']:
                ready.append(name)
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
        return dict(available_bytes=available, urgent_bytes=urgent, required_bytes=required,
                    throttle=self.throttled, freeze=freeze, resume=resume, limits=limits, abort=abort)


def write_memory_high(group, limit):
    # O_NONBLOCK lets the target do reclaim on its allocation path instead of
    # making the scheduler wait in synchronous reclaim after tightening a cap.
    data = ('max' if limit is None else str(limit)).encode('ascii')
    fd = os.open(group / 'memory.high', os.O_WRONLY | os.O_NONBLOCK)
    try:
        if os.write(fd, data) != len(data):
            raise OSError('short write to memory.high')
    finally:
        os.close(fd)


def audit_decisions(root, plan, freezes, checkpoint_ns):
    budget = plan['budget']
    floor = budget.get('emergency_floor_bytes', budget['foreground_only_floor_bytes'])
    policy = PriorityPolicy(budget['reserve_bytes'], floor, plan['priority'])
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
            decision = policy.decide(now, row['decision']['available_bytes'], tasks)
            if decision != row['decision'] or decision['abort']:
                errors.append(f'tick {tick}: budget decision differs or emergency floor breached')
            applied = row['applied_memory_high']
            if applied.keys() != decision['limits'].keys():
                errors.append(f'tick {tick}: memory.high writes differ')
            for name, limit in decision['limits'].items():
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
