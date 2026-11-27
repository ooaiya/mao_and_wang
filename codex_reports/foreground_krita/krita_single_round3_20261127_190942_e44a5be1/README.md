# Krita 单应用第三轮验证

**PILOT_INVALID；仅采集一次，已停止。** 原代码和原配置再次在46层ORA加载确认的160秒窗口内超时，高压12秒及7层中压均未执行。退出交界再现身份比较异常；具体变化字段未记录，不认定PID重用。

- [完整实验报告与关键内存数据](execution_report.md)
- [逐步骤验收](stage_acceptance.md)
- [原始阶段时间线](phase_timeline.md)
- [异常与原因分析](failure_analysis.md)
- [与上一轮对比](comparison_previous.md)
- [复现与固定参数](reproduction.md)

代码 `6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`；配置SHA `ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d`。

新run `a2f75d1e2f2f4163850e7f0baa56433a`；session `20261127T111105Z-7e7dc22e865e41c6a432e07565e2100a`。

原始封存37成员通过；RSS局部峰8.414474GiB、workload current局部峰8.337151GiB。cleanup/cooldown成功，结束检查无Krita/采集器/worker/unit/cgroup残留。

原数据留VM：`/home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_round3_20261127_190942_e44a5be1/20261127T111105Z-7e7dc22e865e41c6a432e07565e2100a/a2f75d1e2f2f4163850e7f0baa56433a`。五类PNG及派生统计留VM：`/home/mxt/TeamOOM/results/foreground_krita/krita_single_round3_20261127_190942_e44a5be1`。GitHub仅保存本目录Markdown；未修改main/mxt、实验代码、参数或素材，未启动其他应用或并发实验。
