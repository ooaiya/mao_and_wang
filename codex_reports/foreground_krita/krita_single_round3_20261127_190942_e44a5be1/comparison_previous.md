# 与上一轮失败实验对比

实验批次：`krita_single_round3_20261127_190942_e44a5be1`。唯一 run ID：`a2f75d1e2f2f4163850e7f0baa56433a`。

代码：`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`（mxt，前后工作区均干净）；配置 SHA256：`ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d`。

本轮仅执行一次原采集器 collect（--operation krita --rounds 1）；未重构代码、未修改实验配置/素材、未启动其他应用、未自动重试。GitHub仅上传本批次Markdown，原始数据、JSON、日志和PNG全部留VM。

上一轮：`krita_single_20261127_182751 / 19e3a414871c4c2fbda72b20c3468523`。

本轮：`krita_single_round3_20261127_190942_e44a5be1 / a2f75d1e2f2f4163850e7f0baa56433a`。

| 项目 | 上一轮 | 本轮第三轮 |
|---|---|---|
| 代码commit | 6ce22767fdd91ea23d1e4fab0f071a19c44ea92a | 6ce22767fdd91ea23d1e4fab0f071a19c44ea92a |
| 配置SHA256 | ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d | ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d |
| 状态 | PILOT_INVALID | PILOT_INVALID |
| 失败点 | 阶段5：46层加载确认超时 | 阶段5：46层加载确认超时 |
| 退出交界错误 | Krita process identity changed | Krita process identity changed |
| 低压浏览 | 30.000737970s | 30.002240766s |
| 提交至确认失败 | 160.166517341s | 160.258118886s |
| 高压12秒/中压30秒 | 均未执行 | 均未执行 |
| 样本数 | 4743 | 4884 |
| RSS局部峰GiB | 9.586510 | 8.414474 |
| current局部峰GiB | 9.626057 | 8.337151 |
| kernel peak GiB | 9.626545 | 8.337639 |
| anon局部峰GiB | 9.411190 | 8.240261 |
| file局部峰GiB | 0.187656 | 0.075817 |
| 间隔中位ms | 50.002215 | 50.001237 |
| 间隔最大ms | 82.889146 | 63.126450 |
| >500ms缺口 | 0 | 0 |
| Swap/OOM/PSI增量 | 均0 | 均0 |
| 正常业务自然释放 | 未验证 | 未验证 |
| 原始封存 | 37成员PASS | 37成员PASS |
| 清理与无残留 | PASS | PASS |

两轮均为原代码、原参数、同一素材，分别只有一次采集；本轮再次复现相同加载确认超时与退出交界身份异常，**未验证出原代码能完成整套流程**。这支持问题仍可复现，不能证明所有环境下均必然失败，也不能把加载确认失败直接等同于解码故障。

部分峰值不同只说明两个被中止记录窗口的实测资源不同，不表示优化成功、素材改变、完整负载需求下降或某一轮已加载完成。RSS与cgroup计费口径分开；不能从file较低直接认定缓存机制已被修复。没有更改缓存、增加sleep、强制GC或调节实验参数。

两轮都没有高压12秒、中压30秒和正常退出自然释放，不能作为正式历史曲线或用于正式并发时间线。后续建议仍是先审查[上轮诊断](https://github.com/ooaiya/mao_and_wang/tree/mxt_codex/codex_reports/foreground_krita/diagnosis_20261127)中的观测与最小修复方案；本轮不实施、不重试。
