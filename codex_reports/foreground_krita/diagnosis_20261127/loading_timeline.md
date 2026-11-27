# 46 层加载时间线与窗口识别分析

实验批次：`krita_single_20261127_182751`

run：`20261127T103129Z-95a8a57da8714bf5bfd0bf2ac24be523/19e3a414871c4c2fbda72b20c3468523`

源码基准：`6ce22767fdd91ea23d1e4fab0f071a19c44ea92a`；诊断日期：2026-11-27（Asia/Shanghai）。

本次仅只读分析旧记录；未启动 Krita、未重采、未改代码或配置、未执行清理。原始 run 保留。文中“已证实”表示原始证据或固定提交控制流直接支持；“推断”不替代实测；UNKNOWN 表示未记录，不能追溯补造。

所有 t 均以原 origin_monotonic_ns=5797450017395 为基准；墙钟不参与毫秒级排序。

| 事件 | t/s | 解释 |
|---|---:|---|
| phase 1 start | 0.064737919 | 启动 |
| KRITA_PROCESS | 10.124104452 | PID11956，主窗口0x01400019，初始标题Krita |
| phase 1 PASS | 10.124266267 | 启动检查通过 |
| phase 2 PASS | 10.203969012 | 主窗口布局检查通过 |
| DOCUMENT_OPEN_START | 10.204110519 | 低压文档打开 |
| DOCUMENT_OPEN_DONE | 33.455418366 | 标题确认返回 |
| PRE_IMPORT_REVIEW_START | 34.292458934 | 低压浏览开始 |
| PRE_IMPORT_REVIEW_DONE | 64.293196904 | 30.000737970秒完成 |
| phase 4 PASS | 64.293305749 | 低压段完成 |
| phase 5 start | 64.293363799 | 关闭低压，打开46层 |
| HIGH_DOCUMENT_OPEN_START | 64.427471887 | 目标ORA准备打开 |
| HIGH_DOCUMENT_SUBMITTED | 66.726307588 | 已提交目标路径，不等于加载完成 |
| phase 5 FAILED | 226.892824929 | 标题确认超时 |
| GRACEFUL_EXIT_DIAGNOSTIC | 236.914015907 | 约9.834429秒退出等待超时 |
| GRACEFUL_CLEANUP_DONE | 236.914341832 | ok=false |
| worker finished | 237.233679205 | 自动化exit1 |
| stop-request | 237.249096882 | 采集器身份比较异常 |

## 文件和窗口证据

提交的完整路径：

`/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46/layered_9000_46.ora`

输入 124,404,893 字节，原 SHA256=`100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a`。已有逐层解码/CRC 验收通过，原运行前后资产清单一致；这是输入有效性证据，不能代替 Krita 内部导入成功。

初始主窗口有保存 PID/geometry/xproperties，Qt xcb 已验证。启动期间发现过 `0x01400023` 等候选，start_krita 有启动窗口重绑定逻辑。高压文件对话框 ID=`0x01400194`，日志包含对其 xprop/xwininfo 和路径输入命令。失败栈停在第268行而非第264/267行，所以对话框出现、路径提交、原 ID 消失检查已经返回。该判断来自顺序控制流与日志，不声称恢复了当时所有窗口。

打开46层前没有保存完整即时窗口快照；不能把10秒启动标题当作64秒时的实际标题。高压期间只记录了 `wmctrl -lpG` 等命令文本，未持久化 stdout。**提交后实际标题、每次窗口PID、多窗口数目、主窗口是否重建、是否出现新模态窗口均 UNKNOWN。** 初始绑定与守卫证明了部分先验，不证明整个等待期间每一个窗口状态。

## 标题匹配的准确含义

