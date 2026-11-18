"""Append model deviation and measured overlap without changing raw evidence."""
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]);d=json.loads((root/'validation.json').read_text());p=root/'report.md';text=p.read_text()
marker='## 先验与实际执行复核'
if marker not in text:
    rows='\n'.join('|%s|%.3f|%.3f|%.1f%%|%.3f|%.3f|'%(op,r['prior_model_peak_GiB'],r['sampled_peak_GiB'],(r['actual_to_prior_peak_ratio']-1)*100,r['sampled_anon_peak_GiB'],r['sampled_file_peak_GiB']) for op,r in d['tasks'].items())
    tasks=d['tasks'];bgs=[tasks[op] for op in ['xz','table','array']]
    overlap=max(0,min(r['empty_confirmed_ns'] for r in bgs)-max(r['actual_start_ns'] for r in bgs))/1e9
    after=all(r['actual_start_ns']>=tasks['foreground_krita']['empty_confirmed_ns'] for r in bgs)
    text+='\n\n'+marker+'\n\n|任务|先验模型峰值 GiB|实测峰值 GiB|相对模型差异|匿名独立峰值 GiB|文件独立峰值 GiB|\n|---|---:|---:|---:|---:|---:|\n'+rows
    text+='\n\n三个后台全部在前台进程退出后开始执行：%s；从首次执行至退出的跨度交集 %.6f 秒（分段模式须排除其中冻结区间后再计算实际解冻交集）。\n'%(after,overlap)
    text+=('这一轮没有前后台执行重叠。' if after else '至少一项后台在前台退出前开始执行；实际解冻重叠区间需以running_intervals_ns复核。')+'不据此声称效率最优。\n'
    x=tasks['xz'];text+='\nXZ总记账峰值相对先验模型差异 %+.1f%%；实测匿名峰值 %.3fGiB，文件记账峰值 %.3fGiB。文件缓存初态、归属与回收可能影响总记账，未通过独立因果实验区分各因素。匿名和文件各自峰值不必同刻，不能直接相加当瞬时峰值。\n'%((x['actual_to_prior_peak_ratio']-1)*100,x['sampled_anon_peak_GiB'],x['sampled_file_peak_GiB'])
    p.write_text(text)
(root/'report_supplement_provenance.json').write_text(json.dumps(dict(script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),validation_sha256=hashlib.sha256((root/'validation.json').read_bytes()).hexdigest(),raw_csv_modified=False),indent=2))
print('supplemented report')
