# 内存与 PSI

批次 `krita_psi_observe_20261128_001508_7d4ec673`，run ID `f04ca1afb5da4fffac37c7e1d3c0d292`。代码 `4fbc49555484055bf78f2b6d437b6a04c791dd9f`，配置 SHA256 `8d487b076463470474d3c102dcc269e255b81fc74038faf2d7dd6bba795c6cd0`。

| 指标 | 结果 |
| --- | --- |
| RSS 局部峰 | 11.720 GiB |
| cgroup current 峰 | 11.992 GiB |
| 内核 memory.peak | 11.992 GiB |
| anon 峰 | 11.547 GiB |
| file 峰 | 0.431 GiB |
| 最低 MemAvailable | 1.918 GiB |
| 应用 Swap 峰字节 | 1716224 |
| 整机 Swap 峰字节 | 39841792 |
| 整机 Full / Some avg10 最大值 | 24.61 / 24.79 |
| 应用采样点 | 12046 |
| 采样间隔中位 / 最大 | 0.049992 s / 0.094238 s |
| 大于 500 ms 的缺口 | 0 |

以下为各自 avg10 达到 10% 的连续样本时段。持续时间由首末实测时间差计算。

| 轨道 | 开始 | 末值时刻 | 持续 | 峰值 |
| --- | --- | --- | --- | --- |
| Full | 559.571246 s | 575.511822 s | 15.940576 s | 24.61 |
| Some | 559.571246 s | 575.511822 s | 15.940576 s | 24.79 |

| 首末计数差 | 增量 |
| --- | --- |
| event_oom | 0 |
| event_oom_kill | 0 |
| event_oom_group_kill | 0 |
| global_psi_full_total | 6523029 |
| global_psi_some_total | 6649133 |
| pgscan_direct | 11898 |
| pgscan_kswapd | 389347 |
| pgscan_anon | 24161 |
| pgscan_file | 377084 |
| pgsteal_direct | 9191 |
| pgsteal_kswapd | 362115 |
| pgsteal_anon | 9794 |
| pgsteal_file | 361512 |
| pswpin | 1648 |
| pswpout | 9289 |
| oom_kill | 0 |

第一实例经证实正常退出至第二实例身份就绪之间的采样点共 0 个。该区段若存在，可能包含第二实例启动期间的 cgroup 计费。
本轮缺少可验收的正常释放区段。

主机压力、可用内存和 Swap 使用整机口径。应用采样与 cgroup 统计分别保留。PNG 使用实际采样时钟并在超过 500 ms 的缺口断线。
