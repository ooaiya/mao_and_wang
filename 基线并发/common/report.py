"""Render measured scopes without treating PSI as GUI response latency."""
import json
from pathlib import Path


class ReportGenerator:
    def __init__(self,run_dir,experiment_name='OOM concurrency'):
        self.run_dir=Path(run_dir);self.name=experiment_name
    def generate_report(self):
        summary=json.loads((self.run_dir/'summary.json').read_text());stats=summary.get('collector',{})
        total=json.loads((self.run_dir/'environment.json').read_text())['meminfo_bytes']['MemTotal']
        return '\n'.join([f'# {self.name}','',f"运行状态：{summary['status']}",f"原生调度：{summary.get('scheduling',{'policy':'baseline','active_scheduling':False})}",f'实际 MemTotal：{total} Bytes = {total/1e9:.6f} GB = {total/2**30:.6f} GiB',
            f"整机已分配驻留页峰值（MemTotal−MemFree，含缓存）：{stats.get('system_resident_allocated_peak_bytes')} Bytes",
            f"压力占用代理峰值（MemTotal−MemAvailable）：{stats.get('system_pressure_used_peak_bytes')} Bytes",
            f"最低 MemAvailable：{stats.get('min_available_bytes')} Bytes",
            f"低内存事件：{stats.get('low_memory_events')} 次；持续 {stats.get('low_memory_duration_s')} 秒",
            '', '任务级 memory.current / memory.peak 来自独立 cgroup；RSS、PSS、USS、虚拟内存、Swap、磁盘 I/O 分列。',
            '前台响应延迟：NOT_COLLECTED（当前手动前台不采集输入/响应关联）；P50/P95/P99/最大值均为 N/A。PSI 不冒充 GUI 延迟。',
            'OOM 计数增量和内核事件分开记录，SIGKILL 不单独认定为 OOM。全局 OOM 尝试次数若无内核证据则未知。',''])
    def save_report(self,filename='report.md'):
        p=self.run_dir/filename;p.write_text(self.generate_report());return str(p)
