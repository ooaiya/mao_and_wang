> 本次根据用户随后授权发布Markdown报告。文中“不提交/推送”描述此前实验阶段；实验结果仍为PILOT_INVALID。原始数据、素材、日志及PNG保留在VM。

# 新生成Krita素材与单轮独立采集报告

批次 `20261127_154636`。最终状态：**PILOT_INVALID（安全停止，流程不完整）**。素材结构与本地配置核验、正式环境预检均通过；唯一一轮正式Krita尝试在46层文档导入时因持续的整机内存PSI full触发原安全阈值。没有形成经过验证的完整低压→高压→中压前台参考；不得用于固定时间线或正式并发建模。

## 执行范围与版本

用户已明确取消历史素材字节SHA匹配要求，允许生成结构符合原配置的 synthetic generated assets。既有检索结论由本轮任务提供：main、mxt、mxt_codex及指定提交b65b767均没有ORA原文件。本轮依指令未重复检索或清理177条旧路径，也未生成历史素材的冒名副本。

独立源码副本 `/tmp/TeamOOM-krita-b65b767-20261127T074636Z` 固定为main / `b65b76724c440d9c48738dd063b9311245aad178`。原始生成器、配置模板、采集器和GitHub原SHA256SUMS均未修改。实际 `/home/mxt/TeamOOM/repo` 仍为mxt / `81f1f27d82b861b05f8a479a170035d39225fd67`，工作区干净。本轮未git add/commit/push/merge、切换真实仓库分支或修改GitHub main；未访问或修改OOM、原OOM_assets或Page Hotness资源；未删除原Krita/Raster/Array/Table/PeaZip/HandBrake数据。

只启动Krita应用。采集器的独立systemd user单元内包含Krita、规定的自动化/监督辅助进程；collector自身在测量边界之外，父slice另含hold辅助单元。没有启动PeaZip、HandBrake、Table、Raster、Array、并发任务或冻结调度；未计算固定启动偏移。

## 合成基础ORA生成

基础文件 `/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/generation_tmp/light_9000_source.ora`。生成脚本 generate_base_ora.py（VM本地复现脚本） 使用固定seed `20261127`：确定性x/y渐变、256/64像素棋盘、11/13像素纹理，叠加48个由局部PRNG确定的几何轮廓及斜线。不使用全分辨率随机噪声，RGB完全不透明且非空白。画布与单层PNG均9000×9000。ZIP成员为mimetype、stack.xml、mergedimage.png、Thumbnails/thumbnail.png、data/layer_00.png，mimetype第一且不压缩，内容image/openraster；ZIP时间戳固定1980-01-01，便于重建。

基础PNG 2644446 B，SHA256 `de7e4ad54ae25d6969c0b1acdead4dfa107b82445c73b0fe0f1dc898c86ae3f7`。基础ORA 5394398 B，SHA256 `87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8`。完整参数和环境版本位于 `/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/generation_tmp/generation_parameters.json`。基础生成使用Python3.10.12 / NumPy2.2.6 / Pillow12.3.0；原始分层生成器、配置、验证和采集使用现有共享venv，Pillow11.1.0、PyAutoGUI0.9.54、opencv-python4.10.0.84，与固定源码requirements相符。没有安装或更改共享依赖。

## 正式素材与结构验收

素材目录 `/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets`。通过指定提交的原 prepare_layered_ora.py 分别执行 `--layers 46`、`--layers 7 --compact-layers 2 --compact-size 5400`，返回码均0；没有重写分层逻辑。命令和生成器副本见 asset_assembly_commands.json 与 reproduction/prepare_layered_ora.b65b767.py。

|正式素材|字节|画布和实际图层|本次SHA256|
|---|---:|---|---|
|light_9000.ora（两个目录各一份）|5394398（每份）|9000×9000；1层9000×9000|`87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8`|
|layered_9000_46.ora|124404893|9000×9000；46层均9000×9000|`100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a`|
|layered_9000_07.ora|22265294|9000×9000；第0–4层9000×9000，第5–6层5400×5400|`7d7679e2072c387a207d9d393525a071f59fdfc3eaf7c491051ee402eedcc5aa`|

