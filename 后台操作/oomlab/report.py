import csv
import math
import statistics
from pathlib import Path
from .common import GIB, load_json, save_json
from .metrics import read_curve
REGISTRY = ('xz', 'table', 'array_processing')


def stats(values):
    if not values:
        return {'n': 0, 'mean': None, 'std': None, 'cv': None}
    mean = statistics.mean(values)
    # Sample standard deviation (n-1), undefined for fewer than two observations.
    cv = statistics.stdev(values) / mean if len(values) >= 2 and mean != 0 else None
    return {'n': len(values), 'mean': mean, 'std': statistics.stdev(values) if len(values)>=2 else None, 'cv': cv}


def align(curves, durations, step):
    """Linear interpolation only within observed domain AND workload lifetime.

    No zero padding, no extension beyond completion. n varies by metric/time.
    """
    if step <= 0 or not math.isfinite(step):
        raise ValueError('时间网格必须为有限正数')
    keys = ['memory_current', 'memory_peak', 'stat_anon', 'stat_file', 'stat_kernel', 'swap_current']
    if not durations:
        return []
    result = []
    indices = [0] * len(curves)
    for tick in range(math.floor(max(durations) / step) + 1):
        t = tick * step
        row = {'relative_s': round(t, 9)}
        values = {k: [] for k in keys}
        for j, (curve, duration) in enumerate(zip(curves, durations, strict=True)):
            if not curve or t > duration or t < curve[0]['relative_s'] or t > curve[-1]['relative_s']:
                continue
            while indices[j] + 1 < len(curve) and curve[indices[j] + 1]['relative_s'] <= t:
                indices[j] += 1
            a = curve[indices[j]]
            b = curve[min(indices[j] + 1, len(curve) - 1)]
            span = b['relative_s'] - a['relative_s']
            weight = (t - a['relative_s']) / span if span else 0
            for k in keys:
                if a.get(k) is not None and b.get(k) is not None:
                    values[k].append(a[k] + weight * (b[k] - a[k]))
        for k in keys:
            s = stats(values[k])
            row[k + '_mean'] = s['mean']
            row[k + '_n'] = s['n']
            row[k + '_cv'] = s['cv']
            row[k + '_std'] = s['std']
        result.append(row)
    return result


def eligible(meta):
    return (meta.get('success') is True and meta.get('verified') is True
            and meta.get('cleanup_ok') is True and meta.get('duration_s', 0) > 0
            and meta.get('peak_bytes') is not None
            and meta.get('events_delta', {}).get('max') == 0
            and meta.get('events_delta', {}).get('oom') == 0
            and meta.get('events_delta', {}).get('oom_kill') == 0)


