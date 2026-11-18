# AT-SPI 重复 Application 修复与共享文件夹部署

本次只修复当前 Krita AT-SPI 应用选择，不改采集框架和实验设计。真实桌面验证：**NOT_RUN**；实际 Layers 表是否可读：**NOT_RUN / 尚未确认**。没有启动完整 PILOT、45 张 PNG 导入或 1800 秒保持。

## 问题和修复机制

旧选择器先按 PID 收集 Application，随后要求 `len(apps)==1`。实机同 PID 的两个 root proxy 中，一个有完整 GUI 树，另一个 childCount=0，旧代码在检查树之前就拒绝。

现在每次 `snapshot()` 重新获取 AT-SPI Desktop，不在模块或控制器内缓存任何 Desktop/Application/子节点 proxy。自动化原本每次查询也都启动新的 helper 子进程，这一方式保留。

逐个检查精确 PID、Application role、childCount、非 defunct 状态和实际可读的可见界面子树。仅有非空根不足以成功；必须读取界面后代，并在遍历结束重新核对根 PID/role/childCount/状态。相同 name、PID、bus/path 不用于合并 Application。

|候选情况|结果|
|---|---|
|一个经过完整验证的有效对象 + 空对象|使用唯一有效对象，记录空对象 rejected_empty|
|两个或以上有效界面树|不可重试的歧义，自动化立即失败，进入原有安全清理|
|全部为空、尚无本轮 PID 对象|retryable=true，控制器抛 GuiPending，重新查询，受现有启动期限约束|
|对象失效、树读取异常、可见树不完整|不返回成功；下次重新获取 Desktop 和 proxy|
|一个有效对象 + 同 PID 的不可读非空对象|不猜测不可读对象是否也有效，继续等待重新获取|
|其他 PID / 非 Application role|拒绝该候选|

所有候选记录 name、PID、role/role_id、path、bus_name、childCount、选择结果和读取错误。完整 JSON 保留在 `krita/accessibility-last.json`，每次结果以 ACCESSIBILITY_QUERY 进入 automation.log 和原有 phase-events.jsonl；空对象重试不会被误当成阶段成功或阶段失败。

唯一 Layers 表仍按真实 Table 接口读取 nRows。打开基础 ORA 必须为 1，导入完成必须为 46，保持期间继续校验；重复 Layers 表不会按名字或路径合并。查询失败、重复、数量不足不会继续保持，超出预期立即失败。没有 OCR 或固定等待降级。独立 helper 的 `--expect-layers 1` 只读检查，不打开文件、不输入、不导入图层。

## 修改文件及原因

|文件（相对仓库根）|原因|
|---|---|
|foreground/krita_gui/scripts/krita_accessibility.py|修复候选选择、完整树检查、重试/歧义语义；补齐候选诊断和独立只读层数检查|
|foreground/krita_gui/scripts/krita_auto.py|仅在 probe_state 接入可重试/不可重试结果，持久记录每次候选；其余阶段和输入逻辑保持原样|
|foreground/krita_gui/tests/test_accessibility.py|新增 32 项 fake AT-SPI/控制器协议测试，覆盖用户要求的 12 类情况及失效、重取、日志、CLI|
|foreground/krita_gui/tests/test_pilot.py|更新一个原有 fake 的 role/childCount/索引访问接口，使其具备真实 Application→frame→Layers 结构；原测试继续执行|
|foreground/krita_gui/scripts/build_atspi_bundle.py|只打包上述修复、测试、本文档、补丁和真实单元测试日志；不使用引用已删除 GUI 模块的旧打包脚本|
|foreground/krita_gui/AT_SPI_DUPLICATE_FIX.md|本次交付说明和 Windows 共享文件夹部署、只读实机检查命令|

collector 的 engine/metrics/units/phases/validation 已检查，没有修改。进程 PID/PPID/starttime/exe/cgroup、实际 libqxcb.so、XWayland PID/WM_CLASS、唯一主窗口、焦点/几何复核及 OOM/素材前后校验保留。45 张、8000×8000 基础 ORA、八阶段、1800 秒和 50ms 均未修改。没有更改后台、并发、MemShift、freezer、调度器、旧报告或实验结果。

用户确认本次不改配置：远程旧模板仍为 13,000,000,000，而虚拟机已有运行配置为 16,000,000,000。本补丁包 **不含任何配置文件**，不得把旧模板复制覆盖虚拟机配置。最低 MemAvailable、SwapFree 和其他安全条件同样保留。

## 单元测试与静态检查

```bash
python -m compileall -q foreground/krita_gui
PYTHONPATH=foreground/krita_gui python -W error::ResourceWarning -m unittest discover -s foreground/krita_gui/tests -v
git diff --check
```

全部 **101 项通过**：原有 69 项 + 新增 32 项。compileall、diff --check 通过。新增用例全部使用 fake AT-SPI 与 mock 子进程，不连接真实 PID 4117；原有测试夹具亦为 TEST_ONLY。没有把任何测试夹具的 cgroup 或图层数当作实机结果。归档中的 UNITTEST.log 是实际单元测试输出。

## Windows 共享文件夹部署

将交付 ZIP 放入 Windows 共享文件夹，在 Ubuntu 解压到一个新的临时目录，例如 `/tmp/krita-atspi-fix-<时间>`。先校验，后应用；不要直接向旧结果目录解压。归档包含六个完整修改文件、changes.patch、BUNDLE.json、FILELIST.txt、SHA256SUMS 和 UNITTEST.log。

