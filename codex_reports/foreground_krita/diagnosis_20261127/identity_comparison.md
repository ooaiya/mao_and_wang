# 进程身份逐字段对照与异常调用链

实验批次：`krita_single_20261127_182751`

run：`20261127T103129Z-95a8a57da8714bf5bfd0bf2ac24be523/19e3a414871c4c2fbda72b20c3468523`

源码基准：`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`；诊断日期：2026-11-27（Asia/Shanghai）。

本次仅只读分析旧记录；未启动 Krita、未重采、未改代码或配置、未执行清理。原始 run 保留。文中“已证实”表示原始证据或固定提交控制流直接支持；“推断”不替代实测；UNKNOWN 表示未记录，不能追溯补造。

## 基准与字段

原始事件名称是 `KRITA_PROCESS`，并非名为 KRITA_START 的事件；以该启动事件和 `krita/krita-process.json` 为基准。应用由自动化 Popen 创建；worker 的 workload-pid.json 指明自动化 PID=11954。unit 的 MainPID=11952 是 supervisor，不是 Krita。

| 字段 | 初始记录 | 所有后续完整 Krita process-observations | 失败瞬间/终态 | 是否变化 |
|---|---|---|---|---|
| PID | 11956 | 11956 | 终态 cgroup.procs 仍有 11956 | 没有观测到不同 Krita PID；不能单凭 PID 数字证明终态完整身份 |
| PPID | 11954 | 11954 | UNKNOWN；父自动化已退出 | 未捕获变化后的值；重新托管是推断 |
| starttime | 579752（内核时钟 tick） | 579752 | UNKNOWN | 未观测到变化；不能认定 PID 重用 |
| executable | /usr/bin/krita | /usr/bin/krita | UNKNOWN | 未观测到变化 |
| cgroup | 0:: 后为下述路径 | 相同路径（观测不带 0:: 前缀） | 终态该 workload cgroup 中仍有 11956 | 未观测到越界 |

workload 路径：`/user.slice/user-1000.slice/user@1000.service/oomcollect.slice/oomcollect-19e3a414871c4c2fbda72b20c3468523.slice/oomcollect-19e3a414871c4c2fbda72b20c3468523-krita.service`。

第一次完整 Krita 进程清单 monotonic_ns=5797727529247；最后一次为 6034551385603（t=237.101368208 s）。其间所有 Krita 完整身份 tuple 一致。最后成功子 cgroup 采样 t=237.175358488 s 仍是 PPID=11954、starttime=579752、状态 R。该采样的进程字段不包含 exe，不能把它充当同一时刻的完整 exe 证据。

终态边界 parent procs=[11948,11952,11956]，krita procs=[11952,11956]；11948 为 hold supervisor，11952 为 workload supervisor，11954 自动化已消失。journal 还记录过 dconf helper 11965。不存在已记录的第二 Krita PID；未发现证据支持重启，但未记录的极短间隙仍不能被绝对排除。

## 两处守卫必须区分

| 位置 | 比较条件 | 本轮证据 |
|---|---|---|
| krita_auto.py owned() | Popen 未退出；PPID=os.getpid()；starttime=CTX birth；exe basename=krita | 可抛“本轮Krita已退出”或“本轮Krita进程身份改变”；本轮英文异常不来自这里 |
| metrics.py process_sample() | 使用记录 PID；比较 (starttime,PPID,完整exe路径) 与启动记录；之后另查 cgroup | 第 101 行抛英文 `Krita process identity changed`；说明比较不符，但没有差值输出 |
| units.py check_members/check_descendants | 遍历成员/派生进程，核验出生时间与 cgroup 边界 | 本轮没有该处对应的 PID reused/escaped 异常文本 |
| units.py stop() | UUID unit、Description、Slice、ControlGroup、supervisor PID/starttime，停止后为空 | cleanup.json 显示成功，没有名称全局 kill |

源码：[owned()](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/scripts/krita_auto.py#L57)、[process_sample()](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/oomlab_krita_collect/metrics.py#L92)、[单位身份与清理](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/oomlab_krita_collect/units.py#L36)。

process_sample 在 Z/X 时返回空，在 /proc 文件消失时返回空；本轮却抛身份比较异常，因此不能把它解释成普通“进程不存在”。它在三元组比较后才检查 cgroup；本次报错点没有执行到后续 cgroup 分支，不能以未出现越界报错证明失败瞬间 cgroup 已被该函数核验。

## 时序与因果链

| 事件 | monotonic_ns | t/s |
|---|---:|---:|
| 高压确认超时 | 6024342842324 | 226.892824929 |
| graceful Popen.wait 超时 | 6034364033302 | 236.914015907 |
| GRACEFUL_CLEANUP_DONE，ok=false | 6034364359227 | 236.914341832 |
| 最后成功 Krita 采样 | 6034625375883 | 237.175358488 |
| worker 完成，自动化 exit=1 | 6034683696600 | 237.233679205 |
| stop-request，英文身份错误 | 6034699114277 | 237.249096882 |
| systemd 开始停止 unit（journal 墙钟） | 不与单调时间伪精确对齐 | 18:35:30 +0800 |

graceful_shutdown 的 wait 超时证明等待截止时 Popen 尚未等到应用退出；不能据它判 GUI 永久挂死。自动化返回以后 Popen 对象不再由该进程持续观测，**失败瞬间的 Popen.poll 值 UNKNOWN**。

自动化主异常分支明确调用 graceful_shutdown 并返回 1；worker `p.wait()` 后才写 finished；采集器先 sample_rows，再检查 finished，sample_rows 先调用 process_sample 再写子样本。由此可定位英文错误发生于**加载超时后的自动化退出交界、systemd stop 之前**，不是加载等待中 owned() 报错。它中断了正常 finishes/remaining-processes 汇总，把 metadata.error 留成次生错误，主超时仍保留在 automation.log/phase-events。

最可能解释是 11954 退出时，尚存 Krita 的 PPID 重新托管，引发仍按最初 PPID 比较的采样守卫。该解释与父已消失、子仍在、发生顺序及代码相符；但是失败元组未落盘，**具体变更字段、实际新 PPID、是否存在其他竞态均 UNKNOWN**。不能将 11952、1124 或 1 猜写成实际新 PPID，更不能改称已确认 PID 重用。

## 清理结论

cooperative_stop 确实执行并写 stop-request；因为 finished 已存在，其等待循环无需继续采样，cooperative_worker_completed=true 只证明 worker 完成标记存在。随后终态 snapshot 保存成员，Unit.stop 在所有权守卫后停止本 UUID unit；hold 与 slice 也成功。没有已记录的二次 stop 失败。remaining-processes.json 缺失由控制流提前跳出解释，不是已经存在后又被删除的证据。

下一轮若要修复，必须先让失败差值与状态转换有证据；不删 PPID/starttime/exe/cgroup 守卫、不全局按名终止进程。仅方案见 [next_fix_plan.md](next_fix_plan.md)。
