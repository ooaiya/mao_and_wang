"""Run only after validation. Derived figures/report, preserving the raw report."""
import csv,hashlib,json,sys
from pathlib import Path

def main(root):
    root=Path(root);v=json.loads((root/'validation.json').read_text());s=json.loads((root/'summary.json').read_text());p=json.loads((root/'planning/offline_plan.json').read_text())
    if not v['success']:raise RuntimeError('incomplete/failed trial must not be presented as successful throughput')
    a=v['offline_plan_audit'];t0=s['T0_monotonic_ns'];fg_end=(s['tasks']['foreground_krita']['empty_confirmed_ns']-t0)/1e9
    proofs=json.loads((root/'freeze_events.json').read_text());early=next((r for r in proofs if r.get('reason')=='offline_planned_early_resume'),None)
    pause=next((r for r in proofs if early and r['operation']=='xz' and r['action']=='freeze' and r['confirmed_monotonic_ns']>early['confirmed_monotonic_ns']),None)
    actual_start=(early['confirmed_monotonic_ns']-t0)/1e9 if early else None
    actual_pause=(pause['confirmed_monotonic_ns']-t0)/1e9 if pause else None
    xz=s['tasks']['xz'];task_start=(xz['actual_start_ns']-t0)/1e9
    overlap=sum(max(0,min((b-t0)/1e9,fg_end)-max((a-t0)/1e9,task_start)) for a,b in xz['running_intervals_ns'])
    task_rows={'foreground_krita':[],'xz':[]}
    with (root/'task_memory.csv').open() as f:
        for r in csv.DictReader(f):
            if r['operation'] in task_rows:task_rows[r['operation']].append(((int(r['monotonic_ns'])-t0)/1e9,int(r['memory_current_bytes'])/2**30))
    import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    from matplotlib.ticker import FuncFormatter
    font='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc';fm.fontManager.addfont(font)
    plt.rcParams.update({'font.family':fm.FontProperties(fname=font).get_name(),'axes.unicode_minus':False,'svg.fonttype':'none'})
    fig,axs=plt.subplots(3,1,figsize=(13,8),sharex=True,gridspec_kw={'height_ratios':[2,2,1]})
    left=p['search']['selected']['start_s']-35;right=fg_end+30
    for ax,op,color,label in [(axs[0],'foreground_krita','#3478A8','前台实际内存'),(axs[1],'xz','#DD9138','XZ实际内存')]:
        points=[r for r in task_rows[op] if left<=r[0]<=right];ax.plot([x for x,y in points],[y for x,y in points],color=color,lw=1.5,label=label)
        ax.axvline(fg_end,color='#64717E',ls='--',label='前台真实退出');ax.set_ylabel('GiB');ax.grid(alpha=.2);ax.legend(loc='upper right',fontsize=9)
        if actual_start and actual_pause:ax.axvspan(actual_start,actual_pause,color='#DD9138',alpha=.15)
    axs[1].plot([p['search']['selected']['start_s'],fg_end],[p['search']['selected']['held_upper_bytes']/2**30]*2,color='#9B6230',ls=':',label='前台存活期间的冻结驻留上界（含缓冲）');axs[1].legend(fontsize=9)
    for i,op,color in [(0,'foreground_krita','#3478A8'),(1,'xz','#DD9138')]:
        r=s['tasks'][op];intervals=r.get('running_intervals_ns',[[r['created_ns'],r['empty_confirmed_ns']]])
        for x,y in r.get('pause_intervals_ns',[]):axs[2].barh(i,(y-x)/1e9,left=(x-t0)/1e9,color='#DFE4E9',height=.5)
        for x,y in intervals:axs[2].barh(i,(y-x)/1e9,left=(x-t0)/1e9,color=color,height=.5)
    axs[2].set_yticks([0,1],['前台','XZ']);axs[2].invert_yaxis();axs[2].set_xlim(left,right);axs[2].grid(axis='x',alpha=.2)
    axs[2].xaxis.set_major_formatter(FuncFormatter(lambda x,pos:'%02d:%02d'%(int(x//60),int(x%60))));axs[2].set_xlabel('从首页T0起算，彩色为执行，灰色为内核确认冻结')
    fig.suptitle('曲线规划冻结：提前执行、保留驻留、等待真实退出',fontsize=16,fontweight='bold')
    fig.tight_layout(rect=[0,0,1,.95]);fig.savefig(root/'early_xz_detail.png',dpi=170);plt.close(fig)
    with (root/'planning/early_budget.csv').open() as f:rows=list(csv.DictReader(f))
    fig,ax=plt.subplots(figsize=(13,5));times=[float(r['homepage_s']) for r in rows];reserved=[int(r['reserved_bytes'])/2**30 for r in rows]
    ax.plot(times,reserved,color='#7760AC',label='规划总预算（含安全预留及冻结驻留）');ax.axhline(p['budget']['memtotal_bytes']/2**30,color='#BD3D3D',ls='--',label='实际RAM容量')
    plan=p['search']['selected'];ax.axvspan(plan['start_s'],plan['freeze_request_s'],color='#DD9138',alpha=.25,label='事前计划的XZ执行区间')
    ax.set_xlabel('首页T0后 / 秒');ax.set_ylabel('GiB');ax.grid(alpha=.2);ax.legend();ax.set_title('事前曲线预算，不是实测内存曲线')
    fig.tight_layout();fig.savefig(root/'planning_budget.png',dpi=170);plt.close(fig)
    previous=json.loads((root/'comparison/comparison.json').read_text())
    old=previous[1]['total_s'];serial=previous[0]['total_s'];new=v['total_from_first_launch_s'];io=a['io_receipt']
    report='''# 曲线规划冻结实机结果

本轮四任务全部正确完成：**%s**。全程关闭Swap：**%s**。全局OOM kill增量：**%s**。已验证前台存活时XZ实际读取并压缩：**%s**。

## 固定计划与实际执行

|项目|结果|
|---|---:|
|离线计划XZ恢复：首页后|%.3fs|
|离线计划再次冻结：首页后|%.3fs|
|实际内核确认恢复：首页后|%s|
|实际内核确认再次冻结：首页后|%s|
|XZ在前台期间实际执行交集（扣除任务启动前）|%.3fs|
|再次冻结时XZ记账|%s|
|前台真实退出：首页后|%.3fs|
|规划冻结驻留上界（含反应及进度误差）|%.3fGiB|

冻结不会释放工作内存。窗口结束后XZ保留已完成进度和内存，直到前台进程组真实退出后恢复。运行中不争取新执行时间片，也不做压力分级或公平轮转。现场检查只对固定计划否决、取消或延迟。

## 完成耗时对照

统一从前台动作脚本启动计时，包含冻结等待，不含事前检查和事后校验/绘图。

|轮次|总耗时|
|---|---:|
|串行（Swap开启）|%.3fs|
|第一版冻结（Swap关闭）|%.3fs|
|本轮曲线规划冻结（Swap关闭）|%.3fs|

事前预计比第一版节省%.3fs；实测差值为%.3fs（正数为本轮更快）。单轮执行速度、缓存和环境波动会影响结果，不能把差值全部归因于调度。串行Swap状态不同，只作参考。

## 保护与证据

最低可用内存%.3fGiB，最大采样间隔%.6fs。原Swap已恢复：%s。

离线搜索及预算复核错误：%s。所有恢复只来自预定窗口或真实退出屏障。原生Oracle继续负责前台退出后的Table/Array放行，完整XZ校准峰值持续计入续跑预算。

XZ输入/输出位置回执：%s。

## 模型边界

前台早期预算使用已有前台独立采集与第一版前台独占阶段的同期系统压力曲线，并加5%%前台任务误差，保留时间相关性。系统常驻占用已包含其中，不再重复加固定高水位。XZ包络包含第一版实测的文件缓存偏差，原11.6%%RAM安全预留保留。窗口含±60s前台时序不确定性、较快XZ进度和停止反应缓冲。

历史包络不是未知分配行为的硬上界。本轮结果只验证当前素材、参数及环境，不能声称任意任务不会OOM。前台成功仍指1350s定时窗口、八阶段通过和正常退出，不声称通过无障碍图层表确认了全部导入完成。

## 文件

`early_xz_detail.png`：实际提前执行与再次冻结放大图。

`planning_budget.png`：事前预测预算。

`freezer_memory.png`：整轮实测内存与时序。

`comparison/three_way_timeline.png`：串行、第一版冻结和本轮实际时序对比。

原始采样、内核确认、决策回执、输入摘要与验证结果保留。首版代码及结果未覆盖，修改前第二版另存本地准备目录。
'''%(v['success'],v['swap_zero_all_formal_samples'],v['global_oom_kill_delta'],a['real_xz_progress_while_foreground_alive'],
        plan['start_s'],plan['freeze_request_s'],('%.6fs'%actual_start if actual_start else '无'),('%.6fs'%actual_pause if actual_pause else '无'),
        overlap,('%.3fGiB'%(pause['memory_current_bytes']/2**30) if pause else '无'),fg_end,plan['held_upper_bytes']/2**30,
        serial,old,new,p['prediction']['estimated_saving_s'],old-new,v['system_min_available_GiB'],v['sampling']['max_gap_s'],v['swap_restoration']['restored'],a['errors'],json.dumps(io,ensure_ascii=False))
    decomposition=root/'comparison/duration_decomposition.json'
    if decomposition.exists():
        d=json.loads(decomposition.read_text())
        report+='\n## 耗时差值的算术拆分\n\n第一版XZ实际执行%.3fs，本轮扣除冻结及启动准备后实际执行%.3fs，相差%.3fs。前台时长变化贡献%.3fs，提前重叠贡献%.3fs，交接变化贡献%.3fs，合计%.3fs。这里是时间账本拆分，不能据此确定执行速度变化的原因。\n'%(d['old_xz_active_s'],d['new_xz_active_s'],d['xz_active_duration_contribution_s'],d['foreground_duration_contribution_s'],d['overlap_contribution_s'],d['handoff_contribution_s'],d['contribution_sum_s'])
    old_report=root/'report.md';before=old_report.read_bytes();original=root/'report.original.md'
    if not original.exists():original.write_bytes(before)
    old_report.write_text(report)
    (root/'report_supplement_provenance.json').write_text(json.dumps(dict(original_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),report_sha256=hashlib.sha256(report.encode()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),raw_csv_modified=False),indent=2))
    print(json.dumps(dict(success=v['success'],optimization_success=v['optimization_success'],total_s=new,first_total_s=old,saving_s=old-new,early_actual_s=overlap)))

if __name__=='__main__':main(sys.argv[1])
