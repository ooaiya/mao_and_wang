import csv
import json
import math
import re
import statistics
from pathlib import Path
from .common import SCHEMA,load,verify_seal
from .metrics import deltas
from .phases import validate as valid_phases

REQUIRED_FILES=('environment.json','metadata.json','samples.csv','phase-events.jsonl','automation.log',
                'cgroup-start.json','cgroup-end.json','journal.log','cleanup.json')


def iter_samples(run):
    with open(Path(run)/'samples.csv',newline='') as f:
        for raw in csv.DictReader(f):
            row={}
            for k,v in raw.items():
                if v in ('','null'):row[k]=None
                elif k in ('scope','classification','krita_state'):row[k]=v
                elif k.endswith('_json'):row[k[:-5]]=json.loads(v) if v else None
                elif k in ('relative_s','krita_cpu_percent','krita_elapsed_s') or '_avg' in k:row[k]=float(v)
                else:row[k]=int(v)
            yield row


def read_samples(run):return list(iter_samples(run))


def validate_run(run,verify_manifest=True):
    run=Path(run); errors=[]; info=dict(schema_version=SCHEMA,valid=False,formal_eligible=False,classification=None)
    try:
        if verify_manifest:verify_seal(run)
        for name in REQUIRED_FILES:
            if not (run/name).is_file():raise ValueError('missing evidence: '+name)
        m=load(run/'metadata.json');info['classification']=m['classification'];pilot=m['classification']=='PILOT'
        if m['classification'] not in ('PILOT','TEST_ONLY','FORMAL'):raise ValueError('unknown classification')
        if pilot:
            for name in ('assets_manifest.json','assets_manifest.after.json','config.snapshot.json','memory-events.jsonl','process-observations.jsonl'):
                if not (run/name).is_file():errors.append('missing PILOT evidence: '+name)
            if m['config'].get('mode')!='pilot' or set(m['recipes'])!={'krita'} or m['interval_s']!=.05:errors.append('invalid PILOT boundary/config/interval')
            if m.get('assets_unchanged') is not True or load(run/'assets_manifest.json')!=load(run/'assets_manifest.after.json'):errors.append('PILOT asset integrity proof missing/changed')
            if load(run/'config.snapshot.json')!=m['config']:errors.append('config snapshot mismatch')
        if run.resolve()!=run.absolute() or run.name!=m.get('run_id') or not re.fullmatch('[0-9a-f]{32}',run.name):raise ValueError('run identity/path mismatch')
        if m.get('error') or m.get('evidence_errors'):errors.append(str(m.get('error') or m.get('evidence_errors')))
        if not all(m.get(k) is True for k in ('cleanup_ok','cooldown_ok','operations_verified','journal_ok')):errors.append('incomplete operation/cleanup/cooldown/journal evidence')
        if m['classification']!='TEST_ONLY' and (m.get('asset_before')!=m.get('asset_after') or m.get('asset_directory_before')!=m.get('asset_directory_after')):errors.append('ORA fingerprint changed')
        cleanup=load(run/'cleanup.json')['records']
        if cleanup!=m.get('cleanup') or not cleanup or not all(row.get('ok') is True for row in cleanup):errors.append('cleanup records incomplete')
        if m['classification']!='TEST_ONLY':
            if not re.fullmatch('[0-9a-f]{40}',m.get('source',{}).get('git_sha','')) or m.get('source',{}).get('source_dirty') is not False:errors.append('committed source proof missing')
            for op in m['recipes']:
                unit=load(run/op/'unit-identity.json')
                if unit.get('unit')!='oomcollect-'+m['run_id']+'-'+op+'.service' or not unit.get('starttime') or unit.get('pid',0)<=0:errors.append('unit identity proof missing')
        if m.get('strategy')!='none':errors.append('not a no-strategy measurement')
        starts=load(run/'cgroup-start.json')['scopes'];ends=load(run/'cgroup-end.json')['scopes']
        expected={'parent',*m['recipes']}
        if set(starts)!=expected or set(ends)!=expected:errors.append('incomplete scope snapshots')
        events={}
        for scope in expected:
            delta=deltas(starts[scope],ends[scope]);events[scope]=delta;info['events_delta']=events
            if any(delta.get('event_'+k)!=0 for k in ('max','oom','oom_kill','oom_group_kill')):errors.append('OOM/limit counters nonzero or unknown: '+scope)
            if delta.get('vmstat',{}).get('oom_kill')!=0:errors.append('global OOM kill nonzero or unknown')
        tracks={op:dict(count=0,previous=None,peak=0,max_current=-1,peak_stamp=None,gap=0,offset_low=None,offset_high=None) for op in expected}
        peaks={};times={};duration={};absolute={};gaps={};pressure_since={};process_rows=0
        critical=['wall_time_ns','boottime_ns','monotonic_ns','relative_s','memory_current','memory_peak','mem_available_bytes','swap_free_bytes']+[p+'_'+kind+'_'+k for p in ('cgroup_psi','global_psi') for kind in ('some','full') for k in ('avg10','avg60','avg300','total')]
        for row in iter_samples(run):
            scope=row.get('scope')
            if scope not in tracks:raise ValueError('unknown sample scope')
            track=tracks[scope];previous=track['previous']
            if pilot and row.get('sample_index')!=track['count']:raise ValueError('PILOT sample index gap')
            if pilot and row.get('krita_pid'):
                process_rows+=1
                if scope!='krita':raise ValueError('Krita process metrics outside workload scope')
                for key in ('krita_starttime','krita_ppid','krita_vm_rss_bytes','krita_vm_hwm_bytes','krita_vm_size_bytes','krita_threads','krita_state','krita_elapsed_s'):
                    if row.get(key) is None:raise ValueError('missing Krita process metric: '+key)
            if row.get('classification')!=m['classification']:raise ValueError('measurement classification mismatch')
            if row.get('schema_version')!=SCHEMA or any(row.get(k) is None for k in critical):raise ValueError('missing critical metric: '+scope)
            if row.get('freeze_requested')!=0 or row.get('frozen')!=0:raise ValueError('freezer state changed or missing')
            if any(not math.isfinite(v) or v<0 for v in row.values() if isinstance(v,(int,float))):raise ValueError('negative/nonfinite sample')
            if row['monotonic_ns']<m['origin_monotonic_ns'] or abs(row['relative_s']-(row['monotonic_ns']-m['origin_monotonic_ns'])/1e9)>1e-8:raise ValueError('clock domain mismatch')
            if previous is not None:
                if row['monotonic_ns']<=previous['monotonic_ns'] or row['relative_s']<=previous['relative_s']:raise ValueError('non-monotonic sample time')
                deltas(previous,row)
                if row['memory_peak']<previous['memory_peak']:raise ValueError('memory.peak rolled back')
                track['gap']=max(track['gap'],(row['monotonic_ns']-previous['monotonic_ns'])/1e9)
            offset=row['boottime_ns']-row['monotonic_ns']
            track['offset_low']=offset if track['offset_low'] is None else min(offset,track['offset_low'])
            track['offset_high']=offset if track['offset_high'] is None else max(offset,track['offset_high'])
            track['count']+=1;track['peak']=max(track['peak'],row['memory_peak']);track['previous']=row
            if row['memory_current']>track['max_current']:track.update(max_current=row['memory_current'],peak_stamp=row['monotonic_ns'])
            s=m['config']['safety']
            if row['memory_peak']>=s['max_cgroup_bytes'] or row['mem_available_bytes']<s['min_available_bytes'] or row['swap_free_bytes']<s['min_swap_free_bytes'] or (not pilot and row['global_psi_full_avg10']>=s['max_global_full_avg10']):raise ValueError('sample crossed safety threshold')
            if pilot:
                if row['global_psi_full_avg10']>=s['max_global_full_avg10']:
                    pressure_since.setdefault(scope,row['monotonic_ns'])
                    if (row['monotonic_ns']-pressure_since[scope])/1e9>=m['config']['pilot']['psi_full_sustained_s']:errors.append('sustained severe PSI')
                else:pressure_since.pop(scope,None)
        if pilot and not process_rows:errors.append('no real Krita process samples')
        for scope,track in tracks.items():
            if any(ends[scope].get(k) is None for k in critical):errors.append('incomplete final snapshot: '+scope)
            if ends[scope].get('freeze_requested')!=0 or ends[scope].get('frozen')!=0:errors.append('final freezer state changed or missing')
            if ends[scope]['memory_peak']<track['peak']:errors.append('final memory.peak rolled back')
            if track['count']<2:errors.append('insufficient samples: '+scope);continue
            if pilot:
                elapsed=(track['previous']['monotonic_ns']-starts[scope]['monotonic_ns'])/1e9
                if elapsed>0 and track['count']<.9*elapsed/m['interval_s']:errors.append('PILOT average sampling frequency below 18Hz: '+scope)
            gaps[scope]=track['gap']
            if track['gap']>m['config']['safety']['max_sample_gap_s']:errors.append('sampling gap exceeds explicit threshold')
            if track['offset_high']-track['offset_low']>max(.2,2*m['interval_s'])*1e9:errors.append('suspend/clock-domain discontinuity')
            peaks[scope]=max(track['peak'],ends[scope]['memory_peak']);absolute[scope]=track['peak_stamp']
            if scope in m.get('finishes',{}):
                finish=m['finishes'][scope];origin=finish['start_monotonic_ns'];duration[scope]=(finish['end_monotonic_ns']-origin)/1e9
                if duration[scope]<=0 or finish.get('returncode')!=0 or finish.get('error'):errors.append('invalid operation finish: '+scope)
                times[scope]=max(0,(track['peak_stamp']-origin)/1e9)
        if set(m.get('finishes',{}))!=set(m['recipes']):errors.append('incomplete operation exits')
        if pilot:verify_pilot_process(run,m)
        if 'krita' in m['recipes']:
            if m['classification']!='TEST_ONLY' and not m.get('krita_xcb_verified'):errors.append('actual Krita xcb membership/plugin proof missing')
            events_phase=[json.loads(line) for line in (run/'krita/phase-events.jsonl').read_text().splitlines()]
            if not valid_phases(events_phase,structured=pilot):errors.append('incomplete/out-of-order/error GUI stages')
            if pilot:
                contract=load(run/'assets_manifest.json')['script_contract']
                verify_pilot_events(events_phase,contract)
                if contract.get('completion_mode')=='timed_window':
                    info.update(completion_mode='timed_window',capture_window_complete=True,
                                import_layers_verified=False,capture_origin=contract['capture_origin'])
                if 'pressure_profile' in contract:
                    shape=assess_pressure_profile(iter_samples(run),events_phase,contract,m['config']['safety']['max_sample_gap_s'])
                    info['pressure_profile']=shape
                    errors.extend(shape['errors'])
        info.update(events_delta=events,max_sample_gap_s=gaps,peak_bytes=peaks,time_to_peak_s=times,peak_monotonic_ns=absolute,duration_s=duration,
                    peak_time_method='sampled memory.current maximum; timing has sampling uncertainty',curve_complete=not errors)
        single=len(m['recipes'])==1
        acceptance=single and all(op in m['config']['acceptance'] and m['config']['acceptance'][op]['min_peak_bytes']<=peaks.get(op,-1)<=m['config']['acceptance'][op]['max_peak_bytes'] for op in m['recipes'])
        info.update(single_operation_acceptance=acceptance,valid=not errors,
                    formal_eligible=not errors and m['classification']=='FORMAL' and (acceptance if single else True))
    except Exception as e:errors.append(type(e).__name__+': '+str(e))
    if info.get('classification')=='PILOT':info['status']='PILOT_VALID' if not errors else 'PILOT_INVALID'
    info['errors']=errors
    if errors:info.update(valid=False,formal_eligible=False,curve_complete=False)
    return info


