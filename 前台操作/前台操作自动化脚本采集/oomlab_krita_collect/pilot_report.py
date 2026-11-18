"""Chinese, decimal-GB PILOT report derived from immutable kernel/source evidence."""
import json
from pathlib import Path
from .common import load
from .validation import iter_samples


def gb(value):return 'unavailable' if value is None else f'{value/1_000_000_000:.6f} GB'


def write_report(run,summary):
    run=Path(run);m=load(run/'metadata.json');env=load(run/'environment.json')
    def optional(name):
        try:return load(run/name)
        except (OSError,ValueError):return {}
    assets=optional('assets_manifest.json');end=optional('cgroup-end.json').get('scopes',{})
    from .metrics import deltas
    event_deltas=dict(summary.get('events_delta',{}))
    for scope,first in optional('cgroup-start.json').get('scopes',{}).items():
        if scope in end:
            try:event_deltas[scope]=deltas(first,end[scope])
            except ValueError:pass
    events=[]
    try:events=[json.loads(line) for line in (run/'phase-events.jsonl').read_text().splitlines()]
    except (OSError,ValueError):pass
    ranges=[];starts={e['phase']:e for e in events if e.get('kind')=='phase_start'};ends={e['phase']:e for e in events if e.get('kind')=='phase_end'}
    for number in range(1,9):
        a=starts.get(number,{});b=ends.get(number,{})
        ranges.append(dict(number=number,name=a.get('phase_name','NOT_RUN'),start=a.get('start_timestamp_ns'),end=b.get('end_timestamp_ns'),status=b.get('status','INTERRUPTED' if a else 'NOT_RUN'),duration=b.get('duration_ms'),error=b.get('error_message')))
    contract=assets.get('script_contract',{})
    timed=contract.get('completion_mode')=='timed_window'
    prepared=contract.get('prepared_document')
    if prepared:
        operation_ranges=[('HIGH_DOCUMENT_SUBMITTED','HIGH_DOCUMENT_OPEN_DONE','打开预组装文档'),
                          ('CAPTURE_WINDOW_START','CAPTURE_WINDOW_DONE','高压观测窗口')]
    elif timed:
        operation_ranges=[('LAYER_IMPORT_START','LAYER_IMPORT_SUBMITTED','导入提交'),
                          ('CAPTURE_WINDOW_START','CAPTURE_WINDOW_DONE','定时采集窗口')]
    else:
        operation_ranges=[('LAYER_IMPORT_START','LAYER_IMPORT_DONE','图层导入'),('HOLD_START','HOLD_DONE','保持')]
    if 'pressure_profile' in contract:
        operation_ranges.extend([
            ('PRE_IMPORT_REVIEW_START','PRE_IMPORT_REVIEW_DONE','峰前浏览'),
            ('POST_CLOSE_REVIEW_START','POST_CLOSE_REVIEW_DONE','峰后浏览'),
        ])
    for first,last,label in operation_ranges+[('DOCUMENT_CLOSE_START','DOCUMENT_CLOSE_DONE','文档关闭')]:
        a=next((e for e in events if e.get('kind')==first),{});b=next((e for e in events if e.get('kind')==last),{})
        ranges.append(dict(number=label,name=label,start=a.get('monotonic_ns'),end=b.get('monotonic_ns'),status='PASS' if a and b else 'INTERRUPTED' if a else 'NOT_RUN'))
    peaks={};minimum={};curve={str(r['number']):dict(first=None,last=None,minimum=None,maximum=None,count=0) for r in ranges};peak_stage=None;sampled_peak=-1
    count={};last_index={};analysis_error=None
    try:
        for row in iter_samples(run):
            scope=row['scope'];count[scope]=count.get(scope,0)+1;last_index[scope]=row.get('sample_index')
            for key in ('mem_available_bytes','swap_free_bytes'):
                value=row.get(key)
                if value is not None:minimum[key]=min(minimum.get(key,value),value)
            if scope!='krita':continue
            for key in ('krita_rss_bytes','krita_vm_hwm_bytes','stat_anon','stat_file','global_psi_full_avg10','global_psi_some_avg10','cgroup_psi_full_avg10'):
                value=row.get(key)
                if value is not None:peaks[key]=max(peaks.get(key,value),value)
            current=row.get('memory_current');stamp=row['monotonic_ns']
            if current is None:continue
            if current>sampled_peak:
                sampled_peak=current;peak_stage=next((r['name'] for r in ranges[:8] if r['start'] is not None and r['end'] is not None and r['start']<=stamp<=r['end']),'阶段边界外/未完成阶段')
            for r in ranges:
                if r['start'] is None or stamp<r['start'] or (r['end'] is not None and stamp>r['end']):continue
                track=curve[str(r['number'])];track['count']+=1
                if track['first'] is None:track['first']=current
                track['last']=current;track['minimum']=current if track['minimum'] is None else min(track['minimum'],current);track['maximum']=current if track['maximum'] is None else max(track['maximum'],current)
    except Exception as e:analysis_error=repr(e)
    lines=['# Krita 单轮 PILOT 报告','',f"状态：**{summary.get('status','PILOT_INVALID')}**。分类：PILOT；formal_eligible=false；不代表 FORMAL_ACCEPTED。",'',
           '内存统一采用十进制 GB（bytes / 1,000,000,000）。原始 CSV 保留 bytes。父子峰值分别报告，禁止相加。','',
           '## 环境与素材','',f"系统：{env.get('distribution')}；实际内核：{env.get('kernel')}；桌面会话：{env.get('session_type')}；DISPLAY：{env.get('display')}。",
           f"资源预检：{env.get('resources')}。cgroup：{env.get('cgroup_v2')}。",
           f"实际进程 libqxcb.so 与归属验证：{m.get('krita_xcb_verified',False)}。进程详细证据见 process-observations.jsonl 与 krita/krita-process.json。",
           f"ORA：{assets.get('ora')}。额外 PNG 数：{assets.get('png_count','NOT_RUN')}。",
           f"脚本设计：{assets.get('script_contract')}。每个 PNG 的尺寸、模式、SHA256、大小和 mtime 见 assets_manifest.json。",
           f"前后素材一致：{m.get('assets_unchanged',False)}；源码：{m.get('source',{}).get('git_sha')}。",'',
           '## 八阶段结果','', '|阶段|名称|开始 monotonic ns|结束 monotonic ns|状态|耗时 ms|异常|','|---|---|---|---|---|---|---|']
    for r in ranges[:8]:lines.append('|'+ '|'.join(str(r.get(k,'unavailable')).replace('|','/') for k in ('number','name','start','end','status','duration','error'))+'|')
    if prepared:
        lines+=['',f"高压素材为包含 {prepared['layers']} 层的预组装 ORA。文件摘要和图层清单已核对，以本轮 Krita 文档标题确认打开。"]
    elif timed:lines+=['','本轮为定时采集验证：窗口完成不等于图层导入已验证。未产生 LAYER_IMPORT_DONE 或 HOLD_DONE；import_layers_verified=false。按导入提交时刻计算窗口，不使用旧的 1800 秒保持。']
    lines+=['','## 内存统计','','|指标|结果|','|---|---|']
    stats=[('Krita RSS 峰值',peaks.get('krita_rss_bytes')),('Krita VmHWM',peaks.get('krita_vm_hwm_bytes')),
           ('workload memory.peak',end.get('krita',{}).get('memory_peak')),('parent memory.peak',end.get('parent',{}).get('memory_peak')),
           ('匿名内存采样峰值',peaks.get('stat_anon')),('文件缓存采样峰值',peaks.get('stat_file')),
           ('最低 MemAvailable',minimum.get('mem_available_bytes')),('最低 SwapFree',minimum.get('swap_free_bytes'))]
    lines += [f'|{label}|{gb(value)}|' for label,value in stats]
    for key in ('global_psi_full_avg10','global_psi_some_avg10','cgroup_psi_full_avg10'):lines.append(f'|{key} 峰值 (%)|{peaks.get(key,"unavailable")}|')
    for scope in ('krita','parent'):
        delta=event_deltas.get(scope,{})
        for key in ('event_oom','event_oom_kill'):lines.append(f'|{scope} {key} 增量|{delta.get(key,"unavailable")}|')
    lines+=['','## 阶段与曲线对应','','|阶段|采样数|首值|末值|变化|范围|','|---|---|---|---|---|---|']
    for r in ranges:
        track=curve[str(r['number'])];a=track['first'];b=track['last']
        lines.append(f"|{r['number']} {r['name']}|{track['count']}|{gb(a)}|{gb(b)}|{gb(b-a) if a is not None else 'unavailable'}|{gb(track['minimum'])} — {gb(track['maximum'])}|")
    lines += ['',f'采样 memory.current 最大值位于：{peak_stage or "NOT_RUN"}。memory.peak 是内核生命周期峰值；不能据此声称其精确发生时刻。',
              '保持阶段以首末变化及区间范围说明是否继续增长；未配置稳定性判据，不自动宣称内存稳定。阶段边界的统计误差至少为实际采样间隔。','',
              '## 有效性、停止与清理','',f"各 scope 样本数：{count}；最后 sample_index：{last_index}。",
              f"最大采样间隔（秒）：{summary.get('max_sample_gap_s')}；曲线完整：{summary.get('curve_complete',False)}。",
              f"验证错误：{summary.get('errors')}；分析异常：{analysis_error}。",
              f"停止原因：{m.get('error')}；触发阶段：{m.get('safety_stop',{}).get('phase')}；触发时间：{m.get('safety_stop',{}).get('monotonic_ns')}。",
              f"安全停止完整现场见 stop-request.json（仅发生停止时存在），配置阈值见 config.snapshot.json。",
              f"Krita/自动化退出：{m.get('finishes')}；清理：{m.get('cleanup_ok')}；冷却：{m.get('cooldown_ok')}。",
              '原始采样、日志、cgroup 起止快照、素材前后清单和校验封印均保留。失败后不自动重试；须人工审阅原因。']
    (run/'report.md').write_text('\n'.join(lines)+'\n')
