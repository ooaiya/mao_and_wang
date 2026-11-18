# 冻结并发

| 运行方式 | 入口 |
| --- | --- |
| 曲线分级 XZ | `segmented_runner.py --serial-policy priority` 与 `priority_policy.py` |
| 曲线分级栅格 | `raster_priority.py` 与 `raster_priority_config.json` |
| 仅冻结消融 | 曲线分级 XZ 入口加 `--policy-config priority_freeze_only_config.json` |
| 实时分级 XZ 或栅格 | `realtime_runner.py` 与 `realtime_policy.py`。 [实时反馈策略](实时反馈调度方案.md) |
| 曲线离线续跑 | `segmented_runner.py --serial-policy offline --planner <程序路径>`。 [离线规划器](离线规划器/README.md) |

曲线分级使用无 Swap 串行参照。实时分级使用当前内存反馈，启动时传入当前前台配置、素材清单及可选的栅格参考。两个分级执行器都记录冻结和恢复的 cgroup 内核确认。 [运行与复核命令](../复现实验.md)

事后复核入口为 `review_independent.py`。它读取对应策略的决策和冻结日志，检查内存、Swap、OOM、任务完成及输出。历史分段、离线和首批冻融实验的证据在 [实验结果](../实验结果/README.md)。
