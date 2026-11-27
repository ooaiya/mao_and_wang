# Linux 6.17.13-oomlab：OOM / cgroup / 调度实验接口配置说明

本文记录原实验 VM 使用的 `6.17.13-oomlab` 内核和已验证的接口。换 VM 时按实际内核与 cgroup 挂载核对。当前四任务的运行步骤见 [复现实验](../../复现实验.md)。

## 1. 构建与运行版本

| 项目 | 当前值 |
|---|---|
| 运行内核 | `6.17.13-oomlab` |
| 上游版本 | `6.17.13` |
| 本地版本后缀 | `-oomlab`，来自 `LOCALVERSION=-oomlab` |
| 安装包 | `linux-image-6.17.13-oomlab_6.17.13-1_amd64.deb` |
| 包状态 | `ii` |
| 内核镜像 | `/boot/vmlinuz-6.17.13-oomlab` |
| initramfs | `/boot/initrd.img-6.17.13-oomlab` |
| 模块目录 | `/lib/modules/6.17.13-oomlab` |
| 源码树 | `~/kernel_upgrade/6.17.13/linux-6.17.13/` |
| 权威配置文件 | `~/kernel_upgrade/6.17.13/linux-6.17.13/.config` |

## 2. 已验证的内核配置符号

以下符号来自客户机 `.config` 检查结果。

| 配置项 | 值 | 对实验的意义 |
|---|---:|---|
| `CONFIG_CGROUPS` | `y` | cgroup 框架启用 |
| `CONFIG_MEMCG` | `y` | cgroup v2 内存记账启用 |
| `CONFIG_MEMCG_V1` | `# not set` | 不使用 memcg v1，代码应只面向 cgroup v2 |
| `CONFIG_SWAP` | `y` | swap 子系统启用；memcg 通过 `memory.swap.current` 记账 |
| `CONFIG_CGROUP_FREEZER` | `y` | cgroup v2 freezer 启用 |
| `CONFIG_PSI` | `y` | Pressure Stall Information 启用 |
| `CONFIG_PSI_DEFAULT_DISABLED` | `# not set` | PSI 默认启用 |
| `CONFIG_BPF` | `y` | BPF 框架启用 |
| `CONFIG_BPF_SYSCALL` | `y` | BPF 系统调用接口启用 |
| `CONFIG_BPF_JIT` | `y` | BPF JIT 启用 |
| `CONFIG_BPF_JIT_ALWAYS_ON` | `y` | JIT 强制启用 |
| `CONFIG_BPF_UNPRIV_DEFAULT_OFF` | `y` | 非特权 BPF 默认关闭；BPF 实验通常需要 root/特权环境 |
| `CONFIG_BPF_LSM` | `y` | BPF LSM 支持 |
| `CONFIG_BPF_STREAM_PARSER` | `y` | BPF 流式解析器支持 |
| `CONFIG_BPF_EVENTS` | `y` | BPF 事件支持 |
| `CONFIG_BPF_KPROBE_OVERRIDE` | `y` | kprobe 相关 BPF 支持 |

### 历史配置误区提醒

- 上游新版本已没有独立的 `CONFIG_MEMCG_SWAP` 选项；swap 记账由 `CONFIG_MEMCG=y` + `CONFIG_SWAP=y` 共同支持，运行时表现为子 cgroup 中的 `memory.swap.current`。
- 代码同学不要等待 `CONFIG_MEMCG_SWAP`；应直接使用 cgroup v2 的 `memory.swap.current` / `memory.swap.max`。
- `CONFIG_MEMCG_V1=n` 是预期结果，不影响 cgroup v2 memcg。

### 仍需在客户机确认的 CPU 调度相关符号

本节尚未从 `.config` 读到完整输出；写调度代码前建议导出确认：

```bash
CONF=~/kernel_upgrade/6.17.13/linux-6.17.13/.config
grep -E 'CONFIG_FAIR_GROUP_SCHED|CONFIG_CFS_BANDWIDTH|CONFIG_RT_GROUP_SCHED|CONFIG_SCHED_DEBUG|CONFIG_CPUSET|CONFIG_CGROUP_PIDS' "$CONF"
```

