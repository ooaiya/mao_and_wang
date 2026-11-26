# TeamOOM 第二轮真实后台应用筛选执行报告

批次：`20261126_142729_gui_round2`。执行日期：2026-11-26。所有数值来自本轮真实GUI业务操作及实际cgroup采样；这是探索性筛选，不是正式对照或并发实验。

四个候选均已取得真实输出验证通过的完整采集。HandBrake最接近Array；PeaZip提高了匿名工作集，但仍部分匹配Raster；KNIME成功完成真实列转换，却没有Table要求的自然逐步释放。当前没有足够证据确定三个最终后台应用，不能强行指定。

## 最终有效轮次

| 应用 | 实际配置 | 峰值GiB | 匿名峰值GiB | T90s | 95%平台s | 释放形态 | 耗时s | 完成情况 | 对应目标 | 筛选结论 |
|---|---|---:|---:|---:|---:|---|---:|---|---|---|
| peazip | 17文件；7z/LZMA2 Normal；128MiB；4线程；Solid8g | 5.547 | 3.288 | 154.62 | 17.75 | 工作进程结束边界集中释放；文件缓存残留 | 177.86 | 正常，输出PASS | Raster | PARTIAL_MATCH |
| blender | Classroom；CPU Cycles PATH；1600×900；12spp | 0.904 | 0.899 | 38.61 | 33.47 | 结束边界下降，再少量释放；Render Result驻留 | 88.19 | 正常，输出PASS | Array（备选） | PARTIAL_MATCH |
| handbrake | BBB 0–20s；1080p30；x265 Medium RF22；MKV | 0.990 | 0.891 | 5.49 | 48.95 | 结束时集中释放，非阶梯释放 | 55.40 | 正常，输出PASS | Array（优先） | PARTIAL_MATCH |
| knime | NOAA2024Q1；9原生节点；Columnar；Xmx4096m | 8.021 | 6.782 | 163.47 | 22.23 | 完成后约262秒无明显自然释放 | 196.24 | 正常，输出PASS | Table | PARTIAL_MATCH |

T90为GUI提交后首次达到本轮计算峰值90%的实际采样时刻，不是全局最大值时刻。耗时按最后一次真实GUI提交至完成证据计算，包含原生调度开销；不包含加载、准备及完成后的停留。95%平台仅统计计算窗口，不能把完成后仍驻留的262秒算作计算平台。

## 清理与环境验收

已删除Hugin专属AppImage/解包程序与实验数据；已模拟并卸载darktable、Kdenlive两个APT主包。清理124个专属路径，观测磁盘已用从64,168,513,536降至61,172,097,024字节，净减少2,996,416,512字节（约2.79GiB）。不确定的Qt/KDE、MLT、Frei0r、相机库等共享依赖保留，未运行autoremove。

原17个PeaZip共享输入已经移动至shared_assets：BBB、Tears of Steel、14张RAW及原SHA清单，共1,198,502,763字节；逐文件大小及SHA256复核通过，未复制扩大。保留Krita、baseline、原三条曲线源码、预测器、调度器及其他研究项目。Agent327专属素材已删除，仅保留10.331GiB安全中止结论；Classroom完整链接资产保留。旧PeaZip/Blender/HandBrake有效采样保留，旧混合分析由仅保留应用的历史对比取代。详细证据在`cleanup_summary.md`及原maintenance目录。

实测MemTotal16,728,559,616字节，约15.58GiB；4vCPU；现有Swap2,147,479,552字节；Ubuntu22.04.5/Linux6.17.13-oomlab。未修改虚拟机、内核或Swap。所有应用memory.max/high均为max，无4/8GiB人为上限。所有计算串行，后台证据窗口位于应用cgroup之外。结束验收无teamoom-app/observer活动单元，Krita/HandBrake/ffmpeg仍安装。

## 新旧与补采指标

| 应用/轮次 | 总峰值 | 匿名峰值 | 文件峰值 | T90s | 全局达峰s | P95累计s | 耗时s |
|---|---:|---:|---:|---:|---:|---:|---:|
| peazip/old | 2.402 | 1.287 | 1.091 | 85.00 | 100.50 | 12.35 | 100.95 |
| blender/old | 0.821 | 0.816 | 0.002 | 4.91 | 76.77 | 40.61 | 78.38 |
| handbrake/old | 1.005 | 0.942 | 0.056 | 4.90 | 268.29 | 197.15 | 269.65 |
| peazip/initial | 3.537 | 2.396 | 1.108 | 140.05 | 162.72 | 20.01 | 163.04 |
| handbrake/initial | 0.949 | 0.895 | 0.049 | 3.68 | 72.59 | 69.01 | 73.04 |
| peazip/new | 5.547 | 3.288 | 2.224 | 154.62 | 176.12 | 17.75 | 177.86 |
| blender/new | 0.904 | 0.899 | 0.003 | 38.61 | 82.55 | 33.47 | 88.19 |
| handbrake/new | 0.990 | 0.891 | 0.093 | 5.49 | 55.25 | 48.95 | 55.40 |
| knime/new | 8.021 | 6.782 | 1.179 | 163.47 | 196.20 | 22.23 | 196.24 |

