"""Run a deterministic anonymous-memory workload with observable phases."""

import argparse
import hashlib
import json
import math
import mmap
from dataclasses import dataclass
from pathlib import Path
import time

@dataclass(frozen=True)
class Profile:
    elements: int
    block_elements: int
    dtypes: tuple[str, ...]
    grow_interval_s: float
    hold_s: float
    release_interval_s: float


RASTER_SIDE = 18432
PROFILES = {
    'raster': Profile(RASTER_SIDE ** 2, RASTER_SIDE * 288, ('<f4',) * 3, .45, 35., 0.),
    'table': Profile(2 ** 27, 2 ** 21, ('<u8',) * 4, .45, 35., .35),
    'array': Profile(2 ** 26, 2 ** 22, ('<f4', '<f4', '<f8'), .05, 45., .6),
}
TIMING_FLAGS = ('prepare_s', 'grow_interval_s', 'hold_s', 'release_interval_s')
TILE = 65536  # Bound the scratch space independently of the retained buffers.


def timing_for(task, overrides=None):
    profile = PROFILES[task]
    timing = dict(prepare_s=1., grow_interval_s=profile.grow_interval_s,
                  hold_s=profile.hold_s, release_interval_s=profile.release_interval_s)
    for key, value in (overrides or {}).items():
        if key not in timing:
            raise ValueError(f'unknown timing option: {key}')
        if value is not None:
            if not math.isfinite(value) or value < 0:
                raise ValueError(f'{key} must be finite and nonnegative')
            timing[key] = value
    if timing['grow_interval_s'] == 0 or timing['hold_s'] == 0:
        raise ValueError('the growth interval and peak hold must be positive')
    if (task == 'raster') != (timing['release_interval_s'] == 0):
        raise ValueError('Raster releases all at once; Table and Array release in stages')
    return timing


def timing_args(timing):
    return [arg for key in TIMING_FLAGS
            for arg in ('--' + key.replace('_', '-'), str(timing[key]))]


def add_timing_options(parser):
    for key in TIMING_FLAGS:
        parser.add_argument('--' + key.replace('_', '-'), type=float)


def fill_raster(np, indices, raw, corrected, residual):
    raw[:] = indices % 8192
    np.multiply(raw, np.float32(1.125), out=corrected)
    corrected += np.float32(.25)
    np.subtract(corrected, raw, out=residual)


def fill_table(np, indices, stamp, row_id, value, converted):
    row_id[:] = indices
    stamp[:] = 1_700_000_000 + indices // 1024
    value[:] = (indices * 1664525 + 1013904223) % 65536
    np.multiply(value, np.uint64(100), out=converted)


def fill_array(np, indices, x, y, score):
    x[:] = indices % 1024
    y[:] = (indices * 17 + 11) % 1024
    np.multiply(x, .625, out=score, dtype=np.float64)
    score += np.multiply(y, .375, dtype=np.float64)


FILL = {'raster': fill_raster, 'table': fill_table, 'array': fill_array}


def build_block(task, start, count, dtypes):
    size = count * sum(dtype.itemsize for dtype in dtypes)
    if hasattr(mmap, 'MAP_PRIVATE'):
        region = mmap.mmap(-1, size, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
    else:
        region = mmap.mmap(-1, size)
    try:
        fill_block(region, task, start, count, dtypes)
    except BaseException:
        region.close()
        raise
    return region


def fill_block(region, task, start, count, dtypes):
    import numpy as np

    arrays = []
    offset = 0
    for dtype in dtypes:
        arrays.append(np.ndarray(count, dtype=dtype, buffer=region, offset=offset))
        offset += count * dtype.itemsize
    for left in range(0, count, TILE):
        right = min(left + TILE, count)
        indices = np.arange(start + left, start + right, dtype=np.uint64)
        FILL[task](np, indices, *(array[left:right] for array in arrays))


def run(task, output, trace, timing):
    import numpy as np

    profile = PROFILES[task]
    dtypes = tuple(map(np.dtype, profile.dtypes))
    buffers = []
    resident_bytes = 0
    checksum = hashlib.sha256()

    def event(stream, kind, **details):
        stream.write(json.dumps(dict(event_type=kind, operation=task,
                                     monotonic_ns=time.monotonic_ns(),
                                     retained_bytes=resident_bytes, **details)) + '\n')
        stream.flush()

    with trace.open('x', encoding='utf-8') as stream:
        try:
            event(stream, 'task_start')
            event(stream, 'phase_start', phase='prepare')
            time.sleep(timing['prepare_s'])
            event(stream, 'phase_start', phase='grow')
            for batch, start in enumerate(range(0, profile.elements, profile.block_elements)):
                if batch:
                    time.sleep(timing['grow_interval_s'])
                count = min(profile.block_elements, profile.elements - start)
                region = build_block(task, start, count, dtypes)
                buffers.append(region)
                resident_bytes += len(region)
                event(stream, 'phase_start', phase=f'grown:{batch + 1}')
            peak_bytes = resident_bytes
            event(stream, 'phase_start', phase='hold')
            time.sleep(timing['hold_s'])

            if timing['release_interval_s']:
                event(stream, 'phase_start', phase='release')
                for batch, region in enumerate(buffers, 1):
                    time.sleep(timing['release_interval_s'])
                    checksum.update(region)
                    resident_bytes -= len(region)
                    region.close()
                    event(stream, 'phase_start', phase=f'released:{batch}')
            else:
                event(stream, 'phase_start', phase='verify')
                for region in buffers:
                    checksum.update(region)

            result = dict(task=task, elements=profile.elements, block_elements=profile.block_elements,
                          peak_buffer_bytes=peak_bytes, data_sha256=checksum.hexdigest(),
                          timing_s=timing)
            with output.open('x', encoding='utf-8') as dest:
                json.dump(result, dest, indent=2, allow_nan=False)
                dest.write('\n')
            for region in buffers:
                if not region.closed:
                    region.close()
            resident_bytes = 0
            event(stream, 'task_end')
        finally:
            for region in buffers:
                if not region.closed:
                    region.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', choices=PROFILES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    add_timing_options(parser)
    args = parser.parse_args()
    try:
        timing = timing_for(args.task, {key: getattr(args, key) for key in TIMING_FLAGS})
    except ValueError as error:
        parser.error(str(error))
    run(args.task, args.output, args.output.with_name('phase_trace.jsonl'), timing)


if __name__ == '__main__':
    main()
