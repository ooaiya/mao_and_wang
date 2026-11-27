# 内存、PSI与清理恢复分析

批次：`krita_manual_pilot_20261127_221114_305c963b`。run ID：`1eb123019f8643028b1c531460cc4048`。session：`20261127T141326Z-6180956c096644169237cdfddbc61dd5`。

代码：`bc8018ac6d2edb0bda077b23818b7247a2343c67`；配置 SHA256：`93861208bb21254774927359af03ee2f2d1cca23f70e9759104f8fd7326603bc`。本轮由用户在VM GNOME Terminal前台启动，collect只调用一次（rounds=1），失败后没有重试、没有改参数或代码、没有启动其他实验应用。

结论：**SAFETY_STOP，曲线为部分记录；无完整12秒高压、无7层中压、无正常业务自然释放。**

| 指标 | 实际记录 |
|---|---:|
|Krita样本数|11556|
|parent样本数|11558|
|VmRSS局部峰GiB|11.708439|
|VmHWM最大GiB|11.708439|
|workload current局部峰GiB|11.941624|
|内核memory.peak GiB|11.941742|
|anon局部峰GiB|11.546204|
|file局部峰GiB|0.358387|
|安全停止前current峰GiB|11.585079|
|安全停止前VmRSS峰GiB|11.374512|
|间隔中位ms|50.009090|
|间隔最大ms|107.355556|
|>500ms间隔|0|
|global Full/Some avg10最大|16.08 / 16.37|
|workload Full avg10最大|4.47|
|workload Swap峰B|0|
|整机Swap已用峰B|737280|
|整机pswpin/pswpout增量（页）|0 / 180|
|OOM/oom_kill增量|0 / 0|
|最小MemAvailable GiB|1.898663|


## 独立口径

VmRSS/VmHWM绑定Krita PID 23837；memory.current/peak、anon/file及swap_current来自独立workload cgroup，包含原自动化和helper。parent slice另含hold supervisor。整机MemAvailable、PSI和Swap单列，不计为应用独立使用量，不从MemAvailable下降反算RSS。不同分量峰不相加；RSS和cgroup charge不是同一计费口径。

全记录current峰11.941624GiB包含安全退出等待，安全停止前峰为11.585079GiB；两者分别报告。最后成功Krita采样t=579.131422447s。采样间隔中位50.009090ms、最大107.355556ms，最大未超过原500ms约束；这些只说明已有记录采样连续，不代表业务全流程完整。

## 已证实的PSI触发

原阈值global Full avg10>=10持续5秒。最终触发段的首个parent样本t=563.592906754s，触发样本t=568.594870217s，连续5.001963463s；该点Full avg10=16.08。采集循环先写parent再写Krita，parent当次检查先抛异常，所以Krita轨道最后一条此前样本的连续段仅4.951407643s，并不否定触发证据。

workload PSI Full峰4.47，与整机Full峰16.08分别保留。不能据两者数值不同推断“另一个应用造成故障”；本轮没有其他实验负载，现有记录不足以把全局压力逐进程归因。全局Full total增量6337444微秒、Some total增量6403223微秒。

整机发生180页换出、0页换入；workload Swap峰0字节，整机Swap已用峰737280字节，说明存在少量全机Swap活动，不能混称Krita发生相同规模换出。OOM/oom_kill增量均0。最小MemAvailable=1.898663GiB，高于原1.5GiB储备；current峰低于原12.4GiB预算，主故障明确由PSI守卫触发。

## 释放与曲线文件

| PNG（仅VM） | 口径与意义 |
|---|---|
| krita_rss.png | 原PID RSS/HWM，异常中止窗口 |
| krita_cgroup.png | workload current/peak |
| anon_file.png | workload anon/file分解 |
| mem_available.png | 整机余量，环境监测 |
| global_psi.png | 整机Full/Some及workload Full，标出原阈值与持续区间 |
| swap.png | workload memory.swap.current；整机Swap另在表中列出 |
| cleanup_recovery.png | unit停止后的parent slice与整机恢复，明确不是自然释放 |

所有图使用原T0与真实采样点，缺口不补零、不平滑、不伪造结束。正式捕获窗口未开始，因此没有12秒阶段峰值或平台统计。手工等待增长不能当作核验后的正式高压12秒。

清理恢复观察从t=589.700734032s至606.618708429s；末parent memory.current=0.364525GiB，整机MemAvailable=14.053116GiB。原冷却规则允许干净文件页残留，原cooldown_ok=true；不主动清缓存，也不把残留file计费误写成仍有Krita进程。原退出未正常完成，无法提供业务自然释放速度。
