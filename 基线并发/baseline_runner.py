#!/usr/bin/env python3
"""No-intervention XZ baseline with the automated low–high–medium foreground."""

import argparse
from pathlib import Path
import signal
import sys

FREEZER = Path(__file__).resolve().parents[1] / '冻结并发'
sys.path.insert(0, str(FREEZER))

from raster_baseline import DeadlineBaseline
from segmented_runner import SegmentedFreezer


class XzBaseline(DeadlineBaseline, SegmentedFreezer):
    run_kind = 'xz_baseline'

    def __init__(self, args):
        super().__init__(args.output, '.', '.', FREEZER / 'priority_freeze_only_config.json',
                         args.serial_run, args.foreground_run, args.foreground_source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'serial-run', 'foreground-run', 'foreground-source'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()

    def stop(signum, frame):
        raise KeyboardInterrupt('termination signal')

    signal.signal(signal.SIGTERM, stop)
    return XzBaseline(args).run()


if __name__ == '__main__':
    raise SystemExit(main())
