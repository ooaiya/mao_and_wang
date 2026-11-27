# 人工导入单轮安全停止分析

批次：`krita_manual_pilot_20261127_221114_305c963b`。run ID：`1eb123019f8643028b1c531460cc4048`。session：`20261127T141326Z-6180956c096644169237cdfddbc61dd5`。

代码：`bc8018ac6d2edb0bda077b23818b7247a2343c67`；配置 SHA256：`93861208bb21254774927359af03ee2f2d1cca23f70e9759104f8fd7326603bc`。本轮由用户在VM GNOME Terminal前台启动，collect只调用一次（rounds=1），失败后没有重试、没有改参数或代码、没有启动其他实验应用。

## 确定的主因与调用链

stop-request.reason和metadata.error均为 `RuntimeError: sustained severe global memory PSI full`。global Full avg10>=10的parent记录持续5.001963463秒，原5秒守卫触发。它不是160秒人工等待超时；本轮人工等待已持续约499.886秒，也未达到1800秒总上限。

调用链：原sample_rows写入parent样本 → 原sustained_pressure抛错 → cooperative_stop写stop-request → manual_checkpoint读到请求 → HIGH_DOCUMENT_READY_FAILED及第5阶段STOPPED → graceful_shutdown发Ctrl+Q等待超时 → 原采集器停止精确UUID unit → 冷却/清理/封存。journal时间对应22:22:59安全请求与自动化停止、22:23:09退出等待超时及开始停止unit、22:23:14服务停止完成。

用户当时报告“仍在导入或渲染”，随后报告“krita没有显示导入完成界面，应用自动关闭了”。这些为人工观察，不伪装成机器图层验收。关闭有上述安全控制链证据；没有理由称为用户ABORT、完成后的自然退出，或仅凭窗口关闭推定应用崩溃。

## 确认机制验证到哪里

真实前台TTY、输入线程/请求、原自动低压和人工等待阶段已实际运行。没有manual-import-response.json及HIGH_DOCUMENT_USER_READY，因而没有用户确认，也没有后续窗口、AT-SPI、图层、fresh safety ack或12秒起点。没有结果不能解释成机器读到了非46层；本轮没有这样的观测。

HIGH_DOCUMENT_READY_FAILED中的machine_verification_status/document_verification为FAILED，是安全停止时的失败标志。有效等级为UNCONFIRMED_NO_READY。该事件process_identity_status=VERIFIED，但这只代表原实例完整身份在错误处理检查中仍符合，不能替代文档加载证明。

原事件manual_wait_duration_s=0是未收到READY时保留的初始化值；实际等待时长由START至stop/FAILED的单调时间差派生，分别499.885617288/499.972627916秒。原始事件保持不变，报告明确两种口径。

## 次生退出问题

原graceful_shutdown等待约9.694375秒超时，没有正常退出码证明。metadata.evidence_errors还记录 `grace sampler: RuntimeError('Krita process identity changed')`，发生于安全退出之后的grace采样。未记录失败实际PPID/starttime/exe差值，具体变化字段UNKNOWN；不认定PID重用，不绕过任何身份/cgroup守卫。

cooperative_worker_completed=false与稍后存在finished.json并不矛盾：该标志在cooperative_stop返回时计算，grace sampler先因异常退出循环，worker随后写完成文件。finished.returncode=2属于自动化StopRequested路径，error=null仅表示worker包装无异常，不等于Krita正常退出或业务PASS。

## 数据影响及后续边界

原阶段1–4通过；阶段5STOPPED；高压捕获、正常自然释放和第二实例中压均未执行。只有被中止的等待/退出资源记录可供诊断，不能用于正式历史曲线或并发启动时间线。40成员SHA通过与业务失败不冲突。

本轮安全条件没有改动，原验证器保持PILOT_INVALID。所有重复错误原样保留（sustained severe PSI共384条），报告按类别汇总而不删除原错误。清理成功且无残留，不自动重试。

下一步仅建议审阅此次长导入与全局PSI/回收证据，再由用户决定新的只读诊断或修复任务。本轮不降低层数、修改tile、放宽PSI、扩展时间预算或再启动应用。
