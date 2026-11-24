# 环境审计

当前目标环境（2026-11-05 用户确认）：**Ubuntu 22.04.5 LTS / Linux 6.17.13**；实际 release 为 `6.17.13-oomlab`，Python 3.10.12、RAM 16GB、Swap 2GiB、cgroup v2。`check-env` 仅精确匹配内核基础版本，保留完整实际 release；Ubuntu VERSION_ID=22.04 的检查逻辑不变。下文云端结果与用户提供的内核证据来源分别保留。

本次代码构建/主机测试实际执行在 Debian 13 云容器，Linux 6.18.57，MemTotal 10,452,459,520 Bytes，PID1 为 tail，cgroup v2 挂载只读。历史机器快照已从代码分支移除，不作为当前部署凭据。它不是目标 Ubuntu VM；云容器的 Freezer probe 为 BLOCKED，不能据此否定 VM 的 Freezer 能力。

用户后续提供 [Linux 6.17.13-oomlab 内核接口报告](kernel-6.17.13-oomlab-reference.md)：目标运行版本为 6.17.13-oomlab，CONFIG_CGROUPS/MEMCG/SWAP/CGROUP_FREEZER/PSI 为 y，MEMCG_V1 关闭；cgroup2 为 rw 挂载，子组已报告 frozen 0→1→0 实测，受控 memcg OOM 已报告 oom=1、oom_kill=1。

因此目标内核的 Freezer/memcg 能力已有用户提供的运行证据。接下来需要在实际三线委派 scope 内复核权限、分组、子进程继承和心跳停止/恢复；用户已明确安排先完成 GitHub 代码部署，VM 连接信息后补。本次没有改动/安装/清理内核、GRUB 或 VM 内存，没有执行文档中的 80 MB 限额 OOM 示例。

代码只使用 cgroup v2：Freezer 为核心接口，不要求 freezer 出现在 controllers，也不写 +freezer。根 cgroup 不需要也不提供 cgroup.freeze；创建独立子组后再访问。memory.peak、swap 和各类 PSI 若不可读，记录缺失状态，不用零值伪装支持。

CPU 调度符号在用户报告中尚未全部导出，不将它们猜作 y；CPU/I/O 控制器按运行时实际可用项启用。部署 helper 必需项是 Delegate=yes 与 MemoryAccounting=yes。
