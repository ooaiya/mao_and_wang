"""Deterministic input preparation, real computations, independent verification."""
import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from .common import digest, load_json, save_json, command
from .events import Events
from . import array_processing


def estimated_disk(op, p):
    # Conservative preparation bound, including manifest and temporary files.
    return {'xz': lambda: p['input_mib'] * 1024**2,
            'table': lambda: p['rows'] * (100 + 24 * p['extras']),
            'array_processing': lambda: 64 * 1024}[op]()


def prepare(op, p, directory):
    if op == 'array_processing':
        return array_processing.prepare(p, directory)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {'operation': op, 'parameters': p, 'seed': 20261026, 'complete': False}
    save_json(directory / 'manifest.json', manifest)
    if op == 'xz':
        rng = random.Random(manifest['seed'])
        with open(directory / 'input.bin', 'wb') as f:
            # A deterministic mixture of compressible and random bytes; no giant allocation.
            for _ in range(p['input_mib']):
                f.write(rng.randbytes(512 * 1024))
                f.write((b'OOMlab deterministic compression input\n' * 15000)[:512*1024])
        filename = 'input.bin'
        expected = {'sha256': digest(directory / filename)}
    elif op == 'table':
        filename = 'table.csv'
        counts = [0] * p['categories']
        sums = [0.0] * p['categories']
        with open(directory / filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['user', 'category', 'day', 'amount'] +
                            [f'extra{i}' for i in range(p['extras'])])
            for i in range(p['rows']):
                user = (i * 7919) % p['users']
                category = (i * 7 + i // 31) % p['categories']
                amount = (i * 17) % 10000
                extra = [(i * (j + 3) + j) % 1000 for j in range(p['extras'])]
                writer.writerow([user, category, i % p['days'], amount] + extra)
                counts[category] += 1
                sums[category] += amount * (1 + extra[0] / 1000)
        expected = {'counts': counts, 'sums': sums, 'rows': p['rows']}
    else:
        raise ValueError(op)
    manifest.update(complete=True, file=filename, sha256=digest(directory / filename),
                    size_bytes=(directory / filename).stat().st_size, expected=expected)
    save_json(directory / 'manifest.json', manifest)
    return manifest


def validate_input(directory, op, p):
    m = load_json(Path(directory) / 'manifest.json')
    if not m.get('complete') or m['operation'] != op or m['parameters'] != p:
        raise ValueError('样本未完成或配置不匹配；请在新目录重新 prepare')
    file = Path(directory) / m['file']
    if file.parent.resolve() != Path(directory).resolve():
        raise ValueError('非法样本路径')
    if file.stat().st_size != m['size_bytes'] or digest(file) != m['sha256']:
        raise ValueError('样本摘要/大小校验失败')
    if op == 'array_processing':
        array_processing.validate(directory, m)
    return m


def execute(directory, output, operation_id=None):
    directory, output = Path(directory), Path(output)
    m = load_json(directory / 'manifest.json')
    p, op = m['parameters'], m['operation']
    source = directory / m['file']
    events = Events(output / 'phase_trace.jsonl', operation_id=operation_id or op)
    events.emit('task_start')
    if op == 'array_processing':
        array_processing.execute(directory, output, operation_id=operation_id)
        events.emit('task_finish')
        return
    events.emit('phase_start', phase='INPUT_READY')
    events.emit('phase_end', phase='INPUT_READY')
    if op == 'xz':
        events.emit('phase_start', phase='PREPARE')
        # stdout is the compressed file; stderr goes to the service log.
        import subprocess
        events.emit('phase_end', phase='PREPARE')
        events.emit('phase_start', phase='COMPRESS_START')
        events.emit('phase_end', phase='COMPRESS_START')
        events.emit('phase_start', phase='COMPRESS_RUNNING')
        with open(output / 'compressed.xz', 'xb') as f:
            subprocess.run(['xz', '--threads=1', '--check=crc64', '--stdout',
                            f"--lzma2=dict={p['dict_mib']}MiB,mf=bt4", str(source)],
                           stdout=f, check=True)
        events.emit('phase_end', phase='COMPRESS_RUNNING')
        events.emit('phase_start', phase='COMPRESS_FINISH')
        events.emit('phase_end', phase='COMPRESS_FINISH')
        result = {'compressed_bytes': (output / 'compressed.xz').stat().st_size}
    elif op == 'table':
        import pandas as pd
        types = {'user': 'int64', 'category': 'int64', 'day': 'int64', 'amount': 'float64'}
        types.update({f'extra{i}': 'float64' for i in range(p['extras'])})
        events.emit('phase_start', phase='CSV_LOAD')
        df = pd.read_csv(source, dtype=types)
        events.emit('phase_end', phase='CSV_LOAD')
        events.emit('phase_start', phase='DATA_TRANSFORM')
        df['score'] = df['amount'] * (1 + df['extra0'] / 1000)
        events.emit('phase_end', phase='DATA_TRANSFORM')
        events.emit('phase_start', phase='GROUPBY_USER_CATEGORY')
        groups = df.groupby(['user', 'category'], sort=True)['score'].agg(['sum', 'count'])
        events.emit('phase_end', phase='GROUPBY_USER_CATEGORY')
        events.emit('phase_start', phase='OUTPUT_WRITE')
        groups.to_csv(output / 'user_category.csv')
        events.emit('phase_end', phase='OUTPUT_WRITE')
        events.emit('phase_start', phase='GROUPBY_DAILY')
        daily = df.groupby(['day', 'category'])['score'].sum()
        events.emit('phase_end', phase='GROUPBY_DAILY')
        events.emit('phase_start', phase='OUTPUT_WRITE')
        daily.to_csv(output / 'daily.csv')
        events.emit('phase_end', phase='OUTPUT_WRITE')
        summary = df.groupby('category')['score'].agg(['sum', 'count'])
        result = {'rows': len(df), 'counts': [int(summary.loc[i, 'count']) if i in summary.index else 0
                                            for i in range(p['categories'])],
                  'sums': [float(summary.loc[i, 'sum']) if i in summary.index else 0
                           for i in range(p['categories'])]}
    else:
        raise ValueError(op)
    save_json(output / 'output.json', result)
    with events.phase('CLEANUP'):
        if op == 'table':
            del df, groups, daily, summary
    events.emit('task_finish')


def verify(directory, output):
    import math
    m = load_json(Path(directory) / 'manifest.json')
    if m['operation'] == 'array_processing':
        return array_processing.verify(directory, output)
    expected = m['expected']
    actual = load_json(Path(output) / 'output.json')
    if m['operation'] == 'xz':
        import lzma
        h = hashlib.sha256()
        with lzma.open(Path(output) / 'compressed.xz', 'rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                h.update(block)
        if h.hexdigest() != expected['sha256']:
            raise ValueError('xz 解压摘要不匹配')
    elif m['operation'] == 'table':
        if actual['rows'] != expected['rows'] or actual['counts'] != expected['counts']:
            raise ValueError('表格行数/计数校验失败')
        if not all(math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-6)
                   for a, b in zip(actual['sums'], expected['sums'], strict=True)):
            raise ValueError('表格分类转换统计不匹配')
        # Check persisted grouped outputs independently of output.json.
        for filename, count_column in [('user_category.csv', True), ('daily.csv', False)]:
            total, count = 0.0, 0
            with open(Path(output) / filename) as f:
                for row in csv.DictReader(f):
                    total += float(row['sum'] if count_column else row['score'])
                    if count_column:
                        count += int(row['count'])
            if not math.isclose(total, sum(expected['sums']), rel_tol=1e-9):
                raise ValueError('分组文件合计不匹配')
            if count_column and count != expected['rows']:
                raise ValueError('分组文件行数不匹配')
    else:
        raise ValueError('未知或已移除的负载')
    return {'ok': True, 'method': 'independent prepared expected values / decompressed SHA256'}


if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('directory')
    a.add_argument('output')
    a.add_argument('--operation-id')
    args = a.parse_args()
    execute(args.directory, args.output, args.operation_id)
