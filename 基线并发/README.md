# 无干预并发基线

[baseline_runner.py](baseline_runner.py) 读取本轮的前台参照、三个后台的独立采样和固定偏移。它在隔离 cgroup 中准备任务，由 [release_at_deadline.py](release_at_deadline.py) 在各自偏移到期时放行。实际放行和开跑时间会随事件写入结果目录。两种并发使用同一组负载、偏移和无 Swap 条件。基线保持 cgroup 的 `memory.high` 和 `memory.max` 为 `max`，并记录清理与 OOM 证据。

运行时指定 `--foreground-run`、`--foreground-source`、`--shaped-run`、`--offsets` 和 `--output`。`--policy-config` 可显式传入同一份对照配置。结束后将结果目录传给 [review_baseline.py](review_baseline.py)，生成 `validation.json`、`report.md` 和 `baseline_memory.png`，并核对实际启动与 OOM 证据。

各模式共用的 cgroup 管理、参考曲线、采样和进程准备位于 [common/](common/)。历史内核和采集器审计见 [docs/](docs/)。[运行命令](../复现实验.md)
