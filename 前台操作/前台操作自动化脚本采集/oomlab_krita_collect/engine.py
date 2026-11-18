import csv
import copy
import json
import os
import sys
import time
import uuid
from pathlib import Path
from .common import ROOT,GUI,BACKGROUND,save,load,fresh,fingerprint,SCHEMA
from .metrics import FIELDS,snapshot,deltas,process_sample
from .environment import controls,conflicts
from .units import Unit,members,process_cgroup


def background():
    if str(BACKGROUND) not in sys.path:sys.path.insert(0,str(BACKGROUND))
    from oomlab import workloads
    return workloads


def recipe(operation,c,data=None,profile_name=None):
    if operation=='krita':
        cmd=[sys.executable,'-u',str(GUI/'scripts/krita_auto.py'),c['asset']['path']]
        if c.get('mode')=='pilot':cmd+=['--layers-dir',c['pilot']['layers_dir'],'--settings','{run_root}/config.snapshot.json','--assets-manifest','{run_root}/assets_manifest.json','--control-file','{run_root}/stop-request.json','--process-record','{run_output}/krita-process.json']
        return dict(operation=operation,command=cmd,asset=c['asset'])
    if operation=='smoke':return dict(operation=operation,command=['/usr/bin/sleep','0.2'],classification='TEST_ONLY')
    background()
    from oomlab.common import profile
    parameters=profile(BACKGROUND/'configs/profiles.json',operation,profile_name)
    manifest=background().validate_input(data,operation,parameters)
    return dict(operation=operation,command=[sys.executable,'-m','oomlab.workloads',str(Path(data).resolve()),'{run_output}'],
                data=str(Path(data).resolve()),profile=profile_name,parameters=parameters,input_manifest=manifest)


def directory_state(path):
    return {str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in Path(path).iterdir() if p.is_file()}


def wait_file(path,timeout=30):
    end=time.monotonic()+timeout
    while not Path(path).is_file():
        if time.monotonic()>end: raise TimeoutError('worker gate timeout: '+str(path))
        time.sleep(.02)
    return load(path)


def enforce(row,safety,include_psi=True):
    if row.get('freeze_requested')!=0 or row.get('frozen')!=0:raise RuntimeError('freezer action or missing freezer state; no-policy baseline refused')
    for key,threshold,greater in [('memory_current','max_cgroup_bytes',True),('memory_peak','max_cgroup_bytes',True),
                                 ('mem_available_bytes','min_available_bytes',False),('swap_free_bytes','min_swap_free_bytes',False),
                                 ('global_psi_full_avg10','max_global_full_avg10',True)]:
        if not include_psi and key=='global_psi_full_avg10':continue
        value=row.get(key)
        if value is None or (value>=safety[threshold] if greater else value<safety[threshold]):
            raise RuntimeError('safety threshold/required capability: '+key)


def cooldown_usage(row,timed=False):
    if not timed:return row['memory_current']
    # After owned workloads exit, clean file cache can legitimately remain
    # charged to the slice. Keep anon, shmem, dirty/writeback and kernel usage.
    clean=max(0,(row.get('stat_file') or 0)-sum(row.get(k) or 0 for k in ('stat_shmem','stat_file_dirty','stat_file_writeback')))
    return max(0,row['memory_current']-clean)+(row.get('swap_current') or 0)


