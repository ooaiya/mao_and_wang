# 离线测试与回归汇总

测试对应本地代码提交 `bc8018ac6d2edb0bda077b23818b7247a2343c67`。测试没有启动Krita或新正式采集；生产实现不创建伪TTY，PTY仅由离线测试创建。

| 测试范围 | 数量 | 退出码 | 结果 |
|---|---:|---:|---|
| Krita专项（114项原测试+24项新增） | 138 | 0 | PASS |
| 仓库原有测试 | 52 | 0 | PASS |
| 静态AST/compile与Git diff检查 | — | 0 | PASS |
| 第二、三轮原失败数据复核 | 2轮 | — | 仍为PILOT_INVALID，原封存通过 |

两套完整测试均通过标准unittest discover运行，使用测试私有XDG_RUNTIME_DIR、PYTHONDONTWRITEBYTECODE=1；原源码干净断言和生产锁均保留。测试命令为 `python -m unittest discover -s tests -v`，分别在repo根目录及Krita子项目目录执行。完整命令、时间和日志保存在VM原交付目录。

## 24项新增用例

- `test_manual_import.AutomationTests.test_abort_is_preserved_and_never_verifies`：PASS
- `test_manual_import.AutomationTests.test_accessibility_timeout_is_logged_as_unavailable`：PASS
- `test_manual_import.AutomationTests.test_dialog_and_multiple_main_windows_rejected`：PASS
- `test_manual_import.AutomationTests.test_each_process_identity_field_is_guarded`：PASS
- `test_manual_import.AutomationTests.test_full_12s_after_verification`：PASS
- `test_manual_import.AutomationTests.test_manual_full_event_contract_and_unchanged_pressure_bounds`：PASS
- `test_manual_import.AutomationTests.test_ready_cannot_override_safety_stop`：PASS
- `test_manual_import.AutomationTests.test_ready_machine_proof_and_no_automatic_input`：PASS
- `test_manual_import.AutomationTests.test_slow_evidence_write_cannot_reuse_stale_safety_ack`：PASS
- `test_manual_import.AutomationTests.test_title_mismatch_keeps_actual_title_and_user_confirmation`：PASS
- `test_manual_import.AutomationTests.test_unavailable_is_user_confirmed_not_machine`：PASS
- `test_manual_import.AutomationTests.test_validator_checks_raw_proof_not_only_event_label`：PASS
- `test_manual_import.AutomationTests.test_wait_beyond_160_but_not_1800`：PASS
- `test_manual_import.AutomationTests.test_wrong_layer_counts_stop_without_ready`：PASS
- `test_manual_import.AutomationTests.test_wrong_window_or_accessibility_pid_cannot_use_user_fallback`：PASS
- `test_manual_import.FlowRegressionTests.test_only_high_open_changes_low_tail_and_exit_sequence_unchanged`：PASS
- `test_manual_import.TerminalTests.test_background_tty_rejected`：PASS
- `test_manual_import.TerminalTests.test_explicit_contradiction_never_uses_user_fallback`：PASS
- `test_manual_import.TerminalTests.test_invalid_partial_then_ready_or_abort`：PASS
- `test_manual_import.TerminalTests.test_non_tty_rejected_before_environment_or_application`：PASS
- `test_manual_import.TerminalTests.test_parameters_and_legacy_default_are_unchanged`：PASS
- `test_manual_import.TerminalTests.test_real_foreground_tty_relay_in_independent_process`：PASS
- `test_manual_import.TerminalTests.test_safety_ack_needs_fresh_parent_and_workload`：PASS
- `test_manual_import.TerminalTests.test_wait_does_not_block_50ms_fake_kernel_sampler`：PASS

## VM源文件SHA256

以下源文件本身不上传，摘要用于与VM核对：

| 文件 | SHA256 |
|---|---|
| krita_tests.log | `b286c6ca2f28f4e2ad6e7f3d815f44b166cbf2b8b5297bc61d14c8b6ba876dd6` |
| krita_tests.json | `5a20f2241faabb0d84ee551eb2c2b8620fb618dbc61660619ff4348c6672d706` |
| project_tests.log | `09fbd48a59c401c4d30f0f4aafb077c964ecbdd1ccc700566d4bc177786b0379` |
| project_tests.json | `d77c25ccf90cf5cfdc72ff1bc5697e260c221ef04fe74c69941b00f02e95558e` |
| historical_invalid_regression.json | `bfa880426c93488518b1001d196bb450958bd3672ebf553541a90e98aca8c86d` |
| verification_summary.json | `c01279819ae17bc955bf7aa390b35d17097ad1a56d62c10da4e366d4fad54289` |
| git_diff.patch | `723648cd4021f7cb20fb5f7a92443326da7015c0bdde21681d07753f22886489` |
