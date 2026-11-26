"""Analyze observed GUI tasks; never synthesize missing samples or target curves."""
import argparse,json,math,csv
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
GIB=1024**3
TARGETS={'Raster':(3.819,33.08,38.60),'Table':(4.022,33.55,38.15),'Array':(1.017,3.22,45.70)}


def metrics(df,start,end):
    d=df[(df.monotonic_ns>=start)&(df.monotonic_ns<=end)].copy()
    if end<=start or d.empty:return {'status':'NO_COMPUTE_SAMPLES'}
    t=(d.monotonic_ns.to_numpy()-start)/1e9;y=d.memory_current.to_numpy()/GIB
    peak=float(y.max());i=int(y.argmax());dt=np.diff(t);high=y[:-1]>=.95*peak
    platform=float(dt[high].sum());longest=run=0.
    for delta,on in zip(dt,high):
        run=run+float(delta) if on else 0.;longest=max(longest,run)
    result=dict(growth10_to90_s=float(t[np.flatnonzero(y>=.9*peak)[0]]-t[np.flatnonzero(y>=.1*peak)[0]]),time_to90_s=float(t[np.flatnonzero(y>=.9*peak)[0]]),time_to95_s=float(t[np.flatnonzero(y>=.95*peak)[0]]),status='OBSERVED',samples=len(d),peak_gib=peak,time_to_peak_s=float(t[i]),platform95_total_s=platform,platform95_longest_s=longest,observed_compute_s=float((end-start)/1e9),anon_peak_gib=float(d.memory_anon.max()/GIB),file_peak_gib=float(d.memory_file.max()/GIB))
    # Absolute thresholds above are comparable with the historical scalar metrics.
    # Separately report the actual task increment, excluding the loaded GUI baseline.
    before=df[(df.monotonic_ns<start)&(df.monotonic_ns>=start-1e9)]
    baseline=float(before.memory_current.median()/GIB) if not before.empty else float(y[0])
    result['baseline_gib']=baseline
    result['increment_peak_gib']=max(0.,peak-baseline)
    if peak>baseline:
        lo=t[np.flatnonzero(y>=baseline+.1*(peak-baseline))[0]]
        hi=t[np.flatnonzero(y>=baseline+.9*(peak-baseline))[0]]
        result['increment_growth10_to90_s']=float(hi-lo)
    else:result['increment_growth10_to90_s']=None
    for column,label in [('memory_anon','anon'),('memory_file','file')]:
        values=d[column].to_numpy()/GIB;p=float(values.max())
        result[label+'_time_to90_s']=float(t[np.flatnonzero(values>=.9*p)[0]])
        result[label+'_platform95_s']=float(dt[values[:-1]>=.95*p].sum())
        # Forward difference over an observed 2.5s horizon; no extrapolation.
        future=np.searchsorted(t,t+2.5);valid=future<len(t)
        changes=values[future[valid]]-values[valid]
        result[label+'_max_forward_2_5s_growth_gib']=float(changes.max()) if len(changes) else None
    return result



def select_compute_window(events,overrides=None):
    """Last GUI submission, paired with a later completion and verification."""
    overrides=overrides or {}
    ordered=sorted(events,key=lambda e:e['monotonic_ns'])
    # Keep the original trace immutable. A documented operator correction may
    # supersede a mistaken failure inference; native failures stay disqualifying.
    corrected={e['detail']['supersedes_monotonic_ns']:e['detail']['corrected_kind'] for e in ordered
               if e['kind']=='event_correction' and isinstance(e.get('detail'),dict)
               and 'supersedes_monotonic_ns' in e['detail'] and 'corrected_kind' in e['detail']}
    submits=[e for e in ordered if e['kind']=='task_submit']
    if not submits:return None
    start=overrides.get('task_submit_ns',submits[-1]['monotonic_ns'])
    completes=[e for e in ordered if e['kind']=='task_complete' and e['monotonic_ns']>=start]
    if not completes:return None
    end=overrides.get('task_complete_ns',completes[0]['monotonic_ns'])
    if end<=start:return None
    if not any(e['kind']=='output_verified' and e['monotonic_ns']>=end for e in ordered):return None
    def effective_kind(e):
        if e['kind']=='safety_abort':return 'safety_abort'
        if e['kind']=='task_failed' and isinstance(e.get('detail'),dict):return 'task_failed'
        correction=corrected.get(e['monotonic_ns'])
        return correction if correction in {'configuration_warning','configuration_note'} else e['kind']
    if any(effective_kind(e) in {'task_failed','safety_abort'} and start<=e['monotonic_ns']<=end for e in ordered):return None
    return start,end


