# 原 Table 十轮只读审计

> 发布说明：以下为2026-11-27实验阶段的原始文字报告。本次根据用户随后“报告交付到github的mxt_codex”的明确指令，仅发布整理后的Markdown报告。文中“本轮不提交/不推送”描述此前实验执行阶段；本次报告发布不改变实验状态，也不代表已完成Krita采集。

结论：**NEEDS_RECOLLECTION**。原十轮数据保留完整，但不能作为指定 b65b767 `measure_raster.py --task table` 的同配置历史曲线。此结论由执行入口、输入行数、数据结构和生命周期的明确差异决定；不是因档案缺失而推测。此次未启动任何 Table 任务。

指定提交：`b65b76724c440d9c48738dd063b9311245aad178`。独立临时副本为 `/tmp/TeamOOM-krita-b65b767-20261127T061243Z`，分支 main，相关源码未修改。实际 TeamOOM/repo 的 mxt 分支未切换。

原始归档：`/home/mxt/OOM/data_collection/shared_recovery_20261120/OOM_Dataset_20261101/Table/OOM_Table_10rounds_20261101.tar.gz`，300555642字节，SHA256 `fd63e5961321bbaf1ebe0bc1e62102f1772beae0f8020a0ac0de6a952216a3b8`，与旁侧原始 .sha256 相符。只通过 tarfile 读取成员，未向 OOM 目录解压、移动、写入或覆盖。388个文件成员，包含10份独立轮次 metadata/summary/output/phase trace、聚合副本及输入 manifest。

## 实际调用链及配置比较

`measure_raster.py` 引入 `shaped_workload.PROFILES`，当 `--task table` 存在时运行 `后台操作/曲线任务/shaped_workload.py --task table`，并传入 `timing_for` 生成的四个时间参数。它不会在此路径读取 profiles.json，也不会调用 oomlab.workloads。旧 profiles 的 Table Large 即使与 OOM metadata 相符，也不能证明与新入口相符。

|核对项|b65b767 实际 shaped Table 默认行为|原 OOM 十轮证据|判断|
|---|---|---|---|
|执行入口|shaped_workload.py --task table|metadata.command 为 python -m oomlab.workloads … --operation-id table-large|不同|
|输入规模|134217728元素（逻辑行）|8000000行 CSV，266051003字节；用户200000，分类32，日期31，extras4|不同|
|列/类型|stamp、row_id、value、converted 四列，均为小端uint64 `<u8`|旧 Table Large 对应8个输入字段：user/category/day/amount/extra0–3，增加score；历史档案不含运行源码。固定提交的旧实现用3列int64与5列float64读CSV|明确结构不同；历史精确 dtype 实现摘要证据不足|
|生成方式|mmap匿名主缓冲，每块以65536元素tile确定性填充；stamp=1700000000+idx//1024，value=(idx*1664525+1013904223)%65536，converted=value*100|输入 manifest seed=20261026，table.csv SHA256 f68ccafda469a5693cbd932750b38c86fcfdcc5e6c94e2618cbd609e7ca53943；固定提交旧生成器为CSV公式生成|不同|
|批次|64批，每批2097152元素；每批67108864字节|执行记录为CSV_LOAD→DATA_TRANSFORM→GROUPBY_USER_CATEGORY→OUTPUT_WRITE→GROUPBY_DAILY→OUTPUT_WRITE→CLEANUP；没有64个grown/released事件|不同|
|主缓冲容量|4294967296字节（4 GiB）；其他Python/NumPy开销另计|pandas表、score和分组临时表；metadata未声明固定主缓冲容量|不能等同|
|准备、增长、保持、释放|默认prepare1s；批间grow0.45s；hold35s；逐批release0.35s并校验摘要、close mmap|按真实CSV读取/转换/分组耗时运行；未记录上述hold35s或逐批释放时序|不同|
|采样|freezer_monitor 50ms循环，字段组单调时钟读前/后括号；memory.current/peak/anon/file/swap/events/CPU及主机指标|10轮 metadata.interval_s 均0.05；保存task_memory、process与phase记录；process1s、PSS5s，但若干PSS字段标为未采样|仅目标周期相同，不代表流程相同|
|cgroup|delegated scope下独立 probe cgroup；自身不写memory.max/high；读取实际值；全机swapoff并结束后restore（仅源码审计，此次未执行）|systemd system unit oomlab-a-<run>.service；MemoryMax2995739688、MemorySwapMax0；系统Swap保持启用|不同|
|环境|当前任务约定Ubuntu22.04.5、Linux6.17.13|原十轮 environment 为Ubuntu22.04.5、Linux6.17.12-061712-generic，NumPy2.2.6、pandas2.2.3|不同|
|源码证明|本次 pinned_source_hashes.json 记录实际固定提交源码摘要|归档不含 workloads.py，不含可证明当次源码的Git身份/文件摘要；不能用当前 OOM checkout 代替历史源码证据|历史精确源码身份 UNKNOWN|

上述cgroup和Swap比较只描述历史/固定源码；本轮未关闭Swap、未改变VM参数、未新建后台工作负载。

## 十轮逐项记录

下表均为原 metadata 自报 success=true、verified=true；完整机器记录在 table_rounds_audit.json。独立轮次与聚合目录中的重复副本没有重复计为20轮。

|run_id|计算秒|最大采样间隔ms|元数据/结果/阶段记录|
|---|---:|---:|---|
|0a7bdabe51534bf2bace84c6c3d261a7|31.356497|52.745626|齐全；CSV摘要与参数一致；未重新执行业务计算|
|5a77503ef5d54c5f859ad2366144003c|29.850700|53.610982|齐全；CSV摘要与参数一致；未重新执行业务计算|
|6122946fcad3455d94dfd84a7ff6b59c|30.047099|52.192298|齐全；CSV摘要与参数一致；未重新执行业务计算|
|6989e31af1fb47529b9f7ccdd92e321f|30.437852|56.706762|齐全；CSV摘要与参数一致；未重新执行业务计算|
|7350d7a3b10841c1a04d17983fc3c36c|30.216699|52.781952|齐全；CSV摘要与参数一致；未重新执行业务计算|
|928846d413794ee1b839c7fb5c3b1882|30.541806|55.477619|齐全；CSV摘要与参数一致；未重新执行业务计算|
|9496da788ca942e3aa7dbc05d9f59baa|31.493147|51.815247|齐全；CSV摘要与参数一致；未重新执行业务计算|
|a25f3ce48e6c455ba4a86a7c72beb062|29.353333|51.623941|齐全；CSV摘要与参数一致；未重新执行业务计算|
|d6e11b39c091473c9b30f2c6d5a12bec|48.006386|60.027285|齐全；CSV摘要与参数一致；未重新执行业务计算|
|ee4ecc5ff7ab44028f33f3449d797119|40.015221|56.494196|齐全；CSV摘要与参数一致；未重新执行业务计算|

本轮只核验归档外部SHA和记录一致性，未重新验证每个历史分组输出的数学计算；不将metadata自报验证等同于本轮重算。未发现逐轮 manifest.json 是单独文件，所用输入 manifest 已嵌入每轮 metadata；统一的输入 manifest 位于归档 work/.../table/manifest.json。全部原始CSV、输出、采样和归档原位保留。

后续若决定采用 b65b767 shaped Table，应另行授权采集对应的新历史曲线；不能覆盖本次审计的旧十轮，也不能混用两套曲线计算固定启动时间线。
