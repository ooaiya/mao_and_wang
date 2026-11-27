"""Start the current predictive freeze/thaw experiment."""

from pathlib import Path

from segmented_runner import SegmentedFreezer
from common.concurrent import run_cli


if __name__ == '__main__':
    raise SystemExit(run_cli(SegmentedFreezer, Path(__file__).with_name('raster_priority_config.json')))
