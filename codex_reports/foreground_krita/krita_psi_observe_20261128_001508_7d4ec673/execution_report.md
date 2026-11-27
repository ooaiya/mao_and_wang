# Krita PSI Full 仅观察单轮试采

**PILOT_INVALID**。原验证器 **PILOT_INVALID**。

批次 `krita_psi_observe_20261128_001508_7d4ec673`，run ID `f04ca1afb5da4fffac37c7e1d3c0d292`。代码 `4fbc49555484055bf78f2b6d437b6a04c791dd9f`，配置 SHA256 `8d487b076463470474d3c102dcc269e255b81fc74038faf2d7dd6bba795c6cd0`。

运行已落盘的策略为 `observe_only`。全局 PSI 样本继续保留，原资源硬保护、启动 PSI 和结束冷却检查照常执行。原验证器依照既有规则独立判定有效性。首个阶段错误 `RuntimeError('xdotool exit=1: XGetWindowProperty[_NET_ACTIVE_WINDOW] failed (code=1)\nxdo_get_active_window reported an error')`。采集器随后记录 `RuntimeError: Krita process identity changed`。

人工输入 `READY 46`，等待 522.572619 s。46 层导入和就绪确认 未取得 HIGH_DOCUMENT_READY，12 秒高压 未完成，第二实例 7 层操作 未完成。本轮 未取得可验收的正常自然释放。

RSS 峰 11.720 GiB，cgroup current 峰 11.992 GiB，最低 MemAvailable 1.918 GiB。全局 Full / Some avg10 峰值分别为 24.61 / 24.79。内核 OOM kill 增量 `0`，工作负载 OOM 增量 `0`。支撑数据为已有实测窗口，完整性以阶段和封存结果为准。

此前人工试采在 PSI Full 持续超限后停止。本轮观测到达到旧停止持续时间的高 PSI 段。本轮整机 PSI Full avg10 从 t=559.571 秒到 t=575.512 秒连续达到 10%，持续 15.941 秒，超过原 5 秒停止判据。此后采集继续，直到收到 READY 并进入窗口核验。单次观测只支持比较实际经过的阶段及退出条件。

原始数据留在 VM `/home/mxt/TeamOOM/data_collection/foreground_krita/krita_psi_observe_20261128_001508_7d4ec673/20261127T161722Z-7ddf66c2b53441d9b9995bda22999c5c/f04ca1afb5da4fffac37c7e1d3c0d292`，分析产物位于 `/home/mxt/TeamOOM/results/foreground_krita/krita_psi_observe_20261128_001508_7d4ec673`。

- [阶段时间线](phase_timeline.md)
- [内存分析](memory_analysis.md)
- [配置和素材核验](configuration.md)
- [离线测试](tests_summary.md)
- [原验证器结果](validation_summary.md)
