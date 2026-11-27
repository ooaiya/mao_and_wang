# 四任务串行测试

[run_serial.py](run_serial.py) 接收 `--foreground-run`、`--foreground-source`、`--shaped-run` 和 `--output`。复现实验使用 `--no-swap`。按 Krita、栅格条带校正、列式表转换、数组评分的顺序运行，在上一项 cgroup 清空后才开始下一项。

结束后将结果目录传给 [review_serial.py](review_serial.py)，检查实际交接时间、任务输出和最低可用内存，生成 `validation.json`、`report.md`、`serial_memory.png` 和 `serial_tasks.png`。已配置原 VM 的宿主机可用 [启动](start_serial_vm.py)、[查状态](status_serial.py) 和 [取结果](collect_serial.py) 三个辅助脚本。[运行命令](../复现实验.md)
