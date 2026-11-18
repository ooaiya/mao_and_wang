# 无干预并发基线

两套基线使用相同的低压 → 高压 → 中压 Krita 前台，仅切换后台组合。

- XZ、Array、Table 使用 `基线并发/baseline_runner.py`，从已验收的无 Swap 串行曲线估算提交偏移。
- Raster FFT、Array、Table 使用 `冻结并发/raster_baseline.py`，接收栅格参考曲线和对齐 JSON。

两套基线共享到点放行、系统与任务内存采集和 OOM 复核。记录计划偏移、门控释放、任务真正开始、输出校验和内核 OOM 证据。当前 XZ 基线复用了栅格基线的到点放行逻辑。已有 XZ 历史归档对应较早的前台版本。

启动和事后绘图见 [复现实验](../复现实验.md)。共享采集及 cgroup 管理位于 `common/`。
