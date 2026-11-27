# Krita全局内存PSI Full专项诊断

2026-11-27，只读诊断完成；本次随后授权上传Markdown报告。没有启动Krita、重跑实验、修改参数或清理原始证据。

- [根因分析与同点时间线](root_cause_report.md)
- [历史及当前进程盘点](process_inventory.md)
- [磁盘扩容与Swap审计](disk_swap_audit.md)
- [原始证据完整性盘点](evidence_inventory.md)

确认：全局12.77%时同点Krita为2.14%；Krita2.91%峰值早6.63秒。匿名内存增长、kswapd回收、直接回收和少量整机换页均有证据。具体边界外责任进程和全局缓存绝对历史序列UNKNOWN，未强行归因。

当前新boot空闲PSI为0、Swap使用为0，只能说明重启后状态。磁盘设备已识别100GiB，根分区和文件系统未扩展，约20GiB尚未纳入分区。不能据此认定历史压力已解决或已具备直接重采条件。

CSV、JSON、原始日志、素材和分析PNG保留在VM `/home/mxt/TeamOOM/results/diagnostics/psi_full_root_cause_20261127/`，本次不上传。
