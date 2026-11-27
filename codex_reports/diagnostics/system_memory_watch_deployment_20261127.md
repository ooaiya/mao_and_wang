# 全机内存监控部署与180秒验收

最终状态：**NEEDS_OPTIMIZATION**；覆盖附加状态 **PSS_COVERAGE_PARTIAL**。阶段A扩容PASS，工具已部署且测试通过，但不具备直接接入下一轮Krita正式采集的低开销验收条件。

代码提交`5e9ac31141e6766e12f4db008b07638b5825dfb7`，工具在mxt。48项测试通过，原始测试日志 `/home/mxt/TeamOOM/results/maintenance/system_memory_watch_tests_final_20261127.log`，只留VM。本次正式空载监控运行ID `20261127T095026Z`；命令使用默认1/2/2/10/10秒频率，duration180，用户uid1000，非root。没有启动Krita、PeaZip、HandBrake、Table/Raster/Array或任何压力测试。

|验收项|实测|
|---|---|
|完整运行时长|180.001118579s|
|进程累计CPU|28.217943058s|
|单核平均CPU|15.676538%（要求≤1%，未通过）|
|自身max RSS|26492928B = 25.266MiB（要求≤100MiB，通过）|
|执行异常/中断|error=null，interrupted=false，exit0|
|原始封存|SHA256全部核验通过，JSONL时间戳递增|
|RSS状态读取覆盖率|均值99.9966%，范围99.6923–100%|
|cgroup memory.current读取覆盖|100%，walk_errors=0；只限可枚举且提供该control的域|
|全部可见PID PSS读取覆盖|均值22.9064%|
|具有正VmRSS的进程PSS覆盖|60.1626%|
|PSS扫描耗时|平均0.207690s，最大0.391622s|
|写入累计耗时|约1.748737s（最后health之前累计，非CPU时间）|

RSS状态文件读取成功不代表每个内核线程都提供VmRSS，缺失未填0。PSS总分母包括内核线程；not_found多数是没有smaps_rollup的内核线程及少量进程瞬退，不能全部解释成权限拒绝。PSS状态计数：{'permission_denied': 882, 'not_found': 3601, 'ok': 1332}。正RSS进程覆盖单独列出，避免用内核线程分母掩盖root用户态权限缺口。以≥100MiB作为本报告“高RSS”筛选阈值，漏读PSS的这类进程数量为0；这个阈值仅供覆盖分析，不是监控或实验安全阈值。全机PSS仍不完整，如后续要求覆盖受限root进程，需用户批准新的更高权限只读方案。

各流记录数：{'system': 180, 'processes': 90, 'pss': 18, 'cgroups': 90, 'zones': 18, 'vmware': 18, 'monitor_health': 414, 'configuration': 1}。configuration启动快照在JSONL，结束配置在final_snapshot.json。Vmware结果：{'status': 'UNKNOWN', 'returncode': 75, 'stdout': '', 'stderr': 'UpdateInfo failed: VMware Guest API is not enabled on the host\n'}，标UNKNOWN，未安装或重启Tools。pagetypeinfo/debugfs等无权限情况按原状态保留，不因此宣称局部分配/压缩指标已完全覆盖。

## 扫描耗时和调度偏差

偏差为实际连续启动间隔减目标周期；批扫描不是原子操作，同轮顺序任务会导致偏差。下面统计为采集器自报，监控开销评估使用整个独立进程CPU/实际180s，不以任何子阶段冒充全程。

|流|平均采样耗时s|最大采样耗时s|平均间隔偏差s|最大间隔偏差s|读取失败计数|
|---|---:|---:|---:|---:|---:|
|system|0.001639|0.003721|-0.000102|0.023327|0|
|processes|0.128683|0.176491|-0.000207|0.002203|22430|
|cgroups|0.100825|0.218482|-0.000836|0.044078|0|
|pss|0.208562|0.392462|-0.010757|0.057363|8966|
|zones|0.001576|0.002152|-0.021494|0.071001|18|
|vmware|0.167936|0.176805|-0.021309|0.071517|18|

失败计数含单字段权限/缺失及重复身份检查状态，不等于丢失的完整采样批次数；精确覆盖以各流attempted/readable和逐条status为准。RSS与cgroup扫描本身已有约0.13s/0.10s耗时，CPU整体15.68%超标；这些耗时是壁钟，不能直接等同CPU归因。实现保留完整数据以暴露成本，后续需降低遍历/读取/重复字段与序列化成本，重新验证，而不能宣称该版本是低开销合格方案。

首次实际启动失败ID `20261127T094911Z`，debugfs权限异常导致启动即退出，未形成完整监控，不计作180s成功轮；原失败目录和console日志留存，不覆盖、不删。修复后本次180s完整结束。没有运行任何业务应用或人为压力来验证。

## 原始证据与部署边界

原始数据：`/home/mxt/TeamOOM/data_collection/diagnostics/system_memory_watch/20261127T095026Z`。验收和invocation/console/acceptance：`/home/mxt/TeamOOM/results/diagnostics/system_memory_watch/20261127T095026Z`。数据包括metadata、system/processes/pss/cgroups/zones/vmware/monitor_health JSONL、configuration、final_snapshot和manifest。仅将代码测试提交mxt、Markdown汇报提交mxt_codex；CSV/JSON/JSONL/日志/PNG/素材不进入GitHub。

旧Krita原始run的37份封存成员仍匹配原SHA。main保持b65b76724c440d9c48738dd063b9311245aad178；原采集器、ORA和阈值不改，Swap容量/配置保持原状。不调用要求main的旧GUI入口，不创建服务或新cgroup。

下一阶段：**先审核并优化监控CPU开销，明确是否接受PSS部分覆盖或另行批准权限方案，再决定是否运行带监控Krita单轮**。当前不启动Krita、不计算时间线、不做正式并发。阶段B的运行功能验收完成，性能验收未通过，等待用户审核。
