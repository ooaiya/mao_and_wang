# 前台操作

运行入口为 `前台操作自动化脚本采集/scripts/collect_krita.py`。Krita 通过 XWayland 和 AT-SPI 自动打开文档、缩放、切换高压实例及运行中压尾段。运行配置为 `collection.rapid-9000-medium-tail-extended.json`，峰前低压和峰后中压的观察窗口各为 30 秒。 [ORA 素材](素材/README.md)

根据 [复现实验](../复现实验.md) 运行 `scripts/prepare_handoff_config.py` 生成适配当前 VM 的配置与清单。高压文档确认打开后采样 12 秒，首实例确认退出后由第二实例执行 30 秒中压浏览。导入、关闭和实例切换另外耗时，实测阶段边界以事件日志为准。
