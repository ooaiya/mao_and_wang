# 全机内存监控设计与现有代码审计

新增 `tools/diagnostics/system_memory_watch.py`，配套 `tests/test_system_memory_watch.py`，仅Python标准库，代码分支mxt，提交`5e9ac31141e6766e12f4db008b07638b5825dfb7`。实际开销验收NEEDS_OPTIMIZATION，设计支持指标采集不等于已经满足低开销目标。

现有metrics.py只保留4个全机meminfo字段、部分vmstat、memory PSI和实验cgroup指标；engine.py把Krita/自动化/监督进程与采集器分开；environment.py仍要求main和干净源码。config.py强制50ms和原安全阈值，collection.rapid-9000-medium-tail-extended.json固定低/高/中压设计。本次没有修改这些文件、模板、ORA或自动化脚本，没有调用旧GUI preflight/collect。main分支限制保留为后续独立问题。

## 数据流与时钟

|流|默认频率|内容|
|---|---|---|
|system|1s|全部meminfo（kB转字节，页数保持计数）、CPU/memory/io完整some/full PSI avg10/60/300/total、全部vmstat和/proc/stat CPU计数|
|processes|2s|PID+starttime、comm/exe/state/PPID/UID、VmRSS/HWM/Anon/File/Shmem/Swap/Threads、cgroup映射、新增/退出/迁移|
|cgroups|2s|枚举具有memory.current的域，记录current/peak/swap、完整stat/events/local/pressure、PID列表及数量、events；不累加父子层级|
|pss|10s|smaps_rollup完整可读字段与标准Pss/Anon/File/Shmem/SwapPss，逐PID状态、耗时和覆盖率|
|zones|10s|zoneinfo/buddyinfo/pagetypeinfo完整原文；zone水位/free/protection及order/碎片信息留待离线解析|
|vmware|10s|只读vmware-toolbox-cmd stat balloon，失败UNKNOWN|
|configuration|启动/结束|THP、zswap参数/可访问debug统计、zram设备与mm_stat/disksize/算法、VM参数白名单；结束版本放final_snapshot|
|monitor_health|每次任务后|CPU时间、自身RSS/PSS、读耗时、失败次数、累计写耗时、间隔偏差和lateness|

JSONL批记录均含monotonic_ns、boottime_ns、wall_time_ns和boot_id；读批次另有读前/后monotonic括号，快照不是原子读取。只按monotonic调度；不以墙钟拼接。进程的批时间上下文与starttime一起用于身份区分，PSS扫描也重验PID防重用。元数据记录用户、频率和执行源码SHA。

仅访问只读/proc、/sys及cgroup文件，不启动GUI、创建cgroup或systemd服务。运行器拒绝root和Git目录内输出；不采集cmdline或environ，避免记录凭据参数。错误区分permission_denied/not_found/read_error/parse_error/pid_reused/disappeared；缺失值为null或字段未提供，不填0。smaps权限和目录枚举失败不会被包装成完整覆盖。

原始累计vmstat不当作本轮增量；提供counter_delta处理缺失与回退为未知，离线在同boot/monotonic内计算差。cgroup根可能不提供memory.current，不属于该枚举的可记账域；根全机指标来自system流，不能据129个可读域声称根ABI的所有字段都存在。任意不可遍历目录在walk_errors保留。

## 测试与限制

最终48项现有及新增测试全部通过，无跳过。新增覆盖/proc/stat、带括号comm、PID重用、meminfo单位、完整PSI、counter增量、cgroup读取/删除/迁移、PSS权限、进程退出、字段缺失、单调时钟、JSONL和SHA256封存、模拟目录的SIGTERM安全结束；新增debugfs受限目录枚举回归测试。测试全使用临时合成输入，不运行压力/业务应用。测试进程导入pandas后的RSS与模拟快速采样CPU不用于监控自身开销验收。

系统python最初运行旧测试缺pandas，改用已有runtime/venv解释器，未安装依赖。普通用户首次实际监控在debugfs枚举处失败，已修复为明确记录错误并补测试；失败证据保留。此修复发生在正式完成的180s监控之前，测量源码hash在metadata.json中。

覆盖限制与开销结果见部署报告。后续需优化全PID扫描和cgroup扫描/序列化成本，必要时缓存只读身份字段但必须保留PID重用与迁移正确性，再单独验收，不能减少必需指标或默默降频。若需要完整root进程PSS/受限统计，需用户另行批准权限方案；本次没有放宽权限，当前实现也不会自行root运行。
