# 完整代码差异（Markdown审阅副本）

基准 `6ce22767fdd91ea23d1e4fab0f071a19c44ea92a` → 代码提交 `bc8018ac6d2edb0bda077b23818b7247a2343c67`。原patch为 91314 字节，SHA256 `723648cd4021f7cb20fb5f7a92443326da7015c0bdde21681d07753f22886489`。为保留patch中的行末空白且通过文档空白检查，行末ASCII空格显示为␠、Tab显示为⇥；将这两个标记分别还原为空格和Tab即可逐字节恢复原patch，其余内容未变。本文件仅供审阅，不在mxt_codex应用代码变更。

````diff
diff --git a/前台操作/前台操作自动化脚本采集/MANUAL_HIGH_IMPORT.md b/前台操作/前台操作自动化脚本采集/MANUAL_HIGH_IMPORT.md
new file mode 100644
index 0000000..8ab34fb
--- /dev/null
+++ b/前台操作/前台操作自动化脚本采集/MANUAL_HIGH_IMPORT.md
@@ -0,0 +1,85 @@
+# 46层 ORA 人工导入确认
+
+本次改造只替换高压46层文档的打开确认；开发验收不启动Krita或正式采集。正式运行须在用户审核后另行发起。
+
+## 配置与运行边界
+
+新增 `configs/collection.rapid-9000-manual-high-import.json`，按当前VM上一轮的实际配置复制，唯一行为字段差异是 `automation.manual_high_import=true`。原部署配置、其他模板及前三轮结果不覆盖。该开关仅允许prepared_document为46层、9000×9000的timed_window实验；不设置开关的旧模式保留，用于兼容与回归。
+
+Krita5.0.2、46层素材及SHA256、原7层中压素材、tile67%、低压30秒、高压12秒、中压30秒、50ms采样、最大500ms缺口、全部安全阈值和1800秒整体上限保持原值。open_timeout_s仍160，继续用于原自动低压/中压打开；人工等待不套用这个超时，也不把它增加到600秒。整体运行上限从原采集器启动门开始约束，人工等待和核验都包含在内，不能无限等待。
+
+人工导入目标：
+
+```text
+/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46/layered_9000_46.ora
+size = 124404893
+sha256 = 100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a
+```
+
+## 交互流程
+
+1. 在VM的真实前台终端启动原 `scripts/collect_krita.py`，选择新增配置和新的外部结果目录。不能重定向stdin、使用nohup/后台任务或通过非交互Codex工具假装输入。前台检查使用 `sys.stdin.isatty()`、字符设备和 `tcgetpgrp()==getpgrp()`；失败在启动业务应用前拒绝。
+2. 自动启动、身份/窗口归属检查、低压打开、30秒浏览及关闭低压文档沿用原逻辑。
+3. 前台显示 `[MANUAL IMPORT REQUIRED]` 与完整目标路径。用户在已启动的Krita中手动Ctrl+O，选择46层ORA，等待导入结束，检查画布和图层面板，然后返回终端。
+4. 仅接受整行 `READY 46` 或 `ABORT`。错误输入重新提示；部分输入不确认；提示前排队的旧输入丢弃。ABORT或终端EOF进入原有安全停止/精确unit清理路径，不继续捕获。
+5. READY收到时立即保存终端读取的实际monotonic/wall时间；不开始12秒。再次核验完整进程身份、唯一可见正常窗口、无残留文件/模态框、AT-SPI及图层数，并等待采样器对新一轮parent/workload样本完成原安全检查。
+6. 核验通过发出HIGH_DOCUMENT_READY，从该时点完整捕获12秒。核验失败发出HIGH_DOCUMENT_READY_FAILED并停止，不能发出成功事件或进入中压。
+7. 成功后原关闭第一实例、验证正常退出、第二实例、自动7层文档、中压30秒、退出、清理、封存及验证流程保持原样。异常unit清理释放不能当作自然业务释放。
+
+```mermaid
+flowchart LR
+    L[自动低压30秒并关闭] --> W[人工导入等待]
+    W -->|READY 46及输入时间| V[身份 窗口 图层 安全核验]
+    W -->|ABORT EOF 安全停止 总超时| F[失败并清理]
+    V -->|失败| F
+    V -->|通过 HIGH_DOCUMENT_READY| H[完整12秒捕获]
+    H --> O[原关闭与第二实例中压流程]
+```
+
+## 终端、采样与安全检查的分工
+
+systemd worker内的自动化原本没有交互stdin。生产实现不分配伪终端、不把文件或管道伪装为TTY：只有前台collector读取用户的真实stdin。一个独立输入线程使用select/os.read轮询，通过本run的请求/应答文件转交输入及原始时间戳。GUI自动化继续独立运行，采样主循环没有readline、input或等待用户的阻塞调用。终端线程在封存前停止。
+
+自动化每次人工等待轮询都验证原Popen仍存活、PID、PPID、starttime、完整executable和cgroup，并检查停止请求与原整体截止时间。原50ms采样、OOM/PSI/Swap/内存保护持续工作。READY核验的安全应答只在两种scope都取得请求之后的新样本、通过原enforce/OOM/持续PSI检查并写CSV后产生；另核对原磁盘余量阈值。应答超过500ms或无法对应原CSV时拒绝放行。未删除或放宽任何身份/cgroup守卫。
+
+## 证据与验证等级
+
+所有新协议文件都在新run目录，随原manifest.sha256封存，不进入Git：manual-terminal.json、manual-import-request.json、manual-import-response.json、manual-safety-request.json、manual-safety.json，以及krita/high-document-manual-evidence.json。
+
+READY证据保存完整wmctrl stdout、本PID窗口的xprop与xwininfo、当前活动窗口ID及其xprop、AT-SPI stdout/stderr/解析快照、核验前后完整身份、Layers观测值、标题匹配结果与安全应答。用户返回终端后活动窗口可以是终端；这只作为证据保存，不向终端发送GUI输入。
+
+| 结果 | 处理与报告 |
+|---|---|
+| 唯一Layers表=46，标题匹配，其他检查通过 | MACHINE_VERIFIED；机器独立核对层数和文档名，仍保留用户确认记录 |
+| AT-SPI无法提供唯一层数，其他检查通过 | MACHINE_LAYER_CHECK_UNAVAILABLE；document_verification=USER_CONFIRMED，不标作机器成功 |
+| 层数=46但标题不匹配 | 保存实际标题、title_matches_expected=false，document_verification=USER_CONFIRMED |
+| 机器明确读到非46层、窗口/身份不符、模态框或安全失败 | FAILED，停止；人工READY不能覆盖 |
+| 没有完成核验、没有成功/明确失败结果 | NOT_VERIFIED，流程不完整，不能通过完整实验验收 |
+
+机器独立核对范围是可访问性层数、窗口标题和所有权；画布正常显示仍来自用户目视确认。多个Layers表不能冒充唯一机器结果；已知错误层数即使伴随其他AT-SPI错误也不能退回人工放行。
+
+验证器在新模式中增加原始证据、终端来源、字段一致性和安全样本时间校验，并区分以上等级。原8阶段、正常退出、原峰值/平台验收、50ms/500ms、OOM/PSI与封存规则仍执行；不能用READY消除其他失败。计时结束事件的import_verified=false仍保留，表示经过12秒本身不是层数证明。
+
+## 事件和五个时间点
+
+| 事件 | monotonic_ns / wall_time_ns 的含义 |
+|---|---|
+| HIGH_DOCUMENT_MANUAL_IMPORT_START | 关闭低压文档之后，开始人工等待 |
+| HIGH_DOCUMENT_USER_READY | 终端线程实际收到READY整行的原时间，跨进程原样保留 |
+| HIGH_DOCUMENT_MACHINE_VERIFY_START | 自动化实际开始READY核验 |
+| HIGH_DOCUMENT_MACHINE_VERIFY | 身份/窗口/图层及新安全应答核验结束 |
+| HIGH_DOCUMENT_READY | 核验通过后正式12秒起点；不能回填为输入或开始导入时刻 |
+| CAPTURE_WINDOW_START / CAPTURE_WINDOW_DONE | 捕获函数实际进入/退出时间；origin_monotonic_ns必须指向HIGH_DOCUMENT_READY，结束不得早于origin+12秒 |
+| HIGH_DOCUMENT_READY_FAILED | 确认/核验失败，附原错误，不允许有后续成功捕获 |
+
+新HIGH_DOCUMENT事件共同字段至少包括：run_id、request_id、expected_asset、expected_sha256、expected_layers、user_confirmation、manual_wait_duration_s、monotonic_ns、wall_time_ns、krita_pid、window_id、actual_window_title、machine_layer_count、machine_verification_status、process_identity_status、document_verification。未知值明确为null/NOT_VERIFIED；不编造已知值。
+
+USER_READY后保留user_ready_monotonic_ns/user_ready_wall_time_ns；核验结果保留verification_started_monotonic_ns/wall_time_ns，READY再记录verification_finished_monotonic_ns/wall_time_ns。正式高压统计窗口同样从HIGH_DOCUMENT_READY起算，人工等待和核验不混入12秒高压统计，整个原始时间序列仍完整保存。
+
+## 离线验收
+
+`tests/test_manual_import.py`使用虚拟时钟、模拟进程/窗口/AT-SPI、测试私有PTY和fake kernel。生产代码没有创建PTY。覆盖READY/ABORT、非TTY/后台TTY拒绝、错误及部分输入、完整身份字段变化、层数不符、标题不匹配、AT-SPI不可用、模态与多主窗口、原安全停止、200秒人工等待与1800秒总时限、核验后完整12秒、机器/人工证据防混淆、原安全应答及低压/第二实例/中压流程回归。
+
+真实前台PTY子进程测试不mock前台TTY检查，确认输入转交到正确run；另在等待输入时以50ms读取测试私有fake kernel，确认输入等待不阻塞采样。它们都是离线功能测试，不代表已测得真实Krita负载的采样性能或导入成功。
+
+运行原有项目与专项测试时设置测试私有XDG_RUNTIME_DIR，防止锁文件写入沙箱只读/run；不修改生产measurement_lock。完整专项测试包含“源码必须干净”的原有断言，需在代码提交后运行；不删除或mock该断言来伪造通过。
diff --git a/前台操作/前台操作自动化脚本采集/README.md b/前台操作/前台操作自动化脚本采集/README.md
index c32ed2e..8f2a00e 100644
--- a/前台操作/前台操作自动化脚本采集/README.md
+++ b/前台操作/前台操作自动化脚本采集/README.md
@@ -3,3 +3,7 @@
 `scripts/collect_krita.py` 运行独立采集。运行配置为 `configs/collection.rapid-9000-medium-tail-extended.json`，峰前低压和峰后中压的观察窗口各为 30 秒。用 `scripts/prepare_handoff_config.py` 写入当前 VM 的路径、屏幕尺寸和输入摘要。
␠
 [运行步骤](../../复现实验.md) · [场景时序](TIMED_CAPTURE.md)
