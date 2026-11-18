import csv,json,hashlib,statistics,itertools
from pathlib import Path
import numpy as np
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--analysis-root',type=Path,required=True);args=parser.parse_args()
BASE=args.analysis_root.resolve();OUT=BASE/'final_analysis';OUT.mkdir(exist_ok=True)
DT=.05

def readj(p):return json.loads(p.read_text())
def events(p):return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
def savecsv(name,rows):
 rows=list(rows)
 if not rows:return
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with (OUT/name).open('w') as h:
  w=csv.DictWriter(h,fieldnames=keys);w.writeheader();w.writerows(rows)
def windows(t,mask):
 ed=np.diff(np.r_[False,mask,False].astype(int));return [(float(t[a]),float(t[b-1])) for a,b in zip(np.where(ed==1)[0],np.where(ed==-1)[0])]

rounds=[];data={};inventory=[];validation=[]
def add(op,p,start,end,selected=True,notes='',meta=None):
 rows=list(csv.DictReader(p.open()));ns=np.array([int(r['monotonic_ns']) for r in rows],dtype=np.int64);m=np.array([int(r['memory_current']) for r in rows],dtype=np.float64);t=(ns-start)/1e9;ok=(ns>=start)&(ns<=end);tt=t[ok];mm=m[ok];ridx=np.flatnonzero(ok);assert np.all(np.diff(ns)>0) and len(tt)>1
 before=np.flatnonzero(ns<=start);initial=float(m[before[-1]]) if len(before) else float(mm[0]);initial_s=float(t[before[-1]]) if len(before) else float(tt[0])
 peak=float(mm.max());i=int(mm.argmax());win=windows(tt,mm>=.95*peak);main=next(w for w in win if w[0]<=tt[i]<=w[1]);baseline=initial
 normalized=(mm-baseline)/(peak-baseline)
 g10=np.flatnonzero(normalized>=.1);g90=np.flatnonzero(normalized>=.9);gstart=float(tt[g10[0]]) if len(g10) else None;gend=float(tt[g90[0]]) if len(g90) else None
 after=np.flatnonzero((np.arange(len(tt))>i)&(mm<.95*peak));decline=float(tt[after[0]]) if len(after) else None
 r={'operation':op,'round_id':p.parent.name,'selected':selected,'status':'VALID' if op!='Krita' else 'N1_REFERENCE_SUMMARY_FAILED_MANUAL_MARK','notes':notes,'initial_bytes':int(initial),'initial_sample_relative_s':initial_s,'sampled_peak_bytes':int(peak),'sampled_peak_GB':peak/1e9,'sampled_peak_GiB':peak/2**30,'peak_time_s':float(tt[i]),'peak_monotonic_ns':int(ns[ridx[i]]),'peak_source_csv_line':int(ridx[i])+2,'peak_window_start_s':main[0],'peak_window_end_s':main[1],'peak_window_span_s':main[1]-main[0],'peak_duration_all_windows_s':sum(b-a for a,b in win),'growth_start_10pct_s':gstart,'growth_end_90pct_s':gend,'growth_rate_bytes_per_s':(.8*(peak-baseline)/(gend-gstart)) if gend and gstart is not None and gend>gstart else None,'decline_below_95pct_s':decline,'duration_s':(end-start)/1e9,'record_count':len(tt),'median_interval_s':float(np.median(np.diff(tt))),'max_gap_s':float(np.diff(tt).max()),'end_last_observed_bytes':int(mm[-1]),'end_residual_status':'end observation only; post-cleanup residual not inferred','kernel_high_water_bytes_observed':max(int(x['memory_peak']) for x in rows),'source':str(p),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'start_monotonic_ns':start,'end_monotonic_ns':end}
 if meta:
  r.update(supervisor_duration_s=meta.get('duration_s'),supervisor_to_task_start_s=(start-meta['start']['monotonic_ns'])/1e9,metadata_memory_peak_bytes=meta.get('peak_bytes'),metadata_sampled_current_peak_bytes=meta.get('sampled_current_peak_bytes'))
  for key,val in [('peak_bytes',r['kernel_high_water_bytes_observed']),('sampled_current_peak_bytes',int(m.max())),('duration_s',(meta['finish']['end_ns']-meta['start']['monotonic_ns'])/1e9)]:
   reference=meta.get(key)
   validation.append({'operation':op,'round_id':p.parent.name,'metric':key,'raw_computed':val,'summary_value':reference,'difference':val-reference if reference is not None else None,'validation':'MATCH' if reference is not None and abs(val-reference)<1e-6 else 'CHECK_SCOPE_OR_MISSING','scope':'whole collector/supervisor interval for comparison; formal operation metrics use task_start/task_finish'})
  assert meta['success'] and meta['verified'] and meta['returncode']==0
 data[(op,p.parent.name)]=(tt,mm,r)
 rounds.append(r)
 inventory.append({'operation':op,'round_id':p.parent.name,'file_name':str(p),'file_type':'csv','timestamp_field':'monotonic_ns','memory_field':'memory_current','memory_unit':'Bytes','sample_interval':r['median_interval_s'],'record_count':len(rows),'start_time':start,'end_time':end,'status':r['status'],'source':str(p),'sha256':r['source_sha256']})
 return r

