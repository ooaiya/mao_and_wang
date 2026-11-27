# 第三轮异常与证据边界

实验批次：`krita_single_round3_20261127_190942_e44a5be1`。唯一 run ID：`a2f75d1e2f2f4163850e7f0baa56433a`。

代码：`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`（mxt，前后工作区均干净）；配置 SHA256：`ce9e225a8ab42eb6aa79f161227f1a98e2284b6e11a6f9ddf4d1e8b5ce3ee80d`。

本轮仅执行一次原采集器 collect（--operation krita --rounds 1）；未重构代码、未修改实验配置/素材、未启动其他应用、未自动重试。GitHub仅上传本批次Markdown，原始数据、JSON、日志和PNG全部留VM。

## 主异常

t=73.770084656s提交46层ORA；t=234.028203542s阶段5FAILED，原文 `TimeoutError('素材加载超时；最后诊断=None')`；间隔160.258118886s。open_timeout_s仍160。没有HIGH_DOCUMENT_OPEN_DONE、capture窗口或第二实例事件。主故障可确定为**加载确认超时**，不能进一步确定实际导入失败/仍在导入/标题识别漏判。

`wait_until` 的 last只在捕获GuiPending或subprocess.TimeoutExpired时更新，普通False结果不更新，因此None不证明窗口不存在、GUI响应正常或加载完成。日志保存wmctrl命令而未保存当时stdout，无法恢复高压实际标题；本次严格保持原代码，没有补装探针或伪造历史窗口快照。实际加载状态仍为D（证据不足）。

## 退出等待与采集器身份异常

| 事件 | t/s |
|---|---:|
| 阶段5确认超时 | 234.028203542 |
| GRACEFUL_EXIT_DIAGNOSTIC | 244.057057065 |
| GRACEFUL_CLEANUP_DONE | 244.057185867 |
| worker finished（自动化exit1） | 244.274933454 |
| 采集器stop-request（身份错误） | 244.295775619 |

原graceful Popen.wait异常为 `TimeoutExpired(['krita', '--nosplash'], 9.852288776000933)`。finished.error=null仅说明worker包装没有异常，不能当业务通过，returncode1属于自动化而不是Krita退出码。

启动身份：PID=16671，PPID=16669，starttime=817373，exe=/usr/bin/krita。process-observations中完整Krita身份共有1组；已记录的元组一直一致，最后完整观察t=244.096789265s；最后成功进程采样t=244.220013436s仍PPID=16669、starttime=817373。

终态krita cgroup.procs=[16667, 16671]；原自动化PID16669已不在其中，而应用PID16671尚在。worker完成至stop-request相隔20.842165ms。源码路径是自动化异常处理→graceful失败→自动化退出→worker完成→下一次采样比较异常→cooperative_stop→unit清理。这与上一轮的次生退出交界问题一致，并非仅依据时间相近关联。

英文异常来自metrics.process_sample()的(starttime,PPID,完整exe)比较，不是自动化owned()的中文异常；失败实际值未落盘，**具体字段UNKNOWN**。父退出后的PPID重新托管最符合现有线索，但未捕获实际新PPID，不作已证实结论，不认定PID重用、重启或越界。

## 环境与数据影响

PSI Full/Some avg10最大0、total增量0；Swap使用0、换入换出0；OOM/oom_kill增量0。没有证据将本轮归因于系统内存保护触发。活动内存增长不是导入完成证据；低于上一轮的局部峰也不是修复效果。

采样异常先于采集器正常finishes/remaining-processes写入点，因此metadata缺finishes、remaining-processes.json不存在；后续中压实例未执行，因此krita-post-process.json不存在。metadata.error是次生错误，主异常仍在automation.log与phase-events中。原封存37成员均通过，文件未被事后删改。

## 清理与自然释放

原采集器保存终态后停止精确UUID unit，cleanup_ok/cooldown_ok/journal_ok均true；systemd清理日志保留。服务被停止造成的释放不能标为正常关闭自然释放。没有获得第一实例正常退出证明；不根据局部RSS或某条线程SIGKILL日志编造整个应用的最终信号。

只读复查没有Krita、其他实验应用、collector、worker、system_memory_watch或oomcollect unit；run parent cgroup不存在。未执行额外按名kill或清理。整轮继续判PILOT_INVALID，已停止，不自动重试。
