# 证据清单、完整性与只读边界

实验批次：`krita_single_20261127_182751`

run：`20261127T103129Z-95a8a57da8714bf5bfd0bf2ac24be523/19e3a414871c4c2fbda72b20c3468523`

源码基准：`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`；诊断日期：2026-11-27（Asia/Shanghai）。

本次仅只读分析旧记录；未启动 Krita、未重采、未改代码或配置、未执行清理。原始 run 保留。文中“已证实”表示原始证据或固定提交控制流直接支持；“推断”不替代实测；UNKNOWN 表示未记录，不能追溯补造。

## 定位

原始 run 根目录：`/home/mxt/TeamOOM/data_collection/foreground_krita/krita_single_20261127_182751/20261127T103129Z-95a8a57da8714bf5bfd0bf2ac24be523/19e3a414871c4c2fbda72b20c3468523`。

原结果根目录：`/home/mxt/TeamOOM/results/foreground_krita/krita_single_20261127_182751`。

本次诊断目录：`/home/mxt/TeamOOM/results/maintenance/krita_failure_diagnosis_20261127`。其 JSON 仅为本地检查及提取结果，不上传Git。GitHub仅交付本目录五份Markdown。

## 原始封存检查

原 `manifest.sha256` 中37个成员逐一核对路径集合、大小与SHA256，通过；manifest本身不在自引用清单。诊断前后按同一清单复核，37个文件均不变。manifest自身当前SHA256=`5e2463ad7405c5cdff14e3d7f266d3aed9f44aea9ac1f6b2ee4d0197a984efa4`。这证明现有封存成员完整，不证明原程序曾记录不存在的窗口标题/失败元组或完成整个实验。

| 相对run路径 | 字节 | SHA256 |
|---|---:|---|
| assets_manifest.after.json | 2757 | `81afbf5571a5cb8151f2adb66345251581e80435663757b4502d712e0a31e7f6` |
| assets_manifest.json | 2757 | `81afbf5571a5cb8151f2adb66345251581e80435663757b4502d712e0a31e7f6` |
| automation.log | 22470 | `94fc0bb193a3814197629f88b6d778c48888439d0251b97050e1be587a18006e` |
| boundary.json | 710 | `338ae933e6df7a74d4ee71e0e82f22870e4ec16ba3f242545c92a04a5738c20c` |
| cgroup-end.json | 7413 | `8a69559b57920cbad6d601a5c6256e0584384d00ce303b8f7257041cd7d44d3f` |
| cgroup-observations.jsonl | 317498 | `7815e9a826813a91fdda37b65fb102553317b97c5ab0d634b2cfab45585fca2b` |
| cgroup-start.json | 7267 | `656907bce2281be7d6388646ae135a7565b65b36f053a3c8ce42960d41e7658e` |
| cleanup.json | 2367 | `0791bdcc9006d262e8935525175dcce37e33870a832af9673af105b71c8193cb` |
| config.snapshot.json | 2994 | `ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d` |
| cooldown.jsonl | 260736 | `557827806a1b596e3dc5d8abbaa46f5d273b867c93c89b49e68c757c3fa1c25b` |
| environment.json | 11826 | `d78ad4a340b8e6c3d42f35dc7bb311d013a6791b2a57fdb326acbbf571f7dbcd` |
| hold/ready.json | 87 | `af24e31b464ed15d98f77f5b19d25f8b5abf353f7f6947f117eed64a5a06cd9b` |
| hold/systemd-start.json | 1990 | `ae4075e44f9136e0490ea922750b23df5e65beb8d8c0b6934c1867d972a17328` |
| hold/unit-identity.json | 969 | `c1396d0282b984635829cac270ac8e057062c7bb90b24e57be7b82c77b143177` |
| journal.log | 59661 | `e8dc4e255e0b330c4edb7a6839e08248a3a20a302505185cb0d07a5944780e7d` |
| krita/automation.log | 22432 | `f287ee231c29718867457cef2eb78f7e7911a6667ecbc0dbe9def6134dd80a2f` |
| krita/command.json | 2508 | `b05dacf9a362608327ee6859c7eb5ff2c7486e098627f777050c005010ef01ff` |
| krita/finished.json | 206 | `b63014b9907da641a05d6a235d9a76f15451ef969748ad9ca3f9bd68deb47c3f` |
| krita/go.json | 65 | `2ada7f9c698278b7e265dcf9281d11a7ed1c9aa9794984cc2a4eb3cd6012655e` |
| krita/isolated-krita-config/QtProject.conf | 722 | `f5f7fb885b7a5b5e0e0909bbad529eead568135e2bdab8cb47ac64fcde771e4d` |
| krita/isolated-krita-config/kritadisplayrc | 33 | `e0d9d4b5671e471e591bef6d3f130e28f8caaee4b435408d5e413e3c436f362e` |
| krita/isolated-krita-config/kritarc | 11071 | `d583dd25957e51a7e8acacdb03803c2986bc0d8943a3c70f1729e8e3faa028bc` |
| krita/krita-process.json | 992 | `fec736637cbac3d8941713276a4033bffc771806ecbb9321d08d6ecd27f47ba2` |
| krita/phase-events.jsonl | 18399 | `c9c47d25a0d0992961af92351539e441b13ccf2255a6e5e3f473b3d9392c27b8` |
| krita/ready.json | 88 | `1a7165d154704580b8d99ed9173205385d772ecf5386e91d81d2d3bf736428f7` |
| krita/started.json | 127 | `a7863b4103dc839ac539541b10825c0997c6e64c0731ff92146b8e0aa9081934` |
| krita/systemd-start.json | 1979 | `d6a8d38b8a37c804422aea5b46c6abdf3c0f98a6fec0a847baab17da083ce69e` |
| krita/unit-identity.json | 974 | `019296a6e2a12d7eed6c15e29a86fd616ca7482ddc12b243e92de95e7a817ce2` |
| krita/workload-pid.json | 71 | `6f303e6ea8950be06580182a24f4847f90c957a079af7ea246588be50470ed41` |
| memory-events.jsonl | 749 | `b7fa168e6b0fabdb3b0899f0028dda2f9b67e450df140c852d67b0d40271d052` |
| metadata.json | 24671 | `2cddba3a9e01addb169d4b147d67d5945c153c73329e4d3ce1dbf489a14feec1` |
| phase-events.jsonl | 18476 | `d3bac4481fdd642f9a67fb087844fa70588f410ed42d338077d2a07c7fe14441` |
| process-observations.jsonl | 1140329 | `cab16aa3505c3ab0e04dabc74202f3f42358a670818235f228403342104e5fe3` |
| report.md | 7075 | `6411a059f3b46751aa1ce35f3a5faeb5dde8e6b51854ccb41c0f3670ae560215` |
| samples.csv | 14422627 | `a8380dadcc3dcdfae6f29f3bd19572545b38e72b4b3dea94ecf5715337d3252c` |
| stop-request.json | 7620 | `677604ee0854abdc9bd87b486b8f30bb72efbd9068572295d81b00238c8f1599` |
| summary.json | 2652 | `22d2bbf24d98f4c15d31a613338fa4d9361709274f980184cf040ae381b3e59f` |