for op,glob in [('XZ','new_data/results/*/xz/**/raw.csv'),('Table','new_data/results/*/table/**/raw.csv'),('Array','Array_Large_10Rounds/Array_Large_10Rounds/extracted/**/raw.csv')]:
 for p in sorted(BASE.glob(glob)):
  meta=readj(p.parent/'metadata.json');ph=events(p.parent/'phase_trace.jsonl');s=next(x['monotonic_ns'] for x in ph if x['event_type']=='task_start');e=next(x['monotonic_ns'] for x in ph if x['event_type']=='task_finish');selected=not(op=='Array' and p.parent.name=='9d3859de4be24a28936d0cc6287f38ec')
  add(op,p,s,e,selected,notes='' if selected else '用户明确指定使用其余9轮；本轮保留但不参与代表性曲线',meta=meta)
kp=next(BASE.glob('Krita_Manual_1Round/Krita_Manual_1Round/extracted/*/samples.csv'));ph=events(kp.parent/'phase-events.jsonl');ks=next(x['monotonic_ns'] for x in ph if x.get('label')=='开始批量导入图层');ke=next(x['monotonic_ns'] for x in ph if x.get('label')=='导入完成，开始保持峰值')
kr=add('Krita',kp,ks,ke,notes='n=1；人工标记是GUI开始事件近似；主方案沿用现有导入操作边界；后续实测保持阶段另报')
# Keep the full observed Krita trace as an explicit sensitivity profile.
rows=list(csv.DictReader(kp.open()));km=readj(kp.parent/'metadata.json');kend=km['krita_exit']['monotonic_ns'];use=[r for r in rows if ks<=int(r['monotonic_ns'])<=kend];peakrow=max(use,key=lambda r:int(r['memory_current']));hold={'sampled_peak_bytes':int(peakrow['memory_current']),'peak_time_s':(int(peakrow['monotonic_ns'])-ks)/1e9,'duration_s':(kend-ks)/1e9,'kernel_high_water_bytes':max(int(r['memory_peak']) for r in use),'returncode':km['krita_exit']['returncode'],'interpretation':'observed hold after import; exit -9 alone is not proof of OOM; not added to primary import operation'}