def generate(session, step=.05):
    session = Path(session)
    config = load_json(session / 'session.json')
    runs = [load_json(p) for p in sorted(session.glob('*/metadata.json'))]
    valid, curves = [], []
    for meta in runs:
        meta['report_valid'] = False
        if not eligible(meta):
            continue
        try:
            if Path(meta['run_id']).name != meta['run_id']:
                raise ValueError('非法 run_id')
            curve = read_curve(session / meta['run_id'] / 'raw.csv')
            if not curve or any(not math.isfinite(row['relative_s']) or row['relative_s'] < 0
                                or row.get('memory_current') is None or row['memory_current'] < 0
                                for row in curve):
                raise ValueError('原始曲线为空或包含无效采样')
            if any(b['relative_s'] <= a['relative_s'] for a, b in zip(curve, curve[1:])):
                raise ValueError('原始曲线时间必须严格递增')
            valid.append(meta)
            curves.append(curve)
            meta['report_valid'] = True
        except (OSError, ValueError, KeyError, TypeError) as e:
            meta['report_invalid_reason'] = str(e)
    peaks = stats([m['peak_bytes'] for m in valid])
    anon = stats([m['anon_sampled_peak_bytes'] for m in valid if m.get('anon_sampled_peak_bytes') is not None])
    duration = stats([m['duration_s'] for m in valid])
    retired = config['operation'] not in (*REGISTRY, 'smoke')
    diagnostic_rounds = len(valid) if retired else 0
    if retired:
        # Keep source results, but never count a removed workload as a formal sample.
        for meta in valid:
            meta.update(report_valid=False, report_diagnostic_valid=True,
                        report_invalid_reason='已退役负载，仅保留历史失败诊断数据')
        valid, curves = [], []
        peaks, anon, duration = stats([]), stats([]), stats([])
    required = max(10 if config['operation']=='array_processing' else 3, config['requested_rounds'])
    minimum_bytes = 2_000_000_000 if config['operation']=='array_processing' else GIB
    maximum_bytes = 3_000_000_000
    target = bool(valid) and all(minimum_bytes <= m['peak_bytes'] <= maximum_bytes for m in valid)
    below = bool(valid) and all(m['peak_bytes'] < 16 * GIB for m in valid)
    stable = len(valid) >= required and peaks['cv'] is not None and peaks['cv'] <= .10
    completed = len(runs) == config['requested_rounds'] and len(valid) == len(runs)
    qualified = completed and target and below and stable and config['operation'] != 'smoke'
    average = align(curves, [m['duration_s'] for m in valid], step)
    # Always create a mean CSV, including when no valid data exists.
    keys = list(average[0]) if average else ['relative_s', 'memory_current_mean', 'memory_current_n']
    with open(session / 'mean.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, keys)
        writer.writeheader()
        writer.writerows(average)
    report = {'operation': config['operation'], 'profile': config['profile'],
              'parameters': config['parameters'], 'valid_rounds': len(valid),
              'requested_rounds': config['requested_rounds'], 'required_valid_rounds': required,
              'all_completed': completed,
              'target_1_3_gib': bool(valid) and all(GIB <= m['peak_bytes'] <= 3*GIB for m in valid),
              'target_min_gib':minimum_bytes/GIB, 'target_min_bytes':minimum_bytes,
              'target_max_bytes':maximum_bytes, 'target_peak_range':target,
              'diagnostic_rounds':diagnostic_rounds,
              'below_16_gib': below, 'stable_peak_cv': stable, 'qualified': qualified,
              'peak_bytes': peaks, 'anon_sampled_peak_bytes': anon, 'duration_s': duration,
              'status': ('HISTORICAL_DIAGNOSTIC' if retired else
                         'PREFLIGHT_FAILED' if config.get('status') == 'PREFLIGHT_FAILED' else
                         'QUALIFIED' if qualified else 'UNQUALIFIED' if runs else 'NOT_RUN'),
              'runs': runs}
    save_json(session / 'summary.json', report)
    def fmt(value):
        return 'N/A' if value is None else f'{value:.6g}'
    lines = ['# 单操作内存曲线报告', '', f"操作：{config['operation']} / {config['profile']}",
             f"状态：**{report['status']}**；有效轮次 {len(valid)}/{config['requested_rounds']}，要求 {required}。", '',
             '|检查|结果|', '|---|---|',
             f'|全部正确完成|{completed}|', f'|每轮总峰值在 {minimum_bytes}–{maximum_bytes} Bytes|{target}|',
             f'|每轮总峰严格低于 16 GiB|{below}|', f'|稳定性（总峰值 CV ≤ 10%）|{stable}|', '',
             '|统计项|有效轮次均值|CV|', '|---|---:|---:|',
             f"|cgroup 总峰值 GiB|{fmt(peaks['mean']/GIB if peaks['mean'] is not None else None)}|{fmt(peaks['cv'])}|",
             f"|采样匿名峰值 GiB|{fmt(anon['mean']/GIB if anon['mean'] is not None else None)}|{fmt(anon['cv'])}|",
             f"|运行时长 s|{fmt(duration['mean'])}|{fmt(duration['cv'])}|", '',
             '|run ID|有效|峰值 GiB|匿名采样峰值 GiB|时长 s|退出码|max / OOM / OOM kill 差值|失败原因|',
             '|---|---|---:|---:|---:|---|---|---|']
    for m in runs:
        ev = m.get('events_delta', {})
        lines.append(f"|{m['run_id']}|{m['report_valid']}|{fmt(m['peak_bytes']/GIB if m.get('peak_bytes') is not None else None)}|"
                     f"{fmt(m['anon_sampled_peak_bytes']/GIB if m.get('anon_sampled_peak_bytes') is not None else None)}|{fmt(m.get('duration_s'))}|"
                     f"{m.get('returncode', 'unknown')}|{ev.get('max', 'unknown')} / {ev.get('oom', 'unknown')} / {ev.get('oom_kill', 'unknown')}|"
                     f"{str(m.get('reason') or m.get('report_invalid_reason') or '').replace('|', '/').replace(chr(10), ' ')}|")
    lines += ['', 'CV = 样本标准差（ddof=1）/ 算术均值；少于两轮或均值为零时为 N/A。',
              f'稳定性要求至少 {required} 轮有效样本，总 memory.peak CV ≤ 10%；它不是曲线形状一致性的证明。',
              'mean.csv 采用相对开始时间的固定网格、线性插值；只在实测采样范围及操作结束前参与均值。',
              '结束后、首个样本前不补零、不延长最后值；各列 _n 表示贡献轮数，尾部可能只剩较慢轮次。',
              '每个网格另有 CV，便于检查形状波动；memory.peak 均值曲线不等于各轮峰值均值。',
              '总内存含文件缓存；memory.current 是瞬时采样，memory.peak 是运行期间读取的 cgroup 高水位。',
              '匿名峰值为 50 ms（或指定间隔）采样下界，不是内核匿名高水位；不使用进程 RSS 替代。',
              'OOM 仅统计该 service 的 memory.events 末值减开始门控前基线，不叠加父 slice 计数。',
              '未知/缺失 OOM 计数不会当作零；SIGKILL 本身不能证明 OOM。',
              '服务包含轻量 supervisor；其开销和输入文件缓存都属于该 cgroup 的真实计量。',
              '采样不是实时调度；CSV 的单调时钟显示实际抖动。开始包含 subprocess 启动开销，结束为 wait 返回。',
              '服务器可见内存、单操作峰值、四操作并发峰值、16 GiB 调度预算和 >20.8 GiB 阈值互不等同。',
              '本报告没有四操作并发测量，也不能用独立峰值之和代替并发峰值。', '']
    if not qualified:
        advice = {'xz': '逐档调整真实 LZMA2 字典和输入规模，保持 bt4 单线程；用实测 memory.peak 校准，输入太小会使字典缩减。',
                  'table': '增加/减少 rows、extras 或分组基数；准备使用流式 CSV，处理整表读取、转换和分组，注意 pandas 中间副本。',
                  'array_processing': '以3×elements×8字节为初始数据容量，单轮实测后小幅校准elements；保持三个数组、分块回放和真实计算。上限3,000,000,000 Bytes，不是3GiB。',
                  'smoke': 'sleep 仅验证流程，永不作为后台合格操作。'}
        lines += ['未合格调整建议：' + advice.get(config['operation'], '历史负载，只保留读取能力，不再运行。'),
                  '若发生 OOM/超时或正确性失败，先检查日志和安全上限；不要把失败轮次计入均值。',
                  '准备完成后不要并发运行其他采集。必要时延长采样任务或调小间隔以检查短峰。', '']
    (session / 'report.md').write_text('\n'.join(lines))
    return report
