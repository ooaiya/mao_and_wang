# 第三轮阶段与完整性验收

实验批次：`krita_single_round3_20261127_190942_e44a5be1`。唯一 run ID：`a2f75d1e2f2f4163850e7f0baa56433a`。

代码：`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`（mxt，前后工作区均干净）；配置 SHA256：`ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d`。

本轮仅执行一次原采集器 collect（--operation krita --rounds 1）；未重构代码、未修改实验配置/素材、未启动其他应用、未自动重试。GitHub仅上传本批次Markdown，原始数据、JSON、日志和PNG全部留VM。

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


## 数据与运行有效性分开验收

| 项目 | 状态 | 实际含义 |
|---|---|---|
| 原环境preflight | PASS | ok=true，未放宽约束 |
| 代码/配置/素材一致 | PASS | commit、配置字节及素材SHA一致 |
| 只执行一次 | PASS | 一个collect调用标记、一个session、一个run；无自动重试 |
| Krita RSS记录窗口 | PASS（局部） | 4,884个workload样本，结束于异常前；无完整高压/中压 |
| current/peak及anon/file | PASS（局部） | 原CSV与终态内核证据保留；不是完整业务曲线 |
| MemAvailable与PSI | PASS（局部） | 记录期完整环境监测；不混作应用独立内存 |
| 实际50ms间隔 | PASS | 中位50.001237ms，最大63.126450ms，原0.5s缺口上限未触发 |
| Swap/OOM/PSI增量 | PASS | task swap0、pswpin/out0、OOM0、global Full/Some total增量0 |
| 原始成员SHA256 | PASS | 原verify_seal及逐成员检查37/37 |
| 46层真实就绪证据 | FAIL/未取得 | 没有HIGH_DOCUMENT_OPEN_DONE、46层界面就绪/进度证据 |
| 全部预定阶段 | FAIL | 停于阶段5 |
| 原validate | FAIL | PILOT_INVALID，curve_complete=false |
| 系统清理与无残留 | PASS | 原unit精确停止，worker/unit/cgroup残留为0 |

原自动化用文件名窗口标题作为打开判据，并不直接验46层界面状态。本轮没有修改该逻辑；标题判据也未通过，故不能宣称目标已真实加载完成。低压PASS同样限定为原程序所核对的条件，不额外扩张成未采集的层状态证明。

全部原始文件保留，业务未生成的krita-post-process.json/remaining-processes.json不伪造；封存完整和业务完整是不同检查。
