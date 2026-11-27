# Krita 46层人工导入机制改造交付

状态：**CODE_AND_OFFLINE_TESTS_COMPLETE / WAITING_FOR_REVIEW**。本次未启动Krita、未发起新正式采集、未运行并发实验；测试仅用私有PTY、模拟GUI/进程/内核文件和测试子进程。

本地代码分支mxt，基准`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`，新commit **`bc8018ac6d2edb0bda077b23818b7247a2343c67`**。工作区干净。main保持`b65b76724c440d9c48738dd063b9311245aad178`。本次按用户要求仅向mxt_codex发布Markdown交付，未推送mxt/main，未进行分支合并；代码提交仍在本地mxt，完整差异作为Markdown供审核。

## 修改清单与说明

[12个修改文件](changed_files.md)；[完整Git diff](git_diff.md)。源码与参数/事件的详细说明见[MANUAL_HIGH_IMPORT.md](MANUAL_HIGH_IMPORT.md)；[新配置内容](configuration.md)。

- krita_auto.py：只在manual_high_import模式替换46层打开；不发送自动Ctrl+O、路径或Enter。新增完整身份核验、窗口/AT-SPI证据、人工事件和READY失败停止。低压、中压、第一实例退出/第二实例及原清理逻辑保留。
- manual_import.py：前台真实stdin TTY和前台进程组检查、select/os.read独立输入线程、run/request绑定、输入时刻保留、错误/部分/旧输入处理、ABORT/EOF；等待时不阻塞50ms采样。
- cli.py/environment.py：非TTY和后台TTY在正式业务启动前拒绝。systemd worker不创建伪TTY、不伪造人工输入；由前台collector独立线程转交真实输入。
- engine.py：启动/停止终端桥；原安全检查与CSV写入之后，对核验请求发出parent/workload新样本安全应答。原enforce、OOM、PSI、Swap、内存、采样缺口和1800秒上限不删除、不改值。
- config.py/pilot_assets.py：增加布尔开关及契约capture_origin=manual_document_ready。新配置与上一轮实际部署配置只相差manual_high_import=true；原配置/素材/前三轮数据均未覆盖。
- validation.py：增加机器/人工/未验证/明确失败分类与原始证据交叉校验；保持原8阶段、正常退出、峰值/平台范围、封存及安全约束。人工确认不等于机器验证，计时结束不等于加载完成。
- tests/test_manual_import.py与说明文档：新增24项离线验证和新模式操作说明；不引入新依赖。

## 人工工作流程与时间线

原启动和低压30秒→关闭低压→终端提示人工导入46层→用户导入并目视检查→输入READY 46（此时只记录时间）→进程/窗口/层数与新安全样本核验→HIGH_DOCUMENT_READY→完整12秒→原第一实例退出、第二实例自动7层中压30秒及结束流程。任一步失败停止，不提前进入捕获或中压。

图层唯一且46时记录MACHINE_VERIFIED；不可读取层数时记录MACHINE_LAYER_CHECK_UNAVAILABLE及USER_CONFIRMED；标题不匹配保留实际标题、false匹配状态并标人工确认；任何已知非46层、错误身份/窗口、残留对话框或安全触发都不能人工覆盖。

新事件：HIGH_DOCUMENT_MANUAL_IMPORT_START、HIGH_DOCUMENT_USER_READY、HIGH_DOCUMENT_MACHINE_VERIFY_START、HIGH_DOCUMENT_MACHINE_VERIFY、HIGH_DOCUMENT_READY、HIGH_DOCUMENT_READY_FAILED。共同字段和全部原始证据路径见源码说明。READY输入时刻、核验开始/结束、高压起止分别使用实际monotonic_ns和wall_time_ns记录；正式起点为HIGH_DOCUMENT_READY，CAPTURE_WINDOW_DONE不得早于该点+12秒。不是从用户开始导入或输入READY时回算12秒。

## 验证结果

| 验证 | 最终结果 |
|---|---|
| 静态AST/compile与Git diff检查 | PASS |
| 新增人工机制离线用例 | 24/24 PASS，包含于专项完整回归 |
| 原专项回归 | 114/114 PASS |
| 专项完整回归 | 138/138 PASS |
| 仓库原有测试 | 52/52 PASS |
| 真实前台PTY子进程输入转交 | PASS，无TTY前台检查mock；PTY只由测试创建 |
| 等待输入时50ms fake-kernel采样 | PASS，12个实际时间点，无500ms以上缺口 |
| 200秒人工等待/1800秒总上限 | PASS（虚拟时钟）；160配置未变 |
| 核验后完整12秒及错误起点拒绝 | PASS（虚拟时钟） |
| AT-SPI不可用/错误层数/错误PID/模态/多窗口 | PASS |
| 第二、三轮原失败数据复核 | 仍为PILOT_INVALID，原封存通过 |
| 新真实GUI采集 | NOT_RUN，等待用户审核 |

专项首次在开发中的dirty工作树及沙箱只读/run前置条件失败；保留了原断言及生产锁，提交后设置测试私有XDG_RUNTIME_DIR重新运行138项，全部通过，没有修改验证器消除这些失败。完整日志、命令JSON和历史失败复核JSON均留在VM原交付目录；GitHub仅提供[离线测试汇总](tests_summary.md)，不上传原始日志或JSON。测试未模拟为真实Krita导入成功。

## 参数与历史保护

46层9000×9000、SHA256 `100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a`、124404893字节、tile67%、高压12秒、低压30秒、中压30秒、原7层素材、50ms/500ms、所有原安全阈值保持不变。原配置SHA256仍`ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d`。旧自动模式、原退出守卫及清理逻辑保留；没有实施上一轮退出故障的其他重构。

本目录交付为Markdown报告、交互说明、配置展示及完整diff；实际代码提交仍在本地mxt；没有新增实际run ID，没有上传任何采样/图片/素材，没有覆盖历史证据。任务停止于本地提交和离线测试完成，待用户审核后才能进行下一轮正式采集。
