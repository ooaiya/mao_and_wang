"""Three resident arrays, in-place NumPy processing, bounded seed replay verification."""
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from .common import digest, load_json, save_json
from .events import Events

OPERATION = 'array_processing'
ALGORITHM = 'resident-f64-pcg64-v1'
PEAK_LIMIT_BYTES = 3_000_000_000
PRESETS = {
    'small': dict(elements=1_000_000, dtype='float64', arrays=3, chunk_elements=100_000, seed=20261026),
    'medium': dict(elements=20_000_000, dtype='float64', arrays=3, chunk_elements=500_000, seed=20261026),
    'large': dict(elements=90_000_000, dtype='float64', arrays=3, chunk_elements=1_000_000, seed=20261026),
}
CHECKS = ('count', 'dtype', 'sorted', 'seeded_multiset', 'elementwise', 'aggregates', 'finite')
THREAD_VARIABLES = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                    'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'BLIS_NUM_THREADS')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_parameters(p):
    if set(p) != {'elements', 'dtype', 'arrays', 'chunk_elements', 'seed'}:
        raise ValueError('数组参数必须包含 elements/dtype/arrays/chunk_elements/seed')
    if any(type(p[k]) is not int or p[k] <= 0 for k in ('elements', 'arrays', 'chunk_elements')):
        raise ValueError('数组规模、数量和分块必须为正整数')
    if p['dtype'] != 'float64' or p['arrays'] != 3:
        raise ValueError('正式数组操作固定为三个 float64 数组')
    if type(p['seed']) is not int or not 0 <= p['seed'] < 2**128:
        raise ValueError('随机种子必须为非负128位整数')
    if p['elements'] * 24 > PEAK_LIMIT_BYTES:
        raise ValueError('三个工作数组的数据容量已超过3,000,000,000字节，必须减小规模')
    return p


def descriptor(p):
    validate_parameters(p)
    return dict(schema='oom-array-input-v1', operation=OPERATION, algorithm=ALGORITHM,
                rng='PCG64/SeedSequence([seed,array_index])', parameters=p,
                shape=[p['elements']], dtype=p['dtype'], seed=p['seed'], arrays=p['arrays'])


def prepare(p, directory):
    # No NumPy import or data allocation: large arrays belong exclusively to the worker.
    payload = descriptor(p)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    save_json(directory/'parameters.json', payload)
    manifest = dict(operation=OPERATION, parameters=p, seed=p['seed'], complete=True,
                    file='parameters.json', sha256=digest(directory/'parameters.json'),
                    size_bytes=(directory/'parameters.json').stat().st_size,
                    configuration_sha256=sha(payload), dataset_id='array-'+sha(payload)[:24],
                    generated_utc=datetime.now(timezone.utc).isoformat(),
                    expected={'elements':p['elements'], 'arrays':3, 'dtype':'float64'},
                    theoretical_array_bytes=p['elements']*24)
    save_json(directory/'manifest.json', manifest)
    return manifest


def validate(directory, manifest):
    expected = descriptor(manifest['parameters'])
    path = Path(directory)/'parameters.json'
    if (manifest.get('operation') != OPERATION or not manifest.get('complete')
        or manifest.get('file') != 'parameters.json' or path.is_symlink()
        or load_json(path) != expected or manifest.get('configuration_sha256') != sha(expected)
        or manifest.get('sha256') != digest(path) or manifest.get('size_bytes') != path.stat().st_size
        or manifest.get('expected') != {'elements':expected['shape'][0], 'arrays':3, 'dtype':'float64'}
        or manifest.get('theoretical_array_bytes') != expected['shape'][0]*24
        or manifest.get('seed') != expected['seed']):
        raise ValueError('数组参数 manifest 不完整或摘要/配置不匹配')
    return manifest


def numpy():
    # This executes in the workload process before NumPy import, never in prepare.
    for variable in THREAD_VARIABLES:
        os.environ[variable] = '1'
    import numpy as np
    return np


def chunks(p):
    for start in range(0, p['elements'], p['chunk_elements']):
        yield start, min(p['elements'], start+p['chunk_elements'])


def rng(np, seed, index):
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, index])))