[逐层验收表](asset_validation.md) 与 asset_validation.json记录每个layer src、PNG实际尺寸、颜色模式和完整解码结果，包含基础源及两个light副本，共5个ORA文件、56个实际图层；每个ZIP CRC、XML、画布/图层数、所有PNG（含merged与thumbnail）均通过，两个light字节一致。原始历史SHA清单原样保留；本次实际摘要单独记录在SHA256SUMS.generated（VM本地清单，摘要见报告）。采集器前后assets_manifest相同，分析后重核五份ORA摘要仍一致。

正式目录4个ORA合计 157458983 B（含两个light副本）；加上基础源，共 162853381 B。素材批次当前全部文件逻辑字节 162899192、分配字节 162914304。PNG编码与ORA组装前均检查空间预算并保留10GiB；已有磁盘检查点均≥10GiB：任务前 11.747GiB、预检 11.569GiB、采集后 11.549GiB。原采集器未提供逐样本磁盘字段，故不将这些检查点冒充连续磁盘测量。

## 配置差异和预检

本地配置 `/home/mxt/TeamOOM/runtime/config/krita_rapid_9000_generated_20261127_154636/foreground_config.json`，由原 prepare_handoff_config.py 使用临时模板生成。临时模板只更新asset.sha256、automation.prepared_document.sha256、automation.tail_document.sha256三项。随后原生成器只适配三个素材路径、pilot.layers_dir和实际屏幕2552×1200；相对原模板共8个字段变化。config_diff_audit.json断言其他字段完全相同，原模板SHA256 `69f66692ce83cfcc978fa69860b8645116e165ac9c1cca1cff88ae4628f6c8f5`。

原参数保留：50ms；低压30s；46层文档确认打开后12s；正常关闭首实例并确认退出；第二实例打开7层中压，浏览30s、每5s往返缩放；tile memory67%。pressure_profile保持peak_reference_bytes=12884901888（12GiB）、peak_tolerance_fraction=0.04、max_low_charge_bytes=4294967296、max_low_pressure_bytes=7516192768；tail_charge_range_bytes仍为2–3GiB。原验收器将中压charge范围应用于memory.current；anon另行记录，不混用两种指标。

安全阈值保留：MemAvailable≥1610612736B、SwapFree≥322122547B、磁盘≥10737418240B、其他进程RSS≤1073741824B、最大采样缺口0.5s、cgroup上限13314398617B、全局内存PSI full avg10阈值10（PILOT持续5s触发）、总超时1800s。没有放宽阈值、缩短时长、减少图层或修改tile memory。

正式预检返回0 / ok=true / errors=[]：Ubuntu22.04.5 LTS，Linux6.17.13-oomlab，Krita5.0.2，GNOME Wayland+XWayland，DISPLAY=:0，AT-SPI probe通过、cgroup v2 memory和systemd user manager可用，无冲突进程/服务/socket，独立measurement lock可用。预检MemAvailable 13.051GiB、SwapFree 1.748GiB、全局PSI full avg10=0。运行用户uid/euid均1000（mxt），未sudo运行采集器。系统Swap一直启用。

## 唯一一次采集过程

原入口 collect_krita.py collect --operation krita --rounds 1；无smoke/resume。调用标记 collect_invocation_marker.json阻止重复尝试，collect_invocation.json保存准确命令与起止时间。DATA_ROOT为 `/home/mxt/TeamOOM/data_collection/foreground_krita/rapid_9000_generated_20261127_154636`；实际run为 `/home/mxt/TeamOOM/data_collection/foreground_krita/rapid_9000_generated_20261127_154636/20261127T075412Z-ddd146dd9183414c8108dc5edcf5c04e/c5aea221ac9f440d9e9366b600251210`。采集返回码1，独立validate返回码1，status=PILOT_INVALID，valid=false、formal_eligible=false。

低压单层文档已成功打开，浏览完成 30.001246926s。随后提交46层高压文档，仍处于导入阶段时，全局内存PSI full avg10从t=232.328169s起达到或超过10；采集器在t=237.399454s按持续5s规则发出安全停止请求。最大观测PSI full avg10=12.77，Krita子域PSI full avg10最大2.91；这两个域分别记录。首个停止原因为 `RuntimeError: sustained severe global memory PSI full`。

没有HIGH_DOCUMENT_OPEN_DONE确认，没有完整12s高压窗口；没有首实例正常结束确认，没有第二个中压实例/30s中压窗口。GUI随后尝试Ctrl+Q，出现约9.75s的退出等待超时；GRACEFUL_CLEANUP_DONE.ok=false。采集器后续服务清理完成，metadata.cleanup_ok/cooldown_ok/journal_ok均true、operations_verified=false，采集后无Krita进程或本轮活动单元。不能把安全停止后服务清理作为正常业务完成或自然释放。

