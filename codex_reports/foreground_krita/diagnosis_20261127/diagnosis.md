# Krita PILOT_INVALID 第二轮只读诊断

实验批次：`krita_single_20261127_182751`

run：`20261127T103129Z-95a8a57da8714bf5bfd0bf2ac24be523/19e3a414871c4c2fbda72b20c3468523`

源码基准：`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`；诊断日期：2026-11-27（Asia/Shanghai）。

本次仅只读分析旧记录；未启动 Krita、未重采、未改代码或配置、未执行清理。原始 run 保留。文中“已证实”表示原始证据或固定提交控制流直接支持；“推断”不替代实测；UNKNOWN 表示未记录，不能追溯补造。

## 结论与证据边界

**加载状态选择 D：现有证据不足，无法判定 46 层 ORA 是否加载完成。** 已证实的是在 160 秒标题确认窗口内 `document_named()` 未返回成功，随后自动化失败。不能据此认定 ORA 损坏、导入失败、GUI 死锁或文档已就绪。

持续内存增长、CPU 计数递增及多次 R 状态，支持“仍在进行耗时工作、可能仍在导入”的推断；缺少导入进度、目标文档就绪状态及 46 层界面验收，不能提升为 B 的直接证据。没有加载完成直接证据，不能选 A；没有 GUI 无响应或崩溃的直接证据，不能选 C。窗口标题历史未落盘，无法恢复实际失败标题。

英文 `RuntimeError: Krita process identity changed` 来自**采集器 `metrics.process_sample()`**，并非自动化 `owned()` 的中文身份异常。该处比较 starttime、PPID 和完整 executable 路径，原记录没有保存失败时的实际三元组，**具体变化字段 UNKNOWN，禁止断言 PID 重用**。父自动化退出而 Krita 尚在同一 cgroup 的事实，使 PPID 重新托管成为最有证据支持的解释，但仍须保留为推断。

## A. 主故障：加载确认超时

1. 初始应用 PID 11956，主窗口 `0x01400019`，启动记录标题 `Krita`，Qt xcb 已验证。
2. 低压文档打开确认通过，低压浏览 30.000738 秒完成；第 5 阶段关闭低压文档后提交 46 层文件。
3. `HIGH_DOCUMENT_OPEN_START` 为 t=64.427471887 s；`HIGH_DOCUMENT_SUBMITTED` 为 t=66.726307588 s。提交路径为现有 `layered_9000_46.ora`，没有生成新素材。
4. traceback 位于 `open_document()` 第 268 行，说明前面的指定文件对话框等待及原对话框消失检查已经返回；不等于所有潜在模态窗口都已排除，也不证明文件已解码完成。
5. t=226.892824929 s 抛出 `TimeoutError('素材加载超时；最后诊断=None')`，提交至失败约 160.166517 秒。没有 `HIGH_DOCUMENT_OPEN_DONE`，因此没有合法进入高压 12 秒捕获或后续中压阶段。

