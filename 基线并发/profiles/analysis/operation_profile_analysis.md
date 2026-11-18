# 原始曲线分析结果

详见 ../../docs/V4_问题回应与部署报告.md。主统计为Krita n=1、XZ n=3、Table n=10、Array n=9（用户明确排除第1轮，10轮敏感性单列）。

峰值/时长/均值曲线/峰值窗口均从原始样本计算，内存口径为独立cgroup memory.current；内核高水位单独保留。原始时间戳取CLOCK_MONOTONIC，Krita历史曲线原点是导入标记。首页时刻缺失，以统一时间表中的明确假设区间规划首版，不把历史导入峰值1193.803秒冒充首页峰值。

operation_mean_curves.csv.gz保留每个时间点的贡献轮数，优化只取全体选定轮次共同覆盖区间。未给原始短峰做平滑删除。mean curve的峰值与逐轮峰值均值不同；所有原始轮次包括排除项均保留指标。文件路径是真实分析工作区路径，不冒充目标VM路径，SHA256和archive_sha256.json供复核。

图表：operation_curves.png（四操作多轮/平均曲线）、peak_distributions.png（峰值内存/时间分布）、homepage_overlap.png（高内存窗口及同点任务参考叠加与固定暂停模型）。这些是离线参考，不是三线正式实验结果。固定暂停保留分配内存，图中没有把前台结束后未知的内存填零。
