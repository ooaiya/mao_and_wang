# 无干预并发基线

当前四任务场景用 [raster_baseline.py](../冻结并发/raster_baseline.py) 的 `--shaped-run` 和 `--offsets`。它依据和分级冻结相同的计划偏移放行栅格条带校正、列式表转换和数组评分，在无 Swap 条件下记录实测的内存竞争。

历史基线也使用低压 → 高压 → 中压 Krita 前台，后台组合如下。

- XZ、Array、Table 使用 `基线并发/baseline_runner.py`，从已验收的无 Swap 串行曲线估算提交偏移。
- Raster FFT、Array、Table 使用 `冻结并发/raster_baseline.py`，接收栅格参考曲线和对齐 JSON。

各场景共享到点放行、系统与任务内存采集和 OOM 复核。记录计划偏移、门控释放、任务真正开始、输出校验和内核 OOM 证据。使用同一场景的前台、后台、偏移和 Swap 条件做对照。

启动和事后绘图见 [复现实验](../复现实验.md)。共享采集及 cgroup 管理位于 `common/`。


数据与分支管理见 [Git 数据安全说明](../GIT_DATA_POLICY.md)。仓库中的 `baseline_timeline_plan.json` 和 `freeze_schedule.json` 是保留的历史计划示例，不是本机新实验已验收参照。新的合格前后台参照尚未生成，不能直接开展正式预测实验。
