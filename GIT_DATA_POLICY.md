# TeamOOM Git 数据与分支管理

main 是只读部署基准；正式代码仅在 mxt 修改。mxt_codex 继承 mxt，其独立提交仅允许 codex_reports/ 下的 Markdown 汇报。同步时先在 mxt 完成提交，再在 mxt_codex 明确合并 mxt；合并后的非汇报文件必须与 mxt 父提交完全一致，现有汇报不能在同步提交中修改。

## 数据边界

Git 保存代码、通用配置模板、测试、说明、素材 README、SHA256SUMS、manifest 和参数定义。原始采样、曲线、结果、素材、执行日志、虚拟环境和凭据留在仓库之外。仅允许 tests/fixtures/ 或 tests/resources/ 下明确的合成测试数据，以及 docs/resources/ 下经过审核的说明图片；凭据扫描没有例外。JSON 没有按扩展名整体屏蔽，必要配置继续跟踪。

部署目录以 /home/mxt/TeamOOM 为根：assets/baseline_assets 保存将来经核验的参照，data_collection 保存采集，results 保存实验及离线分析输出，runtime/config 保存本机生成配置，runtime/venv 保存虚拟环境。它们均不在 repo 中。本次不恢复或迁移旧实验数据。

基线并发/baseline_timeline_plan.json、冻结并发/freeze_schedule.json 是历史配置示例，不是当前 VM 已验收计划。归档哈希清单保留在基线并发/profiles/analysis/archive_sha256.json；旧曲线、图表与运行记录已从分支当前文件树移除，main 及既有 Git 历史不重写。

## 本地保护

新检出后运行 `python3 tools/install_git_hooks.py` 安装本地 pre-commit 和 pre-push。运行 `python3 tools/git_guard.py index` 检查暂存树，或 `python3 tools/git_guard.py tree mxt` 检查提交树。检查脚本仅依赖系统 Python 标准库，不安装系统软件。

pre-commit 检查完整暂存树及当前分支；pre-push 检查目标树和所有新上传提交，防止先提交数据再删除而把中间数据带入历史。只允许指定仓库中同名 mxt/mxt_codex 推送，拒绝 main、未知分支、删除和非快进更新。本地钩子可被本机用户修改，不能替代 GitHub 保护和人工审查；禁止绕过钩子。

数据检查使用目录、文件类型和采集文件名规则，凭据检查覆盖认证路径、私钥及常见 token 模式。它不能识别任意改名、编码或语义伪装的数据和秘密，提交前必须审查差异。必要白名单必须随代码审查更新。

## 外部分析输入与输出

以下工具仅用于显式提供的采样包。旧布局分析不能冒充当前实验采集；缺少原始轮次应报错，不能用历史均值替代新参照。随机种子可重建输入，不能重建历史内存时间曲线。

```bash
python3 基线并发/tools/import_archives.py --archives /external/archives --out /home/mxt/TeamOOM/results/imported
python3 基线并发/tools/analyze_profiles.py --analysis-root /external/capture-package --output /home/mxt/TeamOOM/results/analysis/final_analysis
python3 基线并发/tools/build_timeline.py --analysis-root /external/capture-package --analysis-dir /home/mxt/TeamOOM/results/analysis/final_analysis --output /home/mxt/TeamOOM/results/analysis/timeline
python3 基线并发/tools/plot_profiles.py --source-root /external/capture-package --analysis-dir /home/mxt/TeamOOM/results/analysis/final_analysis --plan /home/mxt/TeamOOM/results/analysis/timeline/baseline_timeline_plan.json --freeze-plan /home/mxt/TeamOOM/results/analysis/timeline/freeze_schedule.json --output /home/mxt/TeamOOM/results/analysis/plots
```

分析工具默认输出到 /home/mxt/TeamOOM/results/analysis 下，拒绝任何 Git 工作区内的输出，包括通过软链接解析到工作区的路径。原始输入和中间分析目录分别显式指定；指标中的 source 必须位于显式输入根内。旧指标中的外部绝对路径不会被静默读取。Array 排除轮次必须显式传入 `--exclude-array-round`，不再默认套用旧实验排除选择。

非破坏性检查：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`。策略测试只在临时本地仓库建立合成提交，不连接远端、不执行实际 push、不运行实验。

当前部署边界：Krita + Array + Raster + Table 仅为历史构造场景。下一阶段真实应用实例和素材尚未选择，不沿用旧时间线，不生成替代参照，不自动启动采集或压力实验。

## 2026-11-26 用户指定报告导出例外

用户明确要求将可下载报告包传到mxt_codex。仅允许codex_reports/app_candidates/TeamOOM_reports_20261126.zip，内容摘要固定在tools/git_guard.py的REPORT_ARCHIVES中；修改字节即拒绝，其他ZIP及实验素材/原始采样仍被拒绝。包内仅报告、汇总指标与曲线图，排除媒体、原始采样、日志和带签名的临时下载地址。Git hooks保持启用。
