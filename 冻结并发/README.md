# 冻结并发

当前四任务场景用 [raster_priority.py](raster_priority.py) 运行，传入 `--shaped-run`、`--offsets`、`--foreground-run` 和 `--foreground-source`。分批后台在原偏移开跑，完成首批后可以冻结。三个后台的时序参数和输出校验摘要来自同一批独立采样。启动和复核命令见 [复现实验](../复现实验.md)。

## 查表预测器

[shaped_scene.py](shaped_scene.py) 用独立采样生成半秒分箱上界，保存总占用曲线、匿名内存曲线和阶段标记。每轮现场决策从最新的任务阶段和内存采样开始。

- **Krita**。从最近确认的历史阶段向后查询剩余总占用峰值和匿名内存峰值。两个峰值分别减去现场对应占用，取较大的非负增量作为预留，覆盖整个后台窗口。确认高压实例退出后，按中压尾段的剩余峰值重算。
- **运行中的后台**。从当前阶段内按有效执行时间查候选起点，并用现场匿名内存校对。每个候选分别算总占用增长和匿名增长，取较大的非负值。匿名增长以候选起点匿名量与现场匿名量中的较小值为基准。匹配不到用量时保留阶段候选的上包络。冻结期间有效执行时间暂停。
- **计划启动的后台**。如果启动偏移落在 2.5 秒窗口内，从计划时刻开始计入历史启动曲线的绝对占用。

查表在 [memory_prediction.py](memory_prediction.py) 中实现。可用满足 `MemoryPredictor` 接口的实现替换短窗口预测，并在 `audit_decisions(..., predictor=...)` 中注入同一实现重放。计算所需预测缺失时，策略会在决策日志中记录。

## 冻结与解冻试算

联合余量等于现场 `MemAvailable`，减去 Krita 的剩余峰值预留，再减去同一未来时点各后台预计新增的占用。

| 动作 | 条件与处理 |
| --- | --- |
| 冻结 | 2.5 秒内预计最低余量低于 **500 MiB** 时，先试最少冻结任务数，再按低优先级先试的顺序比较可选执行次序。某任务确认前沿原预测增长，确认后保留确认前的最大增量。若所有方案都越线，仅采用能提高最低余量且不会提前首次越线的方案。 |
| 解冻 | 从暂停位置将待恢复任务的增长加回预测，预计最低余量须严格高于 **756 MiB** 并连续达标 **0.5 秒**。本轮有冻结请求时暂停解冻。多个候选达标时，每轮解冻优先级最高的一项。 |

[segmented_runner.py](segmented_runner.py) 同步采样、决策和执行。常规决策间隔为 **0.2 秒**。一轮有冻融动作时，执行器按顺序等待内核确认并更新状态，然后主循环再进入下一轮。冻结试算按每次动作 **0.7 秒**计入确认前的增长，来源是 0.2 秒检查间隔加 0.5 秒内核确认超时。确认等待较长时，下一轮采样及同一循环中的启动检查会顺延。用日志核对计划和实际开跑。

`priority_decisions.jsonl` 保存 `foreground_peak_growth_bytes`、风险时点、候选及冻融试算结果。`freeze_events.json` 保存请求和确认的单调时钟时间戳。500 MiB 是预测决策门槛，实测余量以 `system_memory.csv` 为准。

## 历史场景和对照入口

| 场景 | 入口 |
| --- | --- |
| 当前分批场景无干预并发 | [raster_baseline.py](raster_baseline.py)，读取同一独立采样、前台与偏移。 |
| 当前分批场景串行 | [run_serial.py](../串行测试/run_serial.py) 配合 `--shaped-run`、前台参照和 `--no-swap`。 |
| 历史 XZ 曲线分级 | [segmented_runner.py](segmented_runner.py) 配合 `--serial-policy priority` 和无 Swap 串行参照。 |
| 历史栅格 FFT 曲线分级 | [raster_priority.py](raster_priority.py) 配合 `--raster-run`。串行参照用 `--serial-run` 和 `--raster-alignment`，四项独立参照用 `--independent-run` 导出峰值偏移。 |
| 历史离线续跑 | `segmented_runner.py --serial-policy offline --planner <程序路径>`。参见 [离线规划器](离线规划器/README.md)。 |

新分级计划默认启用 `priority.freeze_prediction.reserve_foreground_peak`。关闭该开关会同时切换前台预测方式和当前执行器的首批冻结候选门槛。回放历史结果时使用各轮归档的计划及规则。