def fingerprint(np, values):
    # Two commutative checksums for a multiset of exact IEEE float64 bit patterns.
    bits = values.view(np.uint64)  # view, no copy
    return int(bits.sum(dtype=np.uint64)), int(np.bitwise_xor.reduce(bits, initial=np.uint64(0)))


def combine(a, b):
    return ((a[0]+b[0]) & ((1 << 64)-1), a[1]^b[1])


def aggregate(np, array, p):
    total = squares = compensation = square_compensation = 0.0
    low, high = math.inf, -math.inf
    data_sha = hashlib.sha256()
    for start, end in chunks(p):
        block = array[start:end]
        if not np.isfinite(block).all():
            raise ValueError('数组包含非有限数值')
        value = float(block.sum(dtype=np.float64)) - compensation
        updated = total+value
        compensation = (updated-total)-value
        total = updated
        value = float(np.einsum('i,i->', block, block, optimize=False)) - square_compensation
        updated = squares+value
        square_compensation = (updated-squares)-value
        squares = updated
        low, high = min(low, float(block.min())), max(high, float(block.max()))
        data_sha.update(memoryview(block).cast('B'))
    return dict(elements=len(array), dtype=str(array.dtype), sum=total, sum_squares=squares,
                mean=total/len(array), min=low, max=high, data_sha256=data_sha.hexdigest())


def verify_working(np, arrays, p, stats, events):
    n = p['elements']
    if len(arrays) != 3 or any(a.shape != (n,) or a.dtype != np.float64 for a in arrays):
        raise ValueError('数组元素数量、形状或类型不匹配')
    width = min(n, p['chunk_elements'])
    replay_b, replay_c = np.empty(width, dtype=np.float64), np.empty(width, dtype=np.float64)
    generators = [rng(np, p['seed'], i) for i in range(3)]
    expected_a = actual_a = (0, 0)
    previous = None
    expected_sums, expected_squares = [0.0]*3, [0.0]*3
    for start, end in chunks(p):
        length = end-start
        a, b, c = (array[start:end] for array in arrays)
        if (previous is not None and previous > float(a[0])) or np.any(a[1:] < a[:-1]):
            raise ValueError('数组排序校验失败')
        previous = float(a[-1])
        actual_a = combine(actual_a, fingerprint(np, a))
        generators[0].random(out=replay_b[:length])
        expected_a = combine(expected_a, fingerprint(np, replay_b[:length]))
        expected_sums[0] += float(replay_b[:length].sum())
        expected_squares[0] += float(np.einsum('i,i->', replay_b[:length], replay_b[:length], optimize=False))
        generators[1].random(out=replay_b[:length])
        np.add(a, replay_b[:length], out=replay_b[:length])
        generators[2].random(out=replay_c[:length])
        np.multiply(replay_b[:length], replay_c[:length], out=replay_c[:length])
        np.add(replay_c[:length], .125, out=replay_c[:length])
        np.sqrt(replay_c[:length], out=replay_c[:length])
        if not np.array_equal(b, replay_b[:length]) or not np.array_equal(c, replay_c[:length]):
            raise ValueError('数组逐元素计算校验失败')
        for i, block in ((1, replay_b[:length]), (2, replay_c[:length])):
            expected_sums[i] += float(block.sum())
            expected_squares[i] += float(np.einsum('i,i->', block, block, optimize=False))
        events.emit('phase_progress', phase='VERIFY', completed=end, total=n)
    if actual_a != expected_a:
        raise ValueError('排序后数组与种子生成的原始多重集合不匹配')
    if not all(math.isclose(stats[i][key], values[i], rel_tol=1e-11, abs_tol=1e-9)
               for key, values in (('sum', expected_sums), ('sum_squares', expected_squares)) for i in range(3)):
        raise ValueError('数组聚合校验失败')
    return {key: True for key in CHECKS}


