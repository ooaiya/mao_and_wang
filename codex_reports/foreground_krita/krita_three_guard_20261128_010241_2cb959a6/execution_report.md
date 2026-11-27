# Krita 三项内存压力参考阈值观测单轮试采

**SAFETY_STOP**。原验证器 **PILOT_INVALID**。

批次 `krita_three_guard_20261128_010241_2cb959a6`，run ID `717be1060cc54a55ae1c93d0dee082f8`。代码 `715afeaf0644d35da3cb207ab211dbaa85f75b6a`，配置 SHA256 `c6b19c657518b3ca754f7dd4474e973c878bc590183d60fb37fa89c7bd88b6f5`。

本轮唯一一次采集在 t=67.159 秒触发采样缺口守卫。直接触发的 parent 间隔为 **849.817 ms**，工作负载轨道随后记录 **858.477 ms**。原验证器判为 `PILOT_INVALID`，数据有效性与操作完整性均为 false。

运行元数据核实 PSI Full、MemAvailable、cgroup current / peak 均为 `observe_only`，SwapFree 等硬保护继续判断。三项参考指标在已有窗口均未越线。采集 unit 和全部可读祖先的 `memory.max` 为 `max`，根节点未提供该文件。

低压浏览完成 30 秒。人工提示后 7.259 秒发生安全停止，未收到 READY，也没有取得 46 层导入完成证据。完整 12 秒高压、第二实例、7 层操作和正常业务自然释放均未取得。新增的核验失败被动等待路径本轮未进入。

| 指标 | 已采窗口 |
| --- | ---: |
| RSS 峰 | 1.125 GiB |
| cgroup current 峰 | 1.060 GiB |
| 内核 memory.peak | 1.060 GiB |
| cgroup current 首次达峰（相对时间） | 30.002176 秒 |
| anon / file 峰 | 0.954 / 0.100 GiB |
| 最低 MemAvailable | 12.474 GiB |
| PSI Full / Some avg10 峰 | 0.36% / 0.36% |
| 工作负载 Swap / 整机已用 Swap 峰 | 0 / 22392832 字节 |
| OOM / OOM Kill 增量 | 0 / 0 |
| 工作负载样本 | 1338 |

环境在冷却阶段恢复，清理通过，宿主复查无实验进程、unit 或 cgroup 残留。41 个原始文件通过 SHA256 核验。

原始 run 保存在 `/home/mxt/TeamOOM/data_collection/foreground_krita/krita_three_guard_20261128_010241_2cb959a6/20261127T170333Z-de94fa0bafad46c7b8fa033071cd036c/717be1060cc54a55ae1c93d0dee082f8`。全分辨率 PNG 和分析报告保存在 `/home/mxt/TeamOOM/results/foreground_krita/krita_three_guard_20261128_010241_2cb959a6`。GitHub 报告使用 Markdown 可渲染曲线，以满足报告分支现有钩子。

- [阶段时间线](phase_timeline.md)
- [内存与超阈值统计](memory_analysis.md)
- [故障归因](failure_analysis.md)
- [配置与素材](configuration.md)
- [修改文件](changed_files.md)
- [曲线](curves.md)
- [测试](tests_summary.md)
- [验收](validation_summary.md)
- [内核限制与冷却恢复](kernel_and_recovery.md)
