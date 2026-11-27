# 未选中候选应用清理审计

> 发布说明：以下为2026-11-27实验阶段的原始文字报告。本次根据用户随后“报告交付到github的mxt_codex”的明确指令，仅发布整理后的Markdown报告。文中“本轮不提交/不推送”描述此前实验执行阶段；本次报告发布不改变实验状态，也不代表已完成Krita采集。

状态：已完成确认归属的候选清理与保护核验；Krita素材阶段因缺少指定原始9000 ORA停止，未进入预检、采集或并发。时间批次 `20261127_141145`。

清理前 inventory_before.json 列出164条显式路径及文件数、逻辑/分配字节、应用版本/来源和归属证据。补充 inventory_supplement_before.json 先记录另外10条临时路径，apt_archive_inventory_before.json 在删除前通过DPKG包头确认3个专属缓存安装包。共177条路径；deleted_paths.json、cleanup_supplement_result.json和apt_archive_cleanup_result.json记录结果。未用通配符rm -rf、apt autoremove或大范围purge；未复制候选有效载荷作备份。

|应用|本轮操作|
|---|---|
|DBeaver25.3.5、DuckDB JDBC1.4.2.0|删除专属便携版、下载包/驱动、workspace、实验数据库/临时目录/SQL、原始采样、Parquet输出、截图、曲线和专属复现配置|
|Apache Hop2.20.0|删除专属便携版/ZIP、项目/流水线/排序临时目录/JVM专属配置、原始采样/无效中断轮、3份CSV输出、GUI截图/日志/曲线。与DBeaver共用的便携版私有JRE随双方淘汰移除；系统Java未操作|
|QGIS|应用包此前已卸载；清除剩余受干扰轮QGIS专属raw、私有桌面缓存/配置、临时目录和临时调试代码；此前系统清理文字审计保留|
|KNIME|应用/素材此前已清理；本轮清除私有桌面storage/HSTS及残余GUI截图|
|Blender、Hugin|此前已卸载并清理大体积专属资源；本轮清除4个Blender空临时目录及Hugin崩溃报告目录|
|darktable、Kdenlive|DPKG确认无已安装应用本体；清除Kdenlive私有备份/陈旧锁和3个APT缓存安装包（kdenlive、kdenlive-data、darktable）|
|混合报告|保留有效PeaZip/HandBrake单应用曲线，重新生成仅这两者的共同坐标/归一化汇总和报告ZIP，再清理含DBeaver/Hop的旧混合ZIP及专属曲线。混合JSON/CSV只保留有效条目，简短淘汰结论留下|

8个淘汰应用无DPKG已安装本体；Snap清单无这些应用，Flatpak未安装且无app目录，/opt为空；当前项目便携目录仅余受保护PeaZip。先前版本及历史删除证据仍见 results/maintenance/app_candidates_round2_cleanup、app_candidates_round3_cleanup 和先前QGIS文字审计。没有重新卸载未安装的包。

## 实际空间

主删除窗口增加 2220466176 B；临时文件补充窗口增加 126976 B；APT安装包窗口增加 19517440 B。合计 **2240110592 B（2.086266 GiB）**。这是三个实际删除前后 statvfs 可用量变化之和；并非把逻辑文件大小当作释放空间。文件系统全局值可能包含日志等正常波动，含空目录块/审计写入影响。当前可用 12648792064 B（11.780 GiB）。从任务最初盘点到当前的净可用量另见 inventory_after.json，它扣含临时源码副本、审计和新报告占用，不与删除窗口值混为一谈。

## 保留对象核验

PeaZip确认第三轮 `/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3/peazip/round_01`；16个完整原文件614728680B，128MiB字典/4线程/LZMA2 Normal/Solid8g；manifest逐文件SHA匹配；实际backend_argv吻合；原完整归档587639963B，原生完整性日志 Everything is Ok / Files16保留。

HandBrake确认第二轮 `/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2/handbrake/round_02`；原生Activity/timing记录及0–20秒配置、HEVC1080p30 Medium RF22 MKV输出保留；原输出验证598帧、20.031秒、完整解码exit0。不是旧30秒轮替代。

原始raw共有22份文件与历史SHA清单逐一相符；16个输入SHA和保留业务输出、原Krita ORA、原十轮Table归档共42项在清理前后重新摘要一致。输出项是本次前后hash一致并结合既有业务验证日志，不声称本次再次运行压缩或解码。

protected_tree_before.json记录91421个可读条目的路径/类型/大小/mtime/ctime/符号链接目标，inventory_after.json逐根确认完全相同：OOM（含OOM_assets/OOM_results/OOM_data_collection别名目标）、Page Hotness、TeamOOM baseline_assets原Raster/Table/Array/Krita、原real_cases目录、共享venv、PeaZip软件与历史raw、HandBrake配置与历史raw、17个共享输入及公共NOAA。部分OOM特权服务子目录不可读，明确列出，未更改权限或写入；不声称已遍历其内部。未删除移动覆盖这些保护路径。

共享NOAA2024压缩原件/Q1/字段说明此前已明确迁移为公共素材，不能因原下载者KNIME淘汰而删除；全部保留并在前后树指纹中验证。Qt/GDAL/Java/Python/GNOME/XWayland/AT-SPI/systemd/cgroup等共享依赖保留；Ubuntu通用签名软件源即使文件名有QGIS也不被误删。仅一份既有特权QGIS系统清理JSON作为简短文字审计保留，不是应用本体/采样或缓存。

当前保留有效汇总 `/home/mxt/TeamOOM/results/app_candidates/retained_selected_pre_krita_20261127_141145`；报告ZIP `/home/mxt/TeamOOM/results/app_candidates/TeamOOM_retained_selected_pre_krita_20261127_141145.zip` 及旁侧SHA256。不会操作用户先前下载到宿主机的副本。

## 进程、仓库及后续状态

pre_deletion_process_check.json 确认删除前候选/实验进程及相关运行服务均为空，没有杀进程。最终进程状态会另记 inventory_after_processes.json。实际仓库仍mxt、HEAD `81f1f27d82b861b05f8a479a170035d39225fd67`、工作区干净；原main和mxt_codex没有提交/推送/合并/重置。独立固定提交副本main为 `b65b76724c440d9c48738dd063b9311245aad178`，工作区干净，保留便于复查。没有源码改动，因此未运行会启动工作负载的测试或正式实验。

Table结论见 table_config_audit.md：NEEDS_RECOLLECTION，10轮旧CSV/pandas不等于指定新版shaped Table；原归档外部SHA验证通过，原地保留，本轮不重采。

Krita缺少固定SHA的light_9000.ora，高/中压ORA亦缺失，素材阶段按用户明示停止。报告 `/home/mxt/TeamOOM/results/foreground_krita/krita_collection_report_20261127_141145.md`，状态INCOMPLETE；不得把这次未启动当作有效曲线。
