# 单轮最终验收

批次：`krita_manual_pilot_20261127_221114_305c963b`。run ID：`1eb123019f8643028b1c531460cc4048`。session：`20261127T141326Z-6180956c096644169237cdfddbc61dd5`。

代码：`bc8018ac6d2edb0bda077b23818b7247a2343c67`；配置 SHA256：`93861208bb21254774927359af03ee2f2d1cca23f70e9759104f8fd7326603bc`。本轮由用户在VM GNOME Terminal前台启动，collect只调用一次（rounds=1），失败后没有重试、没有改参数或代码、没有启动其他实验应用。

**终止分类：SAFETY_STOP。原验证器最终状态：PILOT_INVALID。valid=false，formal_eligible=false，curve_complete=false。** 不是用户ABORT，不是PASS；未因报告分类而修改原summary.json/metadata。

| 阶段 | 结果 | 证据边界 |
|---|---|---|
|A. 启动/身份/窗口与低压|PASS|原阶段1–4 PASS，低压浏览30.001286262秒；低压关闭后才进入人工等待|
|B. 人工导入等待|SAFETY_STOP|t=68.751387743秒开始，等待499.885617288秒后触发PSI安全停止|
|C. READY输入及机器核验|NOT_RUN / UNCONFIRMED|无HIGH_DOCUMENT_USER_READY，无response文件，无READY后的机器核验开始/结束事件|
|D. 高压12秒|NOT_RUN|没有HIGH_DOCUMENT_READY及CAPTURE_WINDOW_START/DONE|
|E. 第一实例正常退出/自然释放|FAIL / NOT_OBTAINED|原Ctrl+Q退出等待超时；随后停止精确unit，清理释放不能算自然释放|
|F. 第二实例/7层中压30秒|NOT_RUN|无KRITA_POST_PROCESS、TAIL_DOCUMENT_OPEN_DONE及中压浏览事件|
|G. 资源清理与封存|PASS|cleanup/cooldown/journal均true；40个成员SHA通过；无残留|
|H. 原验证器|PILOT_INVALID|valid=false，curve_complete=false；退出码1|


## 独立核对

| 项目 | 结果 |
|---|---|
| 固定commit/config SHA | PASS，与用户指定相同 |
| 低压/46层/7层素材 | PASS，输入SHA/结构及原CRC验收 |
| 真实前台TTY | PASS，/dev/pts/0，前台PGID与实际采集器一致 |
| 单次collect | PASS，一次性标记，collect_invocations=1，唯一run |
| READY接收与机器独立核验 | 未运行；无人工确认，未证实46层导入完成 |
| 12秒高压与30秒中压 | 未执行 |
| 采样连续性 | 已有窗口PASS，中位50.009090ms、最大107.355556ms，无>500ms缺口 |
| PSI安全条件 | FAIL，global Full持续超阈值，已正确停止 |
| cgroup Swap / OOM | 0 / 0；全机有少量换出，分开报告 |
| 正常退出自然释放 | 未取得；强制unit清理单列 |
| 原始SHA封存 | PASS，40/40成员原verify_seal通过 |
| cleanup/cooldown/journal | PASS |
| operations_verified | false |
| 残留进程/worker/unit/cgroup | 无；MainPID0、inactive/dead，原parent路径不存在 |
| 代码/main/参数保护 | PASS，未更改或推送mxt/main，未合并分支 |

collect退出码1、独立validate退出码1、自动化finished退出码2。用户前台启动脚本把原验证器结果保存为PILOT_INVALID；本报告补充终止原因分类SAFETY_STOP，不覆盖任何原记录。

| 原验证器错误（去重展示） | 次数 |
|---|---:|
| manual import evidence: manual confirmation missing/failed/duplicate/out of order | 1 |
| RuntimeError: sustained severe global memory PSI full | 1 |
| incomplete operation/cleanup/cooldown/journal evidence | 1 |
| sustained severe PSI | 384 |
| incomplete operation exits | 1 |
| FileNotFoundError: [Errno 2] No such file or directory: '/home/mxt/TeamOOM/data_collection/foreground_krita/krita_manual_pilot_20261127_221114_305c963b/20261127T141326Z-6180956c096644169237cdfddbc61dd5/1eb123019f8643028b1c531460cc4048/krita/krita-post-process.json' | 1 |


缺失post-process.json是因为中压实例未执行，不是已完成后记录被删。无READY导致确认事件不完整；所有原始失败证据留在VM。指标峰值仅属于部分记录窗口，不能转成完整实验曲线。

验收后停止，无自动重试、阈值调整或其他应用/并发实验。
