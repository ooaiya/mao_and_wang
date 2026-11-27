# 停止与完整性分析

批次 `krita_three_guard_20261128_010241_2cb959a6`，run ID `717be1060cc54a55ae1c93d0dee082f8`。代码 `715afeaf0644d35da3cb207ab211dbaa85f75b6a`，配置 SHA256 `c6b19c657518b3ca754f7dd4474e973c878bc590183d60fb37fa89c7bd88b6f5`。

终止分类 **SAFETY_STOP**。原验证器状态 `PILOT_INVALID`。

真实前台终端收到 `未记录`，输入相对时间 未取得。核验开始于 未取得，首个错误发生在 67.253506 s，记录如下。

> StopRequested('RuntimeError: 50ms sampler gap exceeded safety bound')

本轮没有 READY 回执，未进入 X11 窗口、AT-SPI 图层数或采样应答核验。新增的被动采样路径只在离线用例得到验证。

安全守卫触发后原自动化尝试优雅退出。诊断 `未记录`。采集器的原始停止原因 `RuntimeError: 50ms sampler gap exceeded safety bound`，停止请求相对时间 67.158948 s。采集器其他证据错误 `[]`。失败处未保存变更的进程身份字段，因此无法证实具体字段。

采集在 t=67.158948 秒触发了保留的 500 ms 缺口守卫。低压浏览完整结束，进入人工提示后仅经过 7.258786 秒，尚未收到 READY。启动后的 3 项软件参考阈值均未越线。

| 轨道 | 上一采样 monotonic_ns | 下一采样 monotonic_ns | 缺口 |
| --- | ---: | ---: | ---: |
| parent | 29387682903235 | 29388532720007 | 849.816772 ms |
| krita | 29387684796317 | 29388543272892 | 858.476575 ms |

parent 轨道先触发守卫。工作负载轨道的下一点来自停止请求之后的收尾采样。相邻样本内存数值接近，缺口附近的 PSI Full 和 Swap 均为 0。原始日志能确认时间间隔和停止关系。采集器没有细分到这一间隔中的每项系统调用时长，无法从现有证据认定调度、I/O 或具体调用是缺口的根因。

阶段时间线显示 `HIGH_DOCUMENT_READY` 未记录。正式 12 秒 未完成。异常清理期间的释放不计作正常自然释放。封存核验 PASS，41 个成员。

详见 [阶段时间线](phase_timeline.md) 和 [原验证器结果](validation_summary.md)。
