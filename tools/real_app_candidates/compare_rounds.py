"""Compare output-verified GUI rounds without reconstructing target time series.

Manifest: {"new": {app: capture_directory}, "old": {app: capture_directory}}.
Only measured samples are drawn, including launch and the observed exit tail.
"""
import argparse,json,csv
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from analyze import metrics,select_compute_window,GIB,TARGETS


def load_round(folder):
    folder=Path(folder);df=pd.read_csv(folder/'task_memory.csv')
    events=sorted([json.loads(s) for s in (folder/'phase_trace.jsonl').read_text().splitlines()],key=lambda e:e['monotonic_ns'])
    override=json.loads((folder/'timing_override.json').read_text()) if (folder/'timing_override.json').exists() else {}
    window=select_compute_window(events,override)
    if not window or (folder/'invalid_capture.md').exists():raise ValueError('Not output verified: '+str(folder))
    start,end=window;result=metrics(df,start,end)
    # Bound natural observation by both real close and last actual sample. Never
    # create a zero sample on exit or count exit as task-driven deallocation.
    last=int(df.monotonic_ns.iloc[-1])
    closes=[e['monotonic_ns'] for e in events if e['kind']=='app_close' and end<=e['monotonic_ns']<=last]
    close=min(closes,default=last)
    post=df[(df.monotonic_ns>=end)&(df.monotonic_ns<=close)]
    result.update(data=str(folder),task_submit_ns=start,task_complete_ns=end,natural_observation_end_ns=close,natural_release_observed_s=max(0.,(close-end)/1e9),release_duration_definition='time from completion to 90% of observed completion-to-tail decrease; censored if tail <10s',natural_release_censored=(close-end)<10e9)
    if len(post):
        first=float(post.memory_current.iloc[0]/GIB);tail=post[post.monotonic_ns>=max(end,close-2e9)]
        residual=float(tail.memory_current.median()/GIB);drop=first-residual
        result.update(completion_memory_gib=first,residual_gib=residual,natural_release_gib=drop,release_ratio=drop/first if first else None,peak_to_residual_ratio=(result['peak_gib']-residual)/result['peak_gib'])
        if drop>0:
            reached=post[post.memory_current/GIB<=first-.9*drop]
            result['release90_duration_s']=float((reached.monotonic_ns.iloc[0]-end)/1e9) if len(reached) else None
        else:result['release90_duration_s']=None
        for col,label in [('memory_anon','anon'),('memory_file','file')]:
            result[label+'_completion_gib']=float(post[col].iloc[0]/GIB)
            result[label+'_residual_gib']=float(tail[col].median()/GIB)
    intervals=df.monotonic_ns.diff()/1e6
    compute=df[(df.monotonic_ns>=start)&(df.monotonic_ns<=end)]
    gaps=compute.monotonic_ns.diff()/1e6
    result['sampling_ms']={'median':float(intervals.median()),'p95':float(intervals.quantile(.95)),'p99':float(intervals.quantile(.99)),'max':float(intervals.max()),'over100ms':int((intervals>100).sum()),'samples':len(df),'compute_median':float(gaps.median()),'compute_p95':float(gaps.quantile(.95)),'compute_max':float(gaps.max()),'compute_over100ms':int((gaps>100).sum())}
    result['host']={'min_available_gib':float(df.MemAvailable.min()/GIB),'max_swap_used_gib':float((df.SwapTotal-df.SwapFree).max()/GIB),'global_oom_delta':int(df.global_oom_kill.iloc[-1]-df.global_oom_kill.iloc[0]),'cgroup_oom_kill_max':max(json.loads(v).get('oom_kill',0) for v in df.memory_events)}
    result['peak_entire_capture_gib']=float(df.memory_current.max()/GIB)
    result['kernel_peak_entire_capture_gib']=float(df.memory_peak.max()/GIB)
    result['compute_cpu_seconds']=float((compute.cpu_usage_usec.iloc[-1]-compute.cpu_usage_usec.iloc[0])/1e6) if 'cpu_usage_usec' in compute else None
    result['compute_average_cpu_cores']=result['compute_cpu_seconds']/result['observed_compute_s'] if result['compute_cpu_seconds'] is not None else None
    result['compute_swap_pages']={c:float(compute[c].iloc[-1]-compute[c].iloc[0]) if c in compute else None for c in ['pswpin_pages','pswpout_pages']}
    for col in ['cgroup_swap_current','pswpin_pages','pswpout_pages']:
        result['host'][col+'_max']=float(df[col].max()) if col in df else None
        result['host'][col+'_delta']=float(df[col].iloc[-1]-df[col].iloc[0]) if col in df else None
    result['unavailable_columns']=[c for c in ['cgroup_swap_current','pswpin_pages','pswpout_pages','cpu_pressure','io_pressure'] if c not in df]
    return dict(folder=folder,df=df,events=events,start=start,end=end,metrics=result)


