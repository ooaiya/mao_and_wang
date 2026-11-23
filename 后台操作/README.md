# 后台工作负载与独立内存采集

当前并发场景使用 [曲线任务/shaped_workload.py](曲线任务/shaped_workload.py) 中的栅格条带校正（`raster`）、内存列式表转换（`table`）和批量数组评分（`array`）。三个任务生成确定性数据，记录分批增长、持有和释放阶段。用 [measure_raster.py](栅格频域任务/measure_raster.py) 的 `--task` 分别采集三个后台，命令见 [复现实验](../复现实验.md)。

## 历史 XZ、Table 与 Array 操作

以下档位和采集流程适用于 `oomlab/` 中的 XZ 压缩、CSV 表格和原数组处理。输入可从交接资料取得并按 [素材清单](素材/README.md) 核验。历史栅格 FFT 自生成瓦片和整幅数据，入口位于 `栅格频域任务/`。

| 操作 ID | 工作负载 | 类型 | 正式档位 |
|---|---|---|---|
| `xz` | XZ 压缩 | 单线程压缩 | `large` |
| `table` | Table 表格处理 | 大规模结构化数据生成、读取和分组计算 | `large` |
| `array_processing` | Array 数组处理 | NumPy 数组生成和数值计算 | `large` |

配置统一位于 `configs/profiles.json`。档位参数不等于实际峰值，最终以内存采集结果为准。

### 配置参考

#### XZ 压缩

| 参数 | small | medium | large（正式档位） |
|---|---:|---:|---:|
| 输入数据大小（MiB） | 256 | 1024 | **1792** |
| 字典大小（MiB） | 96 | 128 | **128** |
| 线程数 | 1 | 1 | **1** |

#### Table 表格处理

| 参数 | small | medium | large（正式档位） |
|---|---:|---:|---:|
| 数据行数 | 10,000 | 4,000,000 | **8,000,000** |
| 用户数 | 1,000 | 200,000 | **200,000** |
| 分类数 | 32 | 32 | **32** |
| 天数 | 31 | 31 | **31** |
| 扩展字段数 | 4 | 4 | **4** |

#### Array 数组处理

| 参数 | small | medium | large（正式档位） |
|---|---:|---:|---:|
| 元素总数 | 1,000,000 | 20,000,000 | **90,000,000** |
| 数据类型 | float64 | float64 | **float64** |
| 数组个数 | 3 | 3 | **3** |
| 分块大小（元素数） | 100,000 | 500,000 | **1,000,000** |
| 随机种子 | 20261026 | 20261026 | **20261026** |

三个 float64 数组的理论原始数据容量为 2,160,000,000 Bytes（约 2.01 GiB）。Array 是实际的 NumPy 数组数值计算工作负载，不是将旧图像处理操作改名。理论数据容量也不等于进程实际内存峰值。

## 目录结构

```text
后台操作/
├── oomlab/
│   ├── cli.py              # 单操作采集命令行入口
│   ├── workloads.py        # XZ、Table、Array 的样本准备/执行/校验
│   ├── array_processing.py # Array 数组操作的具体实现
│   ├── collect.py          # 单操作多轮采集
│   ├── report.py           # 单操作统计报告和曲线对齐
│   ├── metrics.py          # cgroup 内存指标读取
│   ├── telemetry.py        # 系统与进程指标采集
│   ├── services.py         # 单操作 systemd 服务管理
│   ├── worker.py           # 单操作工作进程门控
│   ├── environment.py      # 环境和控制文件检查
│   ├── oom_evidence.py     # OOM 证据收集
│   ├── events.py           # 操作阶段事件记录
│   └── common.py           # 公共工具函数
├── configs/
│   └── profiles.json       # 三个后台操作的 small/medium/large 配置
├── 曲线任务/               # 当前栅格、列式表和数组的分批工作负载
├── 栅格频域任务/           # 单任务曲线采集及历史栅格 FFT
├── docs/                   # 后台工作负载设计、排障与验证记录
├── scripts/                # 环境检查、准备、采集、报告和测试入口
├── tests/                  # 单操作采集与工作负载测试
└── requirements.txt
```

