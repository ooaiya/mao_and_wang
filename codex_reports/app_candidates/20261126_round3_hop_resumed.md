# 第三轮真实后台应用筛选：Hop续接完成

批次`20261126_170421_gui_round3`。2026-11-26（Asia/Shanghai）从DBeaver已完成之后续接，只重采Hop，未重做清理、PeaZip、DBeaver或HandBrake。结果目录`/home/mxt/TeamOOM/results/app_candidates/20261126_170421_gui_round3`；原始采样`/home/mxt/TeamOOM/data_collection/app_candidates/20261126_170421_gui_round3`。完整选取路径见selected_rounds.json，HandBrake引用第二轮固定20秒数据。

## 筛选结果

保留PeaZip Medium作为Raster候选，固定保留HandBrake20秒作为Array候选。DBeaver和Hop的本操作均不满足Table生命周期；两者中Hop阶段变化更多，但不能据此认定匹配。**最终三个后台应用尚不能确定，缺少Table应用。** 未为凑齐三个而扩大峰值或调整GC；未启动正式并发、时间线计算或修改HistoricalLookup及冻结调度。

|应用|总峰GiB|匿名峰GiB|总/匿名T90秒|总/匿名95%平台秒|全局峰秒|采集窗口秒|结论|
|---|---:|---:|---:|---:|---:|---:|---|
|peazip|3.832|3.263|84.76/42.69|8.20/37.31|95.91|96.48|retain|
|handbrake|0.990|0.891|5.49/5.49|48.95/49.10|55.25|55.40|retain_fixed|
|dbeaver|1.367|1.291|26.88/26.88|1.05/1.10|28.23|28.38|reject_current_operation|
|hop|1.759|1.519|30.76/9.81|5.60/6.70|34.51|61.03|reject_current_operation|

T90与95%平台均为计算窗口内绝对内存阈值，GUI基线不扣除；归一化图另外按提交前1秒基线扣除增量，无时间拉伸。95%平台是阈值以上累计时长，最长连续时长另存JSON，不是肉眼判断的平稳段。匿名峰与file峰不一定同一时刻，总峰不能简单由两个分量峰相加。

## 业务与阶段证据

PeaZip使用16个完整原有文件，614,728,680字节（586.25MiB），含BBB视频、14个RAW和原有小型校验清单。原17文件均保留，没有复制或填充。7z完整性检查Everything is Ok。LZMA2 Normal、128MiB、4线程、solid8g不变。

DBeaver25.3.5 + DuckDB1.4.2/JDBC1.4.2.0，4线程，SET memory_limit=6GB（原生显示5.5GiB），专属temp目录，Temurin21.0.8+9。GUI COPY：CSV类型转换、质量筛选、单位换算、站点日期元素排序、Parquet输出11,671,664字节。原生查询延迟25.546秒；GUI提交至profiling完成观察28.377秒，二者不能混用。全部5,476,377行验证PASS，Q1日期、字段、原值、/10转换、单位、排序和双指纹全部通过。保留原生完成截图与自然释放尾段。

Hop2.20.0，独立项目及配置，复用同一个Temurin JRE，无系统Java修改。2GiB正常JVM堆、排序缓冲1,000,000行、默认本地引擎，各节点1份。真实输入9,579,563行；质量/元素筛选排除4,103,186行；输出5,476,377行（CSV表头另1行），221,835,714字节。最终原生流水线59.962秒；GUI提交至fd关闭完成观察61.028秒，关闭观察不确定性约0.516秒。8个节点全部成功，截图hop_corrected_success_metrics.png含实际节点计数。全量业务核验见reports/hop_Q1_verification.json，PASS后才纳入本表。所有行均校验数值及站点/日期/元素排序，输出记录指纹与同一Q1输入和DBeaver完全相同。

Hop在GUI启动后立即切到独立X11窗口，截图hop_corrected_background.png和阶段事件确认后台运行。计算完成后继续自然观察249.64秒，再经GUI退出；未重置节点、显式GC、清缓存、增加业务sleep或人为数组。读取外部验证脚本在计算结束后运行，不属于应用cgroup。JVM匿名内存是整应用实际驻留观测，**不是Java heap-used遥测**，不可把Xmx视为实际峰值或整应用限额。

## 排除记录与修复

hop/round_01包含用户个人时间暂停，明确不是程序错误；原始文件不截断、不拼接，invalid_capture.md标记排除。hop/round_02_resumed的GUI和77.365秒原生运行成功，但独立核验发现236/10→23.0、278/10→27.0，业务错误，排除。保留失败日志reports/hop_round02_failed_verification.log及完整原始采样。

