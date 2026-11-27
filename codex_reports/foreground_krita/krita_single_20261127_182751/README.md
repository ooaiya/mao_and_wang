# 重启后Krita单应用采集

状态：PILOT_INVALID。VM/素材/正式预检通过，唯一一次采集低压30秒完成；46层文档在原160秒加载确认窗口内超时，高压12秒和中压未完成。退出期间另有Krita process identity changed守卫错误，保留证据，没有修改守卫或重试。

全局PSI Full/Some最大值均0，任务Swap0，无OOM；这次失败不归类为上一轮PSI持续超限。部分记录峰值和曲线不能作完整前台参考。

- [完整执行报告](execution_report.md)
- [旧无效数据清理与保留范围](cleanup_report.md)
- [现有ORA逐层验收](asset_validation.md)
- [新轮次阶段事件](phase_timeline.md)

代码只在mxt最小化允许main/mxt白名单，保留dirty源码和全部其他安全检查。项目52测试、Krita专项114测试通过。Markdown交付到mxt_codex；PNG、日志、JSON/CSV和素材仅留VM，路径见完整报告。main不变；本轮停止，不运行其他应用、额外监控或并发。