并发公共模块位于 `基线并发/common/`。并发入口见 [无干预基线](../基线并发/README.md) 与 [冻结并发](../冻结并发/README.md)。

## 环境准备

在仓库根目录进入本目录后，创建虚拟环境并安装依赖：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Large 独立采集流程

先检查环境：

```bash
.venv/bin/python -m oomlab.cli check-env
```

确认环境准入通过、磁盘空间和内存余量满足要求后，再准备三个操作的 Large 样本。每个数据目录应是新的空目录：

```bash
mkdir -p "$HOME/oom_data"
.venv/bin/python -m oomlab.cli prepare --operation xz --profile large --data "$HOME/oom_data/xz"
.venv/bin/python -m oomlab.cli prepare --operation table --profile large --data "$HOME/oom_data/table"
.venv/bin/python -m oomlab.cli prepare --operation array_processing --profile large --data "$HOME/oom_data/array_processing"
```

样本准备完成后，逐个操作采集，不要同时运行多个独立采集器：

```bash
.venv/bin/python -m oomlab.cli collect --operation xz --profile large --data "$HOME/oom_data/xz" --rounds 10 --results "$HOME/oom_results/xz"
.venv/bin/python -m oomlab.cli collect --operation table --profile large --data "$HOME/oom_data/table" --rounds 10 --results "$HOME/oom_results/table"
.venv/bin/python -m oomlab.cli collect --operation array_processing --profile large --data "$HOME/oom_data/array_processing" --rounds 10 --results "$HOME/oom_results/array_processing"
```

每个操作都会生成独立的采集会话、原始 CSV、元数据、正确性校验和报告。重点检查 `summary.json`、`report.md`、`mean.csv`、`memory.events` 和每轮 `metadata.json`。失败轮次、证据不完整轮次或触及安全限制的轮次不能作为有效样本。

## 采集与安全原则

- 单操作采集必须逐个执行；同一用户的采集锁会拒绝重叠的独立采集会话。
- Large 档位会消耗较多内存和磁盘空间。环境预检失败或可用资源不足时应停止，不要绕过保护检查。
- CLI 以普通实验用户启动，由工具按需调用 systemd 权限。
- OOM 事件、任务退出码、正确性验证和清理证据必须一起核查；SIGKILL 本身不能证明发生了 OOM。

## 目标虚拟机环境

本项目目标环境为 Ubuntu 22.04.5 LTS / Linux 6.17.13。该版本组合与后台代码当前记录的目标环境一致。部署后仍需通过 `check-env` 检查 systemd、cgroup v2 控制器、权限和可用资源；预检失败时应根据具体错误排查，不要绕过保护检查。

## 历史实测参考

仓库此前记录的 10 轮平均值如下，仅作为历史参考，不代表当前虚拟机的最新测量结果：

| 操作 | 峰值内存 | 峰值时间 | 持续时间 |
|---|---:|---:|---:|
| XZ large | 2.394 GB | 770.0 s | 770.3 s |
| Table large | 2.618 GB | 9.6 s | 33.2 s |
| Array large | 2.203 GB | 19.6 s | 22.0 s |

前台 Krita 的采集入口和并发实验均在仓库其他顶层目录维护。

## Array Large 原始素材归档

从虚拟机旧仓库恢复的 Array Large 原始配置与清单已单独归档至 [`素材/Array_Large/`](素材/Array_Large/)：

- `parameters.json`：原始数组工作负载参数及算法标识。
- `manifest.json`：原始样本清单、参数文件哈希和数据集 ID。
- `README.md`：素材说明、参数摘要和来源。

该目录仅保存可复现样本的配置与清单，不包含十轮采集结果。十轮原始结果、报告和每轮证据应独立备份，供后续三线并发实验使用。