def main():
    p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--selection',type=Path);a=p.parse_args()
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    # Real Git validation, not a mere .git name test.
    import subprocess
    if subprocess.run(['git','-C',str(output),'rev-parse','--show-toplevel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:raise SystemExit('Output must be outside a Git worktree')
    selection=json.loads(a.selection.read_text()) if a.selection else {}
    all_results=[];curves=[]
    for folder in sorted(a.data_root.glob('*/*')):
        source=folder/'task_memory.csv'
        if not source.exists():continue
        df=pd.read_csv(source);events=[json.loads(l) for l in (folder/'phase_trace.jsonl').read_text().splitlines()];app=folder.parent.name;name=app+'/'+folder.name
        submits=[e for e in events if e['kind']=='task_submit'];completes=[e for e in events if e['kind']=='task_complete'];closes=[e for e in events if e['kind']=='app_close'];exits=[e for e in events if e['kind']=='app_exit_inferred']
        overrides=json.loads((folder/'timing_override.json').read_text()) if (folder/'timing_override.json').exists() else {}
        events.sort(key=lambda e:e['monotonic_ns'])
        window=select_compute_window(events,overrides)
        valid=bool(window and not (folder/'invalid_capture.md').exists());result=dict(application=app,round=folder.name,complete_compute_capture=valid,data=str(folder),events=events)
        if valid:
            start,end=window;result['timing_override']=overrides;result.update(metrics(df,start,end));curves.append((name,df,start,end))
            later_closes=[e for e in closes if e['monotonic_ns']>=end];close=later_closes[0]['monotonic_ns'] if later_closes else (exits[0]['detail']['last_alive_ns'] if exits else int(df.monotonic_ns.iloc[-1]));post=df[(df.monotonic_ns>=end)&(df.monotonic_ns<close)]
            result['natural_release_observed_s']=float((close-end)/1e9)
            if not post.empty:
                result['memory_at_completion_gib']=float(post.memory_current.iloc[0]/GIB);result['memory_before_close_gib']=float(post.memory_current.iloc[-1]/GIB);result['natural_release_gib']=float((post.memory_current.iloc[0]-post.memory_current.iloc[-1])/GIB);result['peak_to_preclose_release_gib']=result['peak_gib']-result['memory_before_close_gib']
            result['peak_entire_capture_gib']=float(df.memory_current.max()/GIB);result['kernel_peak_entire_capture_gib']=float(df.memory_peak.max()/GIB)
            result['target_metric_distance']={k:float(sum(abs(math.log(max(v,.001)/target)) for v,target in zip([result['peak_gib'],result['time_to_peak_s'],result['platform95_total_s']],spec))) for k,spec in TARGETS.items()}
            result['closest_by_metrics']=min(result['target_metric_distance'],key=result['target_metric_distance'].get)
        else:result['status']='INCOMPLETE_OR_FAILED';start=df.monotonic_ns.iloc[0]
        result['host_and_cgroup']={'minimum_MemAvailable_gib':float(df.MemAvailable.min()/GIB),'max_cgroup_swap_gib':(float(df.cgroup_swap_current.max()/GIB) if 'cgroup_swap_current' in df else None),'max_host_swap_used_gib':float((df.SwapTotal-df.SwapFree).max()/GIB),'host_swap_used_delta_gib':float(((df.SwapTotal-df.SwapFree).iloc[-1]-(df.SwapTotal-df.SwapFree).iloc[0])/GIB),'swapin_pages_delta':(int(df.pswpin_pages.iloc[-1]-df.pswpin_pages.iloc[0]) if 'pswpin_pages' in df else None),'swapout_pages_delta':(int(df.pswpout_pages.iloc[-1]-df.pswpout_pages.iloc[0]) if 'pswpout_pages' in df else None),'global_oom_delta':int(df.global_oom_kill.iloc[-1]-df.global_oom_kill.iloc[0]),'cgroup_oom_kill_max':max(json.loads(v).get('oom_kill',0) for v in df.memory_events)}
        result['unavailable_columns']=[key for key in ['pswpin_pages','pswpout_pages','cgroup_swap_current'] if key not in df]
        result['capture_duration_s']=float((df.monotonic_ns.iloc[-1]-df.monotonic_ns.iloc[0])/1e9)
        result['sample_interval_ms']={'median':float(df.monotonic_ns.diff().median()/1e6),'p95':float(df.monotonic_ns.diff().quantile(.95)/1e6),'p99':float(df.monotonic_ns.diff().quantile(.99)/1e6),'mean':float(df.monotonic_ns.diff().mean()/1e6),'samples':len(df),'max':float(df.monotonic_ns.diff().max()/1e6),'over100ms':int((df.monotonic_ns.diff()>1e8).sum())}
        if valid:
            d=df[(df.monotonic_ns>=start)&(df.monotonic_ns<=end)]
            result['compute_sample_interval_ms']={'median':float(d.monotonic_ns.diff().median()/1e6),'p95':float(d.monotonic_ns.diff().quantile(.95)/1e6),'max':float(d.monotonic_ns.diff().max()/1e6),'over100ms':int((d.monotonic_ns.diff()>1e8).sum())}
        fig,axes=plt.subplots(2,1,figsize=(12,8),sharex=True);t=(df.monotonic_ns-start)/1e9
        axes[0].plot(t,df.memory_current/GIB,label='cgroup memory.current');hostax=axes[0].twinx();hostax.plot(t,df.MemAvailable/GIB,label='MemAvailable',alpha=.25,color='gray');hostax.set_ylabel('Host available GiB',color='gray');axes[0].set_ylabel('GiB');axes[0].legend()
        axes[1].plot(t,df.memory_anon/GIB,label='anon');axes[1].plot(t,df.memory_file/GIB,label='file');axes[1].set_ylabel('GiB');axes[1].set_xlabel('Seconds relative to last GUI submit; earlier phases preserved');axes[1].legend()
        for e in events:
            if e['kind'] in {'app_launch','task_submit','task_complete','app_close','app_exit_inferred','safety_abort','task_failed'}:
                x=(e['monotonic_ns']-start)/1e9
                for ax in axes:ax.axvline(x,ls='--',alpha=.6);ax.text(x,.98,e['kind'],rotation=90,va='top',transform=ax.get_xaxis_transform(),fontsize=7)
        if valid and overrides.get('task_complete_ns'):
            for ax in axes:ax.axvline((end-start)/1e9,color='green',ls=':',label='log-derived completion')
        fig.suptitle(name+(' — output-verified computation' if valid else ' — incomplete; not a successful curve')); fig.tight_layout();fig.savefig(output/(app+'_'+folder.name+'.png'),dpi=150);plt.close(fig);all_results.append(result)
    if selection:
        curves=[v for v in curves if selection.get(v[0].split('/')[0])==v[0].split('/')[1]]
        if len(curves)!=len(selection):raise ValueError('Selection includes a missing or unverified round')
    for result in all_results:result['selected_for_comparison']=any(v[0]==result['application']+'/'+result['round'] for v in curves)
    if curves:
        fig,ax=plt.subplots(figsize=(12,6))
        for name,df,start,end in curves:
            d=df[(df.monotonic_ns>=start)&(df.monotonic_ns<=min(df.monotonic_ns.iloc[-1],end+60e9))];ax.plot((d.monotonic_ns-start)/1e9,d.memory_current/GIB,label=name)
        ax.set(xlabel='Seconds since GUI submit',ylabel='cgroup memory.current (GiB)',ylim=(0,max(4.3,max(r.get('peak_gib',0) for r in all_results)*1.05)));ax.legend();fig.tight_layout();fig.savefig(output/'all_apps_common_scale.png',dpi=150);plt.close(fig)
    if curves:
        xmin=min(float((df.monotonic_ns.iloc[0]-start)/1e9) for _,df,start,_ in curves)
        xmax=max(float((df.monotonic_ns.iloc[-1]-start)/1e9) for _,df,start,_ in curves)
        ymax=max(4.3,max(float(df.memory_current.max()/GIB) for _,df,_,_ in curves)*1.05)
        for components,filename in [(False,'six_apps_full_lifecycle_common_scale.png'),(True,'six_apps_anon_file_common_scale.png')]:
            rows=math.ceil(len(curves)/2);fig,axes=plt.subplots(rows,2,figsize=(16,4*rows),sharex=True,sharey=True,squeeze=False)
            for ax,(name,df,start,end) in zip(axes.flat,curves):
                t=(df.monotonic_ns-start)/1e9
                ax.plot(t,df.memory_current/GIB,label='memory.current',lw=1.3)
                if components:
                    ax.plot(t,df.memory_anon/GIB,label='anon',lw=1)
                    ax.plot(t,df.memory_file/GIB,label='file',lw=1)
                ax.axvline(0,color='gray',ls='--',label='GUI submit')
                ax.axvline((end-start)/1e9,color='green',ls='--',label='computation complete')
                r=next(v for v in all_results if v['application']+'/'+v['round']==name)
                for e in r['events']:
                    if e['kind'] in {'app_close','app_exit_inferred'}:ax.axvline((e['monotonic_ns']-start)/1e9,color='red',ls=':',label=e['kind'])
                ax.set(title=name,xlim=(xmin,xmax),ylim=(0,ymax),ylabel='GiB');ax.grid(alpha=.2);ax.legend(fontsize=7)
            for ax in axes[-1]:ax.set_xlabel('Seconds relative to last GUI submission; pre-submit phases preserved')
            fig.tight_layout();fig.savefig(output/filename,dpi=150);plt.close(fig)
    fields=['application','round','status','selected_for_comparison','peak_gib','time_to_peak_s','time_to95_s','growth10_to90_s','platform95_total_s','platform95_longest_s','observed_compute_s','anon_peak_gib','file_peak_gib','natural_release_observed_s','natural_release_gib','closest_by_metrics','data']
    with (output/'candidate_summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(all_results)
    (output/'target_reference.json').write_text(json.dumps({'source':'User-provided scalar reference; no historical CSV reconstructed','targets':TARGETS},indent=2))
    (output/'metrics.json').write_text(json.dumps(all_results,ensure_ascii=False,indent=2));print(json.dumps([{k:r.get(k) for k in ['application','round','complete_compute_capture','peak_gib','time_to_peak_s','platform95_total_s','closest_by_metrics']} for r in all_results],indent=2))
if __name__=='__main__':main()
