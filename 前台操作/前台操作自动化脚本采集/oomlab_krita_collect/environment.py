import os
import platform
import re
import shutil
import socket
import stat
import sys
from pathlib import Path
from .common import SCHEMA, command, source_identity, outside_repo
from .asset import pinned
from .metrics import psi

REQUIRED = ('memory.current','memory.peak','memory.stat','memory.events','memory.pressure','cgroup.procs','cgroup.events')


def controls(path):
    capability={}
    for name in REQUIRED+('memory.swap.current','memory.events.local'):
        try: (Path(path)/name).read_text(); capability[name]=True
        except FileNotFoundError: capability[name]=False
        if name in REQUIRED and not capability[name]: raise RuntimeError('missing cgroup control: '+name)
    return capability


def conflicts(c):
    found=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit(): continue
        try:
            name=(entry/'comm').read_text().strip()
            args=(entry/'cmdline').read_bytes().split(b'\0')
            rss=next((int(line.split()[1])*1024 for line in (entry/'status').read_text().splitlines() if line.startswith('VmRSS:')),0)
            if name.casefold() in [p.casefold() for p in c['forbidden_processes']] or name.startswith('memshift') or name=='ms_freezer_guard' or (b'oomlab.workloads' in args) or (int(entry.name)!=os.getpid() and rss>c['safety']['max_other_process_rss_bytes']):
                found.append(dict(pid=int(entry.name),comm=name,rss_bytes=rss))
        except (FileNotFoundError,ProcessLookupError): continue
    for user in [True,False]:
        args=['systemctl']+(['--user'] if user else [])+['list-units','--all','--no-legend','--plain','--no-pager']
        text=command(args).stdout
        for line in text.splitlines():
            fields=line.split()
            if len(fields)>=4 and fields[2] in ('active','activating','deactivating') and (any(re.search(pattern,fields[0],re.I) for pattern in c['forbidden_units']) or fields[0].startswith(('oomcollect-','oomlab-a-'))):
                found.append(dict(unit=fields[0],user_manager=user))
    for path in c['forbidden_sockets']:
        if Path(os.path.expandvars(path)).exists(): found.append(dict(socket=path))
    return found


