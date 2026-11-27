# Krita整机PSI Full异常专项诊断

> 发布说明：本次依据用户随后“报告传到github的mxt_codex”的授权，仅发布Markdown报告。文中不提交/推送的限制描述此前只读诊断阶段。原始数据、CSV、日志、JSON与PNG留在VM。

结论：**原安全停止触发已确认；Krita匿名内存持续增长、系统后台回收、直接回收及少量Swap活动共同出现。Krita增长促发系统回收为LIKELY；全局PSI差额具体归属哪个进程/内核线程仍UNKNOWN。没有证据证明某个未清理应用大量占用内存，也不能排除边界外进程。当前不应将环境已重启或盘已扩容视为具备直接重采条件。**

本轮严格只读：未启动Krita、未重采/并发、未修改阈值/cgroup/Swap/swappiness/内存/分区/配置、未清理缓存或文件、未Git add/commit/push/merge。报告与派生数据仅写入本目录。

## 当前系统

真实仓库 ## mxt...origin/mxt，HEAD 81f1f27d82b861b05f8a479a170035d39225fd67。启动时间 2026-11-27 16:54:55（Asia/Shanghai），boot_id b0f8e49f-ad03-4e9e-ac35-b44d54a4ee14；历史实验boot_id f6f5422e-c9e9-4efe-bdf8-2f8f3844b6c2，两者不同。内存总量16728551424B，约15.58GiB；MemAvailable约14.23GiB；Swap约2GiB、当前使用0；memory PSI some/full avg10均0。当前/proc/meminfo、vmstat、PSI及进程/服务完整快照保留current/，采样时刻不同可有小幅波动。当前zswap参数N；这不能证明旧boot也禁用压缩。

磁盘识别100GiB，但根分区79.50GiB、文件系统df口径77.69GiB，尾部约20GiB未用。见[disk_swap_audit.md](disk_swap_audit.md)。

## 原始证据与作用域

原run `/home/mxt/TeamOOM/data_collection/foreground_krita/rapid_9000_generated_20261127_154636/20261127T075412Z-ddd146dd9183414c8108dc5edcf5c04e/c5aea221ac9f440d9e9366b600251210`，37个原manifest成员逐一SHA256和集合核验通过，未改写。缺失remaining-processes.json标UNKNOWN。见[evidence_inventory.md](evidence_inventory.md)。实验边界含Krita、自动化与监督helper；父slice另含hold；不能将parent或主机作为Krita替代。

## 时间对齐

所有CSV保留原monotonic_ns与relative_s，无重采样、无插值补齐。psi_timeline.csv及memory_timeline.csv保留两个原scope各自行，关键比较只取同一条Krita行的global/cgroup读数。字段读取有先后，属于同组近同时快照，不宣称硬件原子同时读取。

|事件|t，自采集origin秒|monotonic_ns|Global full avg10|Krita full avg10|Krita memory.current GiB|MemAvailable GiB|
|---|---:|---:|---:|---:|---:|---:|
|全局full首次非零|162.302016137|266618071765219|2.17|0.0|4.625961|8.455856|
|全局首次≥10且首次达到全局峰|232.328169133|266688097918215|12.77|2.14|6.780060|6.226418|
|Krita自身首次达到峰|225.697338850|266681467087932|9.42|2.91|6.630169|6.403580|

全局首次≥10发生于2026-11-27T15:58:08.214252+08:00，与首次12.77峰值为同一条样本。Krita2.91峰值早6.630830s，当时全局9.42；不能用12.77与2.91两个各自最大值当作同一时刻。

全局≥10唯一完整观测段：[232.328169133, 238.276326883]s，观测跨度5.948157750s；第一条低于10在238.332775795s。阈值真实跨越位于相邻样本之间，有采样不确定性；并非连续硬件测量。停止请求为t=237.399454495s，从第一条≥10起约5.071285s，符合持续5s规则。该完整超限段尾部已含停止处理，不能全算正常导入期。

关键事件各前后30s已导出event_windows_30s.csv。首次≥10与峰值重合，保留不同anchor标签；后30s超出原记录末尾约247.919s的部分均标记TRUNCATED，未补齐。停止锚点取最近实测行，其时刻与stop-request原时刻差值在facts.json可核对。

超限前约30s到首次超限：anon从5.731277增长到6.719028GiB（增加0.987751）；file从54.328降至45.941MiB；MemAvailable从7.221363降至6.226418GiB。约30s增长斜率33.728MiB/s。PSI上升时仍在46层导入的内存增长阶段，未进入确认的高压平台。

## 回收、缓存、Swap和内核内存

以下全部vmstat是**整机累计计数器**，即使存放在krita行也不能归属于Krita PID；parent/krita重复观测不能相加。起止快照覆盖约248s，另在facts.json提供首末CSV样本口径增量。

|计数器|实验起止增量|
|---|---:|
|pgsteal_file|675831|
|pgscan_direct|6212|
|pgsteal_proactive|0|
|pgscan_anon|6077|
|pgsteal_kswapd|671775|
|oom_kill|0|
|pgscan_direct_throttle|0|
|pgscan_khugepaged|0|
|pgscan_proactive|0|
|pgscan_file|689890|
|pgsteal_khugepaged|0|
|pgsteal_direct|5996|
|pgmajfault|204|
|pswpout|1568|
|pgscan_kswapd|689755|
|pswpin|8|
|pgsteal_anon|1940|
|pgfault|2160572|

kswapd扫描689755页、回收671775页；直接回收扫描6212页、回收5996页，两者均CONFIRMED，后台回收数量占主导。文件页回收675831页，按4KiB页约2.578GiB，表明缓存确实被回收；不能因Cached很大就判缓存泄漏。该累计量不是唯一物理页数，页面可能被反复扫描/回收。

