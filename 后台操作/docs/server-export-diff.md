# server-code 分支与正式基线核对记录

## 核对来源

- 源分支：`server-code`
- 源分支提交：`3002b15d6d36045647feab18a2e96e947db76ea6`
- 核对目标：`main`（核对时提交 `10ee7ded01bc827163eb6b23d5937e00f526ccc9`）
- 核对方法：读取两个 Git tree，对所有同路径 blob SHA 逐一比较。

## 核对结果

服务器分支共有 85 个文件 blob，main 有 77 个文件 blob。main 中的 77 个文件在 server-code 中全部存在，且 blob SHA 完全一致：没有发现后台或前台源码差异，也没有需要从 server-code 覆盖到 main 的源码文件。

server-code 额外包含 8 个交付/归档文件：
- `Download-Code-Only.ps1`
- `Download-OOM-Sequential.ps1`
- `installed-packages.txt`
- `krita-history-SHA256SUMS.txt`
- `krita-history.tar.gz`
- `oom-final-source-export.tar.gz`
- `server-SHA256SUMS.txt`
- `server-environment.txt`

两个 tar.gz 是源码/历史打包副本，不重复放入正式基线；展开后的正式源码已经在 main 中逐文件保存。环境和安装包清单作为部署参考另行归档，不把它们当作目标 VM 的当前状态。

## 正式基线选择

- 后台：以 server-code 中的 `background/` 为准；当前 main 文件与其逐 blob 一致。
- 前台：以 `foreground/krita_gui/` 的 Krita 外部真实桌面 GUI 自动化为准；当前 main 文件与 server-code 逐 blob 一致。
- 不纳入 WPS 自动化导入代码。
- 不纳入 Krita Python 插件式自动化。
- 不迁移旧实验结果；正式后台、前台、并发和调度实验全部重新运行。

## 结果归档说明

server-code 中的 `server-SHA256SUMS.txt` 引用了 `oom-stage-a-project.tar.gz` 和 `oom-stage-a-results.tar.gz`，但这两个文件并未出现在该分支 tree 中，因此不能据此声称完整项目归档或历史实验结果已核验。用户已明确实验结果将重新采集。

## 验证边界

Git blob 完全一致证明 GitHub 两分支的文件对象一致，不等于已在目标 VM 安装依赖、执行测试或完成真实 GUI/并发/OOM 实验。部署与运行状态必须单独记录。