savecsv('operation_round_metrics.csv',rounds);savecsv('operation_data_inventory.csv',inventory);savecsv('xz_round_metrics.csv',[r for r in rounds if r['operation']=='XZ']);savecsv('xz_summary_validation.csv',[r for r in validation if r['operation']=='XZ']);savecsv('all_summary_validation.csv',validation)
summary=[];meanrows=[];profiles={};peakwindows=[]
for op in ['Krita','XZ','Table','Array']:
 ds=[v for (o,rid),v in data.items() if o==op and v[2]['selected']];rs=[r for t,m,r in ds];n=len(rs);s={'operation':op,'n_selected':n,'n_available':sum(r['operation']==op for r in rounds)}
 for key in ['sampled_peak_GB','peak_time_s','duration_s','initial_bytes','peak_window_start_s','peak_window_end_s']:
  v=[r[key] for r in rs]
  for stat,val in [('mean',statistics.mean(v)),('median',statistics.median(v)),('sample_std',statistics.stdev(v) if n>1 else None),('min',min(v)),('max',max(v))]:s[f'{key}_{stat}']=val
 # Full descriptive mean: available observations only, with n on every row.
 grid=np.arange(0,max(t[-1] for t,m,r in ds)+1e-8,DT);matrix=np.full((n,len(grid)),np.nan)
 for i,(t,m,r) in enumerate(ds):
  valid=(grid>=t[0])&(grid<=t[-1]);matrix[i,valid]=np.interp(grid[valid],t,m)
 validcols=np.any(np.isfinite(matrix),axis=0);grid=grid[validcols];matrix=matrix[:,validcols];counts=np.sum(np.isfinite(matrix),axis=0);means=np.nanmean(matrix,axis=0)
 for j,t in enumerate(grid):meanrows.append({'operation':op,'relative_s':float(t),'mean_bytes':float(means[j]),'min_bytes':float(np.nanmin(matrix[:,j])),'max_bytes':float(np.nanmax(matrix[:,j])),'n':int(counts[j]),'required_n':n})
 # Optimization uses constant n, common measured support only: no survivor-tail peak.
 common=counts==n;tg=grid[common];mg=means[common];assert np.allclose(np.diff(tg),DT)
 b=statistics.mean(r['initial_bytes'] for r in rs);pk=float(mg.max());pi=int(mg.argmax());ws=windows(tg,mg>=.95*pk);profiles[op]={'t':tg,'m':mg,'initial':b,'duration':statistics.mean(r['duration_s'] for r in rs),'n':n,'peak':pk,'peak_t':float(tg[pi]),'windows':ws}
 s['mean_curve_peak_GB']=pk/1e9;s['mean_curve_peak_time_s']=float(tg[pi]);s['common_support_start_s']=float(tg[0]);s['common_support_end_s']=float(tg[-1]);summary.append(s)
 for a,b in ws:peakwindows.append({'operation':op,'n':n,'threshold_fraction':.95,'window_start_s':a,'window_end_s':b,'span_s':b-a,'definition':'continuous mean curve >= 95% own peak; only n=all-selected observations'})
 print(op,'n',n,'round_peak_GB',s['sampled_peak_GB_mean'],'round_peak_s',s['peak_time_s_mean'],'duration',s['duration_s_mean'],'MEAN_CURVE',pk/1e9,'at',tg[pi],'WINDOWS',ws)

savecsv('operation_peak_summary.csv',summary);savecsv('operation_timing_summary.csv',summary);savecsv('operation_mean_curves.csv',meanrows);savecsv('operation_peak_windows.csv',peakwindows)
np.savez(OUT/'profiles.npz',**{f'{op}_{k}':p[k] for op,p in profiles.items() for k in ['t','m']})
(OUT/'profile_metadata.json').write_text(json.dumps({op:{k:v for k,v in p.items() if k not in ['t','m']} for op,p in profiles.items()},indent=2))
(OUT/'krita_hold_sensitivity.json').write_text(json.dumps(hold,ensure_ascii=False,indent=2))
# Reconcile aggregate summaries as indices only; missing XZ raw rounds are never treated as available.
for op in ['xz','table']:
 p=next(BASE.glob(f'new_data/results/*/aggregate/{op}_*/summary.json'));d=readj(p)
 print('AGGREGATE',op,'valid_rounds',d.get('valid_rounds'),'runs',len(d.get('runs',[])),'peak',d.get('peak_bytes'))
print('VALIDATION',[(r['operation'],r['round_id'],r['metric'],r['difference']) for r in validation if r['validation']!='MATCH'])
print('KRITA_HOLD',hold)