def cool(path,c,run,classification):
    s=c['safety'];deadline=time.monotonic()+s['cooldown_timeout_s'];stable=None
    timed=c.get('automation',{}).get('completion_mode')=='timed_window'
    hold_pid=load(run/'hold/unit-identity.json')['pid'] if timed else None
    with open(run/'cooldown.jsonl','w',buffering=1) as f:
        while True:
            row=snapshot(path,time.monotonic_ns(),'cooldown');row['classification']=classification
            if timed and members(path)!={hold_pid}:raise RuntimeError('unexpected process remains in cooldown boundary')
            usage=cooldown_usage(row,timed) if row['memory_current'] is not None else None
            row.update(cooldown_usage_bytes=usage,cooldown_metric='current-minus-clean-file-cache-plus-swap' if timed else 'memory.current')
            f.write(json.dumps(row)+'\n')
            ok=(usage is not None and usage<=s['cooldown_cgroup_bytes'] and
                row['mem_available_bytes'] is not None and row['mem_available_bytes']>=s['cooldown_min_available_bytes'] and
                row['global_psi_full_avg10'] is not None and row['global_psi_full_avg10']<=s['cooldown_max_full_avg10'])
            now=time.monotonic();stable=now if ok and stable is None else stable if ok else None
            if stable is not None and now-stable>=s['cooldown_stable_s']:return dict(ok=True,final=row)
            if now>=deadline:raise TimeoutError('cooldown metrics did not recover; stop session')
            time.sleep(min(.5,c['interval_s']))


def parent_identity(hold,slice_name):
    from .common import command
    parent=hold.path.parent
    prop=command(['systemctl','--user','show',slice_name,'--property=Id,ControlGroup']).stdout
    status=dict(l.split('=',1) for l in prop.splitlines() if '=' in l)
    if status.get('Id')!=slice_name or not status.get('ControlGroup') or str(Path('/sys/fs/cgroup')/status['ControlGroup'].lstrip('/'))!=str(parent):
        raise RuntimeError('parent slice membership not proven')
    return parent,status


