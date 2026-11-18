import platform
import shutil
from pathlib import Path
from .common import command, privileged, resource_check, GIB, meminfo

CONTROLS = ('memory.current', 'memory.peak', 'memory.stat', 'memory.events',
            'memory.max', 'cgroup.freeze', 'cgroup.events')


def check_controls(root):
    for name in CONTROLS:
        p = Path(root) / name
        if not p.is_file():
            raise RuntimeError(f'缺少 cgroup v2 控制文件：{p}')
        try:
            p.read_text()
        except PermissionError as e:
            raise RuntimeError(f'无权读取 cgroup 控制文件：{p}') from e


def check_environment(directory, safety_gib=8):
    errors = []
    info = {'platform': platform.platform(), 'pid1': Path('/proc/1/comm').read_text().strip()}
    info['os_release'] = platform.freedesktop_os_release()
    info['kernel'] = platform.release()
    info['target'] = {'os': 'Ubuntu 22.04.5 LTS', 'kernel': '6.17.13', 'memory_gb': 16}
    info['target_matches'] = (info['os_release'].get('ID') == 'ubuntu'
                              and info['os_release'].get('VERSION_ID') == '22.04'
                              and info['kernel'].split('-')[0] == '6.17.13')
    if not info['target_matches']:
        errors.append('目标版本不匹配：要求 Ubuntu 22.04.5 LTS / Linux 6.17.13；当前值已记录')
    info['capabilities'] = {}
    for file in ('cgroup.freeze', 'memory.pressure', 'cpu.pressure', 'io.pressure', 'memory.stat'):
        path = Path('/sys/fs/cgroup') / file
        info['capabilities'][file] = {'readable': path.is_file() and __import__('os').access(path, 4),
                                    'writable_as_user': path.is_file() and __import__('os').access(path, 2)}
    statfile = Path('/sys/fs/cgroup/memory.stat')
    info['memory_stat_fields'] = [line.split()[0] for line in statfile.read_text().splitlines()] if statfile.exists() else []
    for name in ('python3', 'systemctl', 'systemd-run', 'xz'):
        if not shutil.which(name):
            errors.append(f'缺少命令 {name}')
    if info['pid1'] != 'systemd':
        errors.append('PID 1 不是 systemd；请在 Ubuntu 主机上运行，不能在普通容器内采集')
    if not Path('/sys/fs/cgroup/cgroup.controllers').exists():
        errors.append('未挂载统一 cgroup v2')
    else:
        info['controllers'] = Path('/sys/fs/cgroup/cgroup.controllers').read_text().strip()
        for controller in ('memory', 'cpu', 'io'):
            if controller not in info['controllers'].split():
                errors.append(f'cgroup v2 {controller} controller 不可用')
    for module in ('numpy', 'pandas'):
        try:
            imported = __import__(module)
            info[module + '_version'] = imported.__version__
        except ImportError:
            errors.append(f'缺少 Python 依赖 {module}；请在当前 venv 安装 requirements.txt')
    try:
        manager = privileged(['systemctl', 'show', '--property=Version'])
        info['systemd_version'] = manager.stdout.strip()
    except Exception as e:
        errors.append(f'无法访问系统 systemd manager 或 sudo -n 权限不足：{e}')
    info.update(meminfo_bytes=meminfo(), swap=Path('/proc/swaps').read_text(),
                disk_free_bytes=shutil.disk_usage(directory).free)
    try:
        info.update(resource_check(directory, (safety_gib + 2) * GIB, GIB))
    except RuntimeError as e:
        errors.append(str(e))
    info['errors'] = errors
    info['ok'] = not errors
    # Root cgroup may legitimately omit memory.max; validate actual service after creation.
    return info
