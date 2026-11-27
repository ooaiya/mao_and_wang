# 验收与原验证器结论

批次 `krita_psi_observe_20261128_001508_7d4ec673`，run ID `f04ca1afb5da4fffac37c7e1d3c0d292`。代码 `4fbc49555484055bf78f2b6d437b6a04c791dd9f`，配置 SHA256 `8d487b076463470474d3c102dcc269e255b81fc74038faf2d7dd6bba795c6cd0`。

终止归类 **PILOT_INVALID**。原验证器 **PILOT_INVALID**，valid=`False`，curve_complete=`False`。封存核验 PASS，41 个成员。

完成高压 12 秒 **否**，完成 7 层中压 30 秒 **否**。第一实例正常退出事件 未取得，第二实例身份事件 未取得。

READY 后有效确认等级 `未取得`。机器层数 `未取得`。

启动预检 ok=`True`，退出码 `0`。collect 与 validate 退出码分别为 `1`、`1`。清理 `True`，冷却 `True`。宿主复查 `无采集器、worker、Krita、实验 unit 或 cgroup 残留`。

| 原验证器错误 | 次数 |
| --- | --- |
| manual import evidence: manual confirmation missing/failed/duplicate/out of order | 1 |
| RuntimeError: Krita process identity changed | 1 |
| incomplete operation/cleanup/cooldown/journal evidence | 1 |
| sustained severe PSI | 438 |
| incomplete operation exits | 1 |
| FileNotFoundError: [Errno 2] No such file or directory: '/home/mxt/TeamOOM/data_collection/foreground_krita/krita_psi_observe_20261128_001508_7d4ec673/20261127T161722Z-7ddf66c2b53441d9b9995bda22999c5c/f04ca1afb5da4fffac37c7e1d3c0d292/krita/krita-post-process.json' | 1 |
