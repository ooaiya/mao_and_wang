# 后台工作负载

当前场景的栅格条带校正（`raster`）、内存列式表转换（`table`）和批量数组评分（`array`）均由 [shaped_workload.py](曲线任务/shaped_workload.py) 生成输入并执行。修改计算、批次或任务时序时从这个文件开始。每次运行写出 `phase_trace.jsonl` 和可复核的 `output.json`。

[measure_workload.py](曲线任务/measure_workload.py) 用 `--task` 选择单采任务，用 `--python` 指定工作负载环境，用 `--output` 指定新的结果目录。采集器在委派 cgroup 中记录总占用与匿名内存。工作负载写入的 `phase_trace.jsonl` 同时供策略读取，`grown:1` 表示首批分配结束，后续 `grown:N` 记录已完成批次。依赖版本见 [requirements.txt](requirements.txt)，运行与验收见 [复现实验](../复现实验.md)。