`wait_until()` 仅在捕获 `GuiPending` 或 `subprocess.TimeoutExpired` 时更新 last；探针普通返回 False 不记录原因。所以 None 说明此次等待没有留下这两类被捕获异常，不说明没有窗口、没有进度、加载成功或 Krita 响应正常。`wmctrl` 的查询能够返回，也只证明外部窗口查询未以这种超时报错，不能代替 Krita 事件循环响应测试。[源码：wait_until](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/scripts/krita_auto.py#L96)、[open_document](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/scripts/krita_auto.py#L258)。

当前完成谓词只验证窗口 PID 和标题文件名 stem。它混用了“标题识别成功”和“文档加载完成”，既可能漏掉实际已开的文档，也缺少成功时对 46 层就绪的独立证明。具体误判原因尚不能确定；详见 [加载时间线与标题分析](loading_timeline.md)。

## B. 次生故障：退出路径中的身份异常

可核实的控制链为：标题超时 → 自动化异常处理调用 graceful_shutdown → Ctrl+Q 后等待 Krita 退出超时 → 自动化返回 1 → worker 等到自动化退出并写 finished.json → 采集器的下一次进程采样因身份比较不符中止 → cooperative_stop → 保存终态 → 停止已验证所有权的 systemd unit。

这条关系同时由源码分支与日志事件支持，超越“两个错误时间相近”的判断。**身份异常发生于自动化失败后的采样/清理交界，属于首故障所进入的退出路径上的次生故障；具体字段及变化机制仍 UNKNOWN。** 不将其归为已证实的 systemd stop 引起，因为 systemd 停止日志更晚。

尤其注意：第 268 行失败时 `document_open=True` 尚未赋值；graceful_shutdown 因此跳过 close_document，直接尝试退出应用。 t=236.914015907 s 出现约 9.834429 秒 Popen.wait 超时；t=237.233679205 s worker 记录自动化退出 1；t=237.249096882 s 采集器发出身份错误 stop-request，距 worker 完成约 15.418 ms。该 finished 退出码属于自动化，不是 Krita 退出码。[自动化退出路径](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/scripts/krita_auto.py#L319)、[worker](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/oomlab_krita_collect/worker.py#L53)、[身份采样](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/oomlab_krita_collect/metrics.py#L92)。逐字段对照见 [identity_comparison.md](identity_comparison.md)。

## C. 数据影响与五类曲线

| 阶段 | 证据与可用边界 |
|---|---|
| 启动、布局、低压文档确认 | 阶段 1–3 PASS；文档确认仍是现有标题机制，不追加“界面层数已测”的结论 |
| 低压浏览 | 阶段 4 PASS；30 秒活动段可用于此次失败运行的局部诊断，不能替代完整合格轮次 |
| 高压打开 | 阶段 5 FAILED；记录了提交后的资源增长及异常退出等待 |
| 高压 12 秒 | 未执行；没有打开确认成功与 capture 事件 |
| 首实例正常关闭、自然释放 | 未完成；后续 unit 清理下降不能标成正常业务自然释放 |
| 7 层中压 30 秒及后续退出 | 未执行；无第二 Krita 实例/`krita-post-process.json` |

| 已有 VM 曲线 | 能说明什么 | 不能说明什么 |
|---|---|---|
| krita_rss.png | 绑定 PID 的 VmRSS/VmHWM 局部变化 | 不能证明完整加载、完整高压峰值或正常退出 |
| krita_cgroup.png | 独立 workload 的 current/peak；包含自动化、supervisor、派生 helper | 不等于纯 Krita RSS，也不等于整机内存 |
| anon_file.png | workload 的匿名内存和文件页组成，增长主要来自 anon | 不能从 file 小推断导入已完成；分量峰不能直接相加 |
| mem_available.png | 整机余量及环境安全背景 | 不能当作 QGIS/Krita 独立内存曲线 |
| global_psi.png | 记录期整机 PSI Full/Some 无增量、avg10 为 0 | 不能证明 GUI 没有逻辑阻塞或导入一定成功 |

Krita 样本 4,743；间隔中位 50.002215 ms，最大 82.889146 ms，没有超过 500 ms 的间隔。记录期 RSS 峰 9.586510 GiB、cgroup current 采样峰 9.626057 GiB、内核 peak 9.626545 GiB、anon 峰 9.411190 GiB、file 峰 0.187656 GiB；这些全部是**被中止记录窗口中的局部峰值**。原 T90=217.774829 s、95%阈值以上累计 9.700029 s 也只能相对局部峰解释，不是已完成高压阶段的平台。

PSI Full/Some 累计增量与记录的 avg10 最大值均为 0，workload Swap=0，OOM/oom_kill 增量=0；本轮没有已证实的 PSI 或 OOM 失败。读到的最小整机 MemAvailable 为 4,931,690,496 字节，口径单列。

## 清理、封存与当前状态

worker 已写入 finished.json（returncode=1，error=null）；error=null 仅表示 worker 包装层没有抛出异常。metadata 记录 cooperative_worker_completed=true、cleanup_ok=true、cooldown_ok=true、operations_verified=false、success=false。finished 文件存在不代表业务成功。

采集器在 sample_rows 抛错后，未抵达正常完成汇总，因此 metadata 缺少 finishes，remaining-processes.json 未生成。原校验器因不完整流程、身份错误和缺失 post-process 仍判 **PILOT_INVALID / curve_complete=false**。这与 cleanup_ok=true 不冲突：清理成功不能补齐未执行的业务阶段。

cleanup.json 记录 Krita unit、hold unit、UUID slice 均清理成功；journal 记录停止服务，不能据其未逐项显示 Krita 信号而编造具体退出信号。2026-11-27 18:49:40 +0800 再次只读检查：相关应用/采集器/全机监控残留为 0；旧 unit inactive/dead、MainPID=0、ControlGroup 为空；旧 slice cgroup 不存在。没有重新执行 stop/kill。

原 run 的 37 个封存成员 SHA256 全部通过，成员集合齐全；诊断前后复核保持不变。完整封存不等于完整业务曲线。原始窗口输出、失败实际身份元组等证据从未记录，属于采集可观测性缺口，不能靠重新读现存日志补回。[证据清单](evidence_inventory.md)列出每项边界。

## 下一步

先补全窗口/导入状态和身份差值的观测，再按有界状态机修复确认与退出交界，保持全部安全守卫。详见 [next_fix_plan.md](next_fix_plan.md)。本次只交付方案，不实施、不重试，等待用户审核。
