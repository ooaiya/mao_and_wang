"""Normalize workflow phase events used by the shared scene and scheduler."""
import json


def phase_events(operation, rows):
    """Normalize landmarks emitted by the existing workload scripts."""
    krita_events = {'KRITA_PROCESS', 'PRE_IMPORT_REVIEW_START', 'PRE_IMPORT_REVIEW_DONE',
                    'HIGH_DOCUMENT_SUBMITTED', 'CAPTURE_WINDOW_DONE', 'HIGH_INSTANCE_EXIT',
                    'POST_CLOSE_REVIEW_START'}
    for row in rows:
        if 'monotonic_ns' not in row:
            continue
        if operation == 'foreground_krita':
            key = row.get('kind')
            if key not in krita_events:
                continue
        elif row.get('event_type') == 'phase_start':
            key = row['phase']
        elif row.get('event_type') == 'task_start':
            key = 'task_start'
        else:
            continue
        yield key, row['monotonic_ns']


def read_events(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # A live workload can still be writing its final line.
                continue


def reference_markers(operation, rows, origin_ns, duration):
    return {key: (stamp-origin_ns)/1e9 for key, stamp in phase_events(operation, rows)
            if 0 <= (stamp-origin_ns)/1e9 < duration}
