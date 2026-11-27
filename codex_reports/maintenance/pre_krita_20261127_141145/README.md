# 应用清理、原Table审计与Krita准备交付

批次：20261127_141145，Ubuntu22.04.5 / Linux6.17.13-oomlab。用户随后授权将本轮报告交付至GitHub mxt_codex；本提交仅新增/更新codex_reports下Markdown，实验软件、素材、数据和曲线留在VM。

## 结果

- 已清理177条淘汰候选专属路径，三个删除窗口共释放2240110592字节（2.086266GiB）。PeaZip第三轮16文件Medium、HandBrake第二轮固定20秒及原Raster/Array/Table/Krita历史保留。
- 18组保护根可读元数据、42项关键文件SHA256前后相同；受限读取范围如实记录。删除前后未发现运行中的候选或实验进程，没有杀进程。
- 原Table十轮状态 **NEEDS_RECOLLECTION**：旧800万行CSV/pandas与b65b767实际调用的64批、4GiB、四列uint64匿名缓冲不同。旧十轮原位保留，本轮未重采Table。
- Krita状态 **INCOMPLETE（素材缺失，未启动采集）**。缺少固定SHA256的原始light_9000.ora及46层、7层文档，按用户停止条件没有生成替代素材、放宽参数、执行预检/采集/验证。没有可用于建模的新前台曲线。

## 报告

- [清理报告](cleanup_report.md)
- [清理前后盘点及保护核验](inventory_audit.md)
- [Table原始十轮配置审计](table_config_audit.md)
- [Krita素材与采集停止报告](krita_collection_report.md)

继续Krita任务所需的最小资料：原始light_9000.ora，SHA256为 `04dca9c398803650ec04241ab66ddaa26a0f2a110fa90dc5bb6f2af6cc464182`。该文件并非现存旧8000×8000文档，不能替代。

## 版本与边界

指定实验源码提交 `b65b76724c440d9c48738dd063b9311245aad178` 通过临时独立main副本读取，未修改真实main。真实TeamOOM/repo仍处于mxt，HEAD `81f1f27d82b861b05f8a479a170035d39225fd67`，工作区干净。本次报告发布与之前禁止提交的实验执行阶段分开，后续用户的明确上传指令只授权本次报告提交。

本次没有修改实验代码、运行实验应用、计算固定时间线或启动任何多任务实验。保留报告ZIP及SHA256仍在VM results/app_candidates下，本次不上传ZIP或新增二进制例外。