def check(c,results,require_gui=True):
    errors=[]; info=dict(schema_version=SCHEMA,python=sys.version,kernel=platform.release(),platform=platform.platform(),
                         session_id=os.getenv('XDG_SESSION_ID'),session_type=os.getenv('XDG_SESSION_TYPE'),
                         wayland_display=os.getenv('WAYLAND_DISPLAY'),display=os.getenv('DISPLAY'))
    def probe(name,fn):
        try: info[name]=fn()
        except Exception as e: errors.append(name+': '+str(e))
    if os.geteuid()==0: errors.append('run as the logged-in desktop user, never sudo python')
    probe('source',source_identity)
    probe('boot_id',lambda:Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    probe('distribution',lambda:platform.freedesktop_os_release())
    if info.get('source',{}).get('git_branch') not in ('main', 'mxt'): errors.append('formal collection requires main or mxt branch')
    probe('conflicts',lambda:conflicts(c))
    if info.get('conflicts'): errors.append('conflicting processes/units/sockets present')
    for tool in ['systemd-run','systemctl','journalctl','python3']+(['krita','wmctrl','xdotool','xdpyinfo','xprop','xwininfo'] if require_gui else []):
        if not shutil.which(tool): errors.append('missing tool: '+tool)
    probe('user_manager',lambda:command(['systemctl','--user','show','--property=Version']).stdout.strip())
    probe('cgroup_v2',lambda:(Path('/sys/fs/cgroup/cgroup.controllers').read_text().split()))
    if 'memory' not in info.get('cgroup_v2',[]): errors.append('unified cgroup v2 memory unavailable')
    def current_controls():
        from .units import process_cgroup
        path=Path('/sys/fs/cgroup')/process_cgroup(os.getpid()).lstrip('/')
        return dict(path=str(path),capabilities=controls(path))
    probe('cgroup_controls',current_controls)
    info['measurement_boundary']=dict(kind='unique systemd user UUID service/slice',cgroup_path=None,status='NOT_CREATED; resolved and verified from manager before start gate')
    if require_gui:
        if info.get('source',{}).get('source_dirty') is not False:errors.append('formal collection requires committed clean source')
        if info.get('distribution',{}).get('ID')!='ubuntu' or info.get('distribution',{}).get('VERSION_ID')!='22.04' or info['kernel'].split('-')[0]!='6.17.13':
            errors.append('formal target requires Ubuntu 22.04.5 LTS / Linux 6.17.13')
        if info['session_type']!='wayland' or not info['wayland_display'] or not info['display']: errors.append('Wayland session, WAYLAND_DISPLAY and DISPLAY required')
        def wayland():
            value=info['wayland_display']
            if not value: raise RuntimeError('WAYLAND_DISPLAY missing')
            path=Path(value) if value.startswith('/') else Path(os.environ['XDG_RUNTIME_DIR'])/value
            if not stat.S_ISSOCK(path.stat().st_mode): raise RuntimeError('not a Wayland socket')
            return str(path)
        probe('wayland_socket',wayland)
        probe('xdpyinfo',lambda:command(['xdpyinfo']).stdout[:2000])
        probe('display_size',lambda:[int(x) for x in command(['xdotool','getdisplaygeometry']).stdout.split()])
        if info.get('display_size')!=c['display_size']: errors.append('display geometry differs from audited coordinates')
        probe('xwayland_pids',lambda:[int(p.name) for p in Path('/proc').iterdir() if p.name.isdigit() and _comm(p)=='Xwayland'])
        if not info.get('xwayland_pids'): errors.append('XWayland process not found')
        probe('krita_version',lambda:command(['env','QT_QPA_PLATFORM=xcb','krita','--version']).stdout.strip())
        if c.get('mode')=='pilot':
            from .pilot_assets import inventory
            from .common import GUI
            probe('assets_manifest',lambda:inventory(c))
            if 'assets_manifest' in info:info['asset']=info['assets_manifest']['ora']
            def accessibility():
                import json
                data=json.loads(command([c['automation']['accessibility_python'],GUI/'scripts/krita_accessibility.py','--probe'],timeout=10).stdout)
                if data.get('ok') is not True:raise RuntimeError('AT-SPI unavailable: '+str(data))
                return data
            probe('accessibility',accessibility)
            probe('xcb_plugin_files',lambda:[str(p) for p in Path('/usr/lib').glob('**/platforms/libqxcb.so')])
            if not info.get('xcb_plugin_files'):errors.append('Qt xcb plugin file missing')
            info['qt_actual_process_validation']='NOT_RUN; checked from owned PID maps after startup'
        else:probe('asset',lambda:pinned(c['asset']))
    probe('global_psi',lambda:psi(Path('/proc/pressure/memory').read_text()))
    def resources():
        values={}
        for line in Path('/proc/meminfo').read_text().splitlines():
            key,value=line.split(':',1)
            if key in ['MemTotal','MemAvailable','SwapTotal','SwapFree']: values[key]=int(value.split()[0])*1024
        path=outside_repo(results)
        existing=path
        while not existing.exists(): existing=existing.parent
        values['disk_free_bytes']=shutil.disk_usage(existing).free
        values['swap_text']=Path('/proc/swaps').read_text()
        return values
    probe('resources',resources)
    s=c['safety']; r=info.get('resources',{})
    for metric,threshold in [('MemAvailable','min_available_bytes'),('SwapFree','min_swap_free_bytes'),('disk_free_bytes','min_disk_free_bytes')]:
        if r.get(metric,-1)<s[threshold]: errors.append(metric+' below explicit safety threshold')
    if info.get('global_psi',{}).get('full_avg10') is None or info['global_psi']['full_avg10']>s['max_global_full_avg10']: errors.append('global PSI unsafe or missing')
    info.update(ok=not errors,errors=errors)
    return info


def _comm(path):
    try:return (path/'comm').read_text().strip()
    except (FileNotFoundError,ProcessLookupError,PermissionError):return ''
