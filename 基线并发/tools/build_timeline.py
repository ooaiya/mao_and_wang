#!/usr/bin/env python3
"""Generate the shared homepage-origin provisional plan and original Oracle inputs.

The historical homepage event is missing. Its feasible bracket is inferred from
Krita process creation and the later completed-blank-canvas mark, never invented
as an observed timestamp. No workload curve is time-warped.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import numpy as np


def load_events(path):return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def build(analysis_root,repo,homepage_to_import_s=None):
    analysis=analysis_root/'final_analysis';rows=list(csv.DictReader((analysis/'operation_round_metrics.csv').open()))
    npz=np.load(analysis/'profiles.npz');metadata=json.loads((analysis/'profile_metadata.json').read_text())
    kp=next(analysis_root.glob('Krita_Manual_1Round/Krita_Manual_1Round/extracted/*/samples.csv'))
    km=json.loads((kp.parent/'metadata.json').read_text());ev=load_events(kp.parent/'phase-events.jsonl')
    imported=next(x['monotonic_ns'] for x in ev if x.get('label')=='开始批量导入图层')
    blank=next(x['monotonic_ns'] for x in ev if x.get('label')=='打开空白画布完成')
    started=km['krita']['monotonic_ns']
    bounds=((imported-blank)/1e9,(imported-started)/1e9)
    inferred_bounds=bounds
    if homepage_to_import_s is not None:
        if not math.isfinite(homepage_to_import_s) or not 0<=homepage_to_import_s<=1800:
            raise ValueError('calibration delay must be finite and within 0..1800 seconds')
        bounds=(homepage_to_import_s,homepage_to_import_s)
    # Cover Table's hot/cold peak-time dispersion with XZ/Array's broad
    # individual high-memory platforms, rather than aligning four single maxima.
    selected={o:[r for r in rows if r['operation']==o and r['selected']=='True'] for o in ['XZ','Table','Array']}
    common={o:(max(float(r['peak_window_start_s']) for r in values),min(float(r['peak_window_end_s']) for r in values)) for o,values in selected.items() if o!='Table'}
    table_min=min(float(r['peak_time_s']) for r in selected['Table'])
    table_max=max(float(r['peak_time_s']) for r in selected['Table'])
    latest=float(npz['Krita_t'][-1])+bounds[0]-1.0
    table_start=math.floor((latest-table_max)/.05)*.05
    offsets={'foreground_krita':0.0,'table':round(table_start,2)}
    for op in ['XZ','Array']:
        left=table_start+table_max-common[op][1]
        right=table_start+table_min-common[op][0]
        if left>right:raise ValueError(op+' high-memory platform cannot cover all measured Table peak times')
        chosen=left+min(.5,(right-left)/2) if op=='XZ' else (left+right)/2
        offsets[op.lower()]=round(chosen/.05)*.05
        offsets[op.lower()]=round(offsets[op.lower()],2)
    delta=np.unique(np.r_[np.arange(bounds[0],bounds[1]+.001,.05),bounds[1]])
    limits=[(offsets[op.lower()]+float(npz[op+'_t'][0]),offsets[op.lower()]+float(npz[op+'_t'][-1])) for op in ['XZ','Table','Array']]
    lo=max([x[0] for x in limits]+[float(npz['Krita_t'][0])+bounds[1]])
    hi=min([x[1] for x in limits]+[float(npz['Krita_t'][-1])+bounds[0]])
    grid=np.arange(math.ceil(lo/.05)*.05,hi+1e-6,.05)
    foreground=np.interp(grid[:,None]-delta[None,:],npz['Krita_t'],npz['Krita_m'])
    parts={op:np.interp(grid-offsets[op.lower()],npz[op+'_t'],npz[op+'_m']) for op in ['XZ','Table','Array']}
    total=foreground.min(axis=1)+sum(parts.values());index=int(total.argmax());target=float(grid[index]);taskpeak=float(total[index])
    high=foreground.min(axis=1)>=.95*float(npz['Krita_m'].max())
    for op in parts:high &= parts[op]>=.95*float(npz[op+'_m'].max())
    transitions=np.diff(np.r_[False,high,False].astype(int))
    high_windows=[(float(grid[a]),float(grid[b-1])) for a,b in zip(np.flatnonzero(transitions==1),np.flatnonzero(transitions==-1))]
    overlap=sum(b-a for a,b in high_windows)
    curves={}
    for op,values in selected.items():
        for r in values:
            start_ns=int(r['start_monotonic_ns']);end_ns=int(r['end_monotonic_ns'])
            with open(r['source']) as h:sample=[v for v in csv.DictReader(h) if start_ns<=int(v['monotonic_ns'])<=end_ns]
            curves[r['round_id']]=(np.array([(int(v['monotonic_ns'])-start_ns)/1e9 for v in sample]),np.array([int(v['memory_current']) for v in sample]))
    import itertools
    combinations=[]
    for xz,table,array in itertools.product(selected['XZ'],selected['Table'],selected['Array']):
        at=offsets['table']+float(table['peak_time_s']);ratios={};supported=True
        fore_values=np.interp(at-delta,npz['Krita_t'],npz['Krita_m']);ratios['Krita']=float(fore_values.min()/float(npz['Krita_m'].max()))
        for op,r in [('XZ',xz),('Array',array)]:
            t,m=curves[r['round_id']];age=at-offsets[op.lower()];supported &= bool(t[0]<=age<=t[-1]);ratios[op]=float(np.interp(age,t,m)/int(r['sampled_peak_bytes']))
        charge=float(fore_values.min()+np.interp(at-offsets['xz'],*curves[xz['round_id']])+np.interp(at-offsets['array'],*curves[array['round_id']])+int(table['sampled_peak_bytes']))
        combinations.append(dict(task_charge_bytes=charge,XZ_run=xz['round_id'],Table_run=table['round_id'],Array_run=array['round_id'],Table_peak_homepage_s=at,all_running_supported=supported,Krita_min_peak_fraction=ratios['Krita'],XZ_peak_fraction=ratios['XZ'],Array_peak_fraction=ratios['Array'],all_four_at_least_95pct=supported and min(ratios.values())>=.95))
    if not all(r['all_four_at_least_95pct'] for r in combinations):raise ValueError('round-combination high-memory overlap check failed')
    with (repo/'基线并发/profiles/analysis/homepage_round_combination_validation.csv').open('w') as h:
        w=csv.DictWriter(h,fieldnames=list(combinations[0]));w.writeheader();w.writerows(combinations)
    version=hashlib.sha256(json.dumps({'sources':[(r['operation'],r['round_id'],r['source_sha256'],r['selected']) for r in rows],'homepage_bracket_s':bounds,'offsets_s':offsets,'grid_s':.05,'alignment_policy':'cover_all_Table_peak_times_with_per_round_XZ_Array_95pct_platforms_v4'},sort_keys=True).encode()).hexdigest()
    schedule=[dict(operation=o,type='foreground' if o=='foreground_krita' else 'background',start_offset_s=offsets[o]) for o in sorted(offsets,key=offsets.get)]
    plan={'schema_version':4,'status':'INITIAL_DEPLOYMENT_PROVISIONAL_HOMEPAGE_CALIBRATION_REQUIRED','T0_event':'homepage_ready',
        'T0_definition':'Krita main homepage visibly loaded and interactive; auto read-only AT-SPI evidence or explicit homepage-ready confirmation. Never process start, first input, or import trigger.',
        'data_version_sha256':version,'samples':{'foreground_krita':1,'xz':3,'table':10,'array':9},'array_excluded_run':'9d3859de4be24a28936d0cc6287f38ec','array_exclusion_basis':'explicit user instruction in this session; retain 10-round sensitivity',
        'historical_import_origin_monotonic_ns':imported,'historical_homepage_ready_monotonic_ns':None,
        'historical_homepage_to_import_inferred_bounds_s':list(inferred_bounds),'planning_homepage_to_import_bounds_s':list(bounds),'historical_homepage_to_import_assumption_s':statistics.mean(bounds),
        'homepage_to_import_calibration_override_s':homepage_to_import_s,
        'homepage_bracket_assumption':'homepage readiness is after process creation and before the manually marked completed blank canvas; bracket is inferred, not measured',
        'runtime_gui_input_correlation':'deferred by user for initial deployment; operator import-start marker recorded but does not reschedule backgrounds',
        'schedule':schedule,'reference_peak_target_from_homepage_s':target,'reference_four_task_charge_lower_over_homepage_bracket_bytes':taskpeak,
        'four_mean_curves_95pct_overlap_reference_s':overlap,'four_mean_curves_95pct_intervals_homepage_s':high_windows,'round_combinations_validated':len(combinations),'round_combinations_all_four_95pct_at_Table_peak':sum(r['all_four_at_least_95pct'] for r in combinations),'historical_VM_MemTotal_bytes':16719261696,'current_VM_MemTotal_bytes':None,'system_idle_without_tasks_bytes':None,'absolute_130pct_achieved':None,
        'memory_scope':'same-time independent task cgroup charge reference; not actual concurrent physical memory. System idle/prepared initial charges must be added once, swap separately.',
        'optimization':'50ms grid; place every measured Table peak time inside the common per-round XZ/Array >=95% platforms and Krita >=95% plateau over the full inferred homepage bracket; keep 1s earliest-end guard. No duration changes or post-end extrapolation.',
        'limitations':['Krita n=1','homepage event missing from historic trace; true offset is not known','Table has hot/cold timing modes; not every individual maximum coincides','actual manual pacing and concurrent I/O/CPU can change operation timing','historical curve window overlap is a hypothesis to verify in first run, not a zero-overlap statement or a runtime guarantee'],
        'manual_frontend_end':'explicit done marker; Krita process exit is not task_end','steady_clock':'CLOCK_MONOTONIC','high_memory_fraction':.95}
    plan['profile_overlap_contract']={
        'definition':'Each measured Table peak sample falls inside all three other operations >=95% sampled-peak platforms over the inferred homepage bracket; offline, not a runtime guarantee',
        'minimum_peak_fractions':{op:min(r[key] for r in combinations) for op,key in [('Krita','Krita_min_peak_fraction'),('XZ','XZ_peak_fraction'),('Array','Array_peak_fraction')]},
        'combinations':len(combinations),'validated':all(r['all_four_at_least_95pct'] for r in combinations),
        'task_charge_at_Table_peaks_min_bytes':min(r['task_charge_bytes'] for r in combinations),
        'task_charge_at_Table_peaks_max_bytes':max(r['task_charge_bytes'] for r in combinations)}
    plan['kernel_interface_reference']='docs/kernel-6.17.13-oomlab-reference.md: user reports cgroup-v2 rw and frozen0->1->0 on 6.17.13-oomlab; deployment scope/permissions rechecked at actual run'
    (repo/'基线并发/baseline_timeline_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    # Fixed offline freezes at each operation's first 10% growth point. Memory at
    # the freeze point is retained in the model, never replaced with zero.
    events=[];freeze_state={}
    for op in ['xz','array','table']:
        label={'xz':'XZ','array':'Array','table':'Table'}[op];t=npz[label+'_t'];m=npz[label+'_m'];initial=metadata[label]['initial'];threshold=initial+.1*(float(m.max())-initial)
        crossing=float(t[np.flatnonzero(m>=threshold)[0]]);freeze_age=max(.05,math.floor(max(.05,crossing-.1)/.05)*.05)
        at=offsets[op]+freeze_age;freeze_state[op]=(freeze_age,float(np.interp(freeze_age,t,m)))
        events.append(dict(operation=op,action='freeze',offset_ms=round(at*1000),reason='before first 10% growth crossing from selected historical curve',expected_memory_state={'operation_age_s':freeze_age,'retained_current_bytes':freeze_state[op][1]},source_curve=label,schedule_version=version))
    resume=math.ceil((bounds[1]+float(km['krita_exit']['monotonic_ns']-imported)/1e9+2)*20)/20
    # Historical post-import release is an observation, not a normal-end guarantee.
    for op in ['xz','array','table']:
        label={'xz':'XZ','array':'Array','table':'Table'}[op]
        events.append(dict(operation=op,action='resume',offset_ms=round(resume*1000),reason='offline serialized recovery after historical late memory-release observation plus 2s; actual release is not guaranteed',expected_memory_state={'frozen_memory_is_not_freed':True,'foreground_release_verified_at_runtime':False},source_curve=label,schedule_version=version))
        duration=max(float(r['duration_s']) for r in rows if r['operation']==label and r['selected']=='True')
        resume+=duration-freeze_state[op][0]+2
    freeze={'schema_version':4,'timeline_data_version':version,'events':sorted(events,key=lambda x:x['offset_ms']),
        'runtime_decisions':'none; execute fixed absolute timestamps only; memory and PSI are recorded, never consulted for timing',
        'model_limits':['freezing retains preallocated memory','Krita remains alive after manual done, so no memory release is inferred from task_end','resume anchor uses historical later release after process -9; not proof of normal release or OOM avoidance','single-operation cold runtime and post-end file-cache persistence can delay serial recovery; this plan requires target-VM qualification'],
        'OOM_avoidance_proven':False}
    (repo/'冻结并发/freeze_schedule.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2))
    # Original v1 Oracle contract: total anonymous memory envelope, 500ms grid.
    oracle=repo/'基线并发/profiles/oracle';oracle.mkdir(exist_ok=True)
    model_audit=[]
    for op in ['XZ','Table','Array']:
        selected=[r for r in rows if r['operation']==op and r['selected']=='True'];duration=math.ceil(max(float(r['duration_s']) for r in selected)*2)*500
        maxima=np.zeros(duration//500+1,dtype=np.int64)
        for r in selected:
            start=int(r['start_monotonic_ns']);end=int(r['end_monotonic_ns'])
            with open(r['source']) as h:
                for value in csv.DictReader(h):
                    ns=int(value['monotonic_ns'])
                    if not start<=ns<=end:continue
                    index=min(len(maxima)-1,int((ns-start)//500000000));maxima[index]=max(maxima[index],int(value['stat_anon']))
        # Boundary envelope dominates both adjacent measured bins; no narrow peak
        # is dropped during 500ms contract conversion. Residual memory is retained.
        points=[int(max(maxima[max(0,i-1)],maxima[min(i,len(maxima)-1)])) for i in range(len(maxima))]
        text=['memshift-oracle-v1','slot_ms 500','safe_bytes 1099511627776','budget_semantics available_headroom_proxy','base 0 0','error 0 0','foreground 0 0',f'job task {duration} 0 900000 1 1 1 0 incremental']
        text += [f'point task {i*500} {v}' for i,v in enumerate(points)]
        (oracle/(op.lower()+'.tsv')).write_text('\n'.join(text)+'\n')
        model_audit.append(dict(operation=op,field='stat_anon',contract='total-anon-envelope-v1',selected_n=len(selected),duration_ms=duration,source_peak_bytes=max(points),grid_ms=500,aggregation='upper envelope over selected rounds and neighboring bins',task_duration_unmodified=True))
    # Forecast only remaining foreground growth. The live original planner base
    # already contains resident foreground memory; adding its total again is wrong.
    total=math.ceil((bounds[1]+float(metadata['Krita']['duration']))*2)*500
    memory=npz['Krita_m'];times=npz['Krita_t'];peak=float(memory.max())
    remaining=[]
    for ms in range(0,total+1,500):
        ages=[ms/1000-b for b in bounds];observed=[float(np.interp(max(0,a),times,memory)) for a in ages]
        value=0 if ms/1000>bounds[1]+times[-1] else max(0,peak-min(observed))
        remaining.append((ms,round(value)))
    for name,curve in [('foreground_active',remaining),('foreground_complete',[(0,0)])]:
        # The original parser requires a real job in every profile document.
        # Reuse the measured XZ job as document context; workload_foreground RPC
        # extracts only .foreground, never registers an additional task.
        text=[line for line in (oracle/'xz.tsv').read_text().splitlines() if not line.startswith('foreground ')]+[f'foreground {t} {v}' for t,v in curve]
        (oracle/(name+'.tsv')).write_text('\n'.join(text)+'\n')
    (oracle/'model_provenance.json').write_text(json.dumps({'task_models':model_audit,'foreground':'additional future cgroup growth over modeled current; live baseline already includes foreground charge','original_algorithm_changed':False,'source_time_origin':'manual import event; inferred homepage bracket in shared timeline','note':'profile safe_bytes is a parser capacity sentinel; DynamicWorkloads replaces live capacity/base from /proc/meminfo, keeping original risk parameters'},indent=2))
    print(json.dumps({'inferred_homepage_to_import_bounds_s':bounds,'target_s':target,'offsets':offsets,'reference_four_task_charge_GB':taskpeak/1e9,'freezes':events},ensure_ascii=False,indent=2))


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--analysis-root',type=Path,required=True);a.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);a.add_argument('--homepage-to-import-s',type=float,help='explicit measured calibration override; never guessed automatically');args=a.parse_args();build(args.analysis_root,args.repo,args.homepage_to_import_s)
