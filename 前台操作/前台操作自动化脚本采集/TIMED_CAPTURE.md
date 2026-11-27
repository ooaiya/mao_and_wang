# 9000×9000 低压 → 高压 → 中压

用 [采集模板](configs/collection.rapid-9000-medium-tail-extended.json) 生成当前 VM 的配置，再由 [collect_krita.py](scripts/collect_krita.py) 运行单轮独立采集。

1. 低压阶段打开单层 ORA，浏览 30 秒，每 5 秒执行一次往返缩放。
2. 高压阶段打开预组装的 46 层 ORA，文档确认打开后采样 12 秒。随后关闭文档，等待首个 Krita 实例退出。
3. 中压阶段由第二个 Krita 实例打开 7 层 ORA，浏览 30 秒，每 5 秒执行一次往返缩放。画布为 9000×9000，含五个全尺寸图层和两个 5400×5400 图层。

高压耗时包含导入、打开后的 12 秒观察，以及关闭和进程退出。以 `HIGH_DOCUMENT_SUBMITTED`、`HIGH_DOCUMENT_OPEN_DONE` 和 `HIGH_INSTANCE_EXIT` 区分这三个时间点。并发 T0 取第一个 Krita 实例的首页就绪事件，后台偏移相对于 T0。

中压验收要求浏览窗口内各前台采样点的 cgroup `memory.current` 落在 2–3 GiB，同时核对实例身份和素材摘要。独立采集超时配置为 1800 秒。

[运行步骤](../../复现实验.md)
