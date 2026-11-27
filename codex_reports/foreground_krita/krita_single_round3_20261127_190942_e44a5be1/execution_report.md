# Krita 单应用第三轮验证报告

**最终状态：PILOT_INVALID。** 相同代码、相同配置的一次重新采集再次在46层文档加载确认处超时，未完成整套流程。按要求停止，未重试。

实验批次：`krita_single_round3_20261127_190942_e44a5be1`。唯一 run ID：`a2f75d1e2f2f4163850e7f0baa56433a`。

代码：`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`（mxt，前后工作区均干净）；配置 SHA256：`ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d`。

本轮仅执行一次原采集器 collect（--operation krita --rounds 1）；未重构代码、未修改实验配置/素材、未启动其他应用、未自动重试。GitHub仅上传本批次Markdown，原始数据、JSON、日志和PNG全部留VM。

## 代码、配置与预检

当前分支mxt；HEAD与origin/mxt均为 `6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`；origin/main仍为 `b65b76724c440d9c48738dd063b9311245aad178`。本轮不切分支、不合并main与mxt、不产生代码提交。报告通过独立检出发布mxt_codex，原repo保持不变。

原配置直接复用 `/home/mxt/TeamOOM/runtime/config/krita_single_20261127_182751/foreground_config.json`，与上一轮run/config.snapshot.json逐字节相等，SHA256如上；本轮没有生成替代实验配置。配置为Krita5.0.2、50ms、46层9000×9000 ORA、tile67%、高压12秒、低压30秒、原7层文档中压30秒、每5秒缩放、open_timeout160秒。所有安全条件均保留，详 [reproduction.md](reproduction.md)。原7层素材本来就含5层9000×9000和2层5400×5400，本轮未改动。

正式预检返回0，ok=true、errors=[]；MemAvailable=14.140423GiB，SwapFree=1.999996GiB，根分区可用30.079838GiB；1秒整机CPU忙碌率约1.015%。PSI Full/Some avg10均0。旧UUID unit inactive、MainPID0，旧cgroup不存在；无Krita/其他实验应用/采集器/worker/全机监控残留，原measurement_lock可取得。未终止GNOME、Codex或其他系统进程。

素材5个既有路径逐一重新检查大小、SHA256和ORA结构，与前轮完整PNG解码验收对应同一字节；原preflight另外完成ZIP CRC检查。46层ORA为124,404,893字节、SHA256=`100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a`。

## 唯一执行与阶段验收

原始目录：`/home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_round3_20261127_190942_e44a5be1/20261127T111105Z-7e7dc22e865e41c6a432e07565e2100a/a2f75d1e2f2f4163850e7f0baa56433a`。

采集只调用一次，rounds=1；本地独占创建collect_invocation_marker.json阻止再次调用。原程序内部重复preflight为原有检查，不是第二次实验。调用日志、环境及时间戳仅留VM。

| 用户步骤 | 状态 | 证据与边界 |
|---|---|---|
| 1. 启动 Krita | PASS | KRITA_PROCESS t=13.664162121s，PID=16671 |
| 2. 应用身份和窗口归属 | PASS | PPID=16669，birth=817373，/usr/bin/krita；xcb、窗口PID/归属核验 |
| 3. 打开低压文档 | PASS | DOCUMENT_OPEN_DONE t=40.081618387s（原标题确认） |
| 4. 低压浏览 | PASS | 30.002240766s，原定30秒 |
| 5. 关闭低压文档 | PASS | close_document返回后才发出HIGH_DOCUMENT_OPEN_START；依原关闭判据 |
| 6. 提交46层ORA | PASS | HIGH_DOCUMENT_SUBMITTED t=73.770084656s |
| 7. 46层加载完成确认 | FAIL | 160.258118886s后确认超时；无HIGH_DOCUMENT_OPEN_DONE |
| 8. 高压12秒 | NOT_RUN | 没有CAPTURE窗口开始/结束事件 |
| 9. 第一实例正常退出 | FAIL | graceful_shutdown等待应用退出超时；随后由采集器停止精确unit |
| 10. 正常退出后自然释放 | NOT_VERIFIED | 异常中止/服务清理释放不能当作正常业务自然释放 |
| 11. 启动第二实例 | NOT_RUN | 没有KRITA_POST_PROCESS或krita-post-process.json |
| 12. 打开7层文档 | NOT_RUN | 没有进入后续阶段 |
| 13. 中压30秒 | NOT_RUN | 没有进入后续阶段 |
| 14. 全部正常结束 | FAIL | collect退出码1，自动化退出码1 |
| 15. 原完整性验证器 | FAIL | validate退出码1，PILOT_INVALID，curve_complete=false |


原自动化阶段1–4 PASS，第5阶段FAILED，阶段6–8未开始。完整单调时钟事件见 [phase_timeline.md](phase_timeline.md)；逐项验收见 [stage_acceptance.md](stage_acceptance.md)。