`old`为第一轮有效配置：PeaZip32MiB；Blender1280×720/16spp；HandBrake0–120s。`initial`为本轮首次有效的PeaZip64MiB和HandBrake0–30s；`new`为最终选用的补采及其余两应用。全部首轮数据保留，选择路径见selected_rounds.json。总/匿名/file峰值可能不同时，不能简单相加。

### PeaZip：匿名增长改善，文件缓存仍影响形态

使用同17个原文件；11.4.0 GTK2便携GUI，实际后端7-Zip(z)26.04 x64，以两个归档验证日志中的版本为准，先前手写25.01已更正。128MiB实际argv为`-m0=LZMA2 -mmt=4 -mx5 -md=128m -mfb=32 -ms=8g`，无独立7z压缩替代GUI。GUI未显示可读内存估算，未捏造估算值。64MiB首次有效轮因原生完成窗口自动退出，自然释放观察只有0.924秒，明确标记censored。补采仅把原生reporting策略2改0，使Done结果窗口正常保留；后端仍自然结束，未持有业务缓存。

匿名峰值由旧1.287→64MiB的2.396→128MiB的3.288GiB，真实工作集提高。128MiB匿名T90=50.36秒、匿名95%平台107.25秒；后期大部分总曲线台阶来自file，file峰值2.224GiB。总T90=154.62秒、总P95=17.75秒不能误读成匿名工作集持续增长至最后。文件缓存记账受前序热缓存与页归属影响，未drop_caches，不能把file变化全归因于字典。

7z退出边界匿名内存在约1秒内从约3.29GiB降至0.027GiB，GUI仍保留；91.39秒后file仍2.224GiB，总残留2.281GiB。工作进程消失观察稍晚于释放，故completion-to-tail仅0.0005GiB漂移、名义20.41秒release90不具业务释放意义。核心释放发生于真实工作结束边界，不是关闭GUI造成；见peazip_worker_boundary_release.json及完整图。字典调整更接近Raster匿名量级，但增长/平台时间与阶梯成因仍不一致，保留PARTIAL_MATCH。

### Blender：提高分辨率后，Array匹配弱于HandBrake

2.92.0/Classroom原场景，CPU Cycles PATH，1600×900/100%/12spp/frame1，配置脚本不调用render，GUI F12提交。PNG完整解码为1600×900 RGBA。匿名峰值0.899GiB比旧0.816GiB提高有限；初期快速建立大部分工作集，后续缓慢增长使严格T90延至38.61秒。不能根据Samples直接推断内存变化，也不能因全局达峰82.55秒就把全部分配解释成慢增长。

完成前后先集中下降，再约6.52秒释放到本次自然尾部；完成时0.662→残留0.548GiB，完成后下降17.21%，峰值到自然残留下降39.32%。55.27秒自然观察后正常关闭。原生场景和Render Result存在驻留，缺少理想Array阶梯下降；作为备用候选，当前优先级低于HandBrake。

### HandBrake：20秒改善平台，但没有修复集中释放

1.5.1/x2653.5+1-f0c1022b6，BBB1080p30，Medium/RF22，Matroska，30PFR，选项`strong-intra-smoothing=0:rect=0:aq-mode=1`。0–30秒首次有效：峰值0.949GiB、T90=3.68秒、P95=69.01秒；唯一正常时长补采0–20秒：0.990GiB、T90=5.49秒、P95=48.95秒，与Array1.017GiB/45.70秒接近。源视频起始PTS为6000/90000秒，0–20秒实际编码和复核均598帧、20.031秒；0–30秒898帧、30.021秒，不用理想帧数强行改写原生结果。

原生日志完成15:52:22（Asia/Shanghai）按墙钟/单调时钟锚点映射，秒级精度±约1秒；观察器事件原样保留。补采完成至自然尾部下降67.04%，残留0.326GiB，集中下降约在1秒内，计算release90=0.15秒受日志秒级精度约束，不能声称0.15秒的测时精度。没有Array阶梯释放，因此仍是PARTIAL_MATCH，不能仅凭峰值与平台直接MATCH。