```bash
set -euo pipefail
bundle_zip=/media/sf_你的共享目录/krita-atspi-duplicate-application-fix-v1.zip
unpack_dir=$(mktemp -d /tmp/krita-atspi-fix-XXXXXXXX)
unzip "$bundle_zip" -d "$unpack_dir"
bundle_dir="$unpack_dir/krita-atspi-fix"
cd "$bundle_dir"
sha256sum -c SHA256SUMS
cat BUNDLE.json
```

先按实际仓库路径设置变量，检查当前分支、HEAD、未提交内容。补丁以本次远程基线 `5a6df84d23d9de96a20aa07f4b8597cee7f0f92c` 的源码为基础。配置改动不在补丁范围；若修复文件已有其他修改，`git apply --check` 失败时停止，不使用强制覆盖。

```bash
repo_dir=/home/mxt/OOM
cd "$repo_dir"
test "$(git branch --show-current)" = krita-xwayland
git status --short
git log -1 --format='%H %s'
git apply --check "$bundle_dir/changes.patch"
backup_dir=$(mktemp -d /home/mxt/krita-atspi-backup-XXXXXXXX)
git diff --binary > "$backup_dir/worktree.patch"
git diff --cached --binary > "$backup_dir/index.patch"
cp --parents foreground/krita_gui/scripts/krita_accessibility.py \
  foreground/krita_gui/scripts/krita_auto.py foreground/krita_gui/tests/test_pilot.py "$backup_dir/"
git apply "$bundle_dir/changes.patch"
git diff --check
python3 -m compileall -q foreground/krita_gui
PYTHONPATH=foreground/krita_gui python3 -m unittest discover -s foreground/krita_gui/tests -v
```

不要顺带复制任何 collection 配置，不执行 reset/clean，不删除旧日志或结果。应用源码补丁会产生正常的 git 未提交更改；完整 PILOT 原有的源码清洁审计继续有效。本次只做独立只读验证，不绕过审计启动实验。

## 第二步：真实桌面独立验证（尚未执行）

在 mxt 的 GNOME 桌面终端先确认没有已有 Krita。不要复用历史 PID 4117 或旧 XID。以下只启动一个空白基础文档，不导入 PNG、不执行自动化序列。

```bash
cd "$repo_dir"
if pgrep -u "$(id -u)" -x krita >/dev/null; then
  echo '已有 Krita，请先人工核对并关闭；不要附着已有实例。'
  exit 1
fi
QT_QPA_PLATFORM=xcb QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 \
  krita /home/mxt/OOM_assets/krita_8000_manual/blank_8000x8000.ora &
krita_pid=$!
```

等待桌面显示基础文档，再核对本轮真实 PID、exe/cgroup、maps 和窗口（这些命令不判定自动化成功）：

```bash
ps -o pid,ppid,lstart,comm,args -p "$krita_pid"
readlink "/proc/$krita_pid/exe"
cat "/proc/$krita_pid/cgroup"
grep -E 'libqxcb.so|libqwayland' "/proc/$krita_pid/maps"
wmctrl -lpG
```

独立手动启动不属于正式 workload cgroup 的采集流程，因此 **不能据此声称完成正式 cgroup 归属验证**。正式采集仍需原 collector 创建边界并核对身份；本次不执行该流程。

建立新的诊断目录，只读查询准确 PID：

```bash
diag_dir=$(mktemp -d /home/mxt/krita-atspi-diagnostic-XXXXXXXX)
diag_status=0
/usr/bin/python3 foreground/krita_gui/scripts/krita_accessibility.py \
  --pid "$krita_pid" --expect-layers 1 > "$diag_dir/accessibility.json" || diag_status=$?
cat "$diag_dir/accessibility.json"
echo "diagnostics: $diag_dir ; exit: $diag_status"
test "$diag_status" -eq 0
```

若命令非零，先阅读 JSON：`retryable=true` 表示可在当前启动阶段重新执行只读查询；歧义或 Layers 不唯一/计数不符必须停止。不要修改脚本取消检查。向诊断包保留该 JSON、当前 wmctrl/xprop/maps 输出；共享诊断前核对是否包含不需要分享的其他应用名。

成功条件必须同时满足：本轮 PID 精确一致；候选中只有一个可用 GUI 树（空对象被拒绝）；selected_application 指向该对象；gui_nodes 能读取可见主界面；layer_views 恰好一个且 row_count=1；layers_validation.passed=true。再按 wmctrl 中本轮 PID 的唯一正常窗口取得实际 XID，使用 `xprop -id 实际XID _NET_WM_PID WM_CLASS` 与 `xwininfo -id 实际XID` 核对，不能复用旧窗口。

检查后通过 Krita 菜单正常退出本轮手动实例。只有这些实机检查通过后，才可人工审阅准备后续完整 PILOT；**本任务没有自动执行完整采集的命令**。

## 本次交付状态

|项目|状态|
|---|---|
|代码修复|完成|
|单元测试/静态检查|101 项通过；compileall / diff --check 通过|
|ZIP 解压及全部 SHA256 校验|交付前真实执行校验，结果见交付消息|
|目标 Ubuntu 桌面启动/重复对象实机验证|NOT_RUN|
|真实唯一主窗口、Layers 表、基础层数 1|NOT_RUN，未确认可读|
|完整 45 张导入 / 1800 秒 PILOT|NOT_RUN，未执行|

云端工作区没有 DISPLAY、WAYLAND_DISPLAY 或 Krita，也没有本地 VM 接入；不能将上述代码和 fake 测试写成实机 PASS。ZIP 与代码 commit SHA 由本次交付消息提供。