def run_one(session,c,recipes,environment,offsets=None,test_only=False):
    pilot=c.get('mode')=='pilot' and not test_only
    if pilot and (set(recipes)!={'krita'} or offsets):raise ValueError('PILOT only permits one Krita operation, without offsets')
    run=fresh(Path(session)/uuid.uuid4().hex); token=run.name;slice_name='oomcollect-'+token+'.slice'
    jobs={};all_units=[];parent=None;start={};end={};origin=time.monotonic_ns();cleanup=[]
    meta=dict(metric_units={'memory':'bytes','time':'monotonic_ns','relative_time':'seconds'},classification='TEST_ONLY' if test_only else 'PILOT' if pilot else 'FORMAL',run_id=token,strategy='none',recipes=recipes,
              offsets=offsets or {k:0 for k in recipes},interval_s=c['interval_s'],config=c,source=environment.get('source'),
              success=False,error=None,cleanup_ok=False,cooldown_ok=False,operations_verified=False)
    save(run/'config.snapshot.json',c)
    save(run/'metadata.json',meta);save(run/'environment.json',dict(environment,classification=meta['classification']))
    (run/'automation.log').write_text('# schema_version=1\n')
    (run/'phase-events.jsonl').write_text(json.dumps(dict(schema_version=SCHEMA,event='stream_open',monotonic_ns=time.monotonic_ns()))+'\n')
    with open(run/'samples.csv','w',newline='') as f:csv.DictWriter(f,FIELDS).writeheader()
    journal_ok=True;hold=None;last_inventory=0;meta['krita_xcb_verified']=False
    indexes={};previous={};pressure_since={};last_events={};paths={};launched=False
    (run/'memory-events.jsonl').touch();(run/'cgroup-observations.jsonl').touch();(run/'process-observations.jsonl').touch()
    def sample_rows(writer,check_safety=True):
        for scope,path in paths.items():
            row=snapshot(path,origin,scope);row.update(classification=meta['classification'],sample_index=indexes.get(scope,0))
            if pilot and scope=='krita':
                post=jobs[scope].run/'krita-post-process.json'
                record=post if c['automation'].get('prepared_document') and post.is_file() else jobs[scope].run/'krita-process.json'
                row.update(process_sample(record,jobs[scope].cg,row['monotonic_ns'],previous.get(scope)))
            flat={k:row.get(k) if row.get(k) is not None else 'null' for k in FIELDS};flat['vmstat_json']=json.dumps(row['vmstat']);flat['capabilities_json']=json.dumps(row['capabilities'])
            writer.writerow(flat);indexes[scope]=row['sample_index']+1
            counters={k:v for k,v in row.items() if k.startswith(('event_','local_event_'))}
            if counters!=last_events.get(scope):
                with open(run/'memory-events.jsonl','a') as ev:ev.write(json.dumps(dict(schema_version=SCHEMA,scope=scope,monotonic_ns=row['monotonic_ns'],relative_s=row['relative_s'],counters=counters))+'\n')
                last_events[scope]=counters
            old=previous.get(scope);previous[scope]=row
            if not check_safety:continue
            enforce(row,c['safety'],include_psi=not pilot)
            delta=deltas(start[scope],row)
            if any(delta.get('event_'+key)!=0 for key in ('max','oom','oom_kill','oom_group_kill')) or delta.get('vmstat',{}).get('oom_kill')!=0:raise RuntimeError('OOM/limit counters changed or missing')
            if pilot:
                if old and (row['monotonic_ns']-old['monotonic_ns'])/1e9>c['safety']['max_sample_gap_s']:raise RuntimeError('50ms sampler gap exceeded safety bound')
                sustained_pressure(row,c,pressure_since,scope)
    try:
        if pilot:
            from .pilot_assets import inventory
            assets=inventory(c)
            if assets!=environment.get('assets_manifest'):raise ValueError('assets changed after preflight; refusing launch')
            save(run/'assets_manifest.json',assets)
        save(run/'config.snapshot.json',c)
        if not test_only:
            meta['asset_before']=fingerprint(c['asset']['path'])
            meta['asset_directory_before']=directory_state(Path(c['asset']['path']).parent)
            if (c['asset']['sha256'] is not None and meta['asset_before']['sha256']!=c['asset']['sha256']) or any(meta['asset_before'][k]!=environment.get('asset',{}).get(k) for k in meta['asset_before']):
                raise ValueError('ORA changed after preflight; refusing launch')
        hold_run=fresh(run/'hold');hold=Unit('oomcollect-'+token+'-hold.service',hold_run,slice_name);all_units.append(hold)
        hold.start(hold=True,timeout_s=c['safety']['run_timeout_s']+c['safety']['cooldown_timeout_s']+180,stop_timeout_s=c['automation']['graceful_stop_timeout_s'] if pilot else 10);wait_file(hold_run/'ready.json');hold.bind()
        parent,status=parent_identity(hold,slice_name)
        meta['parent_cgroup']=str(parent);meta['parent_properties']=status
        controls(parent)
        for op,spec in recipes.items():
            if op in ('xz','table','array_processing') and not test_only and background().validate_input(spec['data'],op,spec['parameters'])!=spec['input_manifest']:
                raise ValueError('background input changed since single-operation preparation')
            target=fresh(run/op);cmd=[x.replace('{run_output}',str(target)).replace('{run_root}',str(run)) for x in spec['command']]
            save(target/'command.json',dict(command=cmd,recipe=spec,classification=meta['classification']))
            unit=Unit('oomcollect-'+token+'-'+op+'.service',target,slice_name);all_units.append(unit);jobs[op]=unit
            unit.start(timeout_s=c['safety']['run_timeout_s']+c['safety']['cooldown_timeout_s']+180,stop_timeout_s=c['automation']['graceful_stop_timeout_s'] if pilot else 10);wait_file(target/'ready.json');unit.bind();controls(unit.path)
            if unit.path.parent!=parent:raise RuntimeError('child is outside measured parent')
        collector_group=process_cgroup(os.getpid())
        if collector_group==status['ControlGroup'] or collector_group.startswith(status['ControlGroup']+'/'):raise RuntimeError('collector is inside measured parent')
        save(run/'boundary.json',dict(collector_pid=os.getpid(),collector_cgroup=collector_group,parent=str(parent),workloads={op:dict(cgroup=str(u.path),supervisor_pid=u.pid) for op,u in jobs.items()},accounting='workload includes Krita, automation, supervisor and spawned helpers; parent adds hold supervisor; collector excluded; shared desktop services excluded'))
        save(run/'metadata.json',meta)
        print(json.dumps(dict(schema_version=SCHEMA,classification=meta['classification'],event='measurement_boundary_ready',parent=str(parent),children={op:str(u.path) for op,u in jobs.items()})),flush=True)
        origin=time.monotonic_ns()+300_000_000
        paths={'parent':parent,**{op:u.path for op,u in jobs.items()}}
        start={op:dict(snapshot(p,origin,op),classification=meta['classification']) for op,p in paths.items()};save(run/'cgroup-start.json',dict(scopes=start,boundaries=boundary_evidence(paths),classification=meta['classification']))
        for scope,row in start.items():
            enforce(row,c['safety'])
            if any(deltas(row,row).get('event_'+key)!=0 for key in ('max','oom','oom_kill','oom_group_kill')):raise RuntimeError('required event capability missing before launch')
        for op,u in jobs.items():save(u.run/'go.json',dict(start_monotonic_ns=origin+int(meta['offsets'][op]*1e9)))
        launched=True
        next_tick=origin;deadline=time.monotonic()+c['safety']['run_timeout_s']
        with open(run/'samples.csv','a',newline='') as f:
            writer=csv.DictWriter(f,FIELDS)
            while True:
                delay=(next_tick-time.monotonic_ns())/1e9
                if delay>0:time.sleep(delay)
                sample_rows(writer)
                f.flush()
                if time.monotonic()-last_inventory>=.2:
                    with open(run/'cgroup-observations.jsonl','a') as boundary_log:boundary_log.write(json.dumps(dict(schema_version=SCHEMA,monotonic_ns=time.monotonic_ns(),boundaries=boundary_evidence(paths)))+'\n')
                    with open(run/'process-observations.jsonl','a') as observations:
                        for op,u in jobs.items():
                            for member in u.check_members():
                                if Path(member.get('exe','')).name.lower()=='krita':
                                    try:
                                        maps=(Path('/proc')/str(member['pid'])/'maps').read_text()
                                        plugins=sorted({line.split()[-1] for line in maps.splitlines() if 'libqxcb.so' in line or 'libqwayland' in line})
                                        member['qt_plugins']=plugins
                                        if any(Path(p).name=='libqxcb.so' for p in plugins) and not any('libqwayland' in p for p in plugins):meta['krita_xcb_verified']=True
                                    except (FileNotFoundError,ProcessLookupError):continue
                                member['role']='krita' if Path(member.get('exe','')).name.lower()=='krita' else 'supervisor' if member['pid']==u.pid else 'automation_or_helper'
                                observations.write(json.dumps(dict(schema_version=SCHEMA,scope=op,monotonic_ns=time.monotonic_ns(),process=member))+'\n')
                    last_inventory=time.monotonic()
                if all((u.run/'finished.json').exists() for u in jobs.values()):
                    if pilot:sample_rows(writer);f.flush()
                    break
                if time.monotonic()>deadline:raise TimeoutError('workload deadline exceeded')
                next_tick=max(next_tick+int(c['interval_s']*1e9),time.monotonic_ns()+1)
        meta['finishes']={op:load(u.run/'finished.json') for op,u in jobs.items()}
        identity={op:u.check_members() for op,u in jobs.items()};save(run/'remaining-processes.json',dict(scopes=identity))
        for op,u in jobs.items():
            result=meta['finishes'][op]
            if result['returncode']!=0 or result['error']:raise RuntimeError('automation/workload exit failed: '+op)
            if {p['pid'] for p in identity[op]}!={u.pid}:raise RuntimeError('workload descendants remain: '+op)
            if op in ('xz','table','array_processing') and not test_only:
                background().verify(recipes[op]['data'],u.run)
                if background().validate_input(recipes[op]['data'],op,recipes[op]['parameters'])!=recipes[op]['input_manifest']:raise ValueError('background input changed')
        expected_pids={hold.pid}|{u.pid for u in jobs.values()}
        if members(parent)!=expected_pids:raise RuntimeError('unexpected process remains in parent boundary')
        if pilot:
            records=['krita-process.json']
            if c['automation'].get('prepared_document'):records.append('krita-post-process.json')
            for name in records:
                process=load(jobs['krita'].run/name)
                if process['ppid']!=load(jobs['krita'].run/'workload-pid.json')['pid']:raise RuntimeError('Krita PPID does not match automation process')
                if process['cgroup']!='0::'+jobs['krita'].cg:raise RuntimeError('recorded Krita cgroup mismatch')
        meta['operations_verified']=True
    except (Exception,KeyboardInterrupt) as e:
        meta['error']=type(e).__name__+': '+str(e)
        if pilot and launched:
            meta.update(cooperative_stop(run,jobs,c,meta['error'],previous,sample_rows))
    finally:
        meta['origin_monotonic_ns']=origin
        for scope,path in [('parent',parent)]+[(op,u.path) for op,u in jobs.items()]:
            if path is not None:
                try:end[scope]=dict(snapshot(path,origin,scope),classification=meta['classification'])
                except Exception as e:meta.setdefault('evidence_errors',[]).append('final snapshot '+scope+': '+repr(e))
        if not (run/'cgroup-start.json').exists():save(run/'cgroup-start.json',dict(scopes=start,classification=meta['classification']))
        save(run/'cgroup-end.json',dict(scopes=end,boundaries=boundary_evidence({scope:path for scope,path in [('parent',parent)]+[(op,u.path) for op,u in jobs.items()] if path is not None}),classification=meta['classification']))
        if pilot and meta.get('error'):
            # Grace expired or automation failed. Terminal kernel evidence is saved
            # above; stop exact owned units before costly post-run asset hashing.
            for u in jobs.values():
                try:cleanup.append(dict(unit=u.unit,**u.stop()))
                except Exception as e:cleanup.append(dict(unit=u.unit,ok=False,error=repr(e)))
        if not test_only:
            try:
                from .common import source_identity
                if source_identity()!=environment.get('source'):raise ValueError('source changed during operation')
                if pilot:
                    after=inventory(c);save(run/'assets_manifest.after.json',after)
                    if after!=locals().get('assets'):raise ValueError('PILOT ORA/PNG hashes or directory entries changed')
                    meta['assets_unchanged']=True
                meta['asset_after']=fingerprint(c['asset']['path'])
                meta['asset_directory_after']=directory_state(Path(c['asset']['path']).parent)
                if meta['asset_directory_after']!=meta['asset_directory_before']:raise ValueError('asset directory files changed; possible save/autosave')
                if meta['asset_after']!=meta.get('asset_before'):raise ValueError('ORA SHA256/size/mtime changed')
            except Exception as e:
                meta['error']=meta.get('error') or repr(e)
                meta.setdefault('evidence_errors',[]).append('post-run identity/asset audit: '+repr(e))
        with open(run/'automation.log','a') as log,open(run/'phase-events.jsonl','a') as phases,open(run/'journal.log','w') as journal:
            journal.write('# schema_version=1\n')
            for op,u in jobs.items():
                for filename,out in [('automation.log',log),('phase-events.jsonl',phases)]:
                    path=u.run/filename
                    if path.exists():
                        if filename=='automation.log':out.write('\n# operation='+op+'\n')
                        out.write(path.read_text())
                try:
                    from .common import command
                    p=command(['journalctl','--user','--unit='+u.unit,'--no-pager','-o','short-iso'])
                    journal.write('\n# unit='+u.unit+'\n'+p.stdout+p.stderr)
                except Exception as e:journal_ok=False;journal.write(repr(e)+'\n')
        # Persist terminal evidence before stopping any measurement-boundary unit.
        save(run/'metadata.json',meta)
        for u in list(jobs.values())[::-1]:
            if any(record['unit']==u.unit and record.get('ok') for record in cleanup):continue
            try:cleanup.append(dict(unit=u.unit,**u.stop()))
            except Exception as e:cleanup.append(dict(unit=u.unit,ok=False,error=repr(e)))
        if parent is not None and all(x['ok'] for x in cleanup):
            try:meta['cooldown']=cool(parent,c,run,meta['classification']);meta['cooldown_ok']=True
            except Exception as e:meta['error']=meta.get('error') or repr(e)
        if hold:
            try:cleanup.append(dict(unit=hold.unit,**hold.stop()))
            except Exception as e:cleanup.append(dict(unit=hold.unit,ok=False,error=repr(e)))
        # Stop only the exact UUID slice whose ControlGroup was proved above.
        if parent is not None and all(x['ok'] for x in cleanup):
            try:
                from .common import command
                p=command(['systemctl','--user','show',slice_name,'--property=Id,ControlGroup,ActiveState']).stdout
                status=dict(l.split('=',1) for l in p.splitlines() if '=' in l)
                if status.get('Id')!=slice_name or status.get('ControlGroup') not in ('',meta['parent_properties']['ControlGroup']):raise RuntimeError('slice ownership changed')
                command(['systemctl','--user','stop',slice_name]);cleanup.append(dict(unit=slice_name,ok=not parent.exists() or not members(parent)))
            except Exception as e:cleanup.append(dict(unit=slice_name,ok=False,error=repr(e)))
        meta.update(cleanup_ok=bool(cleanup) and all(x['ok'] for x in cleanup),journal_ok=journal_ok,
                    end_monotonic_ns=time.monotonic_ns(),end_wall_time_ns=time.time_ns(),cleanup=cleanup)
        save(run/'cleanup.json',dict(records=cleanup,classification=meta['classification']));save(run/'metadata.json',meta)
        from .validation import validate_run
        summary=validate_run(run,verify_manifest=False)
        meta['success']=summary['valid'];save(run/'metadata.json',meta)
        save(run/'summary.json',summary)
        if pilot:
            from .pilot_report import write_report
            write_report(run,summary)
        from .common import seal
        seal(run)
    return run,summary


