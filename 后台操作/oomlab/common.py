import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

GIB = 1024 ** 3
ROOT = Path(__file__).resolve().parent.parent


def save_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def load_json(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def profile(path, operation, name):
    all_profiles = load_json(path)
    if all_profiles.get('schema_version') != 1:
        raise ValueError('配置 schema_version 必须为 1')
    p = all_profiles[operation][name]
    if operation == 'array_processing':
        from .array_processing import validate_parameters
        return validate_parameters(p)
    keys = {'xz': {'input_mib', 'dict_mib', 'threads'},
            'table': {'rows', 'users', 'categories', 'days', 'extras'}}[operation]
    if set(p) != keys or any(type(v) is not int or v <= 0 for v in p.values()):
        raise ValueError('配置字段必须完整且为正整数')
    if operation == 'xz' and (p['threads'] != 1 or not 1 <= p['dict_mib'] <= 1536):
        raise ValueError('阶段 A 固定 xz 单线程；dict_mib 应为 1..1536')
    if operation == 'table' and p['extras'] < 1:
        raise ValueError('表格至少一个附加列')
    return p


def positive(value):
    v = float(value)
    if not math.isfinite(v) or v <= 0:
        raise ValueError('参数必须为有限正数')
    return v


def meminfo():
    return {k: int(v.split()[0]) * 1024 for k, v in
            (line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())}


def resource_check(directory, memory_bytes, disk_bytes):
    m = meminfo()
    if m['MemAvailable'] < memory_bytes:
        raise RuntimeError(f"可用内存不足：需要 {memory_bytes} 字节，当前 {m['MemAvailable']}")
    free = shutil.disk_usage(directory).free
    if free < disk_bytes:
        raise RuntimeError(f'磁盘剩余空间不足：需要 {disk_bytes} 字节，当前 {free}')
    return {'meminfo_bytes': m, 'disk_free_bytes': free,
            'swap': Path('/proc/swaps').read_text()}


def command(args, check=True):
    return subprocess.run([str(x) for x in args], check=check, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def privileged(args, check=True):
    prefix = [] if os.geteuid() == 0 else ['sudo', '-n']
    return command(prefix + list(args), check=check)
