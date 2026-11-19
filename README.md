# OOM 内存压力与冻结并发实验

`mxt` Ubuntu VM 的独立目录、依赖及采集分支约定见 [VM_MXT_DEPLOYMENT.md](VM_MXT_DEPLOYMENT.md)。正式素材未随 Git 提供，须先核验，不能以个人 OOM 数据代替。

本项目在 Ubuntu 上用自动化 Krita 和三个后台任务构造内存竞争，比较串行、无干预基线、曲线分级冻结、仅冻结和实时分级冻结。XZ 与栅格 FFT 分别与 Krita、Table、Array 组成两套四任务场景。

## 目录

| 目录 | 内容 |
| --- | --- |
| [前台操作](前台操作/README.md) | 9000² 低压 → 高压 → 中压自动化，峰前低压窗口为 630 秒。 |
| [前台素材](前台操作/素材/README.md) | 原实验的 1 层、46 层和 7 层 ORA，以及 SHA-256 清单。 |
| [后台操作](后台操作/README.md) | XZ、Table、Array、栅格 FFT 的工作负载和独立采集。 |
| [后台素材](后台操作/素材/README.md) | XZ Large 的 1792 MiB 输入、XZ Small、Table Large 的 800 万行 CSV，及 Array Large 的生成参数和校验清单。栅格按源码、固定种子及已归档的正式参数现场生成。 |
| [串行测试](串行测试/README.md) | 顺序执行 Krita、XZ、Table、Array，生成曲线分级和无干预基线的参照。 |
| [基线并发](基线并发/README.md) | XZ 和栅格的自动化无干预基线，共用 cgroup、内存、时间线和证据采集模块。 |
| [冻结并发](冻结并发/README.md) | 曲线分级、仅冻结消融、实时分级，以及用于历史曲线续跑的可选离线规划器。 |
| [实验结果](实验结果/README.md) | 原始曲线、决策日志、校验、报告、对照图表和独立绘图脚本。旧轮次记录保留当时的场景和前台版本。 |

## 策略入口

| 对照或策略 | 入口 | 用途 |
| --- | --- | --- |
| 无干预基线 | `基线并发/baseline_runner.py`、`冻结并发/raster_baseline.py` | 以 Krita 首页就绪为 T0，按计划放行后台，记录实际开跑、内存竞争和 OOM 证据。 |
| 曲线分级冻结 | `冻结并发/segmented_runner.py --serial-policy priority`、`冻结并发/raster_priority.py` | 按已测曲线、优先级和现场余量设置软限额并冻结、恢复后台。 |
| 仅冻结对照 | 曲线分级 XZ 入口加 `--policy-config 冻结并发/priority_freeze_only_config.json` | 关闭 `memory.high`，衡量冻结和恢复本身的效果。 |
| 实时分级冻结 | `冻结并发/realtime_runner.py` | 用本轮内存及后台 cgroup 数据分级调度。加 `--raster-reference` 切换为栅格。 |
| 曲线离线续跑 | `冻结并发/segmented_runner.py --serial-policy offline` | 可选的历史曲线对照，使用 `冻结并发/离线规划器/` 的小型 C++ 命令行规划器。 |

[复现实验.md](复现实验.md) 提供安装、素材部署、运行和绘图命令。[任务场景说明.txt](任务场景说明.txt) 解释前后台负载、基线和冻结实验各自验证的问题。

历史实验环境为 Ubuntu 22.04.5、Linux 6.17.13、Python 3.10、16 GB VM。并发脚本沿用原 VM 的桌面账号 `ooaiya`（UID/GID 1000）、GNOME Wayland/XWayland 和 systemd cgroup v2。重新采集时统一前台版本、输入摘要、Swap、偏移及验收口径，按实际日志确认 OOM 和冻结动作。


## 移交核验

- 已核对 4 个前台 ORA 和 8 个后台输入文件的 SHA-256，并核对栅格种子、正式参数和独立采样中记录的工作进程摘要。
- Ubuntu VM 上 254 项测试通过、1 项因环境条件跳过。已验证前台配置生成、基线与冻结入口参数、离线规划器构建，并用归档串行数据生成 XZ 和栅格基线计划。
- 整轮并发压力、GUI 和 OOM 的实测结果见历史归档。本次新版 XZ 基线通过计划检查。