### KNIME：真实Table业务成功，生命周期未匹配

官方5.5.3便携版、自带JRE17、Xmx4096m、Columnar堆外缓存GUI默认4095MB、默认job manager，无Streaming/显式GC/逐节点Reset。工作流自身也明确保存ColumnarBackend，不能只看全局首选项。ModernUI Chromium初始化卡点改用真正经典GUI；9个原生节点通过GUI Shift+F7 Execute All执行，未用BatchApplication或Python节点。发行版无Parquet扩展，采用任务允许的原生CSV Writer回退。

完整2024年Medium共38,455,100行，先实际执行，650.37秒触发MemAvailable<2GiB保护；峰值11.689GiB，匿名11.007GiB，整机最低1.975GiB，cgroupSwap峰值0.224GiB，系统Swap峰值0.753GiB；系统换出182,658页。OOM计数未增加。该轮标记SAFETY_ABORT，原始曲线与失败证据完整保留，不列为成功。

随后取真实连续2024-01-01至03-31子集9,579,563行，仅加表头/筛日期，业务转换仍全部由KNIME完成：Reader→列选择→日期数值类型→质量/观测类型过滤→DATA_VALUE/10→正确单位→站点/日期/要素排序→CSVWriter。输出5,476,377行、265,646,744字节。排除非所选要素4,096,689行、所选要素中质量异常6,497行；全部要素质量标记共11,994行，统计口径分别列明。逐行类型、单位、数值、排序及输入输出记录指纹核验通过。

Q1耗时196.24秒，峰值8.021GiB、匿名6.782GiB、T90=163.47秒，P95=22.23秒。完成后约261.68秒内存8.021→8.025GiB（微增，无自然释放），直至app_close才下降；这262秒包括独立流式结果核验，不属于计算耗时或计算平台。满足慢增长的部分特征，缺少Table逐步释放。峰值高并非单独淘汰原因；主要障碍是内存生命周期，因此按任务要求PARTIAL_MATCH。

## 四个应用对全部三个目标

| 应用 | Raster | Table | Array | 主要依据 |
|---|---|---|---|---|
| peazip | PARTIAL_MATCH | NO_MATCH | NO_MATCH | 匿名内存有真实慢增长并集中释放，但总曲线后段阶梯主要来自file；匿名平台107.25s过长，总T90达154.62s；保留探索，不作为已验收Raster替代 |
| blender | NO_MATCH | NO_MATCH | PARTIAL_MATCH | 初期快速增加后仍缓慢增长，绝对T90为38.61s；存在渲染结果驻留及集中/短尾释放，较HandBrake弱；保留备用 |
| handbrake | NO_MATCH | NO_MATCH | PARTIAL_MATCH | 快速增长、约1GiB、48.95s平台接近Array，但自然下降集中而非阶梯；优先保留Array候选，尚非完整MATCH |
| knime | NO_MATCH | PARTIAL_MATCH | NO_MATCH | 具备实际列式读取转换排序及慢增长，但中间表/堆驻留导致完成后不释放；全年安全中止，Q1可独立完成；不能直接替代Table |

原目标只有用户提供的峰值/全局达峰/P95/增长释放形态，当前baseline目录未找到可归属的目标原始CSV。不生成原始目标时间序列、DTW或相关系数。参考为Raster3.819GiB/33.08s/38.60s（慢阶梯、集中释放）；Table4.022/33.55/38.15（慢连续、逐步释放）；Array1.017/3.22/45.70（快增长、阶梯释放）。用户提供的目标3.22秒是全局峰值，不能当作目标T90数值。

归一化扣除最后提交前1秒中位基线，再按该应用计算增量峰值缩放0–1；只用于形态观察，仍保持真实秒轴，不伸缩时间，不替代真实内存预算。独立全生命周期图保留加载/提交/完成/关闭/退出；公共对比视窗取提交前2秒至完成后60秒，全生命周期图另展示更长自然观察。

## 实际采样质量与安全

| 应用 | 计算样本数 | 间隔中位ms | P95ms | 最大ms | >100ms缺口数 | 最低MemAvailableGiB | 应用Swap峰值GiB | 系统换入/出页（全轮） |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| peazip | 3556 | 50.006 | 51.969 | 82.133 | 0 | 9.679 | 0.000 | 232/0 |
| blender | 1763 | 49.997 | 50.925 | 74.715 | 0 | 11.773 | 0.000 | 1/0 |
| handbrake | 1095 | 50.010 | 51.120 | 672.465 | 1 | 12.088 | 0.000 | 33090/0 |
| knime | 3893 | 50.006 | 51.132 | 1116.654 | 4 | 6.029 | 0.000 | 3300/0 |

