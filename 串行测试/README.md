# 四任务串行测试

低–高–中 Krita、XZ、Table、Array 依次运行。等上一任务的 cgroup 确认清空后才启动下一项。运行器使用已验收的独立前台轮次及相同源码。基线和曲线分级策略读取通过复核的无 Swap 串行数据。

[复现实验](../复现实验.md) 给出 `run_serial.py` 的启动和 `review_serial.py` 的复核命令。 `start_serial_vm.py`、`status_serial.py`、`collect_serial.py` 为原宿主机的部署和归档工具。
