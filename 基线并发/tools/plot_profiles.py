#!/usr/bin/env python3
"""Reproducible plots of measured profiles and the explicitly provisional V4 plan."""
import argparse
import csv
import json
import os
from pathlib import Path
import numpy as np
os.environ.setdefault('MPLCONFIGDIR','/tmp/oomlab-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    a=argparse.ArgumentParser();a.add_argument('--analysis-root',type=Path,required=True);a.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2]);args=a.parse_args()
    repo=args.repo;src=args.analysis_root/'final_analysis';out=repo/'基线并发/profiles/analysis';rows=list(csv.DictReader((src/'operation_round_metrics.csv').open()));mean=np.load(src/'profiles.npz');metadata=json.loads((src/'profile_metadata.json').read_text());plan=json.loads((repo/'基线并发/baseline_timeline_plan.json').read_text());offsets={x['operation']:x['start_offset_s'] for x in plan['schedule']};ops=['Krita','XZ','Table','Array'];colors=['#b54773','#2979a3','#c27a25','#28947d']
    fig,axes=plt.subplots(2,2,figsize=(12,8))
    for ax,op,color in zip(axes.ravel(),ops,colors):
        for r in rows:
            if r['operation']!=op:continue
            with open(r['source']) as h:values=[v for v in csv.DictReader(h) if int(r['start_monotonic_ns'])<=int(v['monotonic_ns'])<=int(r['end_monotonic_ns'])]
            t=np.array([(int(v['monotonic_ns'])-int(r['start_monotonic_ns']))/1e9 for v in values]);m=np.array([int(v['memory_current'])/1e9 for v in values]);included=r['selected']=='True'
            ax.plot(t,m,color=color if included else 'gray',alpha=.25 if included else .5,ls='-' if included else '--',lw=1,label='Excluded Array round 1' if not included else None)
        ax.plot(mean[op+'_t'],mean[op+'_m']/1e9,color=color,lw=2,label=f'Mean with all selected n={metadata[op]["n"]}')
        ax.set_title(op+(' (single import-stage reference)' if op=='Krita' else ''));ax.set_xlabel('Seconds from operation start (Krita: import mark)');ax.set_ylabel('cgroup memory.current (GB)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Original operation traces; no duration warping or raw-peak deletion');fig.tight_layout();fig.savefig(out/'operation_curves.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    for i,(op,color) in enumerate(zip(ops,colors)):
        values=[r for r in rows if r['operation']==op and r['selected']=='True'];axes[0].scatter([i]*len(values),[float(r['sampled_peak_GB']) for r in values],color=color);axes[1].scatter([i]*len(values),[float(r['peak_time_s']) for r in values],color=color)
    for ax in axes:ax.set_xticks(range(4),['Krita n=1','XZ n=3','Table n=10','Array n=9']);ax.grid(alpha=.2)
    axes[0].set_ylabel('Per-round sampled current peak (GB)');axes[1].set_ylabel('Peak time from formal operation start (s)');fig.tight_layout();fig.savefig(out/'peak_distributions.png',dpi=150);plt.close(fig)
    lo,hi=plan['planning_homepage_to_import_bounds_s'];fstart=max(float(mean['Krita_t'][0])+hi,1210);fend=min(float(mean['Krita_t'][-1])+lo,1240);t=np.arange(fstart,fend,.05);deltas=np.unique(np.r_[np.arange(lo,hi+.001,.05),hi]);fg=np.interp(t[:,None]-deltas[None,:],mean['Krita_t'],mean['Krita_m']);parts=[]
    for op in ['XZ','Table','Array']:parts.append(np.interp(t-offsets[op.lower()],mean[op+'_t'],mean[op+'_m'],left=np.nan,right=np.nan))
    parts=np.stack(parts);valid=np.all(np.isfinite(parts),axis=0);lower=fg.min(axis=1)+parts.sum(axis=0);upper=fg.max(axis=1)+parts.sum(axis=0)
    fig,(ax,bx)=plt.subplots(2,1,figsize=(12,7))
    for i,(op,color) in enumerate(zip(ops,colors)):
        selected=[r for r in rows if r['operation']==op and r['selected']=='True'];offset=lo if op=='Krita' else offsets[op.lower()]
        for r in selected:ax.plot([offset+float(r['peak_window_start_s']),offset+float(r['peak_window_end_s'])],[i,i],color=color,alpha=.45,lw=5)
        if op=='Krita':
            for r in selected:ax.plot([hi+float(r['peak_window_start_s']),lo+float(r['peak_window_end_s'])],[i+.12,i+.12],color=color,lw=3,label='Krita robust intersection over homepage bracket')
    ax.set_yticks(range(4),ops);ax.set_xlim(1180,1245);ax.set_xlabel('Seconds from homepage-ready T0');ax.set_title('Individual >=95% peak windows; Table hot/cold modes covered by broad platforms');ax.grid(alpha=.2);ax.legend(fontsize=8)
    bx.fill_between(t[valid],lower[valid]/1e9,upper[valid]/1e9,color='#2e4057',alpha=.2,label='Homepage-origin uncertainty band');bx.plot(t[valid],lower[valid]/1e9,color='#2e4057',label='Conservative reference sum')
    freeze=json.loads((repo/'冻结并发/freeze_schedule.json').read_text());held=[]
    for op in ['XZ','Table','Array']:
        ev=next(e for e in freeze['events'] if e['operation']==op.lower() and e['action']=='freeze');age=np.minimum(np.maximum(t-offsets[op.lower()],mean[op+'_t'][0]),ev['expected_memory_state']['operation_age_s']);held.append(np.interp(age,mean[op+'_t'],mean[op+'_m']))
    frozen=fg.min(axis=1)+sum(held);bx.plot(t,frozen/1e9,color='#39946b',ls='--',label='Fixed-freeze pause model: allocated memory retained')
    bx.set_xlabel('Seconds from homepage-ready T0');bx.set_ylabel('Task cgroup reference charge (GB)');bx.set_title('No system idle added; no physical-memory or OOM-avoidance claim');bx.grid(alpha=.2);bx.legend(fontsize=8);fig.tight_layout();fig.savefig(out/'homepage_overlap.png',dpi=150);plt.close(fig)


if __name__=='__main__':main()