def stats(values):
    if not values:return dict(n=0,mean=None,median=None,p95=None,cv=None)
    vals=sorted(values);mean=statistics.mean(vals);position=(len(vals)-1)*.95;i=int(position)
    p95=vals[i]+(vals[min(i+1,len(vals)-1)]-vals[i])*(position-i)
    return dict(n=len(vals),mean=mean,median=statistics.median(vals),p95=p95,cv=statistics.stdev(vals)/mean if len(vals)>1 and mean else None)


def report(session):
    session=Path(session);config=load(session/'session.json');runs=[]
    for directory in session.iterdir():
        if directory.is_dir() and directory.name!='continuations' and not (directory/'metadata.json').is_file():
            runs.append(dict(run=str(directory),formal_eligible=False,valid=False,errors=['incomplete round directory']))
    for p in sorted(session.glob('*/metadata.json')):
        result=validate_run(p.parent);m=load(p)
        if m.get('source')!=config.get('source') or m.get('recipes')!={config['operation']:config.get('recipe')} or m.get('config')!=config.get('config') or m.get('classification')!=config.get('classification'):
            result.update(valid=False,formal_eligible=False);result['errors'].append('session/round provenance mismatch')
        runs.append(dict(run=str(p.parent),**result))
    pilot=config['classification']=='PILOT'
    valid=[r for r in runs if r['valid'] and r.get('classification')=='PILOT'] if pilot else [r for r in runs if r['formal_eligible']];op=config['operation']
    peaks=stats([r['peak_bytes'][op] for r in valid]); durations=stats([r['duration_s'][op] for r in valid]);topeak=stats([r['time_to_peak_s'][op] for r in valid])
    return dict(schema_version=SCHEMA,classification=config['classification'],formal_eligible=False if pilot else bool(valid),status='NOT_RUN' if not runs else ('PILOT_VALID' if len(runs)==len(valid)==1 else 'PILOT_INVALID') if pilot else 'VALIDATED' if len(valid)==len(runs) else 'STOP_INVALID',
                operation=op,valid_rounds=len(valid),runs=runs,peak_bytes=peaks,duration_s=durations,time_to_peak_s=topeak,
                stable_peak_cv_le_10pct=peaks['cv'] is not None and peaks['cv']<=.10,curve_completeness=[r.get('curve_complete',False) for r in runs])