## 实测部分曲线与统计

图表：独立Krita部分曲线（VM本地文件 `/home/mxt/TeamOOM/results/foreground_krita/generated_asset_krita_20261127_154636/krita_memory_partial.png`）。

曲线只使用Krita独立子cgroup原样采样，不把整机内存或父slice替代成Krita曲线；无平滑、时间拉伸、重采样或补零。T0为metadata.origin_monotonic_ns。蓝色区域是已完成低压浏览；橙线是高压文件提交；红线是安全停止；红色尾段属于停止处理。绿色高压参考带仅显示原配置参数，没有伪造目标或高压实测平台。

|指标|停止请求前|完整已记录窗口（含停止处理）|
|---|---:|---:|
|Krita样本数|4732|4922|
|memory.current观测峰GiB|6.881397|7.129616|
|观测达峰时刻s，自T0|237.303758|247.918587|
|T90 s，自T0|213.166971|218.417694|
|各自观测峰95%阈值以上累计s|15.679774|16.207388|
|anon观测峰GiB|6.820168|7.067455|
|file观测峰GiB|0.164963|0.164963|

内核memory.peak最终读数为 7655628800 B（7.129860GiB），与离散memory.current采样最大值的微小差异保留。95%累计时长按相邻实测点线性阈值交点计算，**不是已完成高压平台时长**；不同列各用自身部分记录的观测峰作阈值，不代表任务最终峰值。各分量峰可能不同时，不能简单相加。

自然释放：**未得到正常业务完成后的自然释放曲线**。高压尚未确认打开即中止，末段仍在增长；安全清理不替代自然释放。中压2–3GiB范围及原12GiB±4%高压窗口均无法验收，不能根据这段中止曲线推断完整导入后的最终峰值。

图表：环境指标（VM本地文件 `/home/mxt/TeamOOM/results/foreground_krita/generated_asset_krita_20261127_154636/environment_partial.png`）。

Krita子cgroup memory.swap.current所有4922个样本和结束快照均0；父slice最大77824B（76KiB），父域额外含hold等辅助进程，单独标明。系统Swap启用，观测期系统vmstat pswpout增加1568页、pswpin增加8页，页大小4096B；不把父域或全机Swap误记为Krita任务Swap。最低MemAvailable 5.903214GiB、最低SwapFree 1.742958GiB。Krita和parent的memory.events max/oom/oom_kill增量均0，全局oom_kill增量0。触发项为全局持续PSI，不能将未触发的OOM/内存上限记为失败原因。

图表：采样间隔（VM本地文件 `/home/mxt/TeamOOM/results/foreground_krita/generated_asset_krita_20261127_154636/sampling_intervals.png`）。

Krita采样间隔：中位 50.053718ms，均值 50.378980ms，P95 54.058216ms，P99 58.402699ms，最大 151.772086ms；超过0.5s的缺口0个。原始时间戳保留，无人为补样。

## 阶段时间戳

