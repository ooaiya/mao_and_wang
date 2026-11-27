# Krita 9000×9000 独立曲线任务

> 发布说明：以下为2026-11-27实验阶段的原始文字报告。本次根据用户随后“报告交付到github的mxt_codex”的明确指令，仅发布整理后的Markdown报告。文中“本轮不提交/不推送”描述此前实验执行阶段；本次报告发布不改变实验状态，也不代表已完成Krita采集。

验收状态：**INCOMPLETE（素材缺失，未启动采集）**。本轮未产生有效前台参考，不标记 VALIDATED_FOREGROUND_REFERENCE，不用于后续时间线建模。

在进入素材准备前已完成候选清理、有效资源保护核验及原 Table 十轮只读审计。此次没有启动 Krita、PeaZip、HandBrake、Table、Raster、Array 或其他实验应用，没有并发、固定启动偏移、Swap变更或采集器修改。

## 停止原因及固定素材

固定源码 `b65b76724c440d9c48738dd063b9311245aad178` 的 `前台操作/素材/README.md` 要求从原实验交接资料取得ORA；仓库仅提供规范/摘要和基于原始单层文档的生成器。已搜索 TeamOOM、OOM（含 OOM_assets 别名）、用户下载/桌面、VM-share和/tmp；未找到9000×9000基础文件或两个多层文档。可读范围中仅有受保护旧文件 `/home/mxt/OOM/assets/krita_8000_manual/blank_8000x8000.ora`，13847字节，SHA256 `1d310235030f6feaf02a84aa4636e419e19c7b653724d776908965eaaebe3054`，不是所需原始基础文档。搜索受限目录见维护目录 krita_asset_audit.json，主要为其他原实验的特权运行子目录；此次未更改权限或写入这些目录。

|目标文件（相对批次根）|固定SHA256|实际状态|
|---|---|---|
|OOM_assets/krita_rapid_9000_46/light_9000.ora|`04dca9c398803650ec04241ab66ddaa26a0f2a110fa90dc5bb6f2af6cc464182`|未找到，未声称通过|
|OOM_assets/krita_rapid_9000_46/layered_9000_46.ora|`64350f6e98ded633f6f7f198d22c02b62c19f7bed711fda38ed9ffa6f47d5c21`|未找到，未声称通过|
|OOM_assets/krita_rapid_9000_tail_07_medium/light_9000.ora|`04dca9c398803650ec04241ab66ddaa26a0f2a110fa90dc5bb6f2af6cc464182`|未找到，未声称通过|
|OOM_assets/krita_rapid_9000_tail_07_medium/layered_9000_07.ora|`408ca79750dfdb55217a63215df26e8646d2780752c74426dd87984ee16550e5`|未找到，未声称通过|

按用户附件“如果基础素材不存在……立即停止素材准备”“不得擅自更换素材……或继续下一阶段”，已停止。没有运行 prepare_layered_ora.py、prepare_handoff_config.py、正式 preflight、collect 或 validate。未建立空素材批次或伪造 assets_manifest、run目录及采样曲线。继续所需的最小资料是原始 `light_9000.ora`，SHA256必须为 `04dca9c398803650ec04241ab66ddaa26a0f2a110fa90dc5bb6f2af6cc464182`；若同时提供已验证46层和7层文件则可直接复制核验。

## 源码、配置及环境记录

临时独立副本 `/tmp/TeamOOM-krita-b65b767-20261127T061243Z`：main、固定HEAD、工作区干净。实际仓库 `/home/mxt/TeamOOM/repo`：mxt、`81f1f27d82b861b05f8a479a170035d39225fd67`、工作区干净。未执行git add/commit/push、实际main切换/重置/合并或源码改动。临时副本保留为本次停止证据，不被当作有效采集输出。

当前只读环境盘点：Ubuntu22.04.5 LTS，Linux `6.17.13-oomlab`；Krita安装版本 `1:5.0.2+dfsg-1build1`；Wayland `wayland-0`、DISPLAY `:0`；xdotool返回屏幕 `2552 1200`。这是环境盘点，**不是正式预检通过**。系统Swap仍启用，未启动Krita cgroup，因此不存在可验收的 memory.swap.current 序列。清理后可用磁盘约 11.780 GiB。

计划素材目录 `/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_medium_tail_20261127_141145`、计划配置目录 `/home/mxt/TeamOOM/runtime/config/krita_rapid_9000_medium_tail_20261127_141145`、计划采样目录 `/home/mxt/TeamOOM/data_collection/foreground_krita/rapid_9000_medium_tail_20261127_141145` 均未作为有效实验创建。没有实际适配配置；固定模板原样保留，不将其原交接VM分辨率2872×1482冒充当前2552×1200。

固定模板应采用：50ms；低压30s；46层高压打开确认后12s；正常关闭首实例并确认退出；7层中压（5个9000²加2个5400²图层）浏览30s，每5s往返缩放；tile memory67%；中压验收2–3GiB（固定字段 tail_charge_range_bytes，采样 charge/memory.current，不能偷换成整机内存或仅anon峰值）。安全阈值未调整：MemAvailable≥1610612736B、SwapFree≥322122547B、磁盘≥10737418240B、其他进程RSS≤1073741824B、最大采样缺口0.5s、cgroup上限13314398617B、全局PSI full avg10≤10、超时1800s。Krita任务若将来采集，任务Swap必须全程0，系统Swap保持启用。

## 曲线、统计和阶段验收

本轮无samples.csv、memory.current/anon/file峰值、阶段单调时钟事件或FG_RUN，均为N/A，不是0。低压、高压、首实例退出及中压阶段均未执行；素材阶段已先触发停止条件，未用smoke或旧8000素材替代，也未自动重试。无validator返回值，验收不通过。

维护记录：`/home/mxt/TeamOOM/results/maintenance/pre_krita_cleanup_20261127_141145`。Table审计为 NEEDS_RECOLLECTION：旧十轮800万行CSV/pandas与新版64批4GiB匿名缓冲的负载不一致，原数据完整保留，本轮未重采。原Raster/Array和Krita历史亦保留。

清理累计177条已审计路径，按三个删除窗口可用空间增量合计 2240110592 B（2.086266 GiB）。保留PeaZip第三轮16输入/配置/原始采样/归档验证/业务输出及曲线，HandBrake第二轮固定20秒对应全部有效资源。保留汇总 `/home/mxt/TeamOOM/results/app_candidates/retained_selected_pre_krita_20261127_141145`，ZIP `/home/mxt/TeamOOM/results/app_candidates/TeamOOM_retained_selected_pre_krita_20261127_141145.zip`；本轮不上传任何文件，不提交或推送。