def verify_pilot_process(run,metadata):
    run=Path(run);unit=load(run/'krita/unit-identity.json')
    automation=load(run/'krita/workload-pid.json')['pid'];cg=unit['properties']['ControlGroup']
    names=['krita-process.json']
    if metadata['config']['automation'].get('prepared_document'):names.append('krita-post-process.json')
    records={}
    for name in names:
        record=load(run/'krita'/name)
        if record['pid'] in records or record['ppid']!=automation or record['cgroup']!='0::'+cg or Path(record['exe']).name.lower()!='krita':
            raise ValueError('Krita process lineage/cgroup mismatch')
        records[record['pid']]=record
        if record.get('libqxcb_verified') is not True or not any(Path(p).name=='libqxcb.so' for p in record.get('qt_plugins',[])) or any('libqwayland' in p for p in record.get('qt_plugins',[])):raise ValueError('Krita loaded xcb proof missing')
        window=record.get('window',{});props=window.get('xproperties','')
        if not record.get('focus_verified') or window.get('id')!=record.get('window_id') or window.get('pid')!=record['pid']:raise ValueError('window/focus ownership evidence missing')
        if not re.search(r'_NET_WM_PID\(CARDINAL\)\s*=\s*'+str(record['pid'])+r'\b',props) or not re.search(r'WM_CLASS\(STRING\)[^\n]*"krita"',props,re.I):raise ValueError('window properties missing')
    proved=set()
    for line in (run/'process-observations.jsonl').read_text().splitlines():
        event=json.loads(line);p=event['process']
        if p['cgroup']!=cg and not p['cgroup'].startswith(cg+'/'):raise ValueError('process observed outside workload')
        if p['pid'] in records:
            record=records[p['pid']]
            if any(p[k]!=record[k] for k in ('ppid','starttime','exe')):raise ValueError('process observation identity mismatch')
            if any(Path(x).name=='libqxcb.so' for x in p.get('qt_plugins',[])) and not any('libqwayland' in x for x in p.get('qt_plugins',[])):proved.add(p['pid'])
    if proved!=set(records):raise ValueError('no independent xcb process observation')
    for row in iter_samples(run):
        if row.get('krita_pid'):
            record=records.get(row['krita_pid'])
            if not record or any(row.get('krita_'+k)!=record[k] for k in ('ppid','starttime')):
                raise ValueError('process sample identity mismatch')
    boundary=load(run/'boundary.json');collector=boundary['collector_cgroup'];parent=metadata['parent_properties']['ControlGroup']
    if collector==parent or collector.startswith(parent+'/'):raise ValueError('collector inside workload parent')


