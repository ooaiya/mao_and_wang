"""Parse V4's separate system/task CSV scopes without legacy RSS aliases."""
import csv
from pathlib import Path


class DataParser:
    def __init__(self,run_dir):self.run_dir=Path(run_dir)
    def get_peak_memory(self,operation='system'):
        filename='system_memory.csv' if operation=='system' else 'task_memory.csv'
        column='resident_allocated_bytes' if operation=='system' else 'memory_current_bytes'
        peak=None;when=None
        with (self.run_dir/filename).open() as h:
            for row in csv.DictReader(h):
                if not row['relative_T0_s'] or float(row['relative_T0_s'])<0:continue
                if operation!='system' and row['operation']!=operation:continue
                if not row[column]:continue
                value=int(row[column])
                if peak is None or value>peak:peak=value;when=float(row['relative_T0_s']) if row['relative_T0_s'] else None
        return (peak/1e9 if peak is not None else None),when
