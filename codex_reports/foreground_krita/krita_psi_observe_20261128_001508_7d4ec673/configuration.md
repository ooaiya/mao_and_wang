# 配置与素材核验

批次 `krita_psi_observe_20261128_001508_7d4ec673`，run ID `f04ca1afb5da4fffac37c7e1d3c0d292`。代码 `4fbc49555484055bf78f2b6d437b6a04c791dd9f`，配置 SHA256 `8d487b076463470474d3c102dcc269e255b81fc74038faf2d7dd6bba795c6cd0`。

本轮独立配置只增加 `pilot.psi_full_stop_enabled=false`。固定版本的 46 层人工导入和 7 层操作继续沿用。

| 项目 | 值 |
| --- | --- |
| PSI Full 采样 | 50 ms，继续保存 Some / Full |
| 运行期间持续超限动作 | observe_only |
| 原启动 PSI 上限 | 10 |
| 原冷却 PSI 上限 | 2 |
| MemAvailable 储备 | 1.500 GiB |
| SwapFree 最低字节 | 322122547 |
| cgroup 上限字节 | 13314398617 |
| 最大采样缺口 | 0.500000 s |
| 运行上限 | 1800.000000 s |

| 素材 | 层数 | 字节 | 校验 | SHA256 |
| --- | --- | --- | --- | --- |
| 低压 | 1 | 5394398 | 文件 SHA256、ZIP CRC、ORA 结构通过 | 87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8 |
| 高压 | 46 | 124404893 | 文件 SHA256、ZIP CRC、ORA 结构通过 | 100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a |
| 中压 | 7 | 22265294 | 文件 SHA256、ZIP CRC、ORA 结构通过 | 7d7679e2072c387a207d9d393525a071f59fdfc3eaf7c491051ee402eedcc5aa |
