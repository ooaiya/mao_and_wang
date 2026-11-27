# 本轮复现与参数审计

实验批次：`krita_single_round3_20261127_190942_e44a5be1`。唯一 run ID：`a2f75d1e2f2f4163850e7f0baa56433a`。

代码：`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`（mxt，前后工作区均干净）；配置 SHA256：`ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d`。

本轮仅执行一次原采集器 collect（--operation krita --rounds 1）；未重构代码、未修改实验配置/素材、未启动其他应用、未自动重试。GitHub仅上传本批次Markdown，原始数据、JSON、日志和PNG全部留VM。

## 实际使用路径

- repo：`/home/mxt/TeamOOM/repo`
- 配置：`/home/mxt/TeamOOM/runtime/config/krita_single_20261127_182751/foreground_config.json`
- Python：`/home/mxt/TeamOOM/runtime/venv/bin/python`
- 原入口：`/home/mxt/TeamOOM/repo/前台操作/前台操作自动化脚本采集/scripts/collect_krita.py`
- 原始run：`/home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_round3_20261127_190942_e44a5be1/20261127T111105Z-7e7dc22e865e41c6a432e07565e2100a/a2f75d1e2f2f4163850e7f0baa56433a`
- 本地结果：`/home/mxt/TeamOOM/results/foreground_krita/krita_single_round3_20261127_190942_e44a5be1`

外部启动包装只负责环境变量、调用记录、唯一调用标记和顺序控制；正式业务、GUI自动化、cgroup、采样、安全条件、清理和验证全部由固定提交的原程序执行。未修改原实验逻辑。

## 实际调用（审计记录，不是要求再执行）

```text
/home/mxt/TeamOOM/runtime/venv/bin/python /home/mxt/TeamOOM/repo/前台操作/前台操作自动化脚本采集/scripts/collect_krita.py preflight --config /home/mxt/TeamOOM/runtime/config/krita_single_20261127_182751/foreground_config.json --results /home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_round3_20261127_190942_e44a5be1
/home/mxt/TeamOOM/runtime/venv/bin/python /home/mxt/TeamOOM/repo/前台操作/前台操作自动化脚本采集/scripts/collect_krita.py collect --config /home/mxt/TeamOOM/runtime/config/krita_single_20261127_182751/foreground_config.json --operation krita --rounds 1 --results /home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_round3_20261127_190942_e44a5be1
/home/mxt/TeamOOM/runtime/venv/bin/python /home/mxt/TeamOOM/repo/前台操作/前台操作自动化脚本采集/scripts/collect_krita.py validate /home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_round3_20261127_190942_e44a5be1/20261127T111105Z-7e7dc22e865e41c6a432e07565e2100a/a2f75d1e2f2f4163850e7f0baa56433a
```

独占创建调用标记后仅调用collect一次，--rounds 1，无resume、无smoke、无后台操作。collect退出1后没有第二次调用。原preflight使用既有GNOME Wayland会话和Qt xcb，未改变系统Java、内核、Swap、VM内存或桌面环境。

## 固定实验参数

| 参数 | 实际值 |
|---|---|
| Krita | krita 5.0.2 |
| 低压文档 | 原9000×9000单层ORA |
| 高压文档 | 原46层ORA，9000×9000 |
| Tile Memory | 67% |
| 低压浏览 | 30s |
| 高压捕获 | 确认打开后12s，本轮未进入 |
| 中压 | 原7层文档，30s，本轮未进入 |
| review_interval | 5s |
| post_close_settle | 10s |
| 采样间隔 | 0.05s |
| open_timeout | 160s |
| startup/import/close/unresponsive timeout | 60/60/75/30s |
| 自动化graceful_stop_timeout | 10s |
| pilot graceful_stop_timeout | 30s |
| 实测屏幕尺寸 | 2552×1200 |

## 原安全条件（未调整）

| 配置字段 | 原值 |
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

其余pressure_profile参考、±4%容差、中压2–3GiB charge范围、forbidden_processes/units/sockets及pilot持续PSI条件均与前轮快照相等；没有新增cgroup memory.max人为硬限额。

## 原素材检查

| 路径 | 字节 | SHA256 | 层数 |
|---|---:|---|---:|
| /home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/generation_tmp/light_9000_source.ora | 5394398 | `87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8` | 1 |
| /home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46/light_9000.ora | 5394398 | `87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8` | 1 |
| /home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46/layered_9000_46.ora | 124404893 | `100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a` | 46 |
| /home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_tail_07_medium/light_9000.ora | 5394398 | `87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8` | 1 |
| /home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_tail_07_medium/layered_9000_07.ora | 22265294 | `7d7679e2072c387a207d9d393525a071f59fdfc3eaf7c491051ee402eedcc5aa` | 7 |

素材大小/SHA/结构重新检查；逐层PNG完整解码使用上一轮对完全相同字节的既有证据，未声称本轮重新运行完整PNG解码。原preflight重新核对ZIP CRC。文件均复用，没有生成、更换或减层。

## 完整性与审计

原manifest.sha256覆盖37成员；原verify_seal成功。VM另保存configuration_integrity.json、before_preflight_checks.json、environment_session.json、三次invocation.json、collect_invocation_marker.json、stage_state.json、post_run_checks.json、metrics.json和seal_verification.json。它们均不上传GitHub。源码工作区前后干净、配置SHA前后一致、旧run原封存也通过。

本轮失败后停止；本文件仅记录复现条件，任何下一次采集需用户另行授权。