## 证据用途与缺口

| 证据 | 用途 | 限制 |
|---|---|---|
| automation.log / krita/automation.log | 命令、超时traceback、退出诊断 | wmctrl stdout未落盘；父日志为合并副本，不是第二次运行 |
| phase-events.jsonl / krita/phase-events.jsonl | 阶段单调时间与状态 | 两份事件流是汇聚/原流，不能计为重复执行 |
| krita/krita-process.json | 启动PID/PPID/birth/exe/cgroup/窗口/xcb | 只存启动窗口，不是高压窗口历史 |
| process-observations.jsonl | 进程全元组；仅一个Krita身份被观测 | 最后完整Krita记录t=237.101368208，失败实际元组缺失 |
| samples.csv | 4743个workload样本，RSS/CPU及独立cg内存 | 抛错的子样本未写入；CSV同时包含parent，分析先按scope过滤 |
| cgroup-observations.jsonl / cgroup-end.json | 归属、最后成员集合、终态内核状态 | cgroup.procs只有PID，不提供终态exe/PPID/birth |
| memory-events.jsonl / summary.json | PSI/OOM计数与有效性 | 无OOM不等于文档业务成功 |
| krita/finished.json | 自动化退出1及时间 | 不是Krita退出状态；error=null不是业务通过 |
| krita/workload-pid.json / unit-identity.json / systemd-start.json | 自动化11954、supervisor11952及精确unit绑定 | 无法恢复未记录的新PPID |
| metadata.json / stop-request.json | 错误、cooperative_stop、终态标志 | metadata.error为次生身份错误；主超时要结合自动化日志 |
| cleanup.json / journal.log / cooldown.jsonl | 精确unit停止、冷却与最终边界 | 清理释放不能当成自然业务释放 |
| assets_manifest*.json / config.snapshot.json | 素材前后不变与参数 | 离线文件验收不能证明应用内部打开成功 |
| 原结果automation_error_excerpt.txt | 便于定位原traceback | 在结果目录，非run/krita下；不是新增原始证据 |
| remaining-processes.json | 正常路径会生成 | 本轮不存在；采样异常先于该写入点 |
| krita/krita-post-process.json | 正常路径后续实例身份 | 本轮不存在；未启动中压实例 |

不存在的高压标题快照、截图、图层/进度/响应证据、失败实际身份三元组，全部明确标UNKNOWN；不伪造、不补采。原始37成员无删除、覆盖或清理。

## 源码与只读核对

固定提交 `6ce22767fdd91ea23d1e4fab0f071a19c44ea92a` 下的 scripts/krita_auto.py（identity/owned/windows/find_window/wait_until/open_document/graceful_shutdown）、oomlab_krita_collect/metrics.py、worker.py、engine.py、units.py 与本地源码一致。报告链接固定到该提交，不引用后续浮动分支解释过去事件。

本次前后应保持：工作分支mxt、HEAD=origin/mxt=`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`；origin/main=`b65b76724c440d9c48738dd063b9311245aad178`；工作区无改动。诊断只新建results/maintenance下文件和独立报告发布检出，不切换原repo、不改mxt/main、不产生代码提交。

宿主环境只读核对时间：2026-11-27 18:49:40 +0800；匹配的Krita/采集器/system_memory_watch进程列表为空，原unit inactive/dead、MainPID=0、ControlGroup空，原slice cgroup不存在。检查只读，没有重新stop/kill。沙箱内的pgrep只会看到工具自身，未用于证明宿主无残留；最终采用宿主/proc与systemctl只读结果。

本次未修改实现，不执行新的GUI实验或实现测试；所提测试仅为下一轮计划。交付检查限Markdown链接/内容、37成员复核、Git差异与原hooks。
