# QGIS Aggregate 单应用独立实验

批次 `20261127_101605_qgis_single`，2026-11-27（Asia/Shanghai）。**当前原生 Aggregate 不适合作为原 Table 的替代。** 已取得真实 GUI 成功结果、完整业务核验及独立 cgroup 曲线；本轮没有启动 Krita、PeaZip、HandBrake、Hop、DBeaver或其他实验应用，没有并发OOM或固定时间线实验。整机MemAvailable/Swap只用于环境监测，不代替QGIS曲线。

## 软件、素材与真实操作

Ubuntu22.04.5，官方Jammy QGIS LTR仓库 `https://qgis.org/ubuntu-ltr`，安装3.44.16-Solothurn；GDAL3.4.1、Qt5.15.3、Python3.10.12。签名指纹2D7E3441A707FDB3E7059441D155B8E6A419C5BE已核验。使用APT最小安装，无系统包升级、无GRASS/QGIS Server应用或额外插件；libqgis-server仅为客户端Python依赖库，不是启动服务器。没有修改VM内存、Swap、内核、现有虚拟环境、预测器、HistoricalLookup或冻结调度。

真实输入 `/home/mxt/TeamOOM/assets/real_cases/app_candidates/shared_assets/weather/2024_Q1_header.csv`，344,899,269字节，SHA256 `236a8bf51416d4483f6376e5039020651f3df12c2c87827ad209e8027e9f436e`，9,579,563行、40,483个站点，2024-01-01至03-31，215个要素/月组合。实际站点字段是ID，DATE和DATA_VALUE原生识别为integer，ELEMENT为text；无几何。未使用Hop已过滤输出，未复制或重复记录，未修改/重新下载NOAA。

QGIS真实桌面加载属性表并打开原生native:aggregate；仅由配置脚本预填尚未执行的原生对话框，正式业务由GUI Run提交，没有调用processing.run或qgis_process执行业务。分组 `array("ELEMENT",substr(to_string("DATE"),1,6))`。保留ELEMENT和MONTH组键；统计ID计数、站点去重数、数值计数、mean、median、minimum、maximum、stdev。不同要素不混组，不统一除10，保留原始数值单位语义。原生项目已保存，输出GeoPackage表monthly_element_summary。

## 单轮结果与参考

|指标|QGIS实测|原Table参考|
|---|---:|---:|
|总峰GiB|6.100399|4.022|
|匿名峰GiB|6.081268|无独立匿名参考|
|file峰GiB|0.008446|无|
|总/匿名T90秒|237.014 / 237.558|无|
|总/匿名95%平台秒|588.146 / 588.146|38.15|
|总/匿名最长连续95%平台秒|588.146 / 588.146|无|
|全局达峰秒|273.020|33.55|
|GUI提交至原生成功事件秒|845.676|无|
|原生日志计算耗时秒|843.43|无|
|50%进度秒|273.112|无|
|100%进度秒|843.772|无|
|成功事件后至首次退出请求自然观察秒|177.765|无|
|自然观察末尾总/匿名GiB|6.092098 / 6.073437|逐步下降|
|自然观察中的总下降GiB|0.000820|无|

增长连续但非常慢，高位平台远长于参考；原生计算返回后自然窗口仍约6.092GiB，几乎不下降，缺少Table的逐步释放。淘汰依据是完整生命周期与时间特征，不是峰值超过4.022GiB。file值很小受到复用素材的暖缓存及原页计费归属影响，不代表读取量小；没有清全局缓存。95%平台采用计算期绝对峰值阈值的累计时长，另列最长连续段；归一化图另扣除提交前基线，不拉伸时间。

**正常退出未实现。** 保持QGIS打开，未重置节点、手动持有缓存、调用GC/malloc_trim或改变分配器。原生对话框保持打开是QGIS默认配置。正常GUI退出请求未被及时处理，主线程继续占CPU；成功返回后十余分钟仍约6.09GiB。晚于自然观察和退出请求的一次短GDB调用栈显示主线程处于glibc malloc_consolidate，由Qt SVG图标加载触发；这只是一次诊断证据，不推断所有QGIS任务或版本都有相同问题。该诊断停顿明确记入事件，不进入自然释放结论。