def compute(np, arrays, p, events):
    n = p['elements']
    with events.phase('ARRAY_GENERATE'):
        for index in range(3):
            # np.empty has not touched pages; random(out=) writes every element.
            arrays.append(np.empty(n, dtype=np.float64))
            generator = rng(np, p['seed'], index)
            for start, end in chunks(p):
                generator.random(out=arrays[index][start:end])
                events.emit('phase_progress', phase='ARRAY_GENERATE', array=index, completed=end, total=n)
    with events.phase('ARRAY_SORT'):
        arrays[0].sort(kind='quicksort')  # ndarray.sort is in-place; no index permutation array.
        events.emit('phase_progress', phase='ARRAY_SORT', completed=n, total=n)
    with events.phase('ARRAY_ADD'):
        for start, end in chunks(p):
            np.add(arrays[0][start:end], arrays[1][start:end], out=arrays[1][start:end])
            events.emit('phase_progress', phase='ARRAY_ADD', completed=end, total=n)
    with events.phase('ARRAY_TRANSFORM'):
        for start, end in chunks(p):
            block = arrays[2][start:end]
            np.multiply(arrays[1][start:end], block, out=block)
            np.add(block, .125, out=block)
            np.sqrt(block, out=block)
            events.emit('phase_progress', phase='ARRAY_TRANSFORM', completed=end, total=n)
    with events.phase('ARRAY_AGGREGATE'):
        stats = [aggregate(np, array, p) for array in arrays]
    with events.phase('VERIFY'):
        checks = verify_working(np, arrays, p, stats, events)
    return dict(schema='oom-array-result-v1', operation=OPERATION, algorithm=ALGORITHM,
                configuration_sha256=sha(descriptor(p)), parameters=p, checks=checks,
                arrays=stats, numpy_version=np.__version__, byte_order='native',
                theoretical_array_bytes=n*24,
                explicit_replay_buffer_bytes=2*min(n,p['chunk_elements'])*8,
                verification='seed replay B/C; monotonic A and seeded multiset sum/xor; bounded aggregation')


def execute(directory, output, operation_id=None):
    directory, output = Path(directory), Path(output)
    manifest = validate(directory, load_json(directory/'manifest.json'))
    p = manifest['parameters']
    events = Events(output/'phase_trace.jsonl', operation_id=operation_id or OPERATION)
    arrays = []
    try:
        result = compute(numpy(), arrays, p, events)
    except BaseException as e:
        events.emit('task_error', error=f'{type(e).__name__}: {e}')
        raise
    finally:
        with events.phase('CLEANUP'):
            arrays.clear()
    with events.phase('OUTPUT_WRITE'):
        # Commit only a fully verified compact result; never persist giant arrays.
        save_json(output/'output.json', {'result':result, 'result_sha256':sha(result)})
    return result


def verify(directory, output):
    manifest = validate(directory, load_json(Path(directory)/'manifest.json'))
    envelope = load_json(Path(output)/'output.json')
    result = envelope['result']
    if envelope.get('result_sha256') != sha(result):
        raise ValueError('数组结果摘要校验失败')
    p = manifest['parameters']
    if (result.get('schema') != 'oom-array-result-v1' or result.get('algorithm') != ALGORITHM
        or result.get('operation') != OPERATION or result.get('parameters') != p
        or result.get('configuration_sha256') != manifest['configuration_sha256']
        or result.get('checks') != {key:True for key in CHECKS} or len(result.get('arrays',[])) != 3):
        raise ValueError('数组输出完整性或操作/参数绑定校验失败')
    for stats in result['arrays']:
        numbers = [stats[k] for k in ('sum', 'sum_squares', 'mean', 'min', 'max')]
        if (stats['elements'] != p['elements'] or stats['dtype'] != 'float64'
            or not re.fullmatch('[0-9a-f]{64}', stats['data_sha256'])
            or not all(math.isfinite(v) for v in numbers)
            or not 0 <= stats['min'] <= stats['mean'] <= stats['max'] <= 2
            or not math.isclose(stats['sum']/p['elements'], stats['mean'], rel_tol=1e-12)):
            raise ValueError('数组统计或数据摘要格式校验失败')
    return dict(ok=True, method=result['verification'], result_sha256=envelope['result_sha256'],
                output_sha256=digest(Path(output)/'output.json'), data_sha256s=[a['data_sha256'] for a in result['arrays']])
