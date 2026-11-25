# 六个真实GUI候选：预检阻塞总结

本轮未进入正式采集，不能认为六项部署完成。完整本机报告位于results/app_candidates/20261125_171530_preflight_blocked/deployment_report.md；未上传原始数据或本机GUI配置。

环境、Swap零使用、可用内存/磁盘、真实mxt GNOME/XWayland访问均已核验；六候选未安装。APT只模拟：Hugin无当前候选，另四项原生候选的计划为260新增、0升级、0删除。未实际安装或修改系统配置/既有venv。

官方Blender Demo页面返回403；官方可访问Cycles目录没有Agent327 CPU实际下载链接。任务书明确禁止猜地址，所以在素材来源核验阶段暂停；没有选GPU/splash或其他场景代替。Hugin官网指向的AppImage为第三方continuous预发布构建，尚未下载/验证。

六项素材未下载、未核验SHA；所有GUI任务、cgroup子进程归属、50ms实测曲线、匹配与DTW、Swap/OOM运行验证均未进行。没有运行Krita高压任务或任何并发，没有虚构匹配结论或输出图。

mxt只补齐通用RAW/视频/Blender/Kdenlive/PTO/TIFF/归档防误上传规则和测试，提交a235af6948610ebb7493777534bd463833a70e77；9项测试通过。旧算法与负载未修改，main未修改。后续需先解决可验证官方CPU素材链接和安装路径，再按原任务逐项部署、开发验证采集工具与真实GUI单轮执行。
