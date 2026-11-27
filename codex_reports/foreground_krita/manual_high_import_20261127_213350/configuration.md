# 新人工导入配置展示

来源代码提交 `bc8018ac6d2edb0bda077b23818b7247a2343c67`，文件 `前台操作/前台操作自动化脚本采集/configs/collection.rapid-9000-manual-high-import.json`。与上一轮VM部署配置比较，唯一差异为 `automation.manual_high_import=true`。此处仅展示配置，未覆盖部署配置或启动采集。

SHA256：`93861208bb21254774927359af03ee2f2d1cca23f70e9759104f8fd7326603bc`。

```json
{
  "schema_version": 1,
  "interval_s": 0.05,
  "asset": {
    "path": "/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46/light_9000.ora",
    "sha256": "87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8",
    "width": 9000,
    "height": 9000,
    "layers": 1
  },
  "display_size": [
    2552,
    1200
  ],
  "safety": {
    "max_sample_gap_s": 0.5,
    "max_other_process_rss_bytes": 1073741824,
    "min_available_bytes": 1610612736,
    "min_swap_free_bytes": 322122547,
    "min_disk_free_bytes": 10737418240,
    "max_cgroup_bytes": 13314398617,
    "max_global_full_avg10": 10,
    "cooldown_cgroup_bytes": 134217728,
    "cooldown_min_available_bytes": 1610612736,
    "cooldown_max_full_avg10": 2,
    "cooldown_timeout_s": 300,
    "cooldown_stable_s": 5,
    "run_timeout_s": 1800
  },
  "acceptance": {},
  "forbidden_processes": [
    "krita",
    "memshiftd",
    "memshift_taskctl",
    "ms_freezer_guard",
    "xz"
  ],
  "forbidden_units": [
    "memshift",
    "freezer",
    "strategy",
    "oomlab-a-"
  ],
  "forbidden_sockets": [
    "${XDG_RUNTIME_DIR}/memshiftd/control.sock",
    "/tmp/memshiftd/control.sock",
    "/data/local/tmp/memshiftd/control.sock"
  ],
  "mode": "pilot",
  "pilot": {
    "layers_dir": "/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46",
    "psi_full_sustained_s": 5,
    "graceful_stop_timeout_s": 30
  },
  "automation": {
    "startup_timeout_s": 60,
    "open_timeout_s": 160,
    "import_timeout_s": 60,
    "close_timeout_s": 75,
    "unresponsive_timeout_s": 30,
    "poll_s": 0.5,
    "accessibility_python": "/usr/bin/python3",
    "graceful_stop_timeout_s": 10,
    "completion_mode": "timed_window",
    "capture_window_s": 12,
    "pressure_profile": {
      "pre_import_review_s": 30,
      "post_close_review_s": 30,
      "review_interval_s": 5,
      "post_close_settle_s": 10,
      "peak_reference_bytes": 12884901888,
      "peak_tolerance_fraction": 0.04,
      "max_low_charge_bytes": 4294967296,
      "max_low_pressure_bytes": 7516192768
    },
    "tile_memory_percent": 67,
    "prepared_document": {
      "path": "/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46/layered_9000_46.ora",
      "sha256": "100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a",
      "width": 9000,
      "height": 9000,
      "layers": 46
    },
    "tail_document": {
      "path": "/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_tail_07_medium/layered_9000_07.ora",
      "sha256": "7d7679e2072c387a207d9d393525a071f59fdfc3eaf7c491051ee402eedcc5aa",
      "width": 9000,
      "height": 9000,
      "layers": 7
    },
    "tail_charge_range_bytes": [
      2147483648,
      3221225472
    ],
    "manual_high_import": true
  }
}
```