源码 [windows()](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/scripts/krita_auto.py#L65) 将 wmctrl 行按 `split(None,8)` 解析，只有9段才入列表；PID 来自第3段，标题为第9段。未记录原始行，无法排查某个真实行是否被解析忽略。标题包含空格本身可被最后一段保留。

[document_named()](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/scripts/krita_auto.py#L252) 先检查窗口 PID=CTX pid，再用下面正则匹配：

```text
(?<![\w.])layered_9000_46(?:\.ora)?(?![\w.])
```

大小写不敏感；stem 经 re.escape。下面仅为**按代码推导的候选测试字符串，不是历史实测标题，也不是确认的 Krita 5.0.2 标题模板**：

| 假设标题 | 预期匹配 | 用途 |
|---|---|---|
| layered_9000_46.ora — Krita | 是 | 完整文件名加应用后缀 |
| layered_9000_46 — Krita | 是 | 无扩展名 |
| *layered_9000_46.ora | 是 | 修改标记 |
| Krita | 否 | 标题尚未更新或只显示应用名 |
| Untitled — Krita | 否 | 其他文档名/临时文档 |
| layered_9000_46_copy.ora | 否 | 后缀下划线属于word边界限制 |
| layered_9000_46.ora.backup | 否 | 点后缀会被边界拦截 |

因此常见的空格、破折号、大小写和可选 .ora 本身不会让该正则失败；缺少实际标题就不能宣称正则存在某个已复现漏判。Linux/XWayland 的本轮实际格式只能重新通过获授权的状态观测确认，本次不启动 GUI 获取它。标题延迟、文档内部名称、窗口PID缺失/不符、窗口重建或列表解析漏项都是待证假设，没有优先选成根因。

该谓词扫描本 PID 的任一窗口，不限最初主窗口ID，也不在此步验证 NORMAL、WM_CLASS、IsViewable、活动文档路径或图层数；故同PID窗口重建并不必然造成失败，反过来同PID标题匹配也不一定证明目标文档加载完成。find_window 有更强的类型和属性校验，但此标题等待没有调用它。[窗口选择](https://github.com/ooaiya/mao_and_wang/blob/6ce22767fdd91ea23d1e4fab0f071a19c44ea92a/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C/%E5%89%8D%E5%8F%B0%E6%93%8D%E4%BD%9C%E8%87%AA%E5%8A%A8%E5%8C%96%E8%84%9A%E6%9C%AC%E9%87%87%E9%9B%86/scripts/krita_auto.py#L73)。

last diagnostic=None 的精确定义：本次 wait_until 没有捕获并记录 GuiPending/subprocess.TimeoutExpired；普通 False 探针不更新 last。不能理解为没有诊断到任何窗口，也不能理解为无响应检测已经证明 GUI 健康。

## 提交后资源活动（原始字节）

| t/s | current | anon | file | VmRSS | 累计CPU ticks | 状态 |
|---:|---:|---:|---:|---:|---:|---|
| 66.736664215 | 809607168 | 600215552 | 199827456 | 785068032 | 3061 | S |
| 96.736985047 | 2732023808 | 2518859776 | 199827456 | 2704289792 | 6056 | R |
| 156.705738024 | 5980528640 | 5761118208 | 199831552 | 5946273792 | 12046 | R |
| 216.722607306 | 9252327424 | 9026322432 | 199831552 | 9211387904 | 18042 | R |
| 226.876064020 | 9785225216 | 9558192128 | 199835648 | 9743093760 | 19056 | R |
| 236.925476301 | 10324959232 | 10096799744 | 199839744 | 10281848832 | 20060 | R |
| 237.175358488 | 10335899648 | 10100568064 | 199839744 | 10293436416 | 20085 | R |

这些实际采样点显示提交后到退出等待结束仍有持续资源增长，约一个CPU核心的活动量；file 约0.186 GiB基本稳定，主要增长在anon。最后正常元组中的 PID/PPID/starttime 保持一致。CPU 非零不能证明具体执行的是解码、合成、界面更新还是其他计算，更不能据9.6GiB RSS判46层已加载。

本轮没有记录导入进度百分比、46层可访问性状态、文档就绪回调、截图或独立事件循环响应探针。没有 high-open-done/capture 事件。**最终选择 D；B 为有资源活动支持的待验证解释，A/C 也未证实。** 没有已证实的160秒内额外异常，不等于能排除所有未观测的GUI问题。
