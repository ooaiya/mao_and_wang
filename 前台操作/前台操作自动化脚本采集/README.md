# Krita 低压 → 高压 → 中压自动化

`scripts/collect_krita.py` 运行独立采集。运行配置为 `configs/collection.rapid-9000-medium-tail-extended.json`，峰前低压和峰后中压的观察窗口各为 30 秒。用 `scripts/prepare_handoff_config.py` 写入当前 VM 的路径、屏幕尺寸和输入摘要。

[运行步骤](../../复现实验.md) · [场景时序](TIMED_CAPTURE.md)