Krita cgroup文件页最大168.922MiB，结束45.984MiB，没有持续大幅积累。该子域缓存失控假说REJECTED；全局Cached/Buffers/Dirty/Writeback等历史绝对序列未保存，主机级缓存积累原因UNKNOWN。Krita匿名内存由0.005367增至7.062847GiB，是本域主要增长分量，但这不证明它是唯一全机原因。

Krita kernel分量最大16.895MiB、slab_unreclaimable最大1.359MiB，不支持本域不可回收内核内存失控；全局SUnreclaim历史UNKNOWN。

系统Swap输出1568页（6.125MiB）、输入8页（32KiB），活动CONFIRMED，但“不足Swap容量或Swap抖动主导”为UNKNOWN。Krita任务swap_current全部0；parent曾达77824B，说明父域额外进程有少量Swap，不能算Krita。最低SwapFree约1.743GiB，最低MemAvailable约5.903GiB，高于原门槛；这不否认局部、zone或短时分配时延。OOM kill增量0。zswap/zram历史启用量、压缩量及zone/THP/compaction轨迹UNKNOWN。

首次超限前30秒窗口（原始最近行t=202.339714715至232.328169133）：整机计数器增量 pgscan_kswapd=250087, pgsteal_kswapd=240670, pgscan_direct=1058, pgsteal_direct=900, pswpin=0, pswpout=996。这些增量证明停止之前已存在回收/换页，不能只用停止后的总量解释。

## 为何global显著高于cgroup

PSI是资源阻塞时间趋势，不是内存使用百分比；avg10为衰减趋势，非逐样本瞬时比例。作用域不同，不可相减为“其他进程占比”。参见[Linux官方PSI文档](https://docs.kernel.org/accounting/psi.html)。

本机可读6.17.13源码kernel/sched/psi.c的collect_percpu_times（约365–410行）按每CPU非idle时间加权，各scope权重不同；约865行还将运行中的memstall任务计入MEM_FULL。mm/vmscan.c的balance_pgdat约7011–7199行使用psi_memstall_enter/leave，支持kswapd回收可计入root域而不等同应用域的机制。因此，全局后台回收与应用自身分配阻塞可呈现很不相同的PSI，数值不要求简单包含或相减。这里是源码机制佐证，不是对正在运行定制内核每一行的运行追踪证明。

本次全局full total增加7026084us，Krita增加502056us；和大量kswapd回收一起支持**边界外后台回收参与为LIKELY**。没有全机线程调度/回收栈，不能确认究竟是kswapd、其他应用、其他内核因素各贡献多少。global12.77/cgroup2.14在同一采样点已证明峰值错位不能独自解释差距；原始采集器global字段来自/proc/pressure/memory、cgroup字段来自各自memory.pressure，未见交换字段证据。

## 根因判断

|可能原因|证据|判断|
|---|---|---|
|其他进程大RSS竞争|无故障时全机RSS快照；只覆盖实验域；预检无冲突仅为启动前瞬间|UNKNOWN|
|文件缓存积累|Krita缓存有限并下降，全局文件页回收约2.58GiB；全局Cached历史缺失|REJECTED（Krita缓存失控）；UNKNOWN（全局积累）|
|Krita匿名内存增长|同点anon持续上升，MemAvailable下降|CONFIRMED（增长）；LIKELY（压力诱因）|
|直接回收|pgscan_direct/pgsteal_direct均正|CONFIRMED|
|kswapd后台回收|扫描和回收约67万页|CONFIRMED；差额PSI归属LIKELY|
|Swap压力|系统少量换页；任务Swap0、SwapFree充裕|CONFIRMED（活动）；UNKNOWN（主要原因）|
|不可回收内核内存|本域很小；全局历史缺失|REJECTED（本域失控）；UNKNOWN（全局）|
|多因素共同作用|应用增长+回收+小量换页共同发生|LIKELY；不能唯一归因|

## 下一步建议与是否可重采

已确认：持续PSI触发、安全停止、匿名增长、回收、少量全机Swap、磁盘只扩设备未扩分区。高度怀疑：Krita分配增长推动回收，root域kswapd/其他边界外线程贡献较多压力。仍待证据：全机PID/RSS/PSS/cgroup归属、各域PSI、完整meminfo、zone水位/allocstall/compaction/THP与压缩、VM balloon和宿主机压力。

下次采集前，应先单独批准低开销的全机诊断旁路计划，连续保留上述缺失字段并验证时间戳和监控开销；需要时在授权范围记录回收tracepoint，才能量化责任线程。本轮仅提出建议，未安装或启用追踪。磁盘如需使用新增20GiB，应另行维护分区/GPT/文件系统并核验，扩Swap另需依据，均不是当前PSI根因修复结论。

重启后当前空闲资源足够只说明当前状态；尚未证明导致原中止的因素已解决，**不具备“已验证可直接重采”的证据条件**。需要补充诊断；不建议以降阈值、清缓存、删常驻进程或加Swap替代归因。Krita历史失败轮仍PILOT_INVALID，本轮无重采。

## 分析图

图表：PSI、内存和回收同轴对齐，保留于VM诊断目录的 `psi_memory_reclaim_alignment.png`。

## 交付

[进程盘点](process_inventory.md)、[磁盘Swap审计](disk_swap_audit.md)、[证据盘点](evidence_inventory.md)、psi_timeline.csv、memory_timeline.csv、event_windows_30s.csv、facts.json及分析图。报告完成后停止，不提交或推送GitHub。
