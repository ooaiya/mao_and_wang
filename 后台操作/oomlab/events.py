"""Monotonic events shared by workload, scheduler and future foreground adapters."""
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path


class Events:
    def __init__(self, path, run_id=None, operation_id=None, epoch_ns=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or self.path.parent.name
        self.operation_id = operation_id
        self.epoch_ns = epoch_ns or time.monotonic_ns()

    def emit(self, event_type, **fields):
        stamp = time.monotonic_ns()
        row = dict(run_id=self.run_id, operation_id=self.operation_id,
                   event_type=event_type, monotonic_ns=stamp,
                   relative_ms=(stamp-self.epoch_ns)/1e6, **fields)
        raw = (json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n').encode()
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            if os.write(fd, raw) != len(raw):
                raise OSError('事件写入不完整')
        finally:
            os.close(fd)
        return row

    @contextmanager
    def phase(self, name):
        self.emit('phase_start', phase=name)
        try:
            yield
        except BaseException as e:
            self.emit('phase_end', phase=name, status='FAILED', error=str(e))
            raise
        else:
            self.emit('phase_end', phase=name, status='COMPLETED')