def verify_pilot_events(events,contract):
    if contract.get('completion_mode')=='timed_window':return verify_timed_events(events,contract)
    names=['DOCUMENT_OPEN_START','DOCUMENT_OPEN_DONE','CANVAS_ZOOM_START','CANVAS_ZOOM_DONE','LAYER_IMPORT_START','LAYER_IMPORT_DONE','HOLD_START','HOLD_DONE','DOCUMENT_CLOSE_START','DOCUMENT_CLOSE_DONE','KRITA_EXIT']
    records=[e for e in events if e.get('kind') in names]
    if [e['kind'] for e in records]!=names:raise ValueError('missing/duplicate/out-of-order PILOT operation events')
    if any(b['monotonic_ns']<a['monotonic_ns'] for a,b in zip(records,records[1:])):raise ValueError('PILOT event time reversed')
    by={e['kind']:e for e in records}
    if by['LAYER_IMPORT_START'].get('import_count')!=contract['import_count'] or by['LAYER_IMPORT_DONE'].get('verified_total_layers')!=1+contract['import_count']:raise ValueError('import count not verified')
    if by['HOLD_START'].get('duration_s')!=contract['hold_duration_s'] or (by['HOLD_DONE']['monotonic_ns']-by['HOLD_START']['monotonic_ns'])/1e9<contract['hold_duration_s']:raise ValueError('source hold not completed')
    if by['KRITA_EXIT'].get('returncode')!=0:raise ValueError('Krita did not exit normally')


