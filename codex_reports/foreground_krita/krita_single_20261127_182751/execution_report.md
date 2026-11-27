# Krita重启后单应用独立采集

最终状态 **PILOT_INVALID**。使用GitHub当前mxt提交 `6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`，没有切换main；本轮只调用原Krita采集器一次，未启动system_memory_watch、其他应用、并发或固定时间线。原始数据只保存在VM。

## 环境与代码

正式预检ok=True，errors=[]，Krita版本krita 5.0.2，分辨率[2552, 1200]，Linux 6.17.13-oomlab。采集前MemAvailable 14.165GiB、SwapFree 2.000GiB，根分区可用30.181GiB。启动前完整meminfo、进程与cgroup快照在last_environment_snapshot.json，仅用于开跑前状态。

唯一代码修改为environment.py白名单由只允许main调整为允许main/mxt；其他分支仍拒绝、dirty源码仍拒绝。新增4项白名单/dirty测试，项目52测试、专项114测试通过。专项测试使用测试私有lock目录解决沙箱只读/run问题，正式采集使用真实GNOME桌面与原measurement_lock，未改锁逻辑。代码已通过hooks推送mxt，其他环境和安全检查原样保留。

## 旧失败数据清理

[清理报告](cleanup_report.md)。仅删除指定PILOT_INVALID轮的CSV和大体积过程观测、派生PNG与统计，保存删除前SHA/字节/目录结构及清理后保留清单。旧故障报告、oom_failure_analysis.md、asset_validation、素材与配置/summary/metadata/phase/logs审计保留。旧manifest保留为历史删除前审计并加PRUNED标识，旧轮不再是完整run，未伪装成有效数据。清理详 `/home/mxt/TeamOOM/results/maintenance/krita_invalid_cleanup_20261127_182751`。其他批次和诊断证据未动。

## 素材与正式配置

直接复用现有合成ORA，未生成新图片或修改内容。逐层完整解码和ZIP CRC重新通过；验收[asset_validation.md](asset_validation.md)及本机asset_validation.json。9000×9000单层；46层每层9000×9000；7层为前5层9000×9000、后2层5400×5400。实际SHA与旧素材清单匹配：

|文件|字节|SHA256|
|---|---:|---|
|light_9000_source.ora|5394398|`87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8`|
|light_9000.ora|5394398|`87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8`|
|layered_9000_46.ora|124404893|`100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a`|
|light_9000.ora|5394398|`87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8`|
|layered_9000_07.ora|22265294|`7d7679e2072c387a207d9d393525a071f59fdfc3eaf7c491051ee402eedcc5aa`|

原模板来自当前mxt的collection.rapid-9000-medium-tail-extended.json；本地 `/home/mxt/TeamOOM/runtime/config/krita_single_20261127_182751/foreground_config.json`，SHA256 `ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d`。原SHA为历史ORA，不要求与现有合成内容一致；临时模板仅用实际三份SHA，原prepare_handoff_config适配路径与实测屏幕，共8个允许字段差异，config_diff_audit.json证明其他字段一致。

正式参数保持：50ms、低压30s、46层打开确认后12s、首实例关闭退出、7层中压浏览30s、每5s缩放、tile memory67%。原压力曲线12GiB参考±4%、低压上限、中压2–3GiB charge范围及全部PSI/内存/Swap/磁盘/超时安全阈值均未放宽。中压原验收使用memory.current charge；anon单独报告，未混用。

## 实际命令与阶段

使用现有runtime/venv解释器与当前mxt scripts/collect_krita.py：preflight --config CONFIG --results DATA_ROOT；预检PASS后collect --config CONFIG --operation krita --rounds 1 --results DATA_ROOT；随后validate实际run。完整展开命令在preflight/collect/validate_invocation.json，原始stdout在对应official.log，只留VM。

DATA_ROOT `/home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_20261127_182751`；唯一run `/home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_20261127_182751/20261127T103129Z-95a8a57da8714bf5bfd0bf2ac24be523/19e3a414871c4c2fbda72b20c3468523`。采集退出码1，独立验证退出码1，原验证状态PILOT_INVALID，valid=False。阶段原事件和[完整时间表](phase_timeline.md)保留，不补造未出现阶段。

metadata.error：`RuntimeError: Krita process identity changed`；原验证器错误去重：

