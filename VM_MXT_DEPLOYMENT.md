# mxt Ubuntu VM 部署约定

本仓库在 `/home/mxt/TeamOOM/repo` 使用 `mxt` 分支。`main` 仅用于读取，不能向它推送；本地 pre-push 保护只允许 `mxt -> mxt`。不要重新执行 `git init`，不要使用 `--no-verify`。

## 独立路径

| 内容 | 路径 |
| --- | --- |
| 前台正式素材 | `/home/mxt/TeamOOM/assets/foreground` |
| 后台正式素材 | `/home/mxt/TeamOOM/assets/background` |
| 独立采集曲线 | `/home/mxt/TeamOOM/data_collection` |
| 正式实验结果 | `/home/mxt/TeamOOM/results` |
| 配置、运行文件 | `/home/mxt/TeamOOM/runtime` |
| Python 环境 | `/home/mxt/TeamOOM/runtime/venv` |
| 输入计划 | `/home/mxt/TeamOOM/inputs` |
| 原生构建 | `/home/mxt/TeamOOM/build` |
| 报告 | `/home/mxt/TeamOOM/reports` |

`runtime/paths.env` 是路径清单；原入口仍需显式传入对应 CLI 路径。不能将个人 OOM 数据作为团队正式输入。素材必须与 `前台操作/素材/SHA256SUMS`、`后台操作/素材/SHA256SUMS` 一致；这些校验清单不表示实际素材已经包含在 Git 中。

## 环境安装与检查

```bash
cd /home/mxt/TeamOOM/repo
python3 -m venv /home/mxt/TeamOOM/runtime/venv
bgpy=/home/mxt/TeamOOM/runtime/venv/bin/python
"$bgpy" -m pip install -r 后台操作/requirements.txt \
  -r 前台操作/前台操作自动化脚本采集/requirements.txt
"$bgpy" -m pip check
bash 冻结并发/离线规划器/build.sh
```

规划器输出位于 `/home/mxt/TeamOOM/build/memshift_oracle_plan`，后续通过 `--planner` 显式指定。Krita、AT-SPI、FFTW、XZ、systemd/cgroup v2 等系统能力仍须按实际 VM 验收。不要替换系统 Python、驱动或编译器来复用个人环境。

## 正式采集前提

正式采集器要求当前分支为 `mxt`，并保留已提交、干净源码的来源校验。该调整仅适配团队分支约定，不放宽源码或实验有效性检查。

从已登录并解锁的 `mxt` GNOME 桌面终端运行 GUI 入口，使用当前会话的 DISPLAY、WAYLAND_DISPLAY 和会话总线。准备配置时将 `--assets-root` 指向团队前台素材目录，配置写入 `runtime/config`，采集输出显式指向 `data_collection`。不要在仓库内生成运行结果。

只有在全部正式输入、配套独立曲线、来源摘要、GUI 会话和权限检查均通过后才能开始正式实验。依赖导入、合成规划器测试、微型 FFTW 检查和单元测试都不等于正式实验验收，不替代真实输入完整性验证。

原有算法、固定时间线、数值参数和 Swap 策略保持不变。具体缺失资料与本机验收结果以 `../reports/data_and_permission_recovery_report.md` 为准，该报告及原始数据不提交到代码仓库。
