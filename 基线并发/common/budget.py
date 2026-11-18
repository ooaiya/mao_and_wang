"""One byte-based capacity reference for both native policies."""
import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / 'configs/memory_budget.json'


def live_budget(memtotal_bytes, config=CONFIG):
    c = json.loads(Path(config).read_text())
    if type(memtotal_bytes) is not int or memtotal_bytes <= 0:
        raise ValueError('positive actual MemTotal bytes required')
    values = {'memtotal_bytes': memtotal_bytes, 'unit': 'bytes', 'source': '/proc/meminfo',
              'config': str(Path(config).resolve()), 'task_priorities': c['task_priorities']}
    for key, fraction in c.items():
        if not key.endswith('_fraction'):
            continue
        if not isinstance(fraction, (int, float)) or not 0 <= fraction < 1:
            raise ValueError('invalid fraction: ' + key)
        values[key.replace('_fraction', '_bytes')] = int(memtotal_bytes * fraction)
    reserve = sum(values[k] for k in ('risk_reserve_bytes', 'error_margin_bytes', 'foreground_guard_bytes'))
    values['reserved_bytes'] = reserve
    values['safe_bytes'] = memtotal_bytes - reserve
    if not 0 < values['reactive_critical_bytes'] < values['reactive_pressure_bytes'] < values['reactive_warning_bytes'] < values['reactive_recover_bytes'] < memtotal_bytes:
        raise ValueError('invalid pressure hysteresis')
    return values
