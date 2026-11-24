# NYC TLC work station independent validation

Read exactly the official 2023/2024 24 Yellow Taxi Parquet files under TeamOOM/assets/real_cases/nyc_transport_workstation. Do not duplicate or inflate them. Install the adjacent requirements only into TeamOOM/runtime/venv. Existing pandas/matplotlib requirements remain in force.

operations.py provides four separately invoked business operations: A Pandas annual summaries for interactive Jupyter use; B DuckDB monthly, zone and hourly reports; C zone boundaries and OD flow; D LightGBM duration regression (2023 training, 2024 test). All files are read once per relevant analytical pass; bounded batches avoid arbitrary RAM pressure. There are no sleeps to hold workload memory and no startup offsets.

D uses 100 trees, 31 leaves, learning rate .1, two CPU threads, seed 20261124. Duration must be 60..7200 seconds, distance .01..100 miles, features finite. Dropoff time is used only to derive the target, never as a feature. Disk-backed features are local model intermediates, not experimental reference curves. The model is saved and reloaded and predictions compared. C retains unknown zone IDs in tabular totals, without inventing geometry.

A notebook is created outside repo in TeamOOM/inputs/real_cases/nyc_transport_workstation and executed under its own user systemd unit. A notebook execution/kernel profile is distinct from a human interactive session; no human responsiveness result is inferred from batch execution. Start JupyterLab on localhost only and retain its authentication token locally; never commit or print the token in reports.

profile.py runs exactly one explicitly requested operation inside a unique teamoom-nyc-X user systemd unit. No memory limits, Swap, swappiness or kernel settings are changed. It logs aggregate cgroup process RSS/PSS, membership, memory.current/peak/events/swap, system availability/PSI and CPU ticks. CPU utilization derives from tick differences over elapsed time. Low system availability stops the related process group instead of increasing pressure. No freezing is performed. Unit metrics include the small observer process; do not label them child-only peaks.

Existing TeamOOM independent_runner.tick remains offset-driven; raster_priority requires historical reference contracts. cgroup_manager.create accepts a fixed operation set and foreground protection is named foreground_krita. Generic process registration alone is not an integrated request-driven selective scheduler. Do not route NYC operations through fabricated timeline configurations or build another scheduler. Natural concurrency remains blocked pending event-driven integration and actual fresh business requests after independent validation.

All data, notebooks, models, logs and results remain outside repo. Tests of feature engineering use tiny synthetic unit fixtures only, never fake measurements or reference curves.