def draw(ax,run,label='',components=True,normalized=False,full=True):
    df=run['df'];start,end=run['start'],run['end'];m=run['metrics']
    if not full:df=df[(df.monotonic_ns>=start-2e9)&(df.monotonic_ns<=end+60e9)]
    t=(df.monotonic_ns-start)/1e9
    columns=[('memory_current','total','-'),('memory_anon','anon','--'),('memory_file','file',':')] if components else [('memory_current','total','-')]
    for col,name,style in columns:
        values=df[col]/GIB
        if normalized:
            before=run['df'][(run['df'].monotonic_ns<start)&(run['df'].monotonic_ns>=start-1e9)]
            base=float(before[col].median()/GIB) if len(before) else float(values.iloc[0])
            compute=run['df'][(run['df'].monotonic_ns>=start)&(run['df'].monotonic_ns<=end)]
            scale=float(compute[col].max()/GIB)-base
            if scale<=0:continue
            values=(values-base)/scale
        ax.plot(t,values,style,lw=1.1,label=(label+' '+name).strip())
    for stamp,color,title in [(start,'gray','submit'),(end,'green','complete')]:
        ax.axvline((stamp-start)/1e9,color=color,ls='--',alpha=.6)
    exits=[e for e in run['events'] if e['kind'] in {'app_close','app_exit','app_exit_inferred'}]
    for e in exits:
        stamp=e['monotonic_ns']
        if stamp>df.monotonic_ns.iloc[-1]+2e9:continue
        ax.axvline((stamp-start)/1e9,color='red',ls=':',alpha=.6)
    ax.grid(alpha=.2);ax.set_xlabel('Real seconds since last GUI submit (no time scaling)');ax.set_ylabel('Baseline-subtracted increment / peak increment' if normalized else 'GiB');ax.legend(fontsize=7)


def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    import subprocess
    a.output.mkdir(parents=True,exist_ok=True)
    if subprocess.run(['git','-C',str(a.output),'rev-parse','--show-toplevel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:raise ValueError('Results must be outside Git')
    manifest=json.loads(a.manifest.read_text());runs={group:{app:load_round(path) for app,path in entries.items()} for group,entries in manifest.items()}
    stats={group:{app:run['metrics'] for app,run in entries.items()} for group,entries in runs.items()}
    (a.output/'candidate_metrics.json').write_text(json.dumps(stats,indent=2,ensure_ascii=False))
    for number,app in [(1,'peazip'),(2,'blender'),(3,'handbrake')]:
        fig,axes=plt.subplots(2,1,figsize=(13,8),sharex=True,sharey=True)
        for group,ax in zip(['old','new'],axes):
            run=runs[group][app];draw(ax,run,group);ax.set_title(app+' '+group+' — full observed lifecycle; red = close/exit')
        fig.tight_layout();fig.savefig(a.output/f'{number:02d}_{app}_before_after.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(13,6));draw(ax,runs['new']['knime']);ax.set_title('KNIME full observed lifecycle; gray submit / green complete / red close or exit');fig.tight_layout();fig.savefig(a.output/'04_knime_memory_curve.png',dpi=150);plt.close(fig)
    for number,normal in [(5,False),(6,True),(7,False)]:
        fig,axes=plt.subplots(2,2,figsize=(16,9),sharex=True,sharey=True)
        for ax,(app,run) in zip(axes.flat,runs['new'].items()):
            draw(ax,run,components=number==7,normalized=normal,full=False);ax.set_title(app)
        fig.suptitle('Real elapsed time; normalized panels subtract each pre-submit baseline' if normal else 'Common memory and time scale; observed samples only');fig.tight_layout()
        fig.savefig(a.output/{5:'05_four_apps_common_scale.png',6:'06_four_apps_normalized.png',7:'07_four_apps_anon_file.png'}[number],dpi=150);plt.close(fig)
    for number,target in [(8,'Raster'),(9,'Table'),(10,'Array')]:
        fig,axes=plt.subplots(1,2,figsize=(16,6))
        for app,run in runs['new'].items():draw(axes[0],run,label=app,components=False,full=False)
        axes[0].axhline(TARGETS[target][0],color='black',ls=':',label=target+' reported peak');axes[0].legend(fontsize=7)
        names=list(runs['new']);peaks=[runs['new'][app]['metrics']['anon_peak_gib'] for app in names]
        axes[1].bar(names,peaks);axes[1].axhline(TARGETS[target][0],color='black',ls=':',label=target+' total peak reference');axes[1].set_ylabel('Measured anonymous peak GiB');axes[1].legend(fontsize=7)
        axes[1].text(.02,.98,f'{target}: total peak {TARGETS[target][0]}GiB; global peak {TARGETS[target][1]}s; P95 {TARGETS[target][2]}s\nTarget has scalar reference only. No reconstructed series or DTW.\nAnonymous lifecycle determines screening; peak bars alone do not imply a match.',transform=axes[1].transAxes,va='top',fontsize=8)
        fig.tight_layout();fig.savefig(a.output/f'{number:02d}_{target.lower()}_candidate_comparison.png',dpi=150);plt.close(fig)
    if 'initial' in runs:
        fig,axes=plt.subplots(2,2,figsize=(16,9))
        for row,app in enumerate(['peazip','handbrake']):
            for group in ['initial','new']:
                draw(axes[row,0],runs[group][app],label=group,components=True,full=False)
                draw(axes[row,1],runs[group][app],label=group,components=False,normalized=True,full=False)
            axes[row,0].set_title(app+' first valid vs normal-parameter supplement');axes[row,1].set_title(app+' baseline-subtracted increments, real time')
        fig.tight_layout();fig.savefig(a.output/'11_parameter_supplements.png',dpi=150);plt.close(fig)
    rows=[dict(application=app,**run['metrics']) for app,run in runs['new'].items()]
    keys=['application','peak_gib','anon_peak_gib','file_peak_gib','time_to90_s','time_to95_s','time_to_peak_s','platform95_total_s','platform95_longest_s','growth10_to90_s','anon_time_to90_s','anon_platform95_s','observed_compute_s','natural_release_observed_s','release90_duration_s','release_ratio','residual_gib','natural_release_censored','data']
    with (a.output/'final_summary.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    print(json.dumps([{key:row.get(key) for key in keys if key!='data'} for row in rows],indent=2))

if __name__=='__main__':main()