+
+46层人工导入使用独立配置 `configs/collection.rapid-9000-manual-high-import.json`，参见
+[人工导入、READY 46 与离线验收](MANUAL_HIGH_IMPORT.md)。该模式要求用户在VM真实前台终端启动；
+READY只记录输入时刻，核验完成后的HIGH_DOCUMENT_READY才开始完整12秒。旧配置及历史证据不覆盖。
diff --git a/前台操作/前台操作自动化脚本采集/configs/collection.rapid-9000-manual-high-import.json b/前台操作/前台操作自动化脚本采集/configs/collection.rapid-9000-manual-high-import.json
new file mode 100644
index 0000000..a0a16d5
--- /dev/null
+++ b/前台操作/前台操作自动化脚本采集/configs/collection.rapid-9000-manual-high-import.json
@@ -0,0 +1,97 @@
+{
+  "schema_version": 1,
+  "interval_s": 0.05,
+  "asset": {
+    "path": "/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46/light_9000.ora",
+    "sha256": "87617e94f6170e9e667f0de974df3ca15c9ea4a1023cd5dee92080fe754fc9f8",
+    "width": 9000,
+    "height": 9000,
+    "layers": 1
+  },
+  "display_size": [
+    2552,
+    1200
+  ],
+  "safety": {
+    "max_sample_gap_s": 0.5,
+    "max_other_process_rss_bytes": 1073741824,
+    "min_available_bytes": 1610612736,
+    "min_swap_free_bytes": 322122547,
+    "min_disk_free_bytes": 10737418240,
+    "max_cgroup_bytes": 13314398617,
+    "max_global_full_avg10": 10,
+    "cooldown_cgroup_bytes": 134217728,
+    "cooldown_min_available_bytes": 1610612736,
+    "cooldown_max_full_avg10": 2,
+    "cooldown_timeout_s": 300,
+    "cooldown_stable_s": 5,
+    "run_timeout_s": 1800
+  },
+  "acceptance": {},
+  "forbidden_processes": [
+    "krita",
+    "memshiftd",
+    "memshift_taskctl",
+    "ms_freezer_guard",
+    "xz"
+  ],
+  "forbidden_units": [
+    "memshift",
+    "freezer",
+    "strategy",
+    "oomlab-a-"
+  ],
+  "forbidden_sockets": [
+    "${XDG_RUNTIME_DIR}/memshiftd/control.sock",
+    "/tmp/memshiftd/control.sock",
+    "/data/local/tmp/memshiftd/control.sock"
+  ],
+  "mode": "pilot",
+  "pilot": {
+    "layers_dir": "/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46",
+    "psi_full_sustained_s": 5,
+    "graceful_stop_timeout_s": 30
+  },
+  "automation": {
+    "startup_timeout_s": 60,
+    "open_timeout_s": 160,
+    "import_timeout_s": 60,
+    "close_timeout_s": 75,
+    "unresponsive_timeout_s": 30,
+    "poll_s": 0.5,
+    "accessibility_python": "/usr/bin/python3",
+    "graceful_stop_timeout_s": 10,
+    "completion_mode": "timed_window",
+    "capture_window_s": 12,
+    "pressure_profile": {
+      "pre_import_review_s": 30,
+      "post_close_review_s": 30,
+      "review_interval_s": 5,
+      "post_close_settle_s": 10,
+      "peak_reference_bytes": 12884901888,
+      "peak_tolerance_fraction": 0.04,
+      "max_low_charge_bytes": 4294967296,
+      "max_low_pressure_bytes": 7516192768
+    },
+    "tile_memory_percent": 67,
+    "prepared_document": {
+      "path": "/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_46/layered_9000_46.ora",
+      "sha256": "100c151300f505b83a108d6c36b1a912251b020e7170945fc504274415e0bb8a",
+      "width": 9000,
+      "height": 9000,
+      "layers": 46
+    },
+    "tail_document": {
+      "path": "/home/mxt/TeamOOM/assets/baseline_assets/foreground/krita/rapid_9000_generated_20261127_154636/OOM_assets/krita_rapid_9000_tail_07_medium/layered_9000_07.ora",
+      "sha256": "7d7679e2072c387a207d9d393525a071f59fdfc3eaf7c491051ee402eedcc5aa",
+      "width": 9000,
+      "height": 9000,
+      "layers": 7
+    },
+    "tail_charge_range_bytes": [
+      2147483648,
+      3221225472
+    ],
+    "manual_high_import": true
+  }
+}
diff --git a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/cli.py b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/cli.py
index 1d20d92..eb18fb0 100644
--- a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/cli.py
+++ b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/cli.py
@@ -11,9 +11,11 @@ from .config import read
 from .environment import check
 from .engine import run_one,recipe
 from .validation import report,validate_run
+from .manual_import import enabled as manual_enabled, require_terminal
␠
␠
 def collect(c,args):
+    if manual_enabled(c):require_terminal()
     pilot=c.get('mode')=='pilot'
     if pilot and (args.operation!='krita' or args.smoke or args.resume_session or args.rounds!=1 or args.target_valid_rounds is not None or args.approve_first_summary_sha256 or args.data):raise ValueError('PILOT is exactly one Krita run; no smoke/background/resume/formal continuation')
     base=outside_repo(args.results);base.mkdir(parents=True,exist_ok=True)
@@ -85,6 +87,7 @@ def main(argv=None):
                 with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
             print(json.dumps(result,ensure_ascii=False,indent=2));return 0
         c=read(args.config)
+        if manual_enabled(c):require_terminal()
         if args.action=='preflight':
             result=check(c,args.results)
             if c.get('mode')=='pilot':
diff --git a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/config.py b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/config.py
index 5139692..3b35028 100644
--- a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/config.py
+++ b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/config.py
@@ -58,6 +58,12 @@ def validate_pilot(c):
     timed=a.get('completion_mode')=='timed_window'
     prepared=a.get('prepared_document')
     tail=a.get('tail_document')
+    if 'manual_high_import' in a:
+        if type(a['manual_high_import']) is not bool or not timed or prepared is None:
+            raise ValueError('manual_high_import requires a boolean and a prepared timed ORA')
+        keys.add('manual_high_import')
+        if a['manual_high_import'] and (prepared['layers']!=46 or (prepared['width'],prepared['height'])!=(9000,9000)):
+            raise ValueError('manual high import is only for the 46-layer 9000x9000 ORA')
     if timed:
         keys|={'completion_mode','capture_window_s'}
         keys.add('prepared_document' if prepared is not None else 'timing_basis')
@@ -70,7 +76,7 @@ def validate_pilot(c):
     if set(a)!=keys:raise ValueError('explicit automation deadlines required')
     for k,v in a.items():
         if k not in ('accessibility_python','completion_mode','timing_basis','pressure_profile',
-                     'prepared_document','tail_document','tail_charge_range_bytes'):
+                     'prepared_document','tail_document','tail_charge_range_bytes','manual_high_import'):
             if type(v) not in (int,float):raise ValueError('numeric automation deadline required')
             positive(v)
     if not Path(a['accessibility_python']).is_absolute():raise ValueError('absolute system accessibility Python required')
diff --git a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/engine.py b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/engine.py
index 45b19aa..979fc8a 100644
--- a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/engine.py
+++ b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/engine.py
@@ -10,6 +10,7 @@ from .common import ROOT,GUI,BACKGROUND,save,load,fresh,fingerprint,SCHEMA
 from .metrics import FIELDS,snapshot,deltas,process_sample
 from .environment import controls,conflicts
 from .units import Unit,members,process_cgroup
+from .manual_import import enabled as manual_enabled, TerminalRelay, service_safety_request
␠
␠
 def background():
@@ -96,6 +97,10 @@ def parent_identity(hold,slice_name):
 def run_one(session,c,recipes,environment,offsets=None,test_only=False):
     pilot=c.get('mode')=='pilot' and not test_only
     if pilot and (set(recipes)!={'krita'} or offsets):raise ValueError('PILOT only permits one Krita operation, without offsets')