标称50ms，不保证每个间隔均50ms。HandBrake补采存在一次672ms计算区间缺口；KNIME Q1有4次>100ms，最大1117ms，平台和穿越时间受实际采样间隔限制，没有插值填缺。旧PeaZip与旧HandBrake缺少cgroupSwap/pswpin/out字段，均报告unavailable，不补零冒充。

所有最终有效轮无系统/cgroup OOM kill、应用cgroupSwap均0；系统全轮有真实换入，主要是既有进程/界面页恢复，不能说“整机没有交换活动”。保持前序缓存与Swap状态，不通过清缓存/重设Swap制造基线。CPU/内存CPU及IO PSI在原始CSV中；process_tree记录实际GUI/JVM/7z子进程，逐条归属核验通过，采集器独立服务未混入。KNIME Medium安全停止有实际交换与压力，详见失败统计，不与有效Q1合并。

## 输出、素材与复现证据

PeaZip128MiB归档1,170,523,123字节，7z t完整性通过，17文件1,198,502,763字节；64MiB输出同样通过。Blender PNG完整解码。HandBrake两次视频ffprobe+全解码通过。KNIME Q1逐行全量核验通过，含输入/输出fingerprint及质量剔除统计。所有业务输出留在outputs，未上传Git。

软件/素材/参数详见software_assets_parameters.json；本地原始文件清单SHA256、下载记录与官方校验保留在各assets/manifests及reproduction。Classroom官方zip SHA256=`0f0ecc58d45f12b2f4272a53e2d8e69135518e16e956b118f10c20d8dcfdf5e6`。KNIME软件官方与实测SHA256均=`015464eaa916544f41c0e369f48563328bb7e86f1d1f929588fb338f200790cd`。NOAA实际下载gzipSHA256=`97ea530b4e63fc6ca217ff34bfe55002a94bebea648e6c8f6f4f6522ecbaba90`；Q1输入SHA256=`236a8bf51416d4483f6376e5039020651f3df12c2c87827ad209e8027e9f436e`。NOAA可持续修订，此哈希仅标识本次快照。

GUI操作与自动化说明见reports/reproduction.md，逐次动作/阶段事件在每轮gui_actions.jsonl及phase_trace.jsonl。启动命令/cgroup限额在environment.json与ancestor_limits.json，原始数据task_memory.csv及process_tree.csv。KNIME原生未执行工作流、实际ini和Columnar截图在reproduction，未将中间表保存进交付包。

局部失败保留：PeaZip路径框快捷键失效导致两次未启动后台的提交；KNIME ModernUI卡点、原生XML字段/日期/Math配置修复、全局Columnar未自动转换旧workflow、非致命FSLocation警告曾被误判失败、Q1保存焦点使首个执行动作无效；均有追加更正，原始行不删改。Medium真实安全停止始终保留。HandBrake原生日志目录修正与事件时长笔误已说明。详见reports/failures_and_deviations.md，未无限重试同一失败配置。

### 关键曲线（文件随本地报告包交付）

- `analysis/01_peazip_before_after.png`

- `analysis/02_blender_before_after.png`

- `analysis/03_handbrake_before_after.png`

- `analysis/04_knime_memory_curve.png`

- `analysis/05_four_apps_common_scale.png`

- `analysis/06_four_apps_normalized.png`

- `analysis/07_four_apps_anon_file.png`

- `analysis/08_raster_candidate_comparison.png`

- `analysis/09_table_candidate_comparison.png`

- `analysis/10_array_candidate_comparison.png`

- `analysis/11_parameter_supplements.png`

- `analysis/12_knime_medium_safety_abort.png`

## 下一阶段建议与明确答复

