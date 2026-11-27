# 离线测试

批次 `krita_psi_observe_20261128_001508_7d4ec673`，run ID `f04ca1afb5da4fffac37c7e1d3c0d292`。代码 `4fbc49555484055bf78f2b6d437b6a04c791dd9f`，配置 SHA256 `8d487b076463470474d3c102dcc269e255b81fc74038faf2d7dd6bba795c6cd0`。

Krita 专项 **145 项通过**，包括 7 项新增用例及原有 138 项。测试使用模拟采样和测试终端，未制造实际 OOM。

新增覆盖 50 ms 连续高 PSI 的记录，默认行为兼容，正常压力，MemAvailable、SwapFree、cgroup、冻结及缺失 PSI 保护，OOM 计数变化和采样缺口，启动与冷却的 PSI 检查，以及布尔配置约束。原专项继续覆盖真实测试终端上的 READY 转交、身份检查和完整 12 秒起点。