+    # The CLI rejects non-TTY use before preflight; keep the direct API equally strict.
+    if manual_enabled(c):
+        from .manual_import import require_terminal
+        require_terminal()
     run=fresh(Path(session)/uuid.uuid4().hex); token=run.name;slice_name='oomcollect-'+token+'.slice'
     jobs={};all_units=[];parent=None;start={};end={};origin=time.monotonic_ns();cleanup=[]
     meta=dict(metric_units={'memory':'bytes','time':'monotonic_ns','relative_time':'seconds'},classification='TEST_ONLY' if test_only else 'PILOT' if pilot else 'FORMAL',run_id=token,strategy='none',recipes=recipes,
@@ -107,7 +112,7 @@ def run_one(session,c,recipes,environment,offsets=None,test_only=False):
     (run/'phase-events.jsonl').write_text(json.dumps(dict(schema_version=SCHEMA,event='stream_open',monotonic_ns=time.monotonic_ns()))+'\n')
     with open(run/'samples.csv','w',newline='') as f:csv.DictWriter(f,FIELDS).writeheader()
     journal_ok=True;hold=None;last_inventory=0;meta['krita_xcb_verified']=False
-    indexes={};previous={};pressure_since={};last_events={};paths={};launched=False
+    indexes={};previous={};pressure_since={};last_events={};paths={};launched=False;terminal=None
     (run/'memory-events.jsonl').touch();(run/'cgroup-observations.jsonl').touch();(run/'process-observations.jsonl').touch()
     def sample_rows(writer,check_safety=True):
         for scope,path in paths.items():
@@ -131,6 +136,8 @@ def run_one(session,c,recipes,environment,offsets=None,test_only=False):
                 if old and (row['monotonic_ns']-old['monotonic_ns'])/1e9>c['safety']['max_sample_gap_s']:raise RuntimeError('50ms sampler gap exceeded safety bound')
                 sustained_pressure(row,c,pressure_since,scope)
     try:
+        if manual_enabled(c):
+            terminal=TerminalRelay(run,c);terminal.start()
         if pilot:
             from .pilot_assets import inventory
             assets=inventory(c)
@@ -169,6 +176,7 @@ def run_one(session,c,recipes,environment,offsets=None,test_only=False):
         for op,u in jobs.items():save(u.run/'go.json',dict(start_monotonic_ns=origin+int(meta['offsets'][op]*1e9)))
         launched=True
         next_tick=origin;deadline=time.monotonic()+c['safety']['run_timeout_s']
+        if terminal:terminal.set_deadline(deadline)
         with open(run/'samples.csv','a',newline='') as f:
             writer=csv.DictWriter(f,FIELDS)
             while True:
@@ -176,6 +184,9 @@ def run_one(session,c,recipes,environment,offsets=None,test_only=False):
                 if delay>0:time.sleep(delay)
                 sample_rows(writer)
                 f.flush()
+                if terminal:
+                    terminal.check()
+                    service_safety_request(run,c,previous)
                 if time.monotonic()-last_inventory>=.2:
                     with open(run/'cgroup-observations.jsonl','a') as boundary_log:boundary_log.write(json.dumps(dict(schema_version=SCHEMA,monotonic_ns=time.monotonic_ns(),boundaries=boundary_evidence(paths)))+'\n')
                     with open(run/'process-observations.jsonl','a') as observations:
@@ -220,6 +231,9 @@ def run_one(session,c,recipes,environment,offsets=None,test_only=False):
         if pilot and launched:
             meta.update(cooperative_stop(run,jobs,c,meta['error'],previous,sample_rows))
     finally:
+        if terminal:
+            try:terminal.close()
+            except Exception as e:meta.setdefault('evidence_errors',[]).append('terminal relay: '+repr(e))
         meta['origin_monotonic_ns']=origin
         for scope,path in [('parent',parent)]+[(op,u.path) for op,u in jobs.items()]:
             if path is not None:
diff --git a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/environment.py b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/environment.py
index b31288e..b9f3f16 100644
--- a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/environment.py
+++ b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/environment.py
@@ -52,6 +52,8 @@ def check(c,results,require_gui=True):
     def probe(name,fn):
         try: info[name]=fn()
         except Exception as e: errors.append(name+': '+str(e))
+    from .manual_import import enabled, require_terminal
+    if enabled(c):probe('manual_terminal',require_terminal)
     if os.geteuid()==0: errors.append('run as the logged-in desktop user, never sudo python')
     probe('source',source_identity)
     probe('boot_id',lambda:Path('/proc/sys/kernel/random/boot_id').read_text().strip())
diff --git a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/manual_import.py b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/manual_import.py
new file mode 100644
index 0000000..3bafa87
--- /dev/null
+++ b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/manual_import.py
@@ -0,0 +1,170 @@
+"""Real foreground-terminal input, relayed without blocking the 50 ms sampler.
+
+The systemd automation has no terminal. Do not invent a PTY for it: only the
+foreground collector reads the user's actual stdin. Run-bound files carry the
+receipt timestamp to the independently running automation.
+"""
+import os
+from pathlib import Path
+import select
+import stat
+import shutil
+import sys
+import termios
+import threading
+import time
+from .common import load, save
+
+
+def enabled(config):
+    return config.get('automation', {}).get('manual_high_import') is True
+
+
+def require_terminal(stream=None):
+    stream = sys.stdin if stream is None else stream
+    message = '人工导入需要真实前台TTY；请从VM终端前台启动，不能重定向stdin或后台运行'
+    if not stream.isatty():
+        raise RuntimeError(message)
+    fd = stream.fileno()
+    if not stat.S_ISCHR(os.fstat(fd).st_mode) or os.tcgetpgrp(fd) != os.getpgrp():
+        raise RuntimeError(message)
+    return dict(tty=os.ttyname(fd), reader_pid=os.getpid(), foreground_pgid=os.getpgrp(),
+                stdin_isatty=True, foreground_checked=True)
+
+
+def prompt(asset):
+    return ('\n[MANUAL IMPORT REQUIRED]\n即将导入46层高压 ORA 文档。\n目标文件：\n'
+            + asset + '\n请切换到当前已经启动的 Krita 窗口：\n'
+            '1. 使用 Ctrl+O 或文件菜单打开文件。\n2. 选择上述46层 ORA。\n'
+            '3. 等待文件导入完成。\n4. 确认画布正常显示。\n'
+            '5. 确认图层面板包含46层。\n6. 返回当前终端。\n'
+            '输入 READY 46 确认导入完成；输入 ABORT 安全终止本轮实验。\n')
+
+
+class TerminalRelay:
+    """One bounded input thread; never performs GUI, process or sample queries."""
+    def __init__(self, run, config, stream=None, output=None):
+        self.run = Path(run)
+        self.asset = config['automation']['prepared_document']
+        self.stream = sys.stdin if stream is None else stream
+        self.output = sys.stdout if output is None else output
+        self.identity = require_terminal(self.stream)
+        self.stopping = threading.Event()
+        self.error = None
+        self.thread = threading.Thread(target=self._run, name='krita-terminal-input', daemon=True)
+
+    def start(self):
+        save(self.run/'manual-terminal.json', dict(self.identity, run_id=self.run.name))
+        self.thread.start()
+
+    def set_deadline(self, deadline):
+        save(self.run/'manual-terminal.json', dict(self.identity, run_id=self.run.name,
+                                                  deadline_monotonic_ns=round(deadline*1e9)))
+
+    def check(self):
+        if self.error is not None:
+            raise RuntimeError('人工终端输入失败：' + self.error)
+
+    def close(self):
+        self.stopping.set()
+        self.thread.join(timeout=1)
+        if self.thread.is_alive():
+            raise RuntimeError('terminal relay did not stop')
+
+    def _say(self, text):
+        print(text, file=self.output, flush=True)
+
+    def _run(self):
+        try:
+            self._read()
+        except Exception as error:
+            self.error = repr(error)
+
+    def _read(self):
+        request_path = self.run/'manual-import-request.json'
+        while not request_path.exists():
+            if self.stopping.wait(.05):
+                return
+        request = load(request_path)
+        if (request.get('run_id') != self.run.name
+                or any(request.get('expected_'+k) != self.asset[k]
+                       for k in ('sha256', 'layers'))
+                or request.get('expected_asset') != self.asset['path']):
+            raise RuntimeError('manual request does not match this run/asset')
+        fd = self.stream.fileno()
+        require_terminal(self.stream)
+        # Reject input queued before the manual phase (including a stale READY).
+        termios.tcflush(fd, termios.TCIFLUSH)
+        self._say(prompt(self.asset['path']))
+        pending = bytearray()
+        overflow = False
+        while not self.stopping.is_set():
+            require_terminal(self.stream)
+            if not select.select([fd], [], [], .05)[0]:
+                continue
+            block = os.read(fd, 4096)
+            received_ns, wall_ns = time.monotonic_ns(), time.time_ns()
+            if not block:
+                self._answer(request, 'ABORT', received_ns, wall_ns, reason='terminal_eof')
+                return
+            for value in block:
+                if value != 10:
+                    if len(pending) < 128:
+                        pending.append(value)
+                    else:
+                        overflow = True
+                    continue
+                text = pending.decode('utf-8', errors='replace').rstrip('\r')
+                pending.clear()
+                if not overflow and text in ('READY 46', 'ABORT'):
+                    self._answer(request, text, received_ns, wall_ns)
+                    return
+                overflow = False
+                self._say('输入无效；仅接受 READY 46 或 ABORT。')
+
+    def _answer(self, request, text, stamp, wall, reason=None):
+        path = self.run/'manual-import-response.json'
+        if path.exists():
+            raise RuntimeError('manual response already exists')
+        save(path, dict(self.identity, run_id=self.run.name, request_id=request['request_id'],
+                        user_confirmation=text, monotonic_ns=stamp, wall_time_ns=wall, reason=reason))
+        self._say('已收到 READY 46，正在核验；尚未开始高压捕获。' if text == 'READY 46'
+                  else '已请求安全终止；等待原采集器完成清理。')
+
+
+def layer_verdict(snapshot, expected=46):
+    """Unavailable is distinct from a measured contradiction and from success."""
+    if snapshot.get('dialogs'):
+        raise ValueError('AT-SPI仍存在可见模态/文件对话框')
+    views = snapshot.get('layer_views', [])
+    counts = [view.get('row_count') for view in views]
+    if any(type(n) is int and n >= 0 and n != expected for n in counts):
+        raise ValueError('机器读取的图层数量不是46：' + repr(counts))
+    if snapshot.get('ok') is not True:
+        return None, 'MACHINE_LAYER_CHECK_UNAVAILABLE'
+    if len(counts) == 1 and type(counts[0]) is int and counts[0] == expected:
+        return counts[0], 'MACHINE_VERIFIED'
+    return None, 'MACHINE_LAYER_CHECK_UNAVAILABLE'
+
+
+def service_safety_request(run, config, previous):
+    """Acknowledge only after a fresh, fully guarded parent AND workload sample.
+
+    Called by the existing sampler, after enforce/OOM/PSI checks and CSV flush.
+    There is no input read or wait here, and at most one small acknowledgement.
+    """
+    run = Path(run)
+    request_path, reply = run/'manual-safety-request.json', run/'manual-safety.json'
+    if not request_path.exists() or reply.exists():
+        return
+    request = load(request_path)
+    if request.get('run_id') != run.name:
+        raise RuntimeError('manual safety request run mismatch')
+    stamps = {scope: previous.get(scope, {}).get('monotonic_ns', 0) for scope in ('parent', 'krita')}
+    if any(stamp < request['monotonic_ns'] for stamp in stamps.values()):
+        return
+    if shutil.disk_usage(run).free < config['safety']['min_disk_free_bytes']:
+        raise RuntimeError('disk free below original safety threshold')
+    save(reply, dict(run_id=run.name, request_id=request['request_id'],
+                     monotonic_ns=time.monotonic_ns(), wall_time_ns=time.time_ns(),
+                     safety_status='PASS', sample_monotonic_ns=stamps))
diff --git a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/pilot_assets.py b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/pilot_assets.py
index 5991021..e3c1d19 100644
--- a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/pilot_assets.py
+++ b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/pilot_assets.py
@@ -26,6 +26,8 @@ def script_contract(path=None,config=None):
         if 'tail_document' in automation:
             contract.update(tail_document=automation['tail_document'],
                             tail_charge_range_bytes=automation['tail_charge_range_bytes'])
+        if automation.get('manual_high_import') is True:
+            contract.update(manual_high_import=True,capture_origin='manual_document_ready')
         if 'pressure_profile' in automation:contract['pressure_profile']=automation['pressure_profile']
         return contract
     return dict(import_count=values['total_layers'],hold_duration_s=values['keep_duration_s'])
diff --git a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/validation.py b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/validation.py
index a07ddd4..95c5ab5 100644
--- a/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/validation.py
+++ b/前台操作/前台操作自动化脚本采集/oomlab_krita_collect/validation.py
@@ -42,6 +42,16 @@ def validate_run(run,verify_manifest=True):
             if m['config'].get('mode')!='pilot' or set(m['recipes'])!={'krita'} or m['interval_s']!=.05:errors.append('invalid PILOT boundary/config/interval')
             if m.get('assets_unchanged') is not True or load(run/'assets_manifest.json')!=load(run/'assets_manifest.after.json'):errors.append('PILOT asset integrity proof missing/changed')
             if load(run/'config.snapshot.json')!=m['config']:errors.append('config snapshot mismatch')
+            if m['config']['automation'].get('manual_high_import') is True:
+                info.update(document_verification='NOT_VERIFIED',machine_verification_status='NOT_VERIFIED')
+                manual_events=[json.loads(line) for line in (run/'krita/phase-events.jsonl').read_text().splitlines()]
+                try:
+                    info.update(verify_manual_evidence(run,m,manual_events,load(run/'assets_manifest.json')['script_contract']))
+                except (ValueError,RuntimeError,OSError,KeyError,TypeError) as error:
+                    failed=any(e.get('kind') in ('HIGH_DOCUMENT_READY','HIGH_DOCUMENT_READY_FAILED') for e in manual_events)
+                    status='FAILED' if failed else 'NOT_VERIFIED'
+                    info.update(document_verification=status,machine_verification_status=status)
+                    errors.append('manual import evidence: '+str(error))
         if run.resolve()!=run.absolute() or run.name!=m.get('run_id') or not re.fullmatch('[0-9a-f]{32}',run.name):raise ValueError('run identity/path mismatch')
         if m.get('error') or m.get('evidence_errors'):errors.append(str(m.get('error') or m.get('evidence_errors')))
         if not all(m.get(k) is True for k in ('cleanup_ok','cooldown_ok','operations_verified','journal_ok')):errors.append('incomplete operation/cleanup/cooldown/journal evidence')
@@ -125,7 +135,8 @@ def validate_run(run,verify_manifest=True):
                 verify_pilot_events(events_phase,contract)
                 if contract.get('completion_mode')=='timed_window':
                     info.update(completion_mode='timed_window',capture_window_complete=True,
-                                import_layers_verified=False,capture_origin=contract['capture_origin'])
+                                import_layers_verified=info.get('machine_verification_status')=='MACHINE_VERIFIED',
+                                capture_origin=contract['capture_origin'])
                 if 'pressure_profile' in contract:
                     shape=assess_pressure_profile(iter_samples(run),events_phase,contract,m['config']['safety']['max_sample_gap_s'])
                     info['pressure_profile']=shape
@@ -213,13 +224,139 @@ def verify_pilot_events(events,contract):
     if by['KRITA_EXIT'].get('returncode')!=0:raise ValueError('Krita did not exit normally')