def verify_timed_events(events,contract):
    prepared=contract.get('prepared_document')
    tail=contract.get('tail_document')
    high_events=['HIGH_DOCUMENT_OPEN_START','HIGH_DOCUMENT_SUBMITTED','HIGH_DOCUMENT_OPEN_DONE']
    import_events=['LAYER_IMPORT_START','LAYER_IMPORT_SUBMITTED']
    restart_events=['HIGH_INSTANCE_EXIT','KRITA_POST_PROCESS']
    load_events=high_events if prepared else import_events
    names=['DOCUMENT_OPEN_START','DOCUMENT_OPEN_DONE','CANVAS_ZOOM_START','CANVAS_ZOOM_DONE',*load_events,
           'CAPTURE_WINDOW_START','CAPTURE_WINDOW_DONE','DOCUMENT_CLOSE_START','DOCUMENT_CLOSE_DONE','KRITA_EXIT']
    stages=[('PRE_IMPORT_REVIEW',load_events[0],'pre_import_review_s'),
            ('POST_CLOSE_REVIEW','KRITA_EXIT','post_close_review_s')]
    profile=contract.get('pressure_profile')
    review_events={label+'_'+suffix for label,_,_ in stages for suffix in ('START','DONE')}
    if profile:
        for label,before,_ in stages:
            index=names.index(before)
            names[index:index]=[label+'_START',label+'_DONE']
    if prepared:
        index=names.index('POST_CLOSE_REVIEW_START')
        names[index:index]=restart_events+(['TAIL_DOCUMENT_OPEN_DONE'] if tail else [])
    selected=set(names+high_events+import_events+restart_events)|review_events|{
        'LAYER_IMPORT_DONE','HOLD_START','HOLD_DONE','TAIL_DOCUMENT_OPEN_DONE'}
    records=[e for e in events if e.get('kind') in selected]
    if [e['kind'] for e in records]!=names:raise ValueError('missing/duplicate/out-of-order timed capture events')
    if any(b['monotonic_ns']<a['monotonic_ns'] for a,b in zip(records,records[1:])):raise ValueError('timed capture event time reversed')
    by={e['kind']:e for e in records}
    origin=by['HIGH_DOCUMENT_OPEN_DONE' if prepared else 'LAYER_IMPORT_SUBMITTED']['monotonic_ns']
    duration=contract['capture_window_s']
    if prepared:
        if any(by[kind].get('asset')!=prepared['path'] for kind in high_events):
            raise ValueError('prepared document path mismatch')
        if by['HIGH_DOCUMENT_OPEN_DONE'].get('verification')!='owned_document_title':
            raise ValueError('prepared document open evidence missing')
    else:
        for kind in import_events:
            if by[kind].get('import_count')!=contract['import_count']:raise ValueError('submitted file count mismatch')
        if by['LAYER_IMPORT_SUBMITTED'].get('verification')!='file_dialog_submission':raise ValueError('submission evidence missing')
    for kind in ['CAPTURE_WINDOW_START','CAPTURE_WINDOW_DONE']:
        e=by[kind]
        if e.get('origin_monotonic_ns')!=origin or e.get('duration_s')!=duration:raise ValueError('capture window origin/duration mismatch')
    if by['CAPTURE_WINDOW_DONE']['monotonic_ns']<origin+duration*1e9:raise ValueError('capture window ended early')
    if by['CAPTURE_WINDOW_DONE'].get('import_verified') is not False:raise ValueError('elapsed time cannot verify layer import')
    if profile:
        identities=[e['pid'] for e in events if e.get('kind')=='KRITA_PROCESS']
        if len(identities)!=1 or type(identities[0]) is not int or identities[0]<=0:
            raise ValueError('missing owned Krita process for three-stage review')
        post_pid=identities[0]
        if prepared:
            post_pid=by['KRITA_POST_PROCESS'].get('pid')
            high_exit=by['HIGH_INSTANCE_EXIT']
            if (type(post_pid) is not int or post_pid<=0 or post_pid==identities[0]
                or high_exit.get('pid')!=identities[0] or high_exit.get('returncode')!=0
                or by['KRITA_EXIT'].get('pid')!=post_pid):
                raise ValueError('prepared document instance exit/restart identity mismatch')
        if tail:
            opened=by['TAIL_DOCUMENT_OPEN_DONE']
            if (opened.get('asset')!=tail['path'] or opened.get('pid')!=post_pid
                or opened.get('verification')!='owned_document_title'):
                raise ValueError('tail document evidence mismatch')
        for label,_,key in stages:
            start,done=by[label+'_START'],by[label+'_DONE']
            review_s=profile[key]
            expected_pid=post_pid if label=='POST_CLOSE_REVIEW' else identities[0]
            if any(e.get('duration_s')!=review_s or e.get('pid')!=expected_pid for e in (start,done)):
                raise ValueError('review duration or Krita process mismatch')
            if done['monotonic_ns']-start['monotonic_ns']<round(review_s*1e9) or done.get('zoom_cycles',0)<2:
                raise ValueError('review ended early or lacks repeated zoom actions')
    if by['KRITA_EXIT'].get('returncode')!=0:raise ValueError('Krita did not exit normally')


