#!/usr/bin/env python3
"""
进程管理模块
负责启动、监控、停止后台操作进程
"""
import os
import time
import subprocess
import signal
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ProcessInfo:
    """进程信息"""
    name: str
    pid: Optional[int] = None
    cgroup_path: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    return_code: Optional[int] = None
    status: str = 'not_started'  # not_started / running / finished / failed / killed
    command: Optional[str] = None


class ProcessManager:
    """进程管理器"""
    
    def __init__(self, cgroup_root: str = '/sys/fs/cgroup'):
        self.cgroup_root = Path(cgroup_root)
        self.processes: Dict[str, ProcessInfo] = {}
    
    def register_process(self, name: str, command: str, cgroup_name: Optional[str] = None) -> ProcessInfo:
        """注册一个进程（还没启动）"""
        info = ProcessInfo(
            name=name,
            command=command,
            cgroup_path=str(self.cgroup_root / cgroup_name) if cgroup_name else None,
        )
        self.processes[name] = info
        return info
    
    def start_process_simple(self, name: str, command: str) -> bool:
        """简单启动进程（不用 systemd-run，直接 subprocess）"""
        info = self.processes.get(name)
        if not info:
            info = self.register_process(name, command)
        
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            
            info.pid = proc.pid
            info.start_time = time.time()
            info.status = 'running'
            return True
        except Exception as e:
            info.status = 'failed'
            return False
    
    def check_process(self, name: str) -> Tuple[str, Optional[int]]:
        """检查进程状态"""
        info = self.processes.get(name)
        if not info or not info.pid:
            return 'not_started', None
        
        try:
            os.kill(info.pid, 0)
            return 'running', info.pid
        except ProcessLookupError:
            info.status = 'finished'
            info.end_time = time.time()
            return 'finished', None
        except PermissionError:
            return 'no_permission', info.pid
    
    def stop_process(self, name: str, timeout_s: int = 10) -> bool:
        """停止进程"""
        info = self.processes.get(name)
        if not info or not info.pid:
            return False
        
        try:
            os.killpg(os.getpgid(info.pid), signal.SIGTERM)
            
            for _ in range(timeout_s):
                time.sleep(1)
                try:
                    os.kill(info.pid, 0)
                except ProcessLookupError:
                    info.status = 'finished'
                    info.end_time = time.time()
                    return True
            
            os.killpg(os.getpgid(info.pid), signal.SIGKILL)
            info.status = 'killed'
            info.end_time = time.time()
            return True
        except Exception as e:
            return False
    
    def get_all_status(self) -> Dict:
        """获取所有进程状态"""
        result = {}
        for name, info in self.processes.items():
            status, pid = self.check_process(name)
            result[name] = {
                'status': status,
                'pid': pid,
                'start_time': info.start_time,
                'duration_s': (time.time() - info.start_time) if info.start_time else 0,
            }
        return result


if __name__ == '__main__':
    pm = ProcessManager()
    print('ProcessManager created')