同时以运行时文件为准，而不是只看编译符号：

```bash
cat /sys/fs/cgroup/cgroup.controllers
cat /sys/fs/cgroup/cgroup.subtree_control
```

## 3. 已实测的运行时接口

### 3.1 cgroup v2 挂载

实测命令：

```bash
findmnt /sys/fs/cgroup
```

实测结果：

```text
TARGET         SOURCE  FSTYPE  OPTIONS
/sys/fs/cgroup cgroup2 cgroup2 rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot
```

要点：

- 文件系统类型是 `cgroup2`；
- `nsdelegate` 表示命名空间委托支持；
- `memory_recursiveprot` 表示递归内存保护；
- 代码应在 `/sys/fs/cgroup/<child-cgroup>` 下操作，不要假设 cgroup v1。

### 3.2 freezer 接口

根 cgroup `/sys/fs/cgroup` 不能冻结，因此根目录没有 `cgroup.freeze`；必须创建子 cgroup。

测试步骤：

```bash
sudo mkdir /sys/fs/cgroup/oomlab-test
sudo bash -c 'nohup sleep 300 >/dev/null 2>&1 & echo $! > /sys/fs/cgroup/oomlab-test/cgroup.procs'

ls -l /sys/fs/cgroup/oomlab-test/cgroup.freeze
cat  /sys/fs/cgroup/oomlab-test/cgroup.events

echo 1 | sudo tee /sys/fs/cgroup/oomlab-test/cgroup.freeze
cat  /sys/fs/cgroup/oomlab-test/cgroup.events

echo 0 | sudo tee /sys/fs/cgroup/oomlab-test/cgroup.freeze
cat  /sys/fs/cgroup/oomlab-test/cgroup.events
```

实测状态转换：

```text
初始：populated 1 / frozen 0
冻结：frozen 1
解冻：frozen 0
```

开发者接口语义：

| 文件 | 写入 | 读取用途 |
|---|---|---|
| `cgroup.freeze` | `1` 请求冻结；`0` 请求解冻 | 当前请求状态 |
| `cgroup.events` | 只读 | `populated`：组内是否有任务；`frozen`：是否已实际冻结 |
| `cgroup.procs` | 写入 PID/TID | 将进程加入 cgroup |

注意：`ps` 的进程 `STAT` 不是 freezer 的权威判据；`cgroup.events` 中的 `frozen` 才是。

### 3.3 memcg 与 swap 记账接口

实测存在的子 cgroup 文件：

```text
memory.current
memory.max
memory.swap.current
memory.events
```

常用文件含义：

| 文件 | 用途 |
|---|---|
| `memory.current` | 当前 cgroup 实际使用的内存字节数 |
| `memory.max` | 内存上限；超限后触发 `max`/`oom` 事件 |
| `memory.peak` | 峰值内存（若存在） |
| `memory.swap.current` | 当前使用的 swap 字节数 |
| `memory.swap.max` | swap 上限（若使用） |
| `memory.events` | 内存事件和 OOM kill 计数 |

### 3.4 OOM 事件接口

受控测试在 80MB 上限 cgroup 中运行 Python 申请内存，进程被内核杀掉。

`memory.events` 实测结果：

```text
low 0
high 0
max 11385
oom 1
oom_kill 1
oom_group_kill 0
```

字段语义：

| 字段 | 含义 |
|---|---|
| `low` | 低于 `memory.low` 保护相关事件计数 |
| `high` | 触及 `memory.high` 限制的事件计数 |
| `max` | 触及 `memory.max` 限制的事件计数 |
| `oom` | 发生 OOM 的事件次数 |
| `oom_kill` | 被 cgroup OOM killer 杀掉的任务数 |
| `oom_group_kill` | 组级 OOM kill 次数 |

示例采集方式：

```bash
mkdir -p /sys/fs/cgroup/oom-experiment
echo 80M | sudo tee /sys/fs/cgroup/oom-experiment/memory.max
cat /sys/fs/cgroup/oom-experiment/memory.events
```

### 3.5 PSI 接口

实测命令：

```bash
cat /proc/pressure/memory
```

实测输出样式：