def assess_pressure_profile(samples,events,contract,max_gap_s):
    """Check measured windows while the same Krita process remains alive."""
    profile=contract['pressure_profile']
    by={e.get('kind'):e for e in events}
    stamp=lambda kind:by[kind]['monotonic_ns']
    tail_range=contract.get('tail_charge_range_bytes')
    post_start=stamp('POST_CLOSE_REVIEW_START')
    if tail_range is None:
        release='HIGH_INSTANCE_EXIT' if 'prepared_document' in contract else 'DOCUMENT_CLOSE_DONE'
        post_start=max(post_start,stamp(release)+round(profile['post_close_settle_s']*1e9))
    windows={
        'pre_import':(stamp('PRE_IMPORT_REVIEW_START'),stamp('PRE_IMPORT_REVIEW_DONE')),
        'high':(stamp('HIGH_DOCUMENT_SUBMITTED' if 'prepared_document' in contract else 'LAYER_IMPORT_SUBMITTED'),
                stamp('CAPTURE_WINDOW_DONE')),
        'post_close':(post_start,stamp('POST_CLOSE_REVIEW_DONE')),
    }
    pid=by['KRITA_PROCESS']['pid']
    post_pid=by['KRITA_POST_PROCESS']['pid'] if 'prepared_document' in contract else pid
    out={name:dict(count=0,min_charge_bytes=None,max_charge_bytes=0,max_system_pressure_bytes=0,
                   max_swap_used_bytes=0,window_s=(end-start)/1e9)
         for name,(start,end) in windows.items()}
    missing_tail_samples=0
    for row in samples:
        if row['scope']!='krita':continue
        t=row['monotonic_ns']
        for name,(start,end) in windows.items():
            if not start<=t<=end:continue
            if row.get('krita_pid')!=(post_pid if name=='post_close' else pid):
                if name=='post_close':missing_tail_samples+=1
                continue
            window=out[name]
            charge=row['memory_current']
            if not window['count']:
                window['first_ns']=t
                window['min_charge_bytes']=charge
            window['last_ns']=t
            window['count']+=1
            window['min_charge_bytes']=min(window['min_charge_bytes'],charge)
            window['max_charge_bytes']=max(window['max_charge_bytes'],charge)
            window['max_system_pressure_bytes']=max(window['max_system_pressure_bytes'],
                                                   row['mem_total_bytes']-row['mem_available_bytes'])
            window['max_swap_used_bytes']=max(window['max_swap_used_bytes'],
                                             row['swap_total_bytes']-row['swap_free_bytes'])
    errors=[]
    gap_ns=round(max_gap_s*1e9)
    for name,(start,end) in windows.items():
        window=out[name]
        if (not window['count'] or window['first_ns']-start>gap_ns or end-window['last_ns']>gap_ns):
            errors.append('incomplete live Krita samples: '+name)
    reference=profile['peak_reference_bytes']
    tolerance=profile['peak_tolerance_fraction']
    if abs(out['high']['max_charge_bytes']-reference)>reference*tolerance:
        errors.append('high-phase charge peak outside reference tolerance')
    for name in ('pre_import','post_close'):
        if (out[name]['max_charge_bytes']>profile['max_low_charge_bytes']
            or out[name]['max_system_pressure_bytes']>profile['max_low_pressure_bytes']):
            errors.append('low-pressure bound exceeded: '+name)
    if tail_range:
        tail=out['post_close']
        if missing_tail_samples:
            errors.append('tail review contains samples without the expected Krita process')
        if (tail['count'] and
            (tail['min_charge_bytes']<tail_range[0] or tail['max_charge_bytes']>tail_range[1])):
            errors.append('tail review charge outside the configured range')
        tail.update(charge_range_bytes=tail_range,missing_process_samples=missing_tail_samples)
    return dict(valid=not errors,errors=errors,windows=out,pid=pid,post_pid=post_pid)
