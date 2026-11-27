# 停止与完整性分析

批次 `krita_psi_observe_20261128_001508_7d4ec673`，run ID `f04ca1afb5da4fffac37c7e1d3c0d292`。代码 `4fbc49555484055bf78f2b6d437b6a04c791dd9f`，配置 SHA256 `8d487b076463470474d3c102dcc269e255b81fc74038faf2d7dd6bba795c6cd0`。

终止分类 **PILOT_INVALID**。原验证器状态 `PILOT_INVALID`。

真实前台终端收到 `READY 46`，输入相对时间 592.070502 s。核验开始于 592.118234 s，首个错误发生在 592.321664 s，记录如下。

> RuntimeError('xdotool exit=1: XGetWindowProperty[_NET_ACTIVE_WINDOW] failed (code=1)\nxdo_get_active_window reported an error')

现有核验顺序先采集 `wmctrl -lpG`，再读取 `xdotool getactivewindow`。本轮证据中已保存的窗口列表为 `0x01400019  0 27737  494  267  1654 782  mxt-virtual-machine Krita`。读取活动窗口失败后，未完成唯一窗口、标题、AT-SPI 图层数和安全采样应答的核验。可用证据只证明用户报告了导入完成，机器没有验收 46 层。当前记录无法解释 X11 活动窗口属性为何缺失。

原自动化尝试优雅退出。诊断 `TimeoutExpired(['krita', '--nosplash'], 9.820409600000858)`。采集器随后在异常退出交界记录 `RuntimeError: Krita process identity changed`，停止请求相对时间 602.742385 s。采集器其他证据错误 `["grace sampler: RuntimeError('Krita process identity changed')"]`。失败处未保存变更的进程身份字段，因此无法证实具体字段。

阶段时间线显示 `HIGH_DOCUMENT_READY` 未记录。正式 12 秒 未完成。异常清理期间的释放不计作正常自然释放。封存核验 PASS，41 个成员。

详见 [阶段时间线](phase_timeline.md) 和 [原验证器结果](validation_summary.md)。
