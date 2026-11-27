# 16.258 GB 与采集器审计

本文记录旧采集器的计量口径和当时的排查结论。当前四任务的整机与 cgroup 采样入口见 [sampling.py](../common/sampling.py)，结果复核见 [复现实验](../../复现实验.md)。

## 已从旧源码确认的问题

旧 `common/monitor.py` 读取 `/proc/<pid>/status`，将 VmRSS 写成 `<operation>_memory_current`，将 VmPeak 写成 `<operation>_memory_peak`。前者是单进程 RSS，后者是虚拟地址空间高水位，均不是同名 cgroup 字段；还会漏掉子进程和文件缓存。旧低内存次数按低样本数计算，旧报告把 PSI full 比例作为卡顿表现，不能代替 GUI 响应延迟。

旧整机峰值报告的计算为 `(system_MemTotal - system_MemAvailable) / 1e9`。当时核查的该字段仅使用这两项整机内存指标。

## 16.258 的精确来源仍待原始行

历史 VM 的 MemTotal 为16,719,261,696 Bytes，约16.719262 GB / 15.571026 GiB。因此16.258 GB本身不超过真实MemTotal，不能只因配置界面写16GB就认定异常。若该值是 GiB，判断又不同；必须核对原始字段、单位与那轮报告公式。

用户尚未提供产生该数值的原始并发采样/报告，已安排后补。当前只能确认上述源码口径错误与单位误读的可能性，不能虚构旧行或宣称找到唯一数值根因。原始16.258问题的精确追溯状态为 WAITING_ORIGINAL_RUN；不通过截断为16或编辑报告解决。

## 当时的修订口径

- 整机：/proc/meminfo 的实际 MemTotal，驻留页分配值 MemTotal−MemFree（含缓存），以及独立的压力代理 MemTotal−MemAvailable；越界数据标记无效，不强行裁剪。
- 任务：稳定且独立的任务根 cgroup 的 memory.current/peak/stat/events/swap。memshiftd 自有冻结子组仍在任务根下，采集只读父任务聚合一次，不再累计其子组。
- 进程：RSS、VmHWM、PSS、USS、VmSize、VmPeak 各有独立名称；虚拟字段不当作物理内存。
- Swap、io.stat、CPU/memory/IO PSI 分列；磁盘字节不进入内存字段。
- 低内存按实际时间戳统计连续事件和持续时间；阈值写入summary。
- Linux vmstat/cgroup事件的增量和kernel journal证据分开保存，不把计数与日志再相加；SIGKILL不单独证明OOM。没有可靠证据的全局OOM尝试次数保持未知。
- T0前原始样本用于预检/基线证据，正式汇总仅计算homepage_ready之后。
- GUI输入到完成的关联按用户要求暂缓；P50/P95/P99和最大延迟均为N/A，不用CPU或PSI伪造。

验证使用固定字节夹具、缺失cgroup、虚拟内存标签、连续低内存片段、T0边界和真实C++服务IPC测试；真实VM的新旧采集对照待原始并发结果与VM连接补齐后进行。
