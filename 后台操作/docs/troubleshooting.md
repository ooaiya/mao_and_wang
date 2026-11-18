# 后台操作独立采集排障

## 环境预检失败

- 检查 Ubuntu 版本、内核、systemd PID 1、cgroup v2 及 memory/cpu/io 控制器。
- 本项目目标虚拟机为 Ubuntu 22.04.5 LTS / Linux 6.17.13，与当前代码记录的目标版本一致。若预检失败，应检查具体的 systemd、cgroup v2、权限或资源错误，不要通过删除检查绕过问题。
- 确认 `python3`、`systemctl`、`systemd-run` 和 `xz` 可用，普通实验用户可以按需使用 sudo。

## 样本准备失败

- 确认 `configs/profiles.json` 中存在所选操作和档位。
- `prepare` 的目标目录必须不存在或为空；为新一轮准备使用新的目录，避免覆盖旧素材。
- 检查磁盘余量。XZ Large 会生成较大的输入文件，Table Large 会生成大规模 CSV。
- Array Large 的参数应保持三个 `float64` 数组；理论数据容量不等于实际进程峰值。

## 采集未完成或报告不合格

- 先检查会话目录中的 `environment.json`、每轮 `metadata.json`、`journal.log`、`workload.log` 和原始 CSV。
- 检查 systemd service 是否按本轮 UUID 创建，cgroup 是否存在且持续可读。
- 核对 `memory.events` 中的 max、oom、oom_kill；缺失值不能当作零，SIGKILL 本身不能证明 OOM。
- 检查工作负载退出码、输出 manifest、SHA-256 和正确性验证结果。
- 触及安全 MemoryMax、发生 OOM、超时、验证失败或清理失败的轮次不能纳入有效均值。

## 权限或清理异常

- 以普通实验用户运行 CLI，不要使用 root 直接启动采集。
- 先确认普通实验用户具有按需调用 systemd 管理命令的权限。
- 只使用该轮 metadata 中记录的 UUID service 执行 cleanup；不要停止其他用户或其他实验的服务。
- 如果清理失败，保留诊断文件、journal 和 cgroup 证据，确认服务状态后再处理；不要删除原始结果。

## 采集并发冲突

同一用户的独立采集器通过锁文件互斥。若提示已有采集运行，先确认之前的采集进程和 systemd service 是否已经结束，再启动下一轮。不要同时运行多个 Large 独立采集任务。