def boundary_evidence(paths):
    data={}
    for scope,path in paths.items():
        try:data[scope]=dict(cgroup_procs=sorted(members(path)),sub_cgroups=sorted(str(p.parent.relative_to(path)) for p in Path(path).rglob('cgroup.procs') if p.parent!=Path(path)))
        except (OSError,ValueError) as e:data[scope]=dict(error=repr(e))
    return data


def sustained_pressure(row,c,since,scope):
    full=row.get('global_psi_full_avg10')
    if full is None:raise RuntimeError('global PSI capability missing')
    if full>=c['safety']['max_global_full_avg10']:
        since.setdefault(scope,row['monotonic_ns'])
        if (row['monotonic_ns']-since[scope])/1e9>=c['pilot']['psi_full_sustained_s']:raise RuntimeError('sustained severe global memory PSI full')
    else:since.pop(scope,None)


def cooperative_stop(run,jobs,c,reason,previous,sampler):
    """Notify owned automation, append to existing raw stream, never restart it."""
    phase=None;diagnostics=[]
    try:
        from .phases import observe
        for line in (jobs['krita'].run/'automation.log').read_text().splitlines():
            event=observe(line,time.monotonic_ns(),time.time_ns())
            if event.get('phase'):phase=event['phase']
    except (OSError,KeyError):pass
    stop=dict(reason=reason,phase=phase,monotonic_ns=time.monotonic_ns(),wall_time_ns=time.time_ns(),last_samples=copy.deepcopy(previous))
    if (run/'stop-request.json').exists():
        try:stop['previous_request']=load(run/'stop-request.json')
        except (OSError,ValueError):pass
    save(run/'stop-request.json',stop)
    until=time.monotonic()+c['pilot']['graceful_stop_timeout_s']
    with open(run/'samples.csv','a',newline='') as f:
        writer=csv.DictWriter(f,FIELDS)
        while time.monotonic()<until and not all((u.run/'finished.json').exists() for u in jobs.values()):
            try:sampler(writer,check_safety=False);f.flush()
            except Exception as error:diagnostics.append('grace sampler: '+repr(error));break
            time.sleep(c['interval_s'])
    result=dict(safety_stop=stop,cooperative_worker_completed=all((u.run/'finished.json').exists() for u in jobs.values()))
    if diagnostics:result['evidence_errors']=diagnostics
    return result
