# 内核限制与冷却恢复

批次 `krita_three_guard_20261128_010241_2cb959a6`，run ID `717be1060cc54a55ae1c93d0dee082f8`。代码 `715afeaf0644d35da3cb207ab211dbaa85f75b6a`，配置 SHA256 `c6b19c657518b3ca754f7dd4474e973c878bc590183d60fb37fa89c7bd88b6f5`。

| 实际 cgroup 路径 | memory.max | memory.high | memory.swap.max | memory.oom.group | 启动 memory.current |
| --- | --- | --- | --- | --- | --- |
| /sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/oomcollect.slice/oomcollect-717be1060cc54a55ae1c93d0dee082f8.slice/oomcollect-717be1060cc54a55ae1c93d0dee082f8-krita.service | max | max | max | 0 | 5898240 |
| /sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/oomcollect.slice/oomcollect-717be1060cc54a55ae1c93d0dee082f8.slice | max | max | max | 0 | 12070912 |
| /sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/oomcollect.slice | max | max | max | 0 | 487743488 |
| /sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service | max | max | max | 0 | 1959157760 |
| /sys/fs/cgroup/user.slice/user-1000.slice | max | max | max | 0 | 3039137792 |
| /sys/fs/cgroup/user.slice | max | max | max | 0 | 3039363072 |
| /sys/fs/cgroup | None | None | None | None | None |

根节点的控制文件若不存在，表中记为 None。此表由启动门开启前读取实际 unit 及祖先得到。

| 冷却属性 | 结果 |
| --- | --- |
| environment_recovered | True |
| cooldown_ok | True |
| 耗时 | 5.018702 s |
| 最终 cgroup current | 0.030 GiB |
| 最终 MemAvailable | 14.039 GiB |
| 最终 Full avg10 | 0.0 |
| 其他冷却错误 | None |
