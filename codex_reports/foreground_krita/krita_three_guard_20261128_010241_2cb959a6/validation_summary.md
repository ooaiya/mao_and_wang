# 验收与原验证器结论

批次 `krita_three_guard_20261128_010241_2cb959a6`，run ID `717be1060cc54a55ae1c93d0dee082f8`。代码 `715afeaf0644d35da3cb207ab211dbaa85f75b6a`，配置 SHA256 `c6b19c657518b3ca754f7dd4474e973c878bc590183d60fb37fa89c7bd88b6f5`。

终止归类 **SAFETY_STOP**。原验证器 **PILOT_INVALID**，valid=`False`，curve_complete=`False`。封存核验 PASS，41 个成员。

曲线数据有效 `False`，操作完整 `False`，清理 `True`，环境恢复 `True`，检出 OOM `False`，验收综合状态 `PILOT_INVALID`。目标压力形态另保留在验证结果的 `pressure_profile`。

完成高压 12 秒 **否**，完成 7 层中压 30 秒 **否**。第一实例正常退出事件 未取得，第二实例身份事件 未取得。

READY 后有效确认等级 `未取得`。机器层数 `未取得`。

启动预检 ok=`True`，退出码 `0`。collect 与 validate 退出码分别为 `1`、`1`。清理 `True`，冷却 `True`。宿主复查 `无采集进程、Krita、worker、unit 或 cgroup 残留`。

| 原验证器错误 | 次数 |
| --- | --- |
| manual import evidence: manual confirmation missing/failed/duplicate/out of order | 1 |
| RuntimeError: 50ms sampler gap exceeded safety bound | 1 |
| incomplete operation/cleanup/cooldown/journal evidence | 1 |
| sampling gap exceeds explicit threshold | 2 |
| incomplete operation exits | 1 |
| FileNotFoundError: [Errno 2] No such file or directory: '/home/mxt/TeamOOM/data_collection/foreground_krita/krita_three_guard_20261128_010241_2cb959a6/20261127T170333Z-de94fa0bafad46c7b8fa033071cd036c/717be1060cc54a55ae1c93d0dee082f8/krita/krita-post-process.json' | 1 |