最终停止本轮专属systemd服务恢复环境。停止附近观测下降约6.088GiB，**这是强制回收，不能作为自然释放或正常退出释放指标，正常退出释放量记为不可用**。成功完成及自然窗口不因强制回收伪造零值；cgroup消失后的应用内存为不可观测，另采30秒真实整机环境尾段。

## 业务验证

原生算法successful=true。独立标准库在应用及30秒尾段采集结束后扫描原始9,579,563行，对全部215组检查组键、8项统计、字段及精度；SQLite integrity_check通过，结果PASS，无错位、丢组或数值错误。输出SHA256 `9316dbf8ffe650103df71c5e4c812f265734582b19a305ac3100205622addea2`。中位数独立计算；标准差采用原生表达式stdev的样本定义，单记录WT10/202402为SQL NULL。

初验曾错误地按总体标准差核验；保留该诊断后依据官方源码修正验证器，重新全量核验通过，**没有修改业务输出或放宽容差**。QGIS3.44的表达式stdev映射StDevSample：[官方源码](https://api.qgis.org/api/3.44/qgsexpressionfunction_8cpp_source.html)。原生Aggregate的first_value是特殊处理，minimum/maximum才是分组统计的正确函数：[Aggregate源码](https://api.qgis.org/api/3.44/qgsalgorithmaggregate_8cpp_source.html)。

## 采集质量与限制

50ms目标；全程29,820样本，中位50.037ms，P95 53.636ms，最大933.330ms，>100ms 1343次。计算期中位50.040ms、P95 64.681ms、最大880.468ms、>100ms 692次。存在明显缺口，峰值时间与边界精度受限，不补点冒充观测。内核peak与采样峰同时记录。

独立cgroup memory.current/stat anon/file/peak/events/swap/max/high、CPU与PSI、进程树及每秒RSS/PSS/状态、整机MemAvailable/Swap/vmstat/CPU/PSI均已采集。memory.max/high=max，无人为内存限额。原始样本SHA256 `c55cb73ffe16b5195cdf8623b43d11b2232e1858c9e0559d17fab37d9d5c50e7`。最低整机MemAvailable 6.317GiB，OOM增量0，应用cgroup Swap峰0；原有整机Swap占用约0.253GiB，未关闭Swap。

原Table没有可用原始CSV，只引用给定标量与形态说明；未生成目标伪序列、DTW或相关系数。已生成并检查总量、匿名/file、基线扣除归一化和Table参考4图，依照淘汰清理要求随后删除，不保留大体积备份。

## 旧轮次与交付边界

20261126_224114轮次曾有Krita，受用户修正被排除；原始记录依用户“不要覆盖原始记录”要求保留并标记invalid，派生结果已清理，不混入本轮。20261126_230327单应用轮次因min/max函数标识错误失败，修正后的轮次未启动成功；没有将失败数据认定为不匹配。本次全新目录重采，不拼接停滞两小时的记录。

本轮只保留简短文字淘汰报告和清理清单；删除专属输出、采样、曲线、日志、项目配置及本次新装QGIS专属软件包，不做全局apt autoremove，不删共享NOAA或公共采集器，不影响Krita、PeaZip、HandBrake及其它项目。实际路径、释放空间和完整性复核见本文末尾清单及本机cleanup_report.md。正常退出限制单列如上，后续正式并发场景未开始。

Git代码仅mxt，mxt_codex仅新增本轮Markdown报告，不上传采样、CSV、PNG、GeoPackage、日志或ZIP；main未修改，hooks保留。34项测试通过。本机生成仅文字报告ZIP并提供PowerShell scp说明。下一步应重新筛选具有合适任务完成/资源释放生命周期的真实Table操作，不把这轮强制回收当成合格释放，也不为凑齐三应用而强行保留QGIS。


# QGIS 淘汰清理清单

观测磁盘净释放 761,774,080 字节（0.709GiB），为系统同期净变化，不伪称精确软件体积。

移除本次新装的 15 个 QGIS 专属包：

- libqgis-3d3.44.16
- libqgis-analysis3.44.16
- libqgis-app3.44.16
- libqgis-core3.44.16
- libqgis-customwidgets
- libqgis-gui3.44.16
- libqgis-native3.44.16
- libqgis-server3.44.16
- libqgispython3.44.16
- python3-qgis
- python3-qgis-common
- qgis
- qgis-common
- qgis-providers
- qgis-providers-common

保留通用Ubuntu签名镜像源及通用依赖；原sources.list未改，不执行全局autoremove。QGIS官方源和专属签名文件已删除。

删除项目专属路径（记录逻辑字节数，不等同物理回收）：

- /home/mxt/TeamOOM/data_collection/app_candidates/20261127_101605_qgis_single：24,372,617 B
- /home/mxt/TeamOOM/data_collection/app_candidates/20261126_230327_qgis_single：10,361,633 B
- /home/mxt/TeamOOM/results/app_candidates/20261126_230327_qgis_single：23,102,108 B
- /home/mxt/TeamOOM/runtime/config/qgis：44,779,884 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/qgis_aggregate_single_round.md：7,309 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/qgis_normalized_memory.png：105,000 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/qgis_noaa_aggregate.gpkg：86,016 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/sampling_quality.json：725 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/reports：85,572 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/monthly_element_summary.gpkg：86,016 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/monthly_element_summary.gpkg-shm：32,768 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/monthly_element_summary.gpkg-wal：0 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/qgis_anon_file_memory.png：98,958 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/qgis_vs_original_table.png：111,183 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/reproduction：13,115,428 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/qgis_metrics.json：3,199 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/final_summary.csv：515 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/business_verification.json：3,003 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/qgis_total_memory.png：78,285 B
- /home/mxt/TeamOOM/results/app_candidates/20261127_101605_qgis_single/qgis_noaa_aggregate.qgz：7,028 B

删除软件缓存和专属系统配置：

- /var/cache/apt/archives/libqgis-app3.44.16_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/python3-qgis-common_1%3a3.44.16+36jammy_all.deb
- /var/cache/apt/archives/qgis-common_1%3a3.44.16+36jammy_all.deb
- /var/cache/apt/archives/libqgis-customwidgets_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/libqgis-gui3.44.16_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/libqgis-native3.44.16_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/python3-qgis_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/libqgis-analysis3.44.16_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/libqgis-3d3.44.16_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/libqgis-server3.44.16_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/libqgispython3.44.16_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/qgis-providers_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/qgis-providers-common_1%3a3.44.16+36jammy_all.deb
- /var/cache/apt/archives/qgis_1%3a3.44.16+36jammy_amd64.deb
- /var/cache/apt/archives/libqgis-core3.44.16_1%3a3.44.16+36jammy_amd64.deb
- /etc/apt/sources.list.d/qgis.sources
- /etc/apt/keyrings/qgis-archive-keyring.gpg

保护与核验：

- NOAA原始gzip、字段/来源说明、Q1及清单均保留。Q1 SHA256复核：236a8bf51416d4483f6376e5039020651f3df12c2c87827ad209e8027e9f436e
- Krita、HandBrake、PeaZip、baseline_assets、公共采集器和原算法未删除。
- 原受Krita干扰轮次原始记录依用户第7条保留、invalid标记，不纳入本轮；本轮与前次函数错误轮次的专属采样/输出/图/日志/配置已删除。
- 正常GUI退出未完成；专属服务停止仅用于恢复环境，释放不算自然释放。
- 不保留大体积备份；报告ZIP只含文字。

最终只读验收：QGIS及Krita无残留进程；QGIS命令和安装目录已移除；Krita、PeaZip、HandBrake可执行文件存在。

代码提交：`81f1f27d82b861b05f8a479a170035d39225fd67`，仅mxt；mxt_codex新增一份Markdown汇报，未上传实验数据或图表。