1. Hugin/darktable/Kdenlive专属部署、数据、配置与进程已清理；共享依赖保留。
2. 清理观测净释放2,996,416,512字节，约2.79GiB。
3. 保留应用共享17文件大小与SHA256完整，BBB与Classroom均可用。
4. 四候选均完成真实GUI业务；KNIME全年失败与Q1成功分别保留。
5. 已取得四条本轮完整有效曲线，另保留PeaZip64MiB/HB30s首轮及KNIME全年失败曲线。
6. PeaZip匿名工作集更接近Raster，但file台阶、平台与时序仍不一致，部分匹配。
7. HandBrake20秒比本轮Blender更接近Array；集中释放差异仍未解决。
8. KNIME具备Table慢增长与列式业务特征，但缺乏任务完成后的自然逐步释放。
9. 优先保留HandBrake；PeaZip继续作为Raster探索；Blender备用；KNIME保留真实ETL结果与配置，暂不作为最终Table替代。
10. 需要新增Table候选。优先试Apache Hop GUI原生CSV→类型/Calculator→排序→文件输出：其正式流水线具备真实转换节点和阶段缓冲生命周期，值得实测；但JVM驻留与流式低工作集仍是风险，未承诺自然逐步释放。[官方流水线说明](https://hop.apache.org/manual/latest/pipeline/pipelines.html)、[原生Sort Rows](https://hop.apache.org/manual/latest/pipeline/transforms/sort.html)。另可试DBeaver GUI+DuckDB真实CSV类型/计算/排序→Parquet导出；避免把整个结果集固定在GUI表格，观察原生查询缓冲释放。[DBeaver官方导出](https://dbeaver.com/docs/dbeaver/Data-export/)、[DuckDB官方Parquet](https://duckdb.org/docs/stable/data/parquet/overview)。这两个仅为下一轮待测候选，释放形态为待验证假设。
11. 当前不具备确定最终三个后台应用的条件。没有完整MATCH，不接入HistoricalLookup，不计算固定偏移，不运行三组正式并发/串行/冻结实验。

## 测试、Git与获取结果

本轮执行`PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/teamoom-tests /home/mxt/TeamOOM/runtime/venv/bin/python -m unittest discover -s tests -v`，30项全部通过，包括采集阶段选择、长准备停留隔离、T90/基线、失败更正保护、真实气象核验、路径边界与Git hooks策略。没有沿用上一轮通过数。

代码提交mxt；执行汇报提交mxt_codex，main固定不变，hooks启用，不force push。新ZIP仅保存在results，不扩展旧报告ZIP的固定哈希Git例外，不上传采样、媒体、输出、日志或软件。

结果目录：`/home/mxt/TeamOOM/results/app_candidates/20261126_142729_gui_round2`；原始采样：`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_142729_gui_round2`。每个app/round下保留CSV；首轮和失败轮不被覆盖。

交付包为同级`TeamOOM_round2_20261126_142729_gui_round2_reports.zip`，包含报告、统计表、必要配置复现证据和全部关键曲线；排除大素材、业务输出、原始采样、原生运行日志和软件。另提供SHA256和包内容清单。

`/mnt/hgfs/VM-share`存在但当前是根ext4上的不可写目录，不是已挂载HGFS。未以sudo创建伪共享或强行改权限。可从宿主机终端获取完整报告包：

```bash
scp mxt@192.168.50.100:/home/mxt/TeamOOM/results/app_candidates/TeamOOM_round2_20261126_142729_gui_round2_reports.zip .
scp mxt@192.168.50.100:/home/mxt/TeamOOM/results/app_candidates/TeamOOM_round2_20261126_142729_gui_round2_reports.zip.sha256 .
```

共享目录恢复挂载且可写后，也可在VM复制并核对：

```bash
cp /home/mxt/TeamOOM/results/app_candidates/TeamOOM_round2_20261126_142729_gui_round2_reports.zip /mnt/hgfs/VM-share/
sha256sum /home/mxt/TeamOOM/results/app_candidates/TeamOOM_round2_20261126_142729_gui_round2_reports.zip /mnt/hgfs/VM-share/TeamOOM_round2_20261126_142729_gui_round2_reports.zip
```

无操作停留只影响它发生时的阶段。如果发生在提交前，已从计算窗口排除；发生在完成后，属于自然驻留观察；若发生在计算中则其期间真实曲线仍保留。独立systemd采集器持续运行，不因对话没有操作而自动停采，但也不能仅凭“采集器在运行”保证每个50ms间隔无缺口。本轮已按实际间隔报告缺口，不把停留算作任务工作量。已淘汰Kdenlive不重跑，其专属数据按本轮授权清理，简要历史结论保留。

本轮代码提交：`15a29291747b18b546fe2af704b037f53a445695`；main核验：`b65b76724c440d9c48738dd063b9311245aad178`（未变）。

本分支只保存Markdown汇报。图像、统计JSON/CSV、工作流与ZIP保存在上述results路径；没有将原始采样、输出或新报告ZIP加入Git。
