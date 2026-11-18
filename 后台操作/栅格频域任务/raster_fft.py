"""Deterministic tiled background estimation followed by full-raster FFT filtering."""

import argparse
import ctypes
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np


TILE = 1024
SEED = 20261116
FFTW_ESTIMATE = 1 << 6


def event(name, **details):
    print(json.dumps(dict(event=name, monotonic_ns=time.monotonic_ns(), **details)), flush=True)


def tile_data(row, col):
    rng = np.random.default_rng(np.random.SeedSequence([SEED, row, col]))
    data = rng.standard_normal((TILE, TILE), dtype=np.float32)
    x = (np.arange(TILE, dtype=np.float32) + col * TILE) / 257
    y = (np.arange(TILE, dtype=np.float32) + row * TILE) / 389
    data += np.sin(x)[None, :] * 4
    data += np.cos(y)[:, None] * 3
    return data


def estimate_background(row, col, sweeps):
    source = tile_data(row, col)
    destination = source.copy()
    for _ in range(sweeps):
        inside = destination[1:-1, 1:-1]
        np.add(source[:-2, 1:-1], source[2:, 1:-1], out=inside)
        inside += source[1:-1, :-2]
        inside += source[1:-1, 2:]
        inside *= np.float32(0.25)
        source, destination = destination, source
    return source[TILE // 4 : -TILE // 4, TILE // 4 : -TILE // 4].mean(dtype=np.float64)


def transform(raster, spectrum, inverse=False):
    fftw = ctypes.CDLL('libfftw3f.so.3')
    create_plan = fftw.fftwf_plan_dft_c2r_2d if inverse else fftw.fftwf_plan_dft_r2c_2d
    create_plan.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
    create_plan.restype = ctypes.c_void_p
    fftw.fftwf_execute.argtypes = fftw.fftwf_destroy_plan.argtypes = [ctypes.c_void_p]
    fftw.fftwf_execute.restype = fftw.fftwf_destroy_plan.restype = None
    source, destination = (spectrum, raster) if inverse else (raster, spectrum)
    plan = create_plan(*raster.shape, source.ctypes.data, destination.ctypes.data, FFTW_ESTIMATE)
    if not plan:
        raise RuntimeError('FFTW failed to create the transform plan')
    try:
        fftw.fftwf_execute(plan)
    finally:
        fftw.fftwf_destroy_plan(plan)


def filter_raster(side, backgrounds):
    raster = np.empty((side, side), dtype=np.float32)
    for i, j in np.ndindex(backgrounds.shape):
        raster[i*TILE:(i+1)*TILE, j*TILE:(j+1)*TILE] = tile_data(i, j) - np.float32(backgrounds[i, j])

    event('forward_fft')
    spectrum = np.empty((side, side // 2 + 1), dtype=np.complex64)
    transform(raster, spectrum)
    event('frequency_filter')
    horizontal = np.square(np.fft.rfftfreq(side).astype(np.float32) * 24)
    vertical = np.square(np.fft.fftfreq(side).astype(np.float32) * 24)
    for first in range(0, side, 64):
        weights = np.exp(-(vertical[first:first+64, None] + horizontal[None, :]))
        spectrum[first:first+64] *= weights

    event('inverse_fft')
    filtered = np.empty_like(raster)
    transform(filtered, spectrum, inverse=True)
    filtered /= np.float32(side * side)

    # Reuse the consumed FFT workspace for a full-resolution residual map.
    event('residual_and_output')
    residual = spectrum.view(np.float32)[:, :side]
    np.subtract(raster, filtered, out=residual)
    digest = hashlib.sha256()
    count = 0
    signal_sum = filtered_sum = signal_energy = filtered_energy = residual_energy = 0.0
    minimum, maximum = math.inf, -math.inf
    tiles = []
    for i, j in np.ndindex(backgrounds.shape):
        region = np.s_[i*TILE:(i+1)*TILE, j*TILE:(j+1)*TILE]
        original = raster[region]
        filtered_tile = filtered[region]
        difference = residual[region]
        count += filtered_tile.size
        signal_sum += original.sum(dtype=np.float64)
        filtered_sum += filtered_tile.sum(dtype=np.float64)
        signal_energy += np.square(original).sum(dtype=np.float64)
        filtered_energy += np.square(filtered_tile).sum(dtype=np.float64)
        tile_energy = float(np.square(difference).sum(dtype=np.float64))
        residual_energy += tile_energy
        minimum = min(minimum, float(filtered_tile.min()))
        maximum = max(maximum, float(filtered_tile.max()))
        digest.update(np.ascontiguousarray(filtered_tile))
        tiles.append(dict(row=i, col=j, correction=float(backgrounds[i, j]),
                          filtered_mean=float(filtered_tile.mean(dtype=np.float64)),
                          residual_rms=math.sqrt(tile_energy / filtered_tile.size)))
    input_mean = signal_sum / count
    output_mean = filtered_sum / count
    if not (math.isclose(input_mean, output_mean, abs_tol=1e-5)
            and 0 < filtered_energy < signal_energy and 0 < residual_energy < signal_energy
            and math.isfinite(minimum) and math.isfinite(maximum)):
        raise RuntimeError('filter failed mean conservation, energy, or finite-output checks')
    return dict(pixels=count, filtered_sha256=digest.hexdigest(), input_mean=input_mean,
                filtered_mean=output_mean, residual_rms=math.sqrt(residual_energy / count),
                input_energy=signal_energy, filtered_energy=filtered_energy,
                minimum=minimum, maximum=maximum, tiles=tiles)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--side', type=int, default=18432)
    parser.add_argument('--sweeps', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--calibration-tiles', type=int)
    args = parser.parse_args()
    tiles_per_side = args.side // TILE
    if args.side < TILE or args.side % TILE or args.sweeps <= 0:
        parser.error('side must be a positive multiple of 1024 and sweeps must be positive')
    if args.calibration_tiles is not None and not 0 < args.calibration_tiles < tiles_per_side**2:
        parser.error('calibration-tiles must be smaller than the full tile count')
    backgrounds = np.zeros((tiles_per_side, tiles_per_side), dtype=np.float64)
    event('tile_background_start', side=args.side, sweeps=args.sweeps, seed=SEED)
    for index, (row, col) in enumerate(np.ndindex(backgrounds.shape), start=1):
        backgrounds[row, col] = estimate_background(row, col, args.sweeps)
        if index % 9 == 0 or index in (args.calibration_tiles, backgrounds.size):
            event('tile_progress', completed_tiles=index, total_tiles=backgrounds.size)
        if index == args.calibration_tiles:
            break
    event('full_raster_start')
    result = filter_raster(args.side, backgrounds)
    result.update(side=args.side, sweeps=args.sweeps, seed=SEED,
                  calibration_tiles=args.calibration_tiles, numpy_version=np.__version__)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    event('finished')


if __name__ == '__main__':
    main()
