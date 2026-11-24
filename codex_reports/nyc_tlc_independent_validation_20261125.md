# NYC TLC 工作站执行总结

源码基准：mxt b17d48094766f8c302acbaeb3c050c94755fe6b1。main未修改。完整报告和所有数据仅保存在虚拟机results/real_cases/nyc_transport_workstation；本提交仅为Markdown汇报。

- 完成Ubuntu、Swap、磁盘、cgroup安全核验；未改Swap、内存或内核参数，未操作旧OOM/Page Hotness。
- 官方2023/2024共24个月及Lookup/区域ZIP已下载，大小、SHA256、记录数和两种schema已记录于本地清单。无重复拼接或模拟替代。
- 在现有隔离venv补充Jupyter、Arrow、DuckDB、GeoPandas、LightGBM等，pip check通过；12项源码/保护测试通过。
- A完成独立Notebook执行；人工交互未验收。B首个SQL因month别名解析失败，已停止，不重试，C/D未启动。失败不是OOM，B采样不能作合格参照。
- 当前未启动常驻JupyterLab/桌面会话。没有自然并发、固定时间线、人工压力或冻融实验，没有声称验证选择性冻结优势。
- 现有执行器仍依赖offsets，任务名称和前台保护固定；已记录具体接口阻塞，没有伪造配置或另写调度器。

下一步需获准修复B并补查询契约测试，再完成B/C/D独立验证及前台交互；事件请求接入通过前不进入自然并发。所有正式代码修改只能在mxt。