␠
␠
+def verify_manual_events(events,contract):
+    names=['HIGH_DOCUMENT_MANUAL_IMPORT_START','HIGH_DOCUMENT_USER_READY',
+           'HIGH_DOCUMENT_MACHINE_VERIFY_START','HIGH_DOCUMENT_MACHINE_VERIFY','HIGH_DOCUMENT_READY']
+    records=[e for e in events if e.get('kind') in names+['HIGH_DOCUMENT_READY_FAILED']]
+    if [e['kind'] for e in records]!=names:
+        raise ValueError('manual confirmation missing/failed/duplicate/out of order')
+    first,user,begin,end,ready=records;asset=contract['prepared_document']
+    if not re.fullmatch('[0-9a-f]{32}',first.get('run_id','')):
+        raise ValueError('manual run identity missing')
+    for event in records:
+        if (event.get('run_id')!=first['run_id'] or event.get('request_id')!=first.get('request_id')
+                or not re.fullmatch('[0-9a-f]{32}',first.get('request_id','')) or event.get('expected_asset')!=asset['path']
+                or event.get('expected_sha256')!=asset['sha256'] or event.get('expected_layers')!=46
+                or event.get('process_identity_status')!='VERIFIED'
+                or type(event.get('krita_pid')) is not int or event['krita_pid']!=first['krita_pid']
+                or not event.get('window_id') or type(event.get('wall_time_ns')) is not int
+                or event['wall_time_ns']<=0 or type(event.get('monotonic_ns')) is not int
+                or event['monotonic_ns']<=0):
+            raise ValueError('manual asset/process/event evidence mismatch')
+    if any(b['monotonic_ns']<a['monotonic_ns'] for a,b in zip(records,records[1:])):
+        raise ValueError('manual clock order invalid')
+    wait=(user['monotonic_ns']-first['monotonic_ns'])/1e9
+    for event in records[1:]:
+        if (event.get('user_confirmation')!='READY 46'
+                or event.get('user_ready_monotonic_ns')!=user['monotonic_ns']
+                or event.get('user_ready_wall_time_ns')!=user['wall_time_ns']
+                or type(event.get('manual_wait_duration_s')) not in (int,float)
+                or not math.isfinite(event['manual_wait_duration_s'])
+                or abs(event['manual_wait_duration_s']-wait)>1e-9):
+            raise ValueError('missing real READY receipt timestamp/confirmation')
+    for event in (end,ready):
+        if (event.get('verification_started_monotonic_ns')!=begin['monotonic_ns']
+                or event.get('verification_started_wall_time_ns')!=begin['wall_time_ns']
+                or event.get('safety_status')!='PASS'
+                or not isinstance(event.get('actual_window_title'),str)
+                or type(event.get('title_matches_expected')) is not bool):
+            raise ValueError('manual machine verification times/evidence missing')
+        status=event.get('machine_verification_status');count=event.get('machine_layer_count')
+        if (status=='MACHINE_VERIFIED' and (type(count) is not int or count!=46)
+                or status=='MACHINE_LAYER_CHECK_UNAVAILABLE' and count is not None
+                or status not in ('MACHINE_VERIFIED','MACHINE_LAYER_CHECK_UNAVAILABLE')):
+            raise ValueError('manual machine layer outcome invalid')
+        level='MACHINE_VERIFIED' if status=='MACHINE_VERIFIED' and event['title_matches_expected'] else 'USER_CONFIRMED'
+        if event.get('document_verification')!=level:
+            raise ValueError('user confirmation cannot be labelled as independent machine verification')
+    if (ready.get('verification_finished_monotonic_ns')!=end['monotonic_ns']
+            or ready.get('verification_finished_wall_time_ns')!=end['wall_time_ns']):
+        raise ValueError('manual verification end timestamp missing')
+    return dict(document_verification=ready['document_verification'],
+                machine_verification_status=ready['machine_verification_status'],
+                machine_layer_count=ready['machine_layer_count'],
+                user_ready_monotonic_ns=user['monotonic_ns'],
+                verification_started_monotonic_ns=begin['monotonic_ns'],
+                verification_finished_monotonic_ns=end['monotonic_ns'],
+                high_document_ready_monotonic_ns=ready['monotonic_ns'])
+
+
+def verify_manual_evidence(run,metadata,events,contract):
+    """New-mode evidence checks ADD to the existing validator and shape bounds."""
+    from .manual_import import layer_verdict
+    result=verify_manual_events(events,contract);run=Path(run)
+    by={e.get('kind'):e for e in events};ready=by['HIGH_DOCUMENT_READY'];user=by['HIGH_DOCUMENT_USER_READY']
+    if ready['run_id']!=metadata['run_id'] or by['KRITA_PROCESS']['pid']!=ready['krita_pid']:
+        raise ValueError('manual event run/PID mismatch')
+    terminal=load(run/'manual-terminal.json');request=load(run/'manual-import-request.json')
+    response=load(run/'manual-import-response.json');proof=load(run/'krita/high-document-manual-evidence.json')
+    if (terminal.get('run_id')!=run.name or terminal.get('stdin_isatty') is not True
+            or terminal.get('foreground_checked') is not True
+            or not terminal.get('tty') or not terminal.get('reader_pid')
+            or ready['monotonic_ns']>=terminal.get('deadline_monotonic_ns',0)):
+        raise ValueError('real foreground TTY/deadline proof missing')
+    for record in (request,response,proof):
+        if record.get('run_id')!=run.name or record.get('request_id')!=ready['request_id']:
+            raise ValueError('manual file run/request mismatch')
+    if (request.get('monotonic_ns')!=by['HIGH_DOCUMENT_MANUAL_IMPORT_START']['monotonic_ns']
+            or response.get('monotonic_ns')!=user['monotonic_ns']
+            or response.get('wall_time_ns')!=user['wall_time_ns']
+            or response.get('user_confirmation')!='READY 46'
+            or response.get('reader_pid')!=terminal['reader_pid'] or response.get('tty')!=terminal['tty']):
+        raise ValueError('manual input receipt proof mismatch')
+    expected=load(run/'krita/krita-process.json')
+    for key in ('process_identity_before','process_identity_after'):
+        if any(proof.get(key,{}).get(k)!=expected[k] for k in ('pid','ppid','starttime','exe','cgroup')):
+            raise ValueError('manual full process identity proof mismatch')
+    if not proof.get('wmctrl_stdout') or not proof.get('active_window') or not proof.get('active_window_xprop'):
+        raise ValueError('manual raw window diagnostics missing')
+    normal=[]
+    for window in proof.get('windows',[]):
+        raw=window.get('xprop','');geometry=window.get('xwininfo','')
+        if window.get('pid')!=expected['pid'] or not re.search(r'_NET_WM_PID\(CARDINAL\)\s*=\s*'+str(expected['pid'])+r'\b',raw):
+            raise ValueError('manual window ownership proof mismatch')
+        if not re.search(r'WM_CLASS\(STRING\)[^\n]*"krita"',raw,re.I):raise ValueError('manual WM_CLASS mismatch')
+        if 'IsViewable' not in geometry:continue
+        if '_NET_WM_WINDOW_TYPE_DIALOG' in raw or '_NET_WM_STATE_MODAL' in raw:raise ValueError('manual dialog remains')
+        if '_NET_WM_WINDOW_TYPE_NORMAL' in raw:normal.append(window)
+    if (len(normal)!=1 or normal[0]['id']!=ready['window_id'] or normal[0]['title']!=ready['actual_window_title']
+            or normal[0]['width']<900 or normal[0]['height']<600):
+        raise ValueError('manual unique visible normal window proof missing')
+    stem=Path(contract['prepared_document']['path']).stem
+    matched=bool(re.search(r'(?<![\w.])'+re.escape(stem)+r'(?:\.ora)?(?![\w.])',normal[0]['title'],re.I))
+    if matched!=ready['title_matches_expected']:raise ValueError('manual title mismatch was hidden')
+    accessible=proof.get('accessibility',{})
+    if accessible.get('ok') is True and (accessible.get('pid')!=expected['pid']
+            or (accessible.get('selected_application') or {}).get('pid')!=expected['pid']):
+        raise ValueError('manual accessibility PID mismatch')
+    count,status=layer_verdict(accessible)
+    if count!=ready['machine_layer_count'] or status!=ready['machine_verification_status']:
+        raise ValueError('manual layer result contradicts raw snapshot')
+    safety=load(run/'manual-safety.json');safety_request=load(run/'manual-safety-request.json')
+    if (proof.get('safety')!=safety or safety.get('run_id')!=run.name
+            or safety.get('request_id')!=ready['request_id'] or safety.get('safety_status')!='PASS'
+            or safety_request.get('run_id')!=run.name or safety_request.get('request_id')!=ready['request_id']):
+        raise ValueError('manual safety acknowledgement missing')
+    stamps=safety.get('sample_monotonic_ns',{})
+    if (set(stamps)!={'parent','krita'} or any(v<safety_request['monotonic_ns'] for v in stamps.values())
+            or safety['monotonic_ns']<max(stamps.values()) or safety['monotonic_ns']>ready['monotonic_ns']
+            or ready['monotonic_ns']-min(stamps.values())>metadata['config']['safety']['max_sample_gap_s']*1e9):
+        raise ValueError('manual safety sample is stale or from before verification')
+    found={row['scope'] for row in iter_samples(run) if row['scope'] in stamps and row['monotonic_ns']==stamps[row['scope']]}
+    if found!={'parent','krita'}:raise ValueError('manual safety evidence absent from raw sample stream')
+    return result
+
+
 def verify_timed_events(events,contract):
     prepared=contract.get('prepared_document')
     tail=contract.get('tail_document')
     high_events=['HIGH_DOCUMENT_OPEN_START','HIGH_DOCUMENT_SUBMITTED','HIGH_DOCUMENT_OPEN_DONE']
+    manual=contract.get('manual_high_import') is True
+    manual_events=['HIGH_DOCUMENT_MANUAL_IMPORT_START','HIGH_DOCUMENT_USER_READY',
+                   'HIGH_DOCUMENT_MACHINE_VERIFY_START','HIGH_DOCUMENT_MACHINE_VERIFY','HIGH_DOCUMENT_READY']
     import_events=['LAYER_IMPORT_START','LAYER_IMPORT_SUBMITTED']
     restart_events=['HIGH_INSTANCE_EXIT','KRITA_POST_PROCESS']
