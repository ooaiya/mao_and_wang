# Krita 46层人工导入单轮试采

**终止分类：SAFETY_STOP。原验证器：PILOT_INVALID，valid=false，curve_complete=false。**

批次：`krita_manual_pilot_20261127_221114_305c963b`。run ID：`1eb123019f8643028b1c531460cc4048`。session：`20261127T141326Z-6180956c096644169237cdfddbc61dd5`。

代码：`bc8018ac6d2edb0bda077b23818b7247a2343c67`；配置 SHA256：`93861208bb21254774927359af03ee2f2d1cca23f70e9759104f8fd7326603bc`。本轮由用户在VM GNOME Terminal前台启动，collect只调用一次（rounds=1），失败后没有重试、没有改参数或代码、没有启动其他实验应用。

## 为什么应用自动关闭

原安全守卫检测到整机 `global_psi_full_avg10 >= 10` 连续至少5秒，在t=568.637005031秒（2026-11-27T22:22:59.059+08:00）写入stop-request。自动化在人工等待轮询中收到StopRequested，尝试Ctrl+Q退出，等待超时后由原采集器停止本UUID unit。用户报告当时仍在导入或渲染、未看到完成界面，与本轮没有收到READY一致。不能将关闭解释成用户ABORT、正常业务结束或已确认的应用崩溃。

触发范围是**整机PSI**，不是Krita cgroup PSI替代值。parent采样轨道从t=563.592906754秒至t=568.594870217秒连续超过阈值，持续5.001963463秒，末值16.08。parent先采样并触发，所以不要求随后尚未写出的Krita行也恰好覆盖完整5秒。详情见[failure_analysis.md](failure_analysis.md)。

## 版本、配置、素材与真实终端

当前mxt HEAD=`bc8018ac6d2edb0bda077b23818b7247a2343c67`，工作区前后干净；main=`b65b76724c440d9c48738dd063b9311245aad178`。未推送mxt、未合并分支。配置为仓库 `configs/collection.rapid-9000-manual-high-import.json`，SHA与用户指定一致；manual_high_import=true、capture_origin=manual_document_ready、tile67%、采样50ms/最大500ms、高压12秒、中压30秒、open_timeout160、总时限1800秒及全部内存/PSI/Swap/cgroup/磁盘阈值均原样。

46层124404893字节、9000×9000及SHA通过；7层和低压文档也通过，原preflight重新核对ZIP CRC。运行前后原素材清单相同，详[asset_validation.md](asset_validation.md)。

Codex工具最初stdin不是TTY，按任务要求没有通过工具启动或分配伪终端。用户在真实GNOME Terminal执行一次性前台命令后，原preflight记录tty=`/dev/pts/0`，stdin_isatty=true、foreground_checked=true，前台PGID=23722；实际collector终端证明记录在run/manual-terminal.json。前台包装只继承真实stdin给原CLI并转录stdout，没有读取或模拟READY。

原preflight返回0，ok=true、errors=[]。MemAvailable=14.020618GiB、SwapFree=1.999996GiB、根分区可用30.062645GiB。此前只读2秒快照无实验进程/worker/unit/cgroup冲突，未终止系统服务或其他进程。

## 各阶段结果

| 阶段 | 结果 | 证据边界 |
|---|---|---|
|A. 启动/身份/窗口与低压|PASS|原阶段1–4 PASS，低压浏览30.001286262秒；低压关闭后才进入人工等待|
|B. 人工导入等待|SAFETY_STOP|t=68.751387743秒开始，等待499.885617288秒后触发PSI安全停止|
|C. READY输入及机器核验|NOT_RUN / UNCONFIRMED|无HIGH_DOCUMENT_USER_READY，无response文件，无READY后的机器核验开始/结束事件|
|D. 高压12秒|NOT_RUN|没有HIGH_DOCUMENT_READY及CAPTURE_WINDOW_START/DONE|
|E. 第一实例正常退出/自然释放|FAIL / NOT_OBTAINED|原Ctrl+Q退出等待超时；随后停止精确unit，清理释放不能算自然释放|
|F. 第二实例/7层中压30秒|NOT_RUN|无KRITA_POST_PROCESS、TAIL_DOCUMENT_OPEN_DONE及中压浏览事件|
|G. 资源清理与封存|PASS|cleanup/cooldown/journal均true；40个成员SHA通过；无残留|
|H. 原验证器|PILOT_INVALID|valid=false，curve_complete=false；退出码1|


本轮实际人工等待约499.886秒，证明没有沿用160秒自动打开确认超时。但READY接收、核验后12秒及后续中压**尚未得到本轮真实运行验证**，不能把离线测试通过写成这次业务通过。

有效确认等级为 **UNCONFIRMED_NO_READY**；无USER_CONFIRMED或MACHINE_VERIFIED。原失败事件/验证器中的FAILED表示安全停止令确认流程失败，不代表机器读到了错误层数。机器在READY之后才取快照，本轮未进入该步；实际导入完成、实际标题和46层机器验收均未取得。

## 关键内存数据

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


以上峰值覆盖被中止窗口及安全退出等待，不是完整高压12秒峰值。current口径包含Krita、自动化、supervisor及helper，RSS单独统计；anon/file分量峰未必同时。整机MemAvailable/PSI/Swap仅是环境指标，不冒充Krita独立曲线。

workload Swap为0，但整机发生少量换出（180页，已用峰737280字节），不能报告“完全没有Swap活动”。OOM和oom_kill为0；cgroup current最高仍低于原cgroup预算，停止原因由PSI记录直接确定。

## 完整性、自然释放与清理

原collect退出1，自动化finished退出2（StopRequested路径），原validate退出1。40个封存成员通过原verify_seal；封存完整不能补齐未运行阶段。既有原始日志和验证器重复错误原样保留，报告仅归并显示，不重写校验结果。

第一实例没有正常退出证据，未取得自然释放曲线；Ctrl+Q约9.694375秒等待超时，后续systemd停止unit，22:23:14日志显示停止完成。独立cleanup_recovery.png只绘清理后的parent slice和整机恢复，不能作为应用自然释放。冷却末parent charge=0.364525GiB，整机MemAvailable恢复至14.053116GiB。

metadata cleanup_ok/cooldown_ok/journal_ok均true，operations_verified=false。grace sampler另记录 `Krita process identity changed`；它发生在安全退出后的清理采样，未绕过守卫。具体变化字段没有记录，不认定PID重用。当前只读复查无实验进程、worker、unit，parent cgroup已消失，MainPID=0、unit inactive/dead。详[validation_summary.md](validation_summary.md)。

## VM数据与交付

原始run：`/home/mxt/TeamOOM/data_collection/foreground_krita/krita_manual_pilot_20261127_221114_305c963b/20261127T141326Z-6180956c096644169237cdfddbc61dd5/1eb123019f8643028b1c531460cc4048`。

结果目录：`/home/mxt/TeamOOM/results/foreground_krita/krita_manual_pilot_20261127_221114_305c963b`。

CSV、完整日志、metadata、阶段/进程/cgroup观测、manifest.sha256、原验证输出均留VM；本目录另保存metrics.json、只读预检、后检及封存核对。曲线为krita_rss.png、krita_cgroup.png、anon_file.png、mem_available.png、global_psi.png、swap.png、cleanup_recovery.png，全部由实际时间点绘制，缺失不补零、不平滑或伪造结束。详[memory_analysis.md](memory_analysis.md)。GitHub只上传Markdown。

本轮已停止，不重试、不改阈值、不自动运行其他应用。后续应先审阅此次持续PSI及回收证据，再决定新任务；本轮不实施修复或调整素材。
