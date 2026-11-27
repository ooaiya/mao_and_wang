# 内存与 PSI

批次 `krita_three_guard_20261128_010241_2cb959a6`，run ID `717be1060cc54a55ae1c93d0dee082f8`。代码 `715afeaf0644d35da3cb207ab211dbaa85f75b6a`，配置 SHA256 `c6b19c657518b3ca754f7dd4474e973c878bc590183d60fb37fa89c7bd88b6f5`。

| 指标 | 结果 |
| --- | --- |
| RSS 局部峰 | 1.125 GiB |
| cgroup current 峰 | 1.060 GiB |
| 内核 memory.peak | 1.060 GiB |
| anon 峰 | 0.954 GiB |
| file 峰 | 0.100 GiB |
| 最低 MemAvailable | 12.474 GiB |
| 应用 Swap 峰字节 | 0 |
| 整机 Swap 峰字节 | 22392832 |
| 整机 Full / Some avg10 最大值 | 0.36 / 0.36 |
| 应用采样点 | 1338 |
| 采样间隔中位 / 最大 | 0.050019 s / 0.858477 s |
| 大于 500 ms 的缺口 | 1 |

PSI 以 avg10 达到 10% 计。MemAvailable 以低于 1.5 GiB 计。cgroup current / peak 以达到配置阈值计。时长为每段连续样本首末时差之和。

| 轨道 | 首次越线 monotonic_ns | 相对时间 | 累计时长 | 次数 |
| --- | --- | --- | --- | --- |
| PSI Full avg10 | 未超限 | 未超限 | 0.000000 s | 0 |
| PSI Some avg10（对照） | 未超限 | 未超限 | 0.000000 s | 0 |
| MemAvailable | 未超限 | 未超限 | 0.000000 s | 0 |
| workload memory.current | 未超限 | 未超限 | 0.000000 s | 0 |
| workload memory.peak | 未超限 | 未超限 | 0.000000 s | 0 |
| parent memory.current | 未超限 | 未超限 | 0.000000 s | 0 |
| parent memory.peak | 未超限 | 未超限 | 0.000000 s | 0 |

| 首末计数差 | 增量 |
| --- | --- |
| event_oom | 0 |
| event_oom_kill | 0 |
| event_oom_group_kill | 0 |
| global_psi_full_total | 54686 |
| global_psi_some_total | 55046 |
| pgscan_direct | 0 |
| pgscan_kswapd | 0 |
| pgscan_anon | 0 |
| pgscan_file | 0 |
| pgsteal_direct | 0 |
| pgsteal_kswapd | 0 |
| pgsteal_anon | 0 |
| pgsteal_file | 0 |
| pswpin | 0 |
| pswpout | 0 |
| oom_kill | 0 |

第一实例开始正常关闭至第二实例启动前的采样点共 0 个。释放窗口的验收证据为 `{}`。
本轮缺少可验收的正常释放区段。

主机压力、可用内存和 Swap 使用整机口径。应用采样与 cgroup 统计分别保留。PNG 使用实际采样时钟并在超过 500 ms 的缺口断线。
