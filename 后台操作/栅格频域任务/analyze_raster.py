"""Plot the solo trace and align it with three unchanged no-Swap serial traces."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
from matplotlib import pyplot as plt

GIB = 2**30
MIB = 2**20
FIELDS = ('memory_current_bytes', 'stat_anon_bytes', 'stat_file_bytes')
RASTER = 'raster_fft'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_curves(path, bounds):
    curves = {task: [] for task in bounds}
    with path.open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            task = row['operation']
            stamp = int(row['monotonic_ns'])
            start, end = bounds[task]
            if start <= stamp < end:
                curves[task].append([(stamp-start)/1e9, *(int(row[key]) for key in FIELDS)])
    return {task: np.asarray(rows) for task, rows in curves.items()}


def longest_high(curve, threshold):
    time, current = curve[:, 0], curve[:, 1]
    high = np.flatnonzero(current >= threshold * current.max())
    runs = np.split(high, np.flatnonzero((np.diff(high) > 1) | (np.diff(time[high]) > .15)) + 1)
    window = max(runs, key=lambda r: time[r[-1]] - time[r[0]])
    return float(time[window[0]]), float(time[window[-1]])


def render(path, raster, xz, stages, high_window):
    fig, (full, zoom) = plt.subplots(2, 1, figsize=(11.5, 7), layout='constrained')
    fig.suptitle('Tiled raster processing and full-raster FFT', fontsize=17, fontweight='bold', x=.055, ha='left')
    time, charge, anon, _ = raster.T
    start = stages['full_raster_start']
    for axis in (full, zoom):
        axis.set_ylabel('Memory (GiB)')
        axis.set_axisbelow(True)
        axis.grid(axis='y', color='#dbe3ed')
        axis.spines[['top', 'right']].set_visible(False)
        axis.set_ylim(-.05, 4.15)
        axis.axvline(start, color='#9b5b16', lw=1, ls=':')
    full.plot(xz[:, 0], xz[:, 1]/GIB, color='#8794a7', lw=1.25, label='XZ cgroup charge')
    full.plot(xz[:, 0], xz[:, 2]/GIB, color='#8794a7', lw=1, ls=':', label='XZ anonymous')
    full.plot(time, charge/GIB, color='#005e99', lw=2.5, label='Raster cgroup charge')
    full.plot(time, anon/GIB, color='#04a386', lw=1.1, ls='--', label='Raster anonymous')
    full.legend(loc='upper left', frameon=False, ncols=2)
    full.set_xlim(0, max(time[-1], xz[-1, 0]) + 8)
    low = float(anon[time < start].max())/MIB
    full.text(start * .54, .37, f'Tiled stage: anonymous peak {low:.0f} MiB', color='#005e70', ha='center')

    zoom.axvspan(*high_window, color='#a7dfcf', alpha=.42, label='At least 95% of raster charge peak')
    zoom.plot(time, charge/GIB, color='#005e99', lw=2.5)
    zoom.plot(time, anon/GIB, color='#04a386', lw=1.1, ls='--')
    for name, label, dx, y in [('full_raster_start', 'Assemble', -.25, 1.5),
                               ('forward_fft', 'Forward FFT', .2, 1.88),
                               ('inverse_fft', 'Inverse FFT', .2, 2.84),
                               ('residual_and_output', 'Residual and output', .2, 3.54)]:
        zoom.axvline(stages[name], color='#647587', ls=':', lw=.8, zorder=0)
        zoom.text(stages[name]+dx, y, label, color='#394a60', fontsize=9,
                  ha='right' if dx < 0 else 'left')
    zoom.set_xlim(start - 2.1, time[-1] + 1.3)
    zoom.set_xlabel('Seconds since task start')
    zoom.legend(loc='upper left', frameon=False)
    fig.savefig(path, dpi=170, facecolor='white')
    plt.close(fig)


def analyze(result, serial, reference, output):
    run = load(result / 'summary.json')
    serial_run = load(serial / 'summary.json')
    plan = load(reference)
    serial_curves = serial / 'task_memory.csv'
    if hashlib.sha256(serial_curves.read_bytes()).hexdigest() != plan['serial_hashes']['task_memory.csv']:
        raise ValueError('serial curve does not match the reference plan')
    if not run['success'] or run['stats']['formal_swap_total_max_bytes'] or run['global_oom_kill_delta']:
        raise ValueError('expected a successful no-Swap raster run')
    workload = load(result / 'output.json')
    if workload['calibration_tiles'] is not None or workload['pixels'] != workload['side']**2:
        raise ValueError('expected a result covering the full raster')
    start = run['t0_ns']
    finish = start + round(run['duration_s'] * 1e9)
    raster = read_curves(result / 'task_memory.csv', {RASTER: (start, finish)})[RASTER]
    phases = [json.loads(line) for line in (result / 'phases.jsonl').read_text(encoding='utf-8').splitlines()]
    stage_times = {r['event']: (r['monotonic_ns'] - start)/1e9 for r in phases if r['event'] != 'tile_progress'}
    gui = [json.loads(line[12:]) for line in (serial / 'foreground_krita/process.log').read_text(encoding='utf-8').splitlines()
           if line.startswith('@@OOM_EVENT ')]
    homepage = next(e['monotonic_ns'] for e in gui if e.get('kind') == 'KRITA_PROCESS')
    bounds = {op: (homepage if op == 'foreground_krita' else rec['start_ns'], rec['empty_confirmed_ns'])
              for op, rec in serial_run['tasks'].items()}
    curves = read_curves(serial_curves, bounds)
    xz = curves.pop('xz')
    curves[RASTER] = raster
    high = longest_high(raster, .95)
    reference_target = plan['alignment']['target_s']
    high_center = sum(high) / 2
    foreground = curves['foreground_krita']
    fg_high_times = foreground[foreground[:, 1] >= .95 * foreground[:, 1].max(), 0]
    if high_center <= reference_target:
        target = reference_target
    else:
        candidates = fg_high_times[fg_high_times >= high_center]
        if not candidates.size:
            candidates = fg_high_times[fg_high_times >= high[0] + .15]
        if not candidates.size:
            raise ValueError('the raster high window starts after the foreground high window')
        target = float(candidates[0])
    shift = target - reference_target
    offsets = {'foreground_krita': 0.0,
               **{op: round(plan['alignment']['offsets_s'][op] + shift, 2) for op in ('array', 'table')},
               RASTER: round(max(0., target - high_center), 2)}
    # Use a fixed 10 ms grid in the joint observation window, with no extrapolation.
    left = max(c[0, 0] + offsets[op] for op, c in curves.items())
    right = min(c[-1, 0] + offsets[op] for op, c in curves.items())
    grid = np.arange(left, right, .01)
    if not len(grid):
        raise ValueError('the selected curves do not have a shared observation window')
    charge = np.array([np.interp(grid - offsets[op], c[:, 0], c[:, 1]) for op, c in curves.items()])
    peak_ratios = charge / np.array([c[:, 1].max() for c in curves.values()])[:, None]
    aligned_points = grid[(peak_ratios >= .95).all(axis=0)]
    total = charge.sum(axis=0)
    peak_index = total.argmax()
    evidence = dict(duration_s=run['duration_s'], xz_reference_duration_s=plan['reference']['task_duration_s']['xz'],
                    peaks_MiB=dict(zip(FIELDS, (raster[:, 1:].max(axis=0)/MIB).tolist())),
                    xz_peaks_MiB=dict(zip(FIELDS, (xz[:, 1:].max(axis=0)/MIB).tolist())),
                    low_stage_anon_peak_MiB=float(raster[raster[:, 0] < stage_times['full_raster_start'], 2].max()/MIB),
                    stage_times_s=stage_times, raster_high_window_s=high, predicted_offsets_s=offsets,
                    reference_target_s=reference_target, chosen_target_s=target,
                    projected_charge_peak_s=float(grid[peak_index]),
                    projected_charge_peak_GiB=float(total[peak_index]/GIB),
                    projected_at_peak={op: dict(charge_GiB=float(charge[i, peak_index]/GIB),
                                                ratio_to_peak=float(peak_ratios[i, peak_index]))
                                       for i, op in enumerate(curves)},
                    all_four_above_95_percent_grid_s=aligned_points.round(3).tolist(),
                    pairing_scope='Offline alignment of independent serial cgroup charges, on a 10 ms interpolation grid.')
    (output / 'alignment.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    render(output / 'raster_memory_curve.png', raster, xz, stage_times, high)
    print(json.dumps(evidence))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--serial', type=Path, required=True)
    parser.add_argument('--reference-plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.result, args.serial, args.reference_plan, args.output)
