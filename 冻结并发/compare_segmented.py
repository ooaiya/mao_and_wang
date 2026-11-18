"""Post-run three-way comparison from actual receipts and kernel intervals."""
import argparse,csv,hashlib,json
from pathlib import Path

OPS=['foreground_krita','xz','table','array'];NAMES=['前台 Krita','XZ','Table','Array'];COLORS=['#3478A8','#DD9138','#389479','#956BB0']
def stamp(s):return '%02d:%05.2f'%(int(s//60),s%60)
def overlap(intervals,a,b):return sum(max(0,min(y,b)-max(x,a)) for x,y in intervals)
def load(root,label):
    root=Path(root);s=json.loads((root/'summary.json').read_text());v=json.loads((root/'validation.json').read_text());first=s['tasks']['foreground_krita'];origin=first.get('created_ns',first.get('start_ns'));tasks={}
    for op in OPS:
        r=s['tasks'][op];start=r.get('actual_start_ns',r.get('start_ns',r.get('created_ns')));path=root/op/'phase_trace.jsonl'
        if op!='foreground_krita' and 'actual_start_ns' not in r and path.exists():
            start=next(e['monotonic_ns'] for e in (json.loads(line) for line in path.read_text().splitlines()) if e['event_type']=='task_start')
        end=r['empty_confirmed_ns'];active=r.get('running_intervals_ns',[[start,end]])
        active=[[(max(x,start)-origin)/1e9,(min(y,end)-origin)/1e9] for x,y in active if y is not None and min(y,end)>max(x,start)]
        paused=r.get('pause_intervals_ns',[[r['freeze_confirmed_ns'],r['release_confirmed_ns']]] if 'freeze_confirmed_ns' in r else [])
        paused=[[(x-origin)/1e9,(y-origin)/1e9] for x,y in paused if y is not None]
        tasks[op]=dict(start_s=(start-origin)/1e9,end_s=(end-origin)/1e9,active=active,paused=paused,
            active_wall_s=sum(y-x for x,y in active),frozen_s=sum(y-x for x,y in paused),returncode=r['returncode'])
    fg_end=tasks['foreground_krita']['end_s'];proofs=json.loads((root/'freeze_events.json').read_text()) if (root/'freeze_events.json').exists() else []
    return dict(label=label,source=str(root),success=v['success'],total_s=max(r['end_s'] for r in tasks.values()),tasks=tasks,
        no_swap=v.get('swap_zero_all_formal_samples',False),oom_kill=v['global_oom_kill_delta'],
        xz_foreground_overlap_s=overlap(tasks['xz']['active'],0,fg_end),xz_resume_count=sum(e['operation']=='xz' and e['action']=='resume' for e in proofs),
        source_summary_sha256=hashlib.sha256((root/'summary.json').read_bytes()).hexdigest())

def main():
    a=argparse.ArgumentParser();a.add_argument('--serial',required=True);a.add_argument('--conservative',required=True);a.add_argument('--segmented',required=True);a.add_argument('--output',required=True);v=a.parse_args()
    out=Path(v.output);out.mkdir(parents=True,exist_ok=True)
    runs=[load(v.serial,'串行'),load(v.conservative,'第一版冻结'),load(v.segmented,'曲线规划冻结')]
    for r in runs:r['shorter_vs_serial_s']=runs[0]['total_s']-r['total_s'];r['shorter_vs_previous_s']=runs[1]['total_s']-r['total_s']
    (out/'comparison.json').write_text(json.dumps(runs,indent=2,ensure_ascii=False))
    with (out/'timings.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['strategy','operation','start_s','end_s','active_wall_s','frozen_s','returncode']);w.writeheader()
        for run in runs:
            for op,r in run['tasks'].items():w.writerow(dict(strategy=run['label'],operation=op,**{k:r[k] for k in w.fieldnames[2:]}))
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    from matplotlib.ticker import FuncFormatter,MultipleLocator
    from matplotlib.patches import Patch
    font='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc';fm.fontManager.addfont(font)
    plt.rcParams.update({'font.family':fm.FontProperties(fname=font).get_name(),'axes.unicode_minus':False,'svg.fonttype':'none'})
    fig,axs=plt.subplots(3,1,figsize=(14,10),sharex=True)
    limit=max(r['total_s'] for r in runs)+50
    for ax,run in zip(axs,runs):
        for i,op in enumerate(OPS):
            r=run['tasks'][op]
            for x,y in r['paused']:ax.barh(i,y-x,left=x,height=.55,color='#E2E5E9',edgecolor='#ABB3BC',hatch='///',lw=.4)
            for x,y in r['active']:ax.barh(i,y-x,left=x,height=.55,color=COLORS[i])
            if op in ['foreground_krita','xz']:ax.text(r['end_s']+10,i,stamp(r['end_s']),va='center',fontsize=9)
        ax.set_ylim(3.6,-.6);ax.set_yticks(range(4),NAMES);ax.set_xlim(0,limit);ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
        ax.set_title('%s：总耗时 %s；XZ与前台重叠 %.2fs；XZ恢复 %d 次'%(run['label'],stamp(run['total_s']),run['xz_foreground_overlap_s'],run['xz_resume_count']),loc='left',fontweight='bold',pad=10)
        for edge in ['top','right']:ax.spines[edge].set_visible(False)
        ax.axvline(run['tasks']['foreground_krita']['end_s'],color='#64717E',ls=':',lw=1)
    axs[-1].xaxis.set_major_locator(MultipleLocator(300));axs[-1].xaxis.set_major_formatter(FuncFormatter(lambda x,p:'%02d:%02d'%(int(x//60),int(x%60))))
    axs[-1].set_xlabel('各轮均以前台自动化启动为00:00；彩色为解冻执行，灰色斜线为冻结等待')
    fig.suptitle('串行 / 第一版冻结 / 曲线规划冻结：实际执行时间线',fontsize=18,fontweight='bold')
    fig.text(.5,.025,'两版冻结均关闭Swap；串行开启Swap。单轮实测，不把全部耗时差异归因于调度。',ha='center',color='#526172')
    fig.tight_layout(rect=[0,.055,1,.96]);fig.savefig(out/'three_way_timeline.png',dpi=160);fig.savefig(out/'three_way_timeline.svg');plt.close(fig)
    run=runs[2];r=run['tasks']['xz'];first=min(x for x,y in r['active']);fg_end=run['tasks']['foreground_krita']['end_s'];lo=max(0,first-10);hi=max(lo+60,fg_end+10)
    fig,axs=plt.subplots(2,1,figsize=(13,5),sharex=True,gridspec_kw={'height_ratios':[1,2]})
    for x,y in r['paused']:axs[0].barh(0,y-x,left=x,height=.5,color='#E2E5E9',edgecolor='#ABB3BC',hatch='///',lw=.4)
    for x,y in r['active']:axs[0].barh(0,y-x,left=x,height=.5,color=COLORS[1])
    knots=sorted({lo,hi,fg_end,*[z for interval in r['active'] for z in interval if lo<=z<=hi]})
    axs[1].plot(knots,[overlap(r['active'],0,t) for t in knots],color=COLORS[1],lw=2)
    for ax in axs:ax.set_xlim(lo,hi);ax.axvline(fg_end,color='#64717E',ls='--',label='前台结束');ax.grid(alpha=.2)
    axs[0].set_yticks([0],['XZ状态']);axs[0].set_title('分段冻结：XZ提前执行与反复暂停的实际记录',loc='left',fontweight='bold')
    axs[1].set_ylabel('累计解冻运行时间 / 秒\n（含IO等待，非CPU时间）');axs[1].set_xlabel('从前台自动化启动起的经过时间');axs[1].legend()
    axs[1].xaxis.set_major_formatter(FuncFormatter(lambda x,p:'%02d:%02d'%(int(x//60),int(x%60))))
    fig.tight_layout();fig.savefig(out/'xz_segment_detail.png',dpi=160);plt.close(fig)
    rows='\n'.join('|%s|%s|%.3f|%d|%s|%s|'%(r['label'],stamp(r['total_s']),r['xz_foreground_overlap_s'],r['xz_resume_count'],r['oom_kill'],r['success']) for r in runs)
    (out/'对比说明.md').write_text('# 三轮实测对比\n\n各轮均从前台自动化启动计时，包含冻结等待，不含事前输入检查和事后校验/绘图。\n\n|策略|总耗时 分:秒|XZ与前台累计执行交集 s|XZ恢复次数|OOM kill|四任务成功|\n|---|---:|---:|---:|---:|---|\n'+rows+'\n\n串行Swap开启，两版冻结Swap关闭。两版冻结素材、参数和名义提交偏移保持一致；只报告实测差异，不将单轮差异全部归因为策略。XZ解冻时间包含IO等待，不能等同有效CPU计算时间。原始起止、全部冻结/运行区间和来源摘要见comparison.json。\n')
    print(json.dumps([dict(strategy=r['label'],total_s=r['total_s'],xz_overlap_s=r['xz_foreground_overlap_s'],xz_resumes=r['xz_resume_count'],success=r['success']) for r in runs]))

if __name__=='__main__':main()