## 关键内存数据（均为被中止窗口的局部记录）

| 指标 | 本轮实际记录 |
|---|---:|
| Krita VmRSS采样峰 | 8.414474 GiB |
| Krita VmHWM最大 | 8.414474 GiB |
| workload memory.current采样峰 | 8.337151 GiB |
| 内核memory.peak终态 | 8.337639 GiB |
| anon采样峰 | 8.240261 GiB |
| file采样峰 | 0.075817 GiB |
| current峰时间 | 244.220013436 s |
| workload样本数 | 4884 |
| 采样间隔中位 | 50.001237 ms |
| 采样间隔最大 | 63.126450 ms |
| >500ms间隔 | 0 |
| cgroup Swap最大 | 0 B |
| OOM/oom_kill增量 | 0 / 0 |
| 整机PSI Full/Some avg10最大 | 0 / 0 |
| 整机PSI Full/Some total增量 | 0 / 0 |
| 整机pswpin/pswpout增量 | 0 / 0 |
| 最小整机MemAvailable | 5.763241 GiB |


memory.current口径是独立workload cgroup，包含Krita、原自动化、supervisor及派生helper；进程RSS单独统计。file/anon分量峰未必同时，不相加成总峰。整机MemAvailable/PSI仅用于环境监测。RSS高于cgroup charge也不表示口径错误，进程映射与cgroup计费不能互相替代。

本轮曲线在中止点前持续增长，不能当作完整高压峰值或合格历史曲线。原始T90=223.799161148s，T95=234.310089277s；局部峰95%以上累计9.909924159s，只描述此次截断数据，不能称为已完成高位平台。没有正常业务结束后的自然释放证据。

## 验证、故障与清理

原collect退出1，独立原validate退出1；valid=false、formal_eligible=false、curve_complete=false。原验证器报告：

- RuntimeError: Krita process identity changed
- incomplete operation/cleanup/cooldown/journal evidence
- incomplete operation exits
- FileNotFoundError: [Errno 2] No such file or directory: '/home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_round3_20261127_190942_e44a5be1/20261127T111105Z-7e7dc22e865e41c6a432e07565e2100a/a2f75d1e2f2f4163850e7f0baa56433a/krita/krita-post-process.json'

主故障仍为 `TimeoutError('素材加载超时；最后诊断=None')`。提交至失败 160.258118886s，保留160秒配置。文档是否实际导入完成仍缺直接证据；本轮不把RSS/CPU或文件对话框消失当完成证明。

随后优雅退出等待约9.852289秒超时，自动化返回1；worker写finished后，采集器metrics.process_sample抛英文身份比较错误。失败实际三元组没有记录，无法确定是PPID/starttime/exe哪项变化；不能断言PID重用。细节见 [failure_analysis.md](failure_analysis.md)。

原封存verify_seal通过，共37个成员；前轮run封存也复核通过。SHA封存PASS仅代表已有文件一致，不把缺失的后续业务阶段洗为通过。本次没有删除前两轮或本轮证据。

metadata：cleanup_ok=True、cooldown_ok=True、journal_ok=True、operations_verified=False。服务停止及冷却成功；这与业务失败不冲突。原采集器完成本UUID unit/hold/slice清理后，只读复查无实验进程/worker/unit残留，新run的parent cgroup已不存在；没有执行额外kill/stop。

## VM曲线与本地交付

本批次结果目录：`/home/mxt/TeamOOM/results/foreground_krita/krita_single_round3_20261127_190942_e44a5be1`。

| 文件 | 说明 |
|---|---|
| krita_rss.png | Krita VmRSS/VmHWM，缺失值保留缺口 |
| krita_cgroup.png | 独立workload current/peak，截断到失败窗口 |
| anon_file.png | anon/file分解 |
| mem_available.png | 整机可用内存环境曲线 |
| global_psi.png | 整机PSI Full/Some环境曲线 |

五图均使用原采样时间，标记PILOT_INVALID，不插值、不补零、不补造自然下降。CSV、全部原日志、metadata、manifest.sha256、samples、进程/cgroup观测、原验证输出保存在VM；派生metrics.json和seal_verification.json也仅留VM。新批次不覆盖上一轮诊断。

## 对比与下一步

[comparison_previous.md](comparison_previous.md)显示两轮相同代码和配置都在相同确认点失败；本轮没有验证出“原代码可正常完成整套采集”。部分峰值不同不是代码优化或成功加载的证据。没有已证实的OOM、Swap或PSI故障。

建议按[上一轮只读诊断修复方案](https://github.com/ooaiya/mao_and_wang/blob/mxt_codex/codex_reports/foreground_krita/diagnosis_20261127/next_fix_plan.md)先评审观测和退出生命周期，再另行授权修改/验证；本轮未实施这些方案，不直接延长超时、不放宽守卫。已停止实验，等待审核。