修复只涉及原生Calculator的业务类型：使用Number常量0.1在乘法左侧，右侧保留Integer DATA_VALUE。例如236→23.6、278→27.8。Hop官方文档说明Calculator采用左操作数类型，声明Number结果不会提前改变算术类型。最终round_03_corrected保持Q1规模、堆、缓冲和引擎不变。新增整数截断回归验证，完整测试34项通过。来源：[Apache Hop Calculator](https://hop.apache.org/manual/latest/pipeline/transforms/calculator.html)。

## 曲线判断

PeaZip原第二轮：总峰5.547GiB、匿名峰3.288GiB、匿名T90 50.36秒、匿名95%平台107.25秒、耗时177.86秒。本轮相应为3.832、3.263、42.69、37.31、96.48。匿名平台接近Raster38.60秒，增长更短，工作进程结束匿名集中释放；file残留降为约0.548GiB。总内存达峰较晚，因为文件缓存继续增长，不能把总T90当匿名增长。匿名峰仍低于Raster总峰3.819GiB，不据此单独淘汰。复用素材未清全局缓存；file页计费受已有页归属影响，所测file残留下降不能全部归因于素材缩小，也不保证冷启动得到同样数值。

HandBrake沿用固定配置：总峰约0.990GiB、匿名约0.891GiB、T90约5.49秒、95%平台约48.95秒、计算约55.40秒。自然释放集中下降，保留与Array目标阶梯释放的差异，不人为塑形。

DBeaver慢增长，但95%平台仅1.05秒；结束附近快速下降，之后总驻留1.065GiB、匿名0.988GiB，没有目标38.15秒高位平台和持续逐步下降。不把其较小峰值当淘汰理由，核心是生命周期不符。

Hop匿名内存较早升高并在处理期反复波动，排序/输出形成阶段变化，file会先增后回落。自然尾部总驻留1.013GiB、匿名0.796GiB。相对提交前总基线0.607GiB，保留部分增量；不能把退出释放算成任务自然释放。匿名主要回落已在排序合并/输出阶段发生，完成至关闭前总内存仅继续下降约0.00038GiB；JSON中的completion-to-tail释放量不包含完成前已发生的回落。其总/匿名95%平台仅5.60/6.70秒，阶段变化比DBeaver明显，但仍不符合原Table慢连续增长、约38秒平台与逐步释放。拒绝当前操作，不通过缩小输入掩盖JVM驻留。

## 采集质量与边界

|应用|采样间隔中位ms|计算期最大间隔ms|计算期>100ms|最低MemAvailable GiB|自然尾段秒|
|---|---:|---:|---:|---:|---:|
|peazip|50.002|850.96|1|9.814|142.67|
|handbrake|50.000|672.47|1|12.088|55.15|
|dbeaver|50.001|1254.88|1|11.599|211.01|
|hop|49.997|783.22|1|11.466|249.64|

各应用目标50ms，实际间隔、缺口、cgroup CPU/PSI、进程树、memory.events、memory.peak、swap及整机MemAvailable均在原始文件和metrics中。计算窗口存在单次长采样缺口，峰值/边界时刻有相应采样误差；内核memory.peak与采样峰同时保存。不补点为观测、不合成退出后的零值。所有选中轮次OOM增量为0，cgroup swap为0；原有整机swap占用仍存在，并未关闭或调整Swap。CPU核数、16GB VM和内核设置保持原样。祖先memory.max/high和进程归属证据在每轮JSON/CSV中。

原Raster/Table/Array只有给定指标，未找到可用历史CSV或参考图片，因此图中仅标量参考线与文字；没有伪造原目标时间序列、DTW或相关系数。原源码未运行或修改。

## 清理与保护

继承清理证据：删除129个显式专属路径（含目录），本项目Blender2.92便携版、Classroom及专属贴图/安装包/GUI配置/所有专属采样/输出/曲线/日志；KNIME5.5.3及专属JRE/workspace/工作流/Columnar缓存/tmp/安装包/全年和Q1专属采样及业务输出；旧混合统计/曲线/ZIP。已用空间69,511,069,696→64,510,545,920字节，观测净释放5,000,523,776字节（4.657GiB），不是本次续接重新删除，安装下载会抵消净值。

NOAA gzip、Q1 CSV、字段说明、来源与SHA256清单已迁入shared_assets/weather，迁移前后SHA256一致；17个PeaZip共享文件逐一核验PASS。清理清单/完整性/空间明细位于reports/cleanup_evidence。保护Krita、baseline、PeaZip原17文件、HandBrake/BBB、NOAA、原三操作和全部调度代码及其他项目。保留应用历史包仅含有效候选，不操作宿主机下载文件。实际采样均保留本机。

## 后续候选查找与交付

两者都不合格后，已继续查找原生桌面候选：QGIS Processing支持非空间表聚合与按表达式排序，可通过GUI模型连接真实质量过滤、单位计算、排序和文件输出；SAGA提供原生表计算工具。它们**仅完成官方能力调查，未安装/实测，未宣称满足内存曲线**。本批不再无限调整DBeaver/Hop。来源：[QGIS排序](https://docs.qgis.org/3.44/en/docs/user_manual/processing_algs/qgis/vectorgeneral.html)、[QGIS聚合](https://documentation.qgis.org/3.44/en/docs/user_manual/processing_algs/qgis/vectorgeometry.html)、[SAGA表计算](https://saga-gis.sourceforge.io/saga_tool_doc/8.5.0/table_calculus.html)。

analysis含每应用完整生命周期、PeaZip前后、两个Table候选、四应用统一坐标、匿名/file分解、总量与分量基线扣除归一化、三个原目标标量对比PNG。final_summary.csv含配置、总/匿名指标、自然释放、结论；candidate_metrics.json保留全部详指标。software_assets_parameters.json记录版本、实际配置、来源、哈希。复现步骤见reproduction/reproduce.md。

报告ZIP与SHA256位于results/app_candidates，下载命令见download_instructions.md。ZIP排除软件、素材、业务输出和原始采样。Git代码存mxt，Markdown汇报存mxt_codex，main不修改，hooks不绕过，不提交任何实测数据/图片/ZIP。Git完成情况另见git_delivery.json。