-    load_events=high_events if prepared else import_events
+    load_events=manual_events if manual else high_events if prepared else import_events
     names=['DOCUMENT_OPEN_START','DOCUMENT_OPEN_DONE','CANVAS_ZOOM_START','CANVAS_ZOOM_DONE',*load_events,
            'CAPTURE_WINDOW_START','CAPTURE_WINDOW_DONE','DOCUMENT_CLOSE_START','DOCUMENT_CLOSE_DONE','KRITA_EXIT']
     stages=[('PRE_IMPORT_REVIEW',load_events[0],'pre_import_review_s'),
@@ -233,15 +370,18 @@ def verify_timed_events(events,contract):
     if prepared:
         index=names.index('POST_CLOSE_REVIEW_START')
         names[index:index]=restart_events+(['TAIL_DOCUMENT_OPEN_DONE'] if tail else [])
-    selected=set(names+high_events+import_events+restart_events)|review_events|{
+    selected=set(names+high_events+manual_events+import_events+restart_events)|review_events|{
+        'HIGH_DOCUMENT_READY_FAILED',
         'LAYER_IMPORT_DONE','HOLD_START','HOLD_DONE','TAIL_DOCUMENT_OPEN_DONE'}
     records=[e for e in events if e.get('kind') in selected]
     if [e['kind'] for e in records]!=names:raise ValueError('missing/duplicate/out-of-order timed capture events')
     if any(b['monotonic_ns']<a['monotonic_ns'] for a,b in zip(records,records[1:])):raise ValueError('timed capture event time reversed')
     by={e['kind']:e for e in records}
-    origin=by['HIGH_DOCUMENT_OPEN_DONE' if prepared else 'LAYER_IMPORT_SUBMITTED']['monotonic_ns']
+    origin=by['HIGH_DOCUMENT_READY' if manual else 'HIGH_DOCUMENT_OPEN_DONE' if prepared else 'LAYER_IMPORT_SUBMITTED']['monotonic_ns']
     duration=contract['capture_window_s']
-    if prepared:
+    if manual:
+        verify_manual_events(events,contract)
+    elif prepared:
         if any(by[kind].get('asset')!=prepared['path'] for kind in high_events):
             raise ValueError('prepared document path mismatch')
         if by['HIGH_DOCUMENT_OPEN_DONE'].get('verification')!='owned_document_title':
@@ -295,7 +435,8 @@ def assess_pressure_profile(samples,events,contract,max_gap_s):
         post_start=max(post_start,stamp(release)+round(profile['post_close_settle_s']*1e9))
     windows={
         'pre_import':(stamp('PRE_IMPORT_REVIEW_START'),stamp('PRE_IMPORT_REVIEW_DONE')),
-        'high':(stamp('HIGH_DOCUMENT_SUBMITTED' if 'prepared_document' in contract else 'LAYER_IMPORT_SUBMITTED'),
+        'high':(stamp('HIGH_DOCUMENT_READY' if contract.get('manual_high_import') else
+                      'HIGH_DOCUMENT_SUBMITTED' if 'prepared_document' in contract else 'LAYER_IMPORT_SUBMITTED'),
                 stamp('CAPTURE_WINDOW_DONE')),
         'post_close':(post_start,stamp('POST_CLOSE_REVIEW_DONE')),
     }
diff --git a/前台操作/前台操作自动化脚本采集/scripts/krita_auto.py b/前台操作/前台操作自动化脚本采集/scripts/krita_auto.py
index 70fa778..5a04c73 100644
--- a/前台操作/前台操作自动化脚本采集/scripts/krita_auto.py
+++ b/前台操作/前台操作自动化脚本采集/scripts/krita_auto.py
@@ -12,6 +12,7 @@ import sys
 import tempfile
 import time
 import traceback
+import uuid
␠
␠
 class GuiPending(RuntimeError):pass
@@ -33,7 +34,7 @@ def check_stop():
         value=json.loads(Path(CTX['control']).read_text());raise StopRequested(value.get('reason','采集器请求安全停止'))
␠
␠
-def run(cmd,timeout=10,allow_stop=True):
+def run(cmd,timeout=10,allow_stop=True,strip=True):
     if allow_stop:check_stop()
     if CTX.get('shutdown_deadline'):
         remaining=CTX['shutdown_deadline']-time.monotonic()
@@ -46,7 +47,7 @@ def run(cmd,timeout=10,allow_stop=True):
     print('  [cmd] '+shlex.join(args),flush=True)
     p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
     if p.returncode:raise RuntimeError(f'{args[0]} exit={p.returncode}: {p.stderr.strip()}')
-    return p.stdout.strip()
+    return p.stdout.strip() if strip else p.stdout
␠
␠
 def identity(pid):
@@ -63,8 +64,12 @@ def owned():
␠
␠
 def windows():
+    return parse_windows(run(['wmctrl','-lpG']))
+
+
+def parse_windows(raw):
     result=[]
-    for line in run(['wmctrl','-lpG']).splitlines():
+    for line in raw.splitlines():
         parts=line.split(None,8)
         if len(parts)==9:result.append(dict(id=parts[0],pid=int(parts[2]),x=int(parts[3]),y=int(parts[4]),width=int(parts[5]),height=int(parts[6]),title=parts[8]))
     return result
@@ -269,6 +274,150 @@ def open_document(asset=None,submitted_kind=None):
     CTX['document_open']=True
␠
␠
+def manual_owned():
+    """Keep every original guard, and bind full exe/cgroup to startup too."""
+    actual=owned();expected=CTX.get('owner_identity')
+    if not expected or any(actual.get(k)!=expected.get(k) for k in ('pid','ppid','starttime','exe','cgroup')):
+        raise RuntimeError('人工确认进程身份不符（PID/PPID/starttime/executable/cgroup）')
+    return actual
+
+
+def manual_checkpoint(terminal):
+    check_stop();manual_owned()
+    if time.monotonic_ns()>=terminal['deadline_monotonic_ns']:
+        raise TimeoutError('原整体运行时间上限已到；人工等待停止')
+
+
+def manual_window_snapshot(proof):
+    """Read-only queries; terminal focus itself is expected after READY."""
+    proof['wmctrl_stdout']=run(['wmctrl','-lpG'],strip=False)
+    proof['active_window']=run(['xdotool','getactivewindow'],strip=False)
+    proof['active_window_xprop']=run(['xprop','-id',proof['active_window'].strip()],strip=False)
+    proof['windows']=[];main=[]
+    for window in parse_windows(proof['wmctrl_stdout']):
+        if window['pid']!=CTX['pid']:continue
+        raw=run(['xprop','-id',window['id'],'_NET_WM_PID','WM_CLASS',
+                 '_NET_WM_WINDOW_TYPE','WM_TRANSIENT_FOR','_NET_WM_STATE'],strip=False)
+        geometry=run(['xwininfo','-id',window['id']],strip=False)
+        proof['windows'].append(dict(window,xprop=raw,xwininfo=geometry))
+        if not re.search(r'_NET_WM_PID\(CARDINAL\)\s*=\s*'+str(CTX['pid'])+r'\b',raw):
+            raise RuntimeError('人工确认窗口PID属性不匹配')
+        if not re.search(r'WM_CLASS\(STRING\)[^\n]*"krita"',raw,re.I):
+            raise RuntimeError('人工确认窗口WM_CLASS不匹配')
+        if 'IsViewable' not in geometry:continue
+        if '_NET_WM_WINDOW_TYPE_DIALOG' in raw or '_NET_WM_STATE_MODAL' in raw:
+            raise RuntimeError('人工确认时仍有文件选择框或模态对话框')
+        if '_NET_WM_WINDOW_TYPE_NORMAL' in raw:main.append(window)
+    if len(main)!=1 or main[0]['width']<900 or main[0]['height']<600:
+        raise RuntimeError('人工确认需要唯一、可见、正常且尺寸符合要求的Krita主窗口')
+    return main[0]
+
+
+def manual_accessibility_snapshot(proof):
+    command=[CTX['settings']['accessibility_python'],str(Path(__file__).with_name('krita_accessibility.py')),
+             '--pid',str(CTX['pid'])]
+    try:
+        p=subprocess.run(command,capture_output=True,text=True,timeout=5)
+        proof['accessibility_raw']=dict(stdout=p.stdout,stderr=p.stderr,returncode=p.returncode)
+        try:data=json.loads(p.stdout.splitlines()[-1])
+        except (ValueError,IndexError):data=dict(ok=False,error='AT-SPI没有有效JSON')
+    except subprocess.TimeoutExpired as error:
+        data=dict(ok=False,error='AT-SPI查询超时')
+        proof['accessibility_raw']=dict(error=repr(error))
+    proof['accessibility']=data
+    if data.get('pid') is not None and data['pid']!=CTX['pid']:
+        raise RuntimeError('人工确认AT-SPI PID不匹配')
+    selected=data.get('selected_application') or {}
+    if data.get('ok') is True and selected.get('pid')!=CTX['pid']:
+        raise RuntimeError('人工确认AT-SPI Application归属不匹配')
+    return data
+
+
+def manual_high_document(prepared):
+    """No key/type/click/open action: the user alone imports the high ORA."""
+    from oomlab_krita_collect.common import load,save
+    from oomlab_krita_collect.manual_import import layer_verdict
+    root=Path(CTX['control']).parent
+    if Path(CTX['record']).parent.parent!=root:raise RuntimeError('人工导入run边界不一致')
+    terminal=load(root/'manual-terminal.json')
+    if terminal.get('run_id')!=root.name or not terminal.get('deadline_monotonic_ns'):
+        raise RuntimeError('缺少真实前台终端及原整体截止时间；请从VM终端前台启动采集器')
+    CTX['asset']=prepared['path']
+    fields=dict(run_id=root.name,request_id=uuid.uuid4().hex,expected_asset=prepared['path'],
+                expected_sha256=prepared['sha256'],expected_layers=prepared['layers'],
+                user_confirmation=None,manual_wait_duration_s=0,krita_pid=CTX['pid'],
+                window_id=CTX['wid'],actual_window_title=None,machine_layer_count=None,
+                machine_verification_status='NOT_VERIFIED',process_identity_status='NOT_VERIFIED',
+                document_verification='NOT_VERIFIED')
+    proof=dict(run_id=root.name);proof_path=root/'krita/high-document-manual-evidence.json'
+    try:
+        manual_checkpoint(terminal);fields['process_identity_status']='VERIFIED'
+        started=emit('HIGH_DOCUMENT_MANUAL_IMPORT_START',**fields)
+        save(root/'manual-import-request.json',dict(fields,monotonic_ns=started['monotonic_ns']))
+        while not (root/'manual-import-response.json').exists():
+            manual_checkpoint(terminal);time.sleep(min(.1,CTX['settings']['poll_s']))
+        manual_checkpoint(terminal)
+        response=load(root/'manual-import-response.json');stamp=response.get('monotonic_ns')
+        if (response.get('run_id')!=root.name or response.get('request_id')!=fields['request_id']
+                or response.get('reader_pid')!=terminal['reader_pid'] or response.get('tty')!=terminal['tty']
+                or type(stamp) is not int or not started['monotonic_ns']<=stamp<=time.monotonic_ns()):
+            raise RuntimeError('人工输入记录不属于本轮或输入时钟无效')
+        fields.update(user_confirmation=response.get('user_confirmation'),
+                      manual_wait_duration_s=(stamp-started['monotonic_ns'])/1e9,
+                      user_ready_monotonic_ns=stamp,user_ready_wall_time_ns=response['wall_time_ns'])
+        if response.get('user_confirmation')=='ABORT':raise StopRequested('用户ABORT/终端EOF，安全停止')
+        if response.get('user_confirmation')!='READY 46':raise RuntimeError('无效人工确认')
+        emit('HIGH_DOCUMENT_USER_READY',monotonic_ns=stamp,wall_time_ns=response['wall_time_ns'],**fields)
+        begin=emit('HIGH_DOCUMENT_MACHINE_VERIFY_START',**fields)
+        fields['verification_started_monotonic_ns']=begin['monotonic_ns']
+        fields['verification_started_wall_time_ns']=begin['wall_time_ns']
+        proof['process_identity_before']=manual_owned()
+        window=manual_window_snapshot(proof)
+        fields.update(window_id=window['id'],actual_window_title=window['title'],
+                      title_matches_expected=document_named(window))
+        manual_checkpoint(terminal)
+        data=manual_accessibility_snapshot(proof)
+        # Retain explicit wrong counts even when verification must fail.
+        fields['observed_layer_counts']=[v.get('row_count') for v in data.get('layer_views',[])]
+        if len(fields['observed_layer_counts'])==1:
+            fields['machine_layer_count']=fields['observed_layer_counts'][0]
+        count,status=layer_verdict(data,prepared['layers'])
+        fields.update(machine_layer_count=count,machine_verification_status=status,
+                      document_verification='MACHINE_VERIFIED' if count==46 and fields['title_matches_expected']
+                      else 'USER_CONFIRMED')
+        manual_checkpoint(terminal)
+        request=dict(run_id=root.name,request_id=fields['request_id'],monotonic_ns=time.monotonic_ns())
+        save(root/'manual-safety-request.json',request)
+        while not (root/'manual-safety.json').exists():
+            manual_checkpoint(terminal);time.sleep(.05)
+        safety=load(root/'manual-safety.json');proof['safety']=safety
+        if (safety.get('run_id')!=root.name or safety.get('request_id')!=fields['request_id']
+                or safety.get('safety_status')!='PASS'
+                or set(safety.get('sample_monotonic_ns',{}))!={'parent','krita'}
+                or any(v<request['monotonic_ns'] for v in safety['sample_monotonic_ns'].values())
+                or time.monotonic_ns()-min(safety['sample_monotonic_ns'].values())>500_000_000):
+            raise RuntimeError('缺少本轮新的完整安全采样确认')
+        manual_checkpoint(terminal);proof['process_identity_after']=manual_owned()
+        end=emit('HIGH_DOCUMENT_MACHINE_VERIFY',safety_status='PASS',**fields)
+        fields.update(verification_finished_monotonic_ns=end['monotonic_ns'],
+                      verification_finished_wall_time_ns=end['wall_time_ns'])
+        proof.update(fields)
+        save(proof_path,proof)
+        manual_checkpoint(terminal)
+        if time.monotonic_ns()-min(safety['sample_monotonic_ns'].values())>500_000_000:
+            raise RuntimeError('核验证据写入后安全采样已过期')
+        CTX.update(wid=window['id'],document_open=True)
+        # Input receipt is preserved above. The FULL 12s starts only now.
+        return emit('HIGH_DOCUMENT_READY',safety_status='PASS',**fields)
+    except (Exception,KeyboardInterrupt) as error:
+        fields.update(document_verification='FAILED',machine_verification_status='FAILED',error_message=repr(error))
+        try:manual_owned()
+        except Exception:fields['process_identity_status']='FAILED'
+        proof.update(fields);save(proof_path,proof)
+        emit('HIGH_DOCUMENT_READY_FAILED',status='FAILED',**fields)
+        raise
+
+
 def review_canvas(label,duration_s,interval_s):
     """Bounded zoom in/out cycles on the owned blank document."""
     start=emit(label+'_START',duration_s=duration_s,pid=CTX['pid'])['monotonic_ns']
@@ -370,6 +519,7 @@ def start_krita(env,timed,settings,event,record):
         plugins=sorted({line.split()[-1] for line in maps.splitlines() if 'libqxcb.so' in line or 'libqwayland' in line})
         if any('libqwayland' in p for p in plugins):raise RuntimeError('实际平台插件含Wayland')
         info.update(schema_version=1,qt_platform='xcb',libqxcb_verified=True,qt_plugins=plugins,window_id=CTX['wid'],window=current,focus_verified=True)
+        CTX['owner_identity']={k:info[k] for k in ('pid','ppid','starttime','exe','cgroup')}
         if prepared:
             info.update(krita_config_home=env['XDG_CONFIG_HOME'],
                         tile_memory_percent=settings['tile_memory_percent'])
@@ -400,13 +550,16 @@ def main(argv=None):
     profile=settings.get('pressure_profile')
     prepared=settings.get('prepared_document')
     tail=settings.get('tail_document')
+    manual=settings.get('manual_high_import') is True
+    if manual and (not prepared or prepared.get('layers')!=46 or not args.control_file or not args.process_record):
+        raise ValueError('人工46层导入必须由真实前台终端的采集器启动')
     if profile is not None and not timed:raise ValueError('pressure profile requires timed capture')
     if prepared and (not profile or type(settings.get('tile_memory_percent')) is not int
                      or not 1<=settings['tile_memory_percent']<=100):
         raise ValueError('prepared ORA needs a pressure profile and an explicit Krita tile budget')
     if tail and not prepared:raise ValueError('tail ORA requires a separate post-peak Krita instance')
     if timed and (type(settings.get('capture_window_s')) not in (int,float) or not 0<settings['capture_window_s']<86400):raise ValueError('invalid capture window')
-    CTX.update(process=None,pid=None,wid=None,birth=None,document_open=False)
+    CTX.update(process=None,pid=None,wid=None,birth=None,document_open=False,owner_identity=None)
     CTX.update(settings=settings,control=args.control_file,record=args.process_record,asset=args.asset)
     # The manifest, not an invented count, selects the complete existing PNG set.
     if args.assets_manifest:
@@ -418,6 +571,7 @@ def main(argv=None):
             if contract.get('tail_document')!=tail:raise RuntimeError('尾段文档与素材契约不一致')
             if contract.get('tile_memory_percent')!=settings['tile_memory_percent']:
                 raise RuntimeError('Krita 瓦片预算与素材契约不一致')
+            if bool(contract.get('manual_high_import'))!=manual:raise RuntimeError('人工导入与素材契约不一致')
         elif contract['import_count']!=total_layers:raise RuntimeError('素材清单与脚本设计不一致')
         if timed:
             if contract.get('completion_mode')!='timed_window' or contract.get('capture_window_s')!=settings['capture_window_s']:raise RuntimeError('采集窗口与素材契约不一致')
@@ -463,9 +617,12 @@ def main(argv=None):
         if prepared:
             with phase(5,'打开预组装多图层文档'):
                 close_document()
-                emit('HIGH_DOCUMENT_OPEN_START',asset=prepared['path'])
-                open_document(prepared['path'],'HIGH_DOCUMENT_SUBMITTED')
-                opened=emit('HIGH_DOCUMENT_OPEN_DONE',asset=prepared['path'],verification='owned_document_title')
+                if manual:
+                    opened=manual_high_document(prepared)
+                else:
+                    emit('HIGH_DOCUMENT_OPEN_START',asset=prepared['path'])
+                    open_document(prepared['path'],'HIGH_DOCUMENT_SUBMITTED')
+                    opened=emit('HIGH_DOCUMENT_OPEN_DONE',asset=prepared['path'],verification='owned_document_title')
                 capture_window(opened['monotonic_ns'],settings['capture_window_s'])
         else:
             capture_import(paths,total_layers,timed,keep_duration_s,settings)
diff --git a/前台操作/前台操作自动化脚本采集/tests/test_manual_import.py b/前台操作/前台操作自动化脚本采集/tests/test_manual_import.py
new file mode 100644
index 0000000..9b127a1
--- /dev/null
+++ b/前台操作/前台操作自动化脚本采集/tests/test_manual_import.py
@@ -0,0 +1,312 @@
+"""Offline PTY and fake GUI/kernel tests; never start Krita."""
+import argparse,contextlib,copy,fcntl,importlib.util,io,json,os,pty,select,subprocess,sys,tempfile,termios,time,unittest
+from pathlib import Path
+from unittest.mock import patch
+from oomlab_krita_collect import cli
+from oomlab_krita_collect.common import GUI,save,load
+from oomlab_krita_collect.config import read
+from oomlab_krita_collect.manual_import import TerminalRelay,require_terminal,layer_verdict,service_safety_request
+from oomlab_krita_collect.pilot_assets import script_contract
+from oomlab_krita_collect.validation import verify_manual_events,verify_manual_evidence,verify_pilot_events,assess_pressure_profile
+from oomlab_krita_collect.metrics import snapshot
+from test_collect import kernel
+spec=importlib.util.spec_from_file_location('manual_auto',GUI/'scripts/krita_auto.py');auto=importlib.util.module_from_spec(spec);spec.loader.exec_module(auto)
+CONFIG=GUI/'configs/collection.rapid-9000-manual-high-import.json'
+
+class Clock:
+    def __init__(self):self.ns=100_000_000_000
+    def advance(self,s):self.ns+=round(s*1e9)
+    def mono(self):return self.ns/1e9
+    def wall(self):return 1_700_000_000_000_000_000+self.ns
+
+class AutomationTests(unittest.TestCase):
+    @contextlib.contextmanager
+    def case(self,count=46,available=True,title='layered_9000_46.ora — Krita',text='READY 46',delay=0,changed=None,modal=False,duplicate=False,safety_fail=False,wrong_window_pid=False,wrong_accessible_pid=False):
+        with tempfile.TemporaryDirectory() as tmp:
+            root=Path(tmp)/('a'*32);(root/'krita').mkdir(parents=True);c=read(CONFIG);asset=c['automation']['prepared_document'];clock=Clock();old=auto.CTX.copy()
+            identity=dict(pid=42,ppid=os.getpid(),starttime=123,exe='/usr/bin/krita',cgroup='0::/owned/krita.service');record=root/'krita/krita-process.json';save(record,identity)
+            terminal=dict(run_id=root.name,reader_pid=99,tty='/dev/pts/TEST_ONLY',stdin_isatty=True,foreground_checked=True,deadline_monotonic_ns=clock.ns+1800_000_000_000);save(root/'manual-terminal.json',terminal)
+            auto.CTX.update(pid=42,wid='0x10',record=str(record),control=str(root/'stop-request.json'),owner_identity=identity.copy(),settings=c['automation'],birth=123,document_open=False)
+            events=[];commands=[]
+            access=dict(ok=True,pid=42,selected_application=dict(pid=42),dialogs=[],layer_views=[dict(row_count=count)]) if available else dict(ok=False,pid=42,error='TEST_ONLY unavailable')
+            if wrong_accessible_pid:access['pid']=43
+            raw='0x10 0 42 0 0 1200 800 TEST_HOST '+title+'\n'
+            if modal or duplicate:raw+='0x11 0 42 0 0 1100 700 TEST_HOST '+title+'\n'
+            def command(args,**kwargs):
+                commands.append(args)
+                if args==['wmctrl','-lpG']:return raw
+                if args==['xdotool','getactivewindow']:return '0x99\n'
+                if args[0]=='xwininfo':return 'Map State: IsViewable\n'
+                if args[:3]==['xprop','-id','0x99']:return '_NET_WM_PID(CARDINAL) = 99\n'
+                kind='DIALOG' if modal and args[2]=='0x11' else 'NORMAL'
+                return '_NET_WM_PID(CARDINAL) = '+('43' if wrong_window_pid else '42')+'\nWM_CLASS(STRING) = "krita", "krita"\n_NET_WM_WINDOW_TYPE(ATOM) = _NET_WM_WINDOW_TYPE_'+kind+'\n'
+            def emit(kind,**fields):
+                e=dict(schema_version=1,kind=kind,monotonic_ns=clock.ns,wall_time_ns=clock.wall());e.update(fields);events.append(e);return e
+            def sleep(seconds):
+                if (root/'manual-import-request.json').exists() and not (root/'manual-import-response.json').exists():
+                    clock.advance(delay or seconds);request=load(root/'manual-import-request.json')
+                    save(root/'manual-import-response.json',dict(terminal,request_id=request['request_id'],user_confirmation=text,monotonic_ns=clock.ns,wall_time_ns=clock.wall()))
+                    if changed:
+                        altered=identity.copy();altered[changed]='changed' if changed in ('exe','cgroup') else 999;owner.return_value=altered
+                    return
+                clock.advance(seconds)
+                if (root/'manual-safety-request.json').exists() and not (root/'manual-safety.json').exists():
+                    if safety_fail:save(root/'stop-request.json',dict(reason='TEST_ONLY safety threshold'));return
+                    request=load(root/'manual-safety-request.json');save(root/'manual-safety.json',dict(run_id=root.name,request_id=request['request_id'],monotonic_ns=clock.ns,wall_time_ns=clock.wall(),safety_status='PASS',sample_monotonic_ns=dict(parent=clock.ns,krita=clock.ns)))
+            with contextlib.ExitStack() as stack:
+                owner=stack.enter_context(patch.object(auto,'owned',return_value=identity.copy()))
+                stack.enter_context(patch.object(auto,'run',side_effect=command));stack.enter_context(patch.object(auto,'emit',side_effect=emit))
+                stack.enter_context(patch.object(auto.time,'monotonic_ns',side_effect=lambda:clock.ns));stack.enter_context(patch.object(auto.time,'monotonic',side_effect=clock.mono));stack.enter_context(patch.object(auto.time,'time_ns',side_effect=clock.wall));stack.enter_context(patch.object(auto.time,'sleep',side_effect=sleep))
+                stack.enter_context(patch.object(auto.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(access),'')))
+                try:yield root,c,asset,events,commands,clock,identity
+                finally:auto.CTX.clear();auto.CTX.update(old)
+
+    def test_ready_machine_proof_and_no_automatic_input(self):
+        with self.case() as (root,c,asset,events,commands,*_):
+            ready=auto.manual_high_document(asset);self.assertEqual(ready['machine_layer_count'],46);self.assertEqual(ready['document_verification'],'MACHINE_VERIFIED');self.assertTrue(auto.CTX['document_open'])
+            self.assertEqual([e['kind'] for e in events],['HIGH_DOCUMENT_MANUAL_IMPORT_START','HIGH_DOCUMENT_USER_READY','HIGH_DOCUMENT_MACHINE_VERIFY_START','HIGH_DOCUMENT_MACHINE_VERIFY','HIGH_DOCUMENT_READY'])
+            proof=load(root/'krita/high-document-manual-evidence.json');self.assertTrue(proof['wmctrl_stdout'].endswith('\n'));self.assertTrue(proof['active_window_xprop']);self.assertEqual(proof['accessibility']['pid'],42)
+            self.assertFalse(any(a[0]=='xdotool' and a[1] in ('key','type','click') for a in commands));self.assertGreater(ready['monotonic_ns'],events[1]['monotonic_ns']);verify_manual_events(events,script_contract(config=c))
+
+    def test_unavailable_is_user_confirmed_not_machine(self):
+        with self.case(available=False) as (root,c,asset,events,*_):
+            ready=auto.manual_high_document(asset);self.assertEqual(ready['document_verification'],'USER_CONFIRMED');self.assertEqual(ready['machine_verification_status'],'MACHINE_LAYER_CHECK_UNAVAILABLE');self.assertIsNone(ready['machine_layer_count']);verify_manual_events(events,script_contract(config=c))
+            events[-1]['document_verification']='MACHINE_VERIFIED'
+            with self.assertRaises(ValueError):verify_manual_events(events,script_contract(config=c))
+
+    def test_title_mismatch_keeps_actual_title_and_user_confirmation(self):
+        with self.case(title='Krita') as (root,c,asset,events,*_):
+            ready=auto.manual_high_document(asset);self.assertFalse(ready['title_matches_expected']);self.assertEqual(ready['actual_window_title'],'Krita');self.assertEqual(ready['document_verification'],'USER_CONFIRMED');self.assertEqual(ready['machine_layer_count'],46)
+
+    def test_wrong_layer_counts_stop_without_ready(self):
+        for count in (0,7,45,47):
+            with self.subTest(count=count),self.case(count=count) as (root,c,asset,events,*_):
+                with self.assertRaisesRegex(ValueError,'图层数量'):auto.manual_high_document(asset)
+                self.assertEqual(events[-1]['kind'],'HIGH_DOCUMENT_READY_FAILED');self.assertEqual(events[-1]['machine_layer_count'],count);self.assertNotIn('HIGH_DOCUMENT_READY',[e['kind'] for e in events])
+
+    def test_abort_is_preserved_and_never_verifies(self):
+        with self.case(text='ABORT') as (root,c,asset,events,*_):
+            with self.assertRaises(auto.StopRequested):auto.manual_high_document(asset)
+            self.assertEqual(events[-1]['user_confirmation'],'ABORT');self.assertNotIn('HIGH_DOCUMENT_MACHINE_VERIFY_START',[e['kind'] for e in events])
+
+    def test_each_process_identity_field_is_guarded(self):
+        for key in ('pid','ppid','starttime','exe','cgroup'):
+            with self.subTest(field=key),self.case(changed=key) as (root,c,asset,events,*_):
+                with self.assertRaises(RuntimeError):auto.manual_high_document(asset)
+                self.assertEqual(events[-1]['process_identity_status'],'FAILED');self.assertNotIn('HIGH_DOCUMENT_READY',[e['kind'] for e in events])
+
+    def test_dialog_and_multiple_main_windows_rejected(self):
+        for options in (dict(modal=True),dict(duplicate=True)):
+            with self.subTest(options=options),self.case(**options) as (root,c,asset,events,*_):
+                with self.assertRaises(RuntimeError):auto.manual_high_document(asset)
+                self.assertEqual(events[-1]['kind'],'HIGH_DOCUMENT_READY_FAILED')
+
+    def test_ready_cannot_override_safety_stop(self):
+        with self.case(safety_fail=True) as (root,c,asset,events,*_):
+            with self.assertRaises(auto.StopRequested):auto.manual_high_document(asset)
+            self.assertNotIn('HIGH_DOCUMENT_READY',[e['kind'] for e in events])
+
+    def test_wrong_window_or_accessibility_pid_cannot_use_user_fallback(self):
+        for options in (dict(wrong_window_pid=True),dict(wrong_accessible_pid=True)):
+            with self.subTest(options=options),self.case(**options) as (root,c,asset,events,*_):
+                with self.assertRaises(RuntimeError):auto.manual_high_document(asset)
+                self.assertNotIn('HIGH_DOCUMENT_READY',[e['kind'] for e in events])
+
+    def test_accessibility_timeout_is_logged_as_unavailable(self):
+        with self.case() as (root,c,asset,events,*_):
+            with patch.object(auto.subprocess,'run',side_effect=subprocess.TimeoutExpired(['TEST_ONLY'],5)):
+                ready=auto.manual_high_document(asset)
+            self.assertEqual(ready['document_verification'],'USER_CONFIRMED')
+            self.assertIn('error',load(root/'krita/high-document-manual-evidence.json')['accessibility_raw'])
+
+    def test_slow_evidence_write_cannot_reuse_stale_safety_ack(self):
+        from oomlab_krita_collect import common
+        with self.case() as (root,c,asset,events,commands,clock,identity):
+            original=common.save
+            def delayed(path,value):
+                original(path,value)
+                if Path(path).name=='high-document-manual-evidence.json':clock.advance(.6)
+            with patch.object(common,'save',side_effect=delayed):
+                with self.assertRaisesRegex(RuntimeError,'过期'):auto.manual_high_document(asset)
+            self.assertNotIn('HIGH_DOCUMENT_READY',[e['kind'] for e in events])
+
+    def test_wait_beyond_160_but_not_1800(self):
+        with self.case(delay=200) as (root,c,asset,events,*_):
+            ready=auto.manual_high_document(asset);self.assertEqual(ready['manual_wait_duration_s'],200);self.assertEqual(c['automation']['open_timeout_s'],160)
+        with self.case(delay=1801) as (root,c,asset,events,*_):
+            with self.assertRaisesRegex(TimeoutError,'整体运行'):auto.manual_high_document(asset)
+            self.assertNotIn('HIGH_DOCUMENT_READY',[e['kind'] for e in events])
+
+    def test_full_12s_after_verification(self):
+        with self.case(delay=200) as (root,c,asset,events,commands,clock,identity):
+            ready=auto.manual_high_document(asset);self.assertGreater(ready['monotonic_ns'],events[1]['monotonic_ns'])
+            with patch.object(auto.time,'sleep',side_effect=clock.advance):auto.capture_window(ready['monotonic_ns'],12)
+            self.assertEqual(events[-2]['origin_monotonic_ns'],ready['monotonic_ns']);self.assertEqual(events[-1]['monotonic_ns']-ready['monotonic_ns'],12_000_000_000);self.assertFalse(events[-1]['import_verified'])
+
+    def test_validator_checks_raw_proof_not_only_event_label(self):
+        with self.case(available=False) as (root,c,asset,events,*_):
+            auto.manual_high_document(asset);events.insert(0,dict(kind='KRITA_PROCESS',pid=42));safety=load(root/'manual-safety.json');rows=[dict(scope=k,monotonic_ns=v) for k,v in safety['sample_monotonic_ns'].items()];metadata=dict(run_id=root.name,config=c)
+            with patch('oomlab_krita_collect.validation.iter_samples',return_value=iter(rows)):
+                self.assertEqual(verify_manual_evidence(root,metadata,events,script_contract(config=c))['document_verification'],'USER_CONFIRMED')
+            proof=load(root/'krita/high-document-manual-evidence.json');proof['accessibility']=dict(ok=True,pid=42,selected_application=dict(pid=42),layer_views=[dict(row_count=7)]);save(root/'krita/high-document-manual-evidence.json',proof)
+            with self.assertRaises(ValueError):verify_manual_evidence(root,metadata,events,script_contract(config=c))
+
+    def test_manual_full_event_contract_and_unchanged_pressure_bounds(self):
+        with self.case(delay=200) as (root,c,asset,events,commands,clock,identity):
+            ready=auto.manual_high_document(asset)
+            with patch.object(auto.time,'sleep',side_effect=clock.advance):auto.capture_window(ready['monotonic_ns'],12)
+            high_end=clock.ns;contract=script_contract(config=c)
+            prefix=[dict(kind='KRITA_PROCESS',monotonic_ns=0,pid=42)]
+            for n,k in enumerate(['DOCUMENT_OPEN_START','DOCUMENT_OPEN_DONE','CANVAS_ZOOM_START','CANVAS_ZOOM_DONE'],1):prefix.append(dict(kind=k,monotonic_ns=n*1_000_000_000))
+            prefix += [dict(kind='PRE_IMPORT_REVIEW_START',monotonic_ns=5_000_000_000,duration_s=30,pid=42),dict(kind='PRE_IMPORT_REVIEW_DONE',monotonic_ns=35_000_000_000,duration_s=30,pid=42,zoom_cycles=6)]
+            records=prefix+events
+            for offset,kind,fields in [(1,'DOCUMENT_CLOSE_START',{}),(2,'DOCUMENT_CLOSE_DONE',{}),(3,'HIGH_INSTANCE_EXIT',dict(pid=42,returncode=0)),(4,'KRITA_POST_PROCESS',dict(pid=43)),(5,'TAIL_DOCUMENT_OPEN_DONE',dict(pid=43,asset=contract['tail_document']['path'],verification='owned_document_title')),(6,'POST_CLOSE_REVIEW_START',dict(pid=43,duration_s=30)),(36,'POST_CLOSE_REVIEW_DONE',dict(pid=43,duration_s=30,zoom_cycles=6)),(37,'KRITA_EXIT',dict(pid=43,returncode=0))]:
+                records.append(dict(kind=kind,monotonic_ns=high_end+offset*1_000_000_000,**fields))
+            verify_pilot_events(records,contract)
+            def sample(stamp,pid,charge):return dict(scope='krita',krita_pid=pid,monotonic_ns=stamp,memory_current=charge,mem_total_bytes=16*2**30,mem_available_bytes=16*2**30-charge,swap_total_bytes=2**30,swap_free_bytes=2**30)
+            samples=[sample(stamp,42,2**30) for stamp in (5_000_000_000,35_000_000_000)]
+            samples += [sample(stamp,42,12*2**30) for stamp in (ready['monotonic_ns'],high_end)]
+            samples += [sample(high_end+offset*1_000_000_000,43,5*2**29) for offset in (6,36)]
+            result=assess_pressure_profile(samples,records,contract,.5);self.assertTrue(result['valid'],result['errors']);self.assertEqual(result['windows']['high']['window_s'],12)
+            for error in ('user_origin','short','failure'):
+                bad=copy.deepcopy(records);by={e['kind']:e for e in bad}
+                if error=='user_origin':by['CAPTURE_WINDOW_START']['origin_monotonic_ns']=by['HIGH_DOCUMENT_USER_READY']['monotonic_ns']
+                elif error=='short':by['CAPTURE_WINDOW_DONE']['monotonic_ns']-=1
+                else:bad.append(dict(kind='HIGH_DOCUMENT_READY_FAILED'))
+                with self.subTest(error=error),self.assertRaises(ValueError):verify_pilot_events(bad,contract)
+            samples[2]['memory_current']=8*2**30;samples[3]['memory_current']=8*2**30
+            self.assertIn('high-phase charge peak outside reference tolerance',assess_pressure_profile(samples,records,contract,.5)['errors'])
+
+class TerminalTests(unittest.TestCase):
+    def test_real_foreground_tty_relay_in_independent_process(self):
+        # Only this test allocates a PTY. Production never creates a terminal.
+        code='''
+import json,sys,time
+from pathlib import Path
+from oomlab_krita_collect.common import load,save
+from oomlab_krita_collect.config import read
+from oomlab_krita_collect.manual_import import TerminalRelay
+root=Path(sys.argv[1]);c=read(sys.argv[2]);relay=TerminalRelay(root,c);relay.start()
+a=c['automation']['prepared_document']
+save(root/'manual-import-request.json',dict(run_id=root.name,request_id='TEST_ONLY',expected_asset=a['path'],expected_sha256=a['sha256'],expected_layers=46))
+ticks=[];end=time.monotonic()+4
+try:
+ while not (root/'manual-import-response.json').exists() and time.monotonic()<end:
+  ticks.append(time.monotonic_ns());time.sleep(.05);relay.check()
+ reply=load(root/'manual-import-response.json')
+ print('TEST_RESULT '+json.dumps(dict(reply=reply,ticks=len(ticks))),flush=True)
+finally:relay.close()
+'''
+        with tempfile.TemporaryDirectory() as tmp:
+            root=Path(tmp)/('d'*32);root.mkdir();master,slave=pty.openpty()
+            os.write(master,b'READY 46\n')  # Old input must be discarded before the prompt.
+            def foreground():
+                os.setsid();fcntl.ioctl(0,termios.TIOCSCTTY,0);os.tcsetpgrp(0,os.getpgrp())
+            env=dict(os.environ,PYTHONPATH=str(GUI),PYTHONDONTWRITEBYTECODE='1')
+            process=subprocess.Popen([sys.executable,'-u','-c',code,str(root),str(CONFIG)],stdin=slave,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,preexec_fn=foreground)
+            try:
+                buffered=b'';until=time.monotonic()+3
+                while b'[MANUAL IMPORT REQUIRED]' not in buffered and time.monotonic()<until:
+                    if select.select([process.stdout],[],[],.1)[0]:
+                        block=os.read(process.stdout.fileno(),4096)
+                        if not block:break
+                        buffered+=block
+                self.assertIn(b'[MANUAL IMPORT REQUIRED]',buffered)
+                time.sleep(.3);os.write(master,b'READY 46\n');output,error=process.communicate(timeout=4)
+                self.assertEqual(process.returncode,0,error.decode())
+                result=json.loads(next(line[len('TEST_RESULT '):] for line in output.decode().splitlines() if line.startswith('TEST_RESULT ')))
+                self.assertEqual(result['reply']['user_confirmation'],'READY 46');self.assertEqual(result['reply']['reader_pid'],process.pid);self.assertTrue(result['reply']['foreground_checked']);self.assertGreaterEqual(result['ticks'],5)
+            finally:
+                if process.poll() is None:process.terminate();process.wait(timeout=2)
+                process.stdout.close();process.stderr.close();os.close(master);os.close(slave)
+
+    def test_non_tty_rejected_before_environment_or_application(self):
+        with patch.object(sys,'stdin',io.StringIO('READY 46\n')),patch.object(cli,'check') as check:
+            with self.assertRaisesRegex(RuntimeError,'TTY'):cli.collect(read(CONFIG),argparse.Namespace())
+            check.assert_not_called()
+
+    def test_background_tty_rejected(self):
+        master,slave=pty.openpty()
+        try:
+            with os.fdopen(os.dup(slave),'r') as stream,patch('os.tcgetpgrp',return_value=os.getpgrp()+1):
+                with self.assertRaisesRegex(RuntimeError,'TTY'):require_terminal(stream)
+        finally:os.close(master);os.close(slave)
+
+    def test_invalid_partial_then_ready_or_abort(self):
+        for answer in ('READY 46','ABORT','EOF'):
+            with self.subTest(answer=answer),tempfile.TemporaryDirectory() as tmp:
+                root=Path(tmp)/('b'*32);root.mkdir();c=read(CONFIG);master,slave=pty.openpty();output=io.StringIO()
+                try:
+                    with os.fdopen(os.dup(slave),'r') as stream,patch('os.tcgetpgrp',side_effect=lambda fd:os.getpgrp()):
+                        relay=TerminalRelay(root,c,stream,output);relay.start()
+                        try:
+                            a=c['automation']['prepared_document'];save(root/'manual-import-request.json',dict(run_id=root.name,request_id='TEST_ONLY',expected_asset=a['path'],expected_sha256=a['sha256'],expected_layers=46));until=time.monotonic()+3
+                            while '[MANUAL IMPORT REQUIRED]' not in output.getvalue() and time.monotonic()<until:time.sleep(.01)
+                            self.assertIn('[MANUAL IMPORT REQUIRED]',output.getvalue());os.write(master,b'wrong\nREADY 7\n'+b'x'*140+b'\n');time.sleep(.05);self.assertFalse((root/'manual-import-response.json').exists())
+                            if answer=='EOF':stamp=time.monotonic_ns();os.write(master,b'\x04')
+                            else:
+                                os.write(master,answer[:2].encode());time.sleep(.05);self.assertFalse((root/'manual-import-response.json').exists());stamp=time.monotonic_ns();os.write(master,(answer[2:]+'\n').encode())
+                            while not (root/'manual-import-response.json').exists() and time.monotonic()<until:time.sleep(.01)
+                            reply=load(root/'manual-import-response.json');self.assertEqual(reply['user_confirmation'],'ABORT' if answer=='EOF' else answer);self.assertGreaterEqual(reply['monotonic_ns'],stamp);self.assertTrue(reply['stdin_isatty']);self.assertIn('输入无效',output.getvalue());relay.check()
+                            if answer=='EOF':self.assertEqual(reply['reason'],'terminal_eof')
+                        finally:relay.close()
+                finally:os.close(master);os.close(slave)
+
+    def test_wait_does_not_block_50ms_fake_kernel_sampler(self):
+        with tempfile.TemporaryDirectory() as tmp:
+            base=Path(tmp);root=base/('c'*32);root.mkdir();c=read(CONFIG);master,slave=pty.openpty();kernel(base/'cg',base/'proc');stamps=[]
+            try:
+                with os.fdopen(os.dup(slave),'r') as stream,patch('os.tcgetpgrp',side_effect=lambda fd:os.getpgrp()):
+                    relay=TerminalRelay(root,c,stream,io.StringIO());relay.start()
+                    try:
+                        a=c['automation']['prepared_document'];save(root/'manual-import-request.json',dict(run_id=root.name,request_id='TEST_ONLY',expected_asset=a['path'],expected_sha256=a['sha256'],expected_layers=46));start=time.monotonic_ns()
+                        for n in range(12):
+                            time.sleep(max(0,(start+n*50_000_000-time.monotonic_ns())/1e9));stamps.append(snapshot(base/'cg',start,proc=base/'proc')['monotonic_ns'])
+                        self.assertTrue(relay.thread.is_alive());self.assertFalse((root/'manual-import-response.json').exists());self.assertEqual(len(stamps),12);self.assertLess(max(b-a for a,b in zip(stamps,stamps[1:])),500_000_000)
+                    finally:relay.close()
+            finally:os.close(master);os.close(slave)
+
+    def test_explicit_contradiction_never_uses_user_fallback(self):
+        for data in [dict(ok=False,layer_views=[dict(row_count=45)]),dict(ok=True,dialogs=[dict(name='Open Images')])]:
+            with self.assertRaises(ValueError):layer_verdict(data)
+        self.assertEqual(layer_verdict(dict(ok=True,layer_views=[dict(row_count=46),dict(row_count=46)])),(None,'MACHINE_LAYER_CHECK_UNAVAILABLE'))
+
+    def test_safety_ack_needs_fresh_parent_and_workload(self):
+        with tempfile.TemporaryDirectory() as tmp:
+            root=Path(tmp);c=read(CONFIG);save(root/'manual-safety-request.json',dict(run_id=root.name,request_id='TEST_ONLY',monotonic_ns=200))
+            service_safety_request(root,c,dict(parent=dict(monotonic_ns=199),krita=dict(monotonic_ns=201)));self.assertFalse((root/'manual-safety.json').exists())
+            service_safety_request(root,c,dict(parent=dict(monotonic_ns=201),krita=dict(monotonic_ns=202)));self.assertEqual(load(root/'manual-safety.json')['safety_status'],'PASS')
+
+    def test_parameters_and_legacy_default_are_unchanged(self):
+        c=read(CONFIG);legacy=read(GUI/'configs/collection.rapid-9000-medium-tail-extended.json');self.assertNotIn('manual_high_import',legacy['automation']);self.assertEqual(c['safety'],legacy['safety']);self.assertEqual(c['interval_s'],.05)
+        for k in ('open_timeout_s','capture_window_s','tile_memory_percent','pressure_profile','tail_charge_range_bytes'):self.assertEqual(c['automation'][k],legacy['automation'][k])
+        self.assertEqual(script_contract(config=c)['capture_origin'],'manual_document_ready')
+        for invalid in (1,'true',None):
+            bad=copy.deepcopy(c);bad['automation']['manual_high_import']=invalid
+            with tempfile.TemporaryDirectory() as tmp:
+                p=Path(tmp)/'c.json';save(p,bad)
+                with self.assertRaises(ValueError):read(p)
+
+class FlowRegressionTests(unittest.TestCase):
+    def test_only_high_open_changes_low_tail_and_exit_sequence_unchanged(self):
+        with tempfile.TemporaryDirectory() as tmp:
+            root=Path(tmp);(root/'krita').mkdir();c=read(CONFIG)
+            for name,key in [('low.ora','asset'),('high.ora','prepared_document'),('tail.ora','tail_document')]:
+                p=root/name;p.touch();target=c['asset'] if key=='asset' else c['automation'][key];target['path']=str(p)
+            c['pilot']['layers_dir']=str(root);settings=root/'config.json';save(settings,c)
+            manifest=root/'assets.json';save(manifest,dict(png_files=[],script_contract=script_contract(config=c),ora=dict(width=9000,height=9000)))
+            calls=[];old=auto.CTX.copy()
+            def start(env,timed,settings,event,record):
+                calls.append(('start',event));auto.CTX.update(pid=42 if event=='KRITA_PROCESS' else 43,wid='0x10')
+            def opened(asset=None):calls.append(('open',asset))
+            def manual(asset):calls.append(('manual',asset['path']));return dict(monotonic_ns=456_000_000_000)
+            with contextlib.ExitStack() as stack:
+                for name,value in [('windows',lambda:[]),('prepare_window',lambda:None),('zoom_relative',lambda:None),('start_krita',start),('open_document',opened),('close_document',lambda:calls.append(('close',))),('manual_high_document',manual),('capture_window',lambda origin,duration:calls.append(('capture',origin,duration))),('quit_krita',lambda event:calls.append(('quit',event))),('review_canvas',lambda label,duration,cadence:calls.append(('review',label,duration,cadence)))]:stack.enter_context(patch.object(auto,name,side_effect=value))
+                stack.enter_context(patch.object(auto.subprocess,'Popen',side_effect=AssertionError('No real GUI allowed')))
+                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
+                try:code=auto.main([c['asset']['path'],'--settings',str(settings),'--assets-manifest',str(manifest),'--control-file',str(root/'stop-request.json'),'--process-record',str(root/'krita/krita-process.json')])
+                finally:auto.CTX.clear();auto.CTX.update(old)
+            self.assertEqual(code,0)
+            self.assertEqual(calls,[('start','KRITA_PROCESS'),('open',None),('review','PRE_IMPORT_REVIEW',30,5),('close',),('manual',c['automation']['prepared_document']['path']),('capture',456_000_000_000,12),('close',),('quit','HIGH_INSTANCE_EXIT'),('start','KRITA_POST_PROCESS'),('open',c['automation']['tail_document']['path']),('review','POST_CLOSE_REVIEW',30,5),('close',),('quit','KRITA_EXIT')])
+
+if __name__=='__main__':unittest.main()
````
