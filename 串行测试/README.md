# 四任务串行测试

当前串行对照用 `run_serial.py --shaped-run <批次目录> --no-swap`，依次运行低–高–中 Krita、栅格条带校正、内存列式表转换和批量数组评分。上一任务的 cgroup 确认清空后才启动下一项。运行器使用已验收的独立前台轮次、同一份源码和三个后台的独立采样。

[复现实验](../复现实验.md) 给出 `run_serial.py` 的启动和 `review_serial.py` 的复核命令。 `start_serial_vm.py`、`status_serial.py`、`collect_serial.py` 为原宿主机的部署和归档工具。

历史 XZ、CSV Table 和原 Array 场景可由同一入口运行。其无 Swap 串行曲线还供历史 XZ 和栅格 FFT 基线及曲线分级模式读取。