```text
some avg10=0.00 avg60=0.00 avg300=0.00 total=301
full avg10=0.00 avg60=0.00 avg300=0.00 total=7
```

字段含义：

- `some`：至少一个任务受内存压力阻塞；
- `full`：所有非空闲任务都被阻塞、无可推进任务；
- `avg10/60/300`：最近 10s、60s、300s 平均压力比例；
- `total`：累计压力时间。

代码中应把 PSI 作为趋势/阻塞指标，不要把它等同于瞬时内存利用率。

### 3.6 BPF 接口

配置层已启用 `CONFIG_BPF=y`、`CONFIG_BPF_SYSCALL=y`。可选检查：

```bash
ls -ld /sys/fs/bpf
bpftool version 2>/dev/null || true
```

注意 `CONFIG_BPF_UNPRIV_DEFAULT_OFF=y`，非特权用户默认不能使用受限 BPF 功能；实验脚本通常应使用 `sudo` 或在特权命名空间内执行。

## 4. 给调度代码作者的最小编程约定

1. 只面向 cgroup v2，路径前缀为 `/sys/fs/cgroup/`。
2. 先创建子 cgroup，再把 PID/TID 写入 `cgroup.procs`。
3. 冻结时：写 `cgroup.freeze=1`，轮询 `cgroup.events` 的 `frozen` 直到为 1。
4. 解冻时：写 `cgroup.freeze=0`，确认 `frozen=0`。
5. 内存限制写 `memory.max`；观察 `memory.current`、`memory.swap.current`、`memory.peak`。
6. OOM 结果以 `memory.events` 中的 `oom`、`oom_kill`、`oom_group_kill` 为准。
7. 资源压力观察 `/proc/pressure/memory`；必要时同时采集 `/proc/pressure/cpu`、`/proc/pressure/io`。
8. 根 cgroup 不提供 freezer 文件；不要在 `/sys/fs/cgroup` 根下测试冻结。
9. 实验结束后应杀掉测试 cgroup 内进程，再 `rmdir` 清理；`cgroup.procs` 是伪文件，`ls -l` 恒为 0 字节，不能用文件大小判断是否为空。

## 5. 在客户机导出权威完整配置和运行时快照

执行下面命令可生成一份可交付给同学的文本报告：

```bash
mkdir -p ~/kernel_upgrade/6.17.13/report
CONF=~/kernel_upgrade/6.17.13/linux-6.17.13/.config
OUT=~/kernel_upgrade/6.17.13/report/oomlab-kernel-runtime-report.txt

{
  echo "===== uname ====="
  uname -a

  echo
  echo "===== cgroup mount ====="
  findmnt /sys/fs/cgroup

  echo
  echo "===== cgroup controllers ====="
  cat /sys/fs/cgroup/cgroup.controllers 2>/dev/null
  cat /sys/fs/cgroup/cgroup.subtree_control 2>/dev/null

  echo
  echo "===== selected kernel config ====="
  grep -E 'CONFIG_CGROUPS|CONFIG_MEMCG|CONFIG_MEMCG_V1|CONFIG_SWAP|CONFIG_CGROUP_FREEZER|CONFIG_PSI|CONFIG_BPF|CONFIG_FAIR_GROUP_SCHED|CONFIG_CFS_BANDWIDTH|CONFIG_RT_GROUP_SCHED|CONFIG_CPUSET|CONFIG_CGROUP_PIDS' "$CONF"

  echo
  echo "===== PSI memory ====="
  cat /proc/pressure/memory
} | tee "$OUT"

cp "$CONF" ~/kernel_upgrade/6.17.13/linux-6.17.13-oomlab.full.config
```

完整原始配置文件复制为：

```text
~/kernel_upgrade/6.17.13/linux-6.17.13-oomlab.full.config
```

## 6. 旧内核清理建议（不是运行时内存释放）

旧内核包占用的是磁盘空间：`/boot` 镜像、`/lib/modules`、headers/tools；删除它们不会直接增加运行时 RAM。

建议保留一个稳定的 Ubuntu 通用内核 `6.8.0-138-generic` 作为 GRUB 回退，先删除自定义旧版 `6.17.12` 和更旧的 `6.8.0-40-generic`，不要一次性删除全部可启动内核。