- RuntimeError: Krita process identity changed
- incomplete operation/cleanup/cooldown/journal evidence
- incomplete operation exits
- FileNotFoundError: [Errno 2] No such file or directory: '/home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_20261127_182751/20261127T103129Z-95a8a57da8714bf5bfd0bf2ac24be523/19e3a414871c4c2fbda72b20c3468523/krita/krita-post-process.json'

本轮具体GUI失败：46层文档在原open_timeout_s=160秒等待内未被document_named窗口检查确认，原始错误为TimeoutError('素材加载超时；最后诊断=None')。低压30秒已完成，高压12秒和7层中压未执行；这是加载确认超时，不将其推断为文件损坏或已知PSI异常。随后正常退出等待也出现约9.83秒超时，由采集器执行服务清理。具体原文保存在VM automation_error_excerpt.txt和run/krita/automation.log。加载失败及退出等待之后，采集器另报告Krita process identity changed；该守卫比较starttime、PPID、exe三项，现有异常文本没有列出实际差值，无法确认是哪一项变化，也不能直接认定PID被重用。本次不修改身份守卫，保留故障证据。正常结束后的自然下降仅在完整成功时可解释；异常退出/安全停止后的服务清理不标作自然释放，不插值或补零。

## 实测指标

下列统计仅针对本次实际记录窗口；若PILOT_INVALID，均是部分记录，不能视为完整任务参考。time-to-threshold取首个真实采样点，不插值；95%时长是相邻两点均≥记录峰95%且间隔≤0.5s的累计时长，不冒充已验证平台。T0=5797450017395 monotonic_ns。

|指标|值|
|---|---:|
|Krita样本数|4743|
|Krita进程VmRSS峰GiB|9.586510|
|Krita进程VmHWM最大GiB|9.586510|
|cgroup memory.current采样峰GiB|9.626057|
|内核memory.peak GiB|9.626545|
|anon峰GiB|9.411190|
|file峰GiB|0.187656|
|采样峰时间s|237.175358|
|T90/T95 s|217.774829/227.475329|
|95%阈值以上累计s|9.700029|
|采样间隔中位/最大ms|50.002215/82.889146|
|>500ms间隔数|0|
|全局PSI Full/Some avg10最大|0.0/0.0|
|Krita cgroup Swap最大B|0|
|cgroup max/oom/oom_kill增量|{'event_max': 0, 'event_oom': 0, 'event_oom_kill': 0}|

RSS、cgroup current、anon/file和主机MemAvailable分别表示不同口径；分量峰可能不同时，不能相加。PILOT_INVALID时不据部分峰值断言完整高压或中压规格符合性。

## 曲线文件（仅VM）

- `/home/mxt/TeamOOM/results/foreground_krita/krita_single_20261127_182751/krita_rss.png`
- `/home/mxt/TeamOOM/results/foreground_krita/krita_single_20261127_182751/krita_cgroup.png`
- `/home/mxt/TeamOOM/results/foreground_krita/krita_single_20261127_182751/anon_file.png`
- `/home/mxt/TeamOOM/results/foreground_krita/krita_single_20261127_182751/mem_available.png`
- `/home/mxt/TeamOOM/results/foreground_krita/krita_single_20261127_182751/global_psi.png`

所有曲线统一原T0，只绘实测点；缺失RSS保留为缺口，>0.5s缺口断线，没有重采样、平滑、补零或伪造自然释放。统计在metrics.json，仅留VM。

## 验收与交付

|检查项|状态|
|---|---|
|VM预检|PASS|
|旧失败数据清理|PASS（保留审计）|
|原ORA复用验收|PASS|
|当前GitHub配置核对|PASS|
|Krita GUI环境|PASS（正式预检）|
|原采集器兼容检查|PASS（最小白名单改动，其余安全不变）|
|正式单轮|PILOT_INVALID|
|原始文件SHA封存|PASS，原verify_seal通过；完整业务流程是否有效另由validator决定|
|曲线生成|PASS，部分/完整状态如实标识|
|main|保持b65b767，不修改/推送|
|mxt|6ce22767fdd91ea23d1e4fab0f071a19c44ea92a，代码/测试已正常推送|
|mxt_codex|随后同步代码并只上传Markdown报告|

下一步依据原验证器结果审核曲线；未通过时必须先分析此次具体错误，不能自动重试或改原负载与阈值。本轮不启动其他应用、不计算并发时间线，保留新run故障证据。GitHub仅交付Markdown，素材、采样CSV/JSONL、PNG和日志不上传。

采集结束后复查：无Krita/其他实验应用、旧collector或system_memory_watch在运行，实际mxt工作区干净；post_run_checks.json保存在VM。
