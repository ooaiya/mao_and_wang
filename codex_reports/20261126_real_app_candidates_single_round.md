# 六个真实GUI后台应用首次筛选与Kdenlive重采

2026-11-25～26，Asia/Shanghai。六应用真实计算均有输出验证；保留15次尝试，7段有效完整计算（含Classroom一次正常参数补采），最终选6段比较。没有正式并发或调度算法接入。

| 应用 | 实际操作 | 峰值GiB | 达峰秒 | 95%平台秒 | 任务耗时秒 | 最匹配目标 |
| --- | --- | --- | --- | --- | --- | --- |
| Blender | Classroom 单帧 CPU 渲染，1280×720 / 16 spp | 0.821 | 76.77 | 40.61 | 78.38 | Array（部分） |
| Hugin | 25 张 2560×1920 原片，全景重映射与融合 | 1.047 | 172.29 | 10.25 | 222.7 | Raster（弱） |
| darktable | 3 张兼容 Canon RAW → 原尺寸 JPEG95 | 1.338 | 13.53 | 7.15 | 14.05 | Array（弱） |
| Kdenlive | 120 秒 1080p30，2 视频＋2 音轨画中画 → H.264/AAC | 1.602 | 257.03 | 98.68 | 257.9 | Array（部分） |
| HandBrake | BBB 前120秒，1080p30 → x265 Medium RF22 MKV | 1.005 | 268.29 | 197.15 | 269.65 | Array（部分） |
| PeaZip | 17 个真实素材文件（1.116 GiB）→ 7z LZMA2 Normal | 2.402 | 100.5 | 12.35 | 100.95 | Raster（部分） |

没有足够证据选出分别满足三类目标的三个合格应用。优先保留Classroom16spp的Array部分匹配，HandBrake/Kdenlive作为Array备用；PeaZip有Raster阶梯增长特征但数值及残留不符；Table需新的候选。形态建议与只比较峰值/全局达峰/95%时间的标量最小距离分开，避免用标量排序冒充匹配验收。

Agent327在取消4/8GiB限制后正常加载、GUI提交CPU渲染准备，实测峰值10.331GiB，可用内存低于2GiB时安全中止，无新增OOM；改用官方Classroom，32spp首轮和16spp补采均真实完成。后者78.38秒、95%区间40.61秒；匿名峰值基本不变，总峰值降低主要源于文件缓存归属变化。

Hugin前两次启动失败和专家编辑器控制点/优化过程保留，最终PTBatcherGUI的25张拼接成功。darktable多格式解码失败，最终只将三张Canon全部导出的末段计为成功，不能声称原14张均完成。PeaZip初轮采集不完整，第二轮17真实文件压缩及校验成功。

Kdenlive在自动审批服务额度耗尽后停在渲染对话框，旧轮没有提交计算；恢复时约2小时15分钟总采样，按用户建议保留并排除，重启round02。实际H.264 CRF23/faster/auto线程导出120秒1080p30，两视频两音轨画中画，GUI完成约4分17秒，全文件解码通过。界面布局变化使输出最初位于/home/mxt/4，原生MLT核对后如实纠正参数，成功后归档到指定results目录。

计算和加载、任务自然释放、关闭请求、推断实际退出分别保存。没有清缓存或改Swap；所有叶cgroup memory.max/high为max。早期HandBrake/PeaZip只记录系统Swap存量，未采换入换出和cgroup Swap三列，指标保留缺测。采样实际约50ms，所有缺口和推断误差记录；不造退出零点，不将cgroup删除当作缓存全部回收。

建议下一批探索Siril真实天文序列叠加与FreeCAD FEM/CalculiX真实模型求解；这是未实测候选，不是已匹配结果。

源码工具：tools/real_app_candidates；17项根测试通过。main及既有hooks保留；不修改正式预测/调度算法。

所有结果（不在Git）位于 /home/mxt/TeamOOM/results/app_candidates/20261125_194918_gui/，完整说明为execution_report.md；原始采样位于 /home/mxt/TeamOOM/data_collection/app_candidates/20261125_194918_gui/。analysis_first_six保留补采前分析，analysis含最终六应用图、分解图、全部轮次JSON和CSV；selected_rounds.json说明最终选段。Git仅保存代码、说明及本Markdown汇报。
