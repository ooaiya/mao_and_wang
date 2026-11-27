# 进程盘点：历史与当前分开

> 发布说明：本次依据用户随后“报告传到github的mxt_codex”的授权，仅发布Markdown报告。文中不提交/推送的限制描述此前只读诊断阶段。原始数据、CSV、日志、JSON与PNG留在VM。

历史process-observations仅有krita scope，共46种PID/starttime身份；cgroup-observations也只覆盖实验子域及父slice。不是全机进程快照。历史Krita的VmRSS存在samples（最大7.240GiB）；其他进程在故障时刻RSS均UNKNOWN。

|历史身份|exe|角色|首次观测相对秒|RSS证据|
|---|---|---|---:|---|
|151752 / 26645577|/usr/bin/python3.10|automation_or_helper|0.107110|UNKNOWN|
|151754 / 26645587|/usr/bin/krita|krita|0.107396|samples.csv|
|151755 / 26645587|/usr/bin/wmctrl|automation_or_helper|0.107427|UNKNOWN|
|151750 / 26645536|/usr/bin/python3.10|supervisor|0.107448|UNKNOWN|
|151765 / 26645689|/usr/bin/wmctrl|automation_or_helper|1.130453|UNKNOWN|
|151794 / 26646612|/usr/bin/wmctrl|automation_or_helper|10.379047|UNKNOWN|
|151805 / 26646713|/usr/bin/xdotool|automation_or_helper|11.387683|UNKNOWN|
|151828 / 26646835|/usr/bin/xdotool|automation_or_helper|12.637651|UNKNOWN|
|151861 / 26646963|/usr/bin/xwininfo|automation_or_helper|13.877636|UNKNOWN|
|151872 / 26647036|/usr/bin/xdotool|automation_or_helper|14.632114|UNKNOWN|
|151881 / 26647339|/usr/bin/wmctrl|automation_or_helper|17.627390|UNKNOWN|
|151920 / 26648839|/usr/bin/wmctrl|automation_or_helper|32.646374|UNKNOWN|
|151963 / 26650305|/usr/bin/python3.10|automation_or_helper|47.298051|UNKNOWN|
|151972 / 26650326|/usr/bin/xdotool|automation_or_helper|47.538924|UNKNOWN|
|151975 / 26650343|/usr/bin/xdotool|automation_or_helper|47.785152|UNKNOWN|
|151981 / 26650370|/usr/bin/xdotool|automation_or_helper|48.047824|UNKNOWN|
|151988 / 26650405|/usr/bin/xwininfo|automation_or_helper|48.301675|UNKNOWN|
|151997 / 26650425|/usr/bin/xdotool|automation_or_helper|48.555213|UNKNOWN|
|152011 / 26650928|/usr/bin/xdotool|automation_or_helper|53.578592|UNKNOWN|
|152027 / 26651423|/usr/bin/xdotool|automation_or_helper|58.576234|UNKNOWN|
|152035 / 26651910|/usr/bin/xdotool|automation_or_helper|63.352522|UNKNOWN|
|152040 / 26651926|/usr/bin/xdotool|automation_or_helper|63.606291|UNKNOWN|
|152050 / 26652409|/usr/bin/xdotool|automation_or_helper|68.345622|UNKNOWN|
|152067 / 26652910|/usr/bin/xprop|automation_or_helper|73.354835|UNKNOWN|
|152071 / 26652925|/usr/bin/xdotool|automation_or_helper|73.595290|UNKNOWN|
|152077 / 26653404|/usr/bin/xdotool|automation_or_helper|78.344847|UNKNOWN|
|152079 / 26653421|/usr/bin/xdotool|automation_or_helper|78.641160|UNKNOWN|
|152098 / 26653538|/usr/bin/wmctrl|automation_or_helper|79.655942|UNKNOWN|
|152116 / 26653673|/usr/bin/xdotool|automation_or_helper|81.145939|UNKNOWN|
|152154 / 26654840|/usr/bin/wmctrl|automation_or_helper|92.651243|UNKNOWN|
|152170 / 26655665|/usr/bin/wmctrl|automation_or_helper|100.916056|UNKNOWN|
|152185 / 26656440|/usr/bin/wmctrl|automation_or_helper|108.643842|UNKNOWN|
|152250 / 26658765|/usr/bin/wmctrl|automation_or_helper|131.904259|UNKNOWN|
|152266 / 26659591|/usr/bin/wmctrl|automation_or_helper|140.158101|UNKNOWN|
|152299 / 26660992|/usr/bin/wmctrl|automation_or_helper|154.167849|UNKNOWN|
|152313 / 26661715|/usr/bin/wmctrl|automation_or_helper|161.412217|UNKNOWN|
|152363 / 26663870|/usr/bin/wmctrl|automation_or_helper|182.947238|UNKNOWN|
|152373 / 26664345|/usr/bin/wmctrl|automation_or_helper|187.718995|UNKNOWN|
|152399 / 26664869|/usr/bin/wmctrl|automation_or_helper|192.964848|UNKNOWN|
|152410 / 26665446|/usr/bin/wmctrl|automation_or_helper|198.713679|UNKNOWN|
|152420 / 26665972|/usr/bin/wmctrl|automation_or_helper|203.968851|UNKNOWN|
|152433 / 26666597|/usr/bin/wmctrl|automation_or_helper|210.212985|UNKNOWN|
|152434 / 26666648|/usr/bin/wmctrl|automation_or_helper|210.741856|UNKNOWN|
|152448 / 26667374|/usr/bin/wmctrl|automation_or_helper|217.978341|UNKNOWN|
|152474 / 26668482|/usr/bin/wmctrl|automation_or_helper|229.068502|UNKNOWN|
|152492 / 26669119|/usr/bin/wmctrl|automation_or_helper|235.443148|UNKNOWN|

A. 启动前常驻：旧environment的xwayland_pids和GNOME会话/AT-SPI检查证明桌面环境存在；故障窗口system journal有gnome-shell[1307]，不能给出其历史RSS。预检conflicts=[]仅说明该瞬间没有命中禁用进程/服务/socket或单进程RSS>1GiB规则，不排除多个中等RSS进程。

B. Krita启动后的辅助进程：上表的automation/supervisor以及已观测短命helper属于实验边界。PID首次观测不等于真实创建时间，starttime保留在历史机器表中。

C. 导入期间新出现的其他边界外进程：UNKNOWN，无全机连续PID/RSS/启动快照，不能从本表推断没有其他进程启动。

D. 无关并行进程：GNOME活动有journal佐证，文件管理器、浏览器、数据库、更新服务、Codex等历史RSS与是否在关键时刻增长UNKNOWN。窗口告警不证明内存泄漏，也未发现可确证的大RSS竞争进程记录。

## 当前重启后状态

以下只描述新boot；完整ps aux、系统和用户运行服务分别在current/processes.txt、services.txt和user_services.txt。当前最大的常驻RSS主要是GNOME Shell、Codex与XWayland，未在进程列表发现实验应用本体；不能据此排除历史干扰。


当前进程摘要：GNOME Shell RSS约262MiB、Codex约247MiB、XWayland约81MiB；系统/用户服务完整快照在VM诊断目录current/。本次仅上传整理后的盘点，不上传ps或服务原始输出。以上为重启后状态，不能回填故障时刻。