|事件|阶段|状态|relative_s|monotonic_ns|Asia/Shanghai|
|---|---|---|---:|---:|---|
|phase_start|启动Krita|RUNNING|0.075505|266455845253673|2026-11-27T15:54:15.961588+08:00|
|KRITA_PROCESS|||12.587106|266468356855034|2026-11-27T15:54:28.473185+08:00|
|phase_end|启动Krita|PASS|12.587307|266468357056162|2026-11-27T15:54:28.473385+08:00|
|phase_start|核对主窗口布局|RUNNING|12.587380|266468357128634|2026-11-27T15:54:28.473457+08:00|
|WINDOW_LAYOUT_READY|||12.677106|266468446854879|2026-11-27T15:54:28.563185+08:00|
|phase_end|核对主窗口布局|PASS|12.677244|266468446992961|2026-11-27T15:54:28.563322+08:00|
|phase_start|打开素材文件|RUNNING|12.677308|266468447056808|2026-11-27T15:54:28.563385+08:00|
|DOCUMENT_OPEN_START|||12.677415|266468447164104|2026-11-27T15:54:28.563493+08:00|
|DOCUMENT_OPEN_DONE|||47.302941|266503072689786|2026-11-27T15:55:03.189020+08:00|
|phase_end|打开素材文件|PASS|47.304292|266503074041529|2026-11-27T15:55:03.190371+08:00|
|phase_start|缩放画布|RUNNING|47.305013|266503074761676|2026-11-27T15:55:03.191091+08:00|
|PRE_IMPORT_REVIEW_START|||48.191369|266503961118460|2026-11-27T15:55:04.077448+08:00|
|PRE_IMPORT_REVIEW_DONE|||78.192616|266533962365386|2026-11-27T15:55:34.078695+08:00|
|phase_end|缩放画布|PASS|78.193045|266533962793771|2026-11-27T15:55:34.079123+08:00|
|phase_start|打开预组装多图层文档|RUNNING|78.193115|266533962863759|2026-11-27T15:55:34.079193+08:00|
|HIGH_DOCUMENT_OPEN_START|||78.439858|266534209606677|2026-11-27T15:55:34.325937+08:00|
|HIGH_DOCUMENT_SUBMITTED|||81.724540|266537494289382|2026-11-27T15:55:37.610620+08:00|
|COLLECTOR_SAFETY_STOP_REQUEST|||237.399454|266693169203577|2026-11-27T15:58:13.285532+08:00|
|phase_end|打开预组装多图层文档|STOPPED|237.594580|266693364329573|2026-11-27T15:58:13.480660+08:00|
|GRACEFUL_EXIT_DIAGNOSTIC|||247.644049|266703413797908|2026-11-27T15:58:23.530128+08:00|
|GRACEFUL_CLEANUP_DONE|||247.644551|266703414300194|2026-11-27T15:58:23.530630+08:00|


所有结构事件含单调时钟时间戳；详细原事件位于run/krita/phase-events.jsonl，派生完整表位于phase_timeline.json与[phase_timeline.md](phase_timeline.md)。未发生的高压完成/中压事件保持缺失，没有补造。

## 原验证器结论与证据

原验证器独立返回PILOT_INVALID，错误去重如下；完整原顺序和重复条目保留于validate_official.log、run/summary.json：

- RuntimeError: sustained severe global memory PSI full
- incomplete operation/cleanup/cooldown/journal evidence
- sustained severe PSI
- incomplete operation exits
- FileNotFoundError: [Errno 2] No such file or directory: '/home/mxt/TeamOOM/data_collection/foreground_krita/rapid_9000_generated_20261127_154636/20261127T075412Z-ddd146dd9183414c8108dc5edcf5c04e/c5aea221ac9f440d9e9366b600251210/krita/krita-post-process.json'

其中合并错误“incomplete operation/cleanup/cooldown/journal evidence”由operations_verified=false等不完整流程导致；metadata显示cleanup、cooldown和journal记录已通过，不将该合并消息误读为全部子项失败。缺少krita-post-process.json与中压第二实例未执行一致。

所需summary.json、metadata.json、config.snapshot.json、assets_manifest.json、samples.csv、krita/phase-events.jsonl、manifest.sha256均存在。分析后按原verify_seal核验run的完整manifest通过，全部生成ORA实际SHA再次通过；**证据完整性通过不等于业务流程通过**。没有修改已封存raw，也没有删除失败轮次。保留预检、唯一采集与独立验证的日志和退出码。

## 交付与停止

- 本报告：[execution_report.md](execution_report.md)。
- 素材验收：[asset_validation.md](asset_validation.md)、asset_validation.json、SHA256SUMS.generated（VM本地清单，摘要见报告）。
- 配置审计：config_diff_audit.json、原临时模板reproduction/template.generated-hashes.json。
- 实测统计：observed_metrics.json；三张曲线PNG；阶段时间戳表。
- 复现：reproduction中的基础生成、原生成器副本、验收、配置、单次调用及分析脚本；正式运行始终直接使用固定提交原脚本。
- 原始run：`/home/mxt/TeamOOM/data_collection/foreground_krita/rapid_9000_generated_20261127_154636/20261127T075412Z-ddd146dd9183414c8108dc5edcf5c04e/c5aea221ac9f440d9e9366b600251210`，只读保留。

按本轮停止条件，安全停止后未继续任何实验、未重试、未改参数。只做必要只读验收、离线图表与报告。生成素材结构可复用；本条PILOT_INVALID曲线不可作为已验证前台参考。未上传任何素材、CSV、结果或日志至GitHub，本轮未提交或推送。
