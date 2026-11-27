# 素材与配置验收

批次：`krita_manual_pilot_20261127_221114_305c963b`。run ID：`1eb123019f8643028b1c531460cc4048`。session：`20261127T141326Z-6180956c096644169237cdfddbc61dd5`。

代码：`bc8018ac6d2edb0bda077b23818b7247a2343c67`；配置 SHA256：`93861208bb21254774927359af03ee2f2d1cca23f70e9759104f8fd7326603bc`。本轮由用户在VM GNOME Terminal前台启动，collect只调用一次（rounds=1），失败后没有重试、没有改参数或代码、没有启动其他实验应用。

| 素材 | 字节 | 画布 | 层数 | SHA256 | 结果 |
|---|---:|---|---:|---|---|
| low / light_9000.ora | 5394398 | 9000×9000 | 1 | `87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8` | PASS |
| high / layered_9000_46.ora | 124404893 | 9000×9000 | 46 | `100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a` | PASS |
| tail / layered_9000_07.ora | 22265294 | 9000×9000 | 7 | `7d7679e2072c387a207d9d393525a071f59fdfc3eaf7c491051ee402eedcc5aa` | PASS |

完整路径：

- `/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46/light_9000.ora`
- `/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46/layered_9000_46.ora`
- `/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_tail_07_medium/layered_9000_07.ora`

启动前重新核对完整文件SHA、大小、stack.xml画布/层数及图层src；真实前台原preflight核对ZIP CRC并返回PASS。metadata.assets_unchanged=true，运行前后assets_manifest完全相同，没有替换或改动素材。7层原素材含5层9000×9000与2层5400×5400，本轮未修改；其画布仍9000×9000。

素材指纹和文件结构验收通过，不等于Krita内部导入完成。本轮没有READY，没有完成后的窗口/图层核验记录。

## 固定配置

配置：`/home/mxt/TeamOOM/repo/前台操作/前台操作自动化脚本采集/configs/collection.rapid-9000-manual-high-import.json`。

SHA256：`93861208bb21254774927359af03ee2f2d1cca23f70e9759104f8fd7326603bc`。

| 字段 | 原值 |
|---|---|
| manual_high_import | true |
| capture_origin（契约） | manual_document_ready |
| open_timeout_s | 160 |
| tile_memory_percent | 67 |
| capture_window_s | 12 |
| pre_import_review_s / post_close_review_s | 30 / 30 |
| interval_s | 0.05 |
| max_sample_gap_s | 0.5 |
| run_timeout_s | 1800 |
| max_global_full_avg10 | 10 |
| pilot.psi_full_sustained_s | 5 |

完整安全值未改：

| 字段 | 值 |
|---|---:|
| safety.max_sample_gap_s | 0.5 |
| safety.max_other_process_rss_bytes | 1073741824 |
| safety.min_available_bytes | 1610612736 |
| safety.min_swap_free_bytes | 322122547 |
| safety.min_disk_free_bytes | 10737418240 |
| safety.max_cgroup_bytes | 13314398617 |
| safety.max_global_full_avg10 | 10 |
| safety.cooldown_cgroup_bytes | 134217728 |
| safety.cooldown_min_available_bytes | 1610612736 |
| safety.cooldown_max_full_avg10 | 2 |
| safety.cooldown_timeout_s | 300 |
| safety.cooldown_stable_s | 5 |
| safety.run_timeout_s | 1800 |
