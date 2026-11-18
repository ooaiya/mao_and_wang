#!/usr/bin/env python3
"""Owned Krita automation: strict layer verification or an explicit timed window."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
import traceback


class GuiPending(RuntimeError):pass
class StopRequested(RuntimeError):pass

CTX=dict(process=None,pid=None,wid=None,birth=None,control=None,settings={},record=None,asset=None,document_open=False)
DEFAULTS=dict(startup_timeout_s=60,open_timeout_s=600,import_timeout_s=600,close_timeout_s=60,
              unresponsive_timeout_s=30,poll_s=.5,accessibility_python='/usr/bin/python3',graceful_stop_timeout_s=10)


def emit(kind,**fields):
    payload=dict(schema_version=1,kind=kind,monotonic_ns=time.monotonic_ns(),wall_time_ns=time.time_ns());payload.update(fields)
    print('@@OOM_EVENT '+json.dumps(payload,ensure_ascii=False),flush=True)
    return payload


def check_stop():
    if CTX.get('control') and Path(CTX['control']).exists():
        value=json.loads(Path(CTX['control']).read_text());raise StopRequested(value.get('reason','采集器请求安全停止'))


def run(cmd,timeout=10,allow_stop=True):
    if allow_stop:check_stop()
    if CTX.get('shutdown_deadline'):
        remaining=CTX['shutdown_deadline']-time.monotonic()
        if remaining<=0:raise TimeoutError('优雅退出期限已到')
        timeout=min(timeout,remaining)
    args=shlex.split(cmd) if isinstance(cmd,str) else [str(x) for x in cmd]
    if args[:1]==['xdotool'] and args[1:2] in (['key'],['type'],['click'],['mousemove']):
        owned();active=run(['xdotool','getactivewindow']);raw=run(['xprop','-id',active,'_NET_WM_PID'])
        if not re.search(r'=\s*'+str(CTX['pid'])+r'\s*$',raw):raise RuntimeError('输入前焦点不属于本轮Krita')
    print('  [cmd] '+shlex.join(args),flush=True)
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError(f'{args[0]} exit={p.returncode}: {p.stderr.strip()}')
    return p.stdout.strip()


def identity(pid):
    p=Path('/proc')/str(pid);raw=(p/'stat').read_text();fields=raw[raw.rindex(')')+2:].split()
    return dict(pid=pid,ppid=int(fields[1]),starttime=int(fields[19]),exe=os.readlink(p/'exe'),cgroup=(p/'cgroup').read_text().strip())


def owned():
    p=CTX['process']
    if not p or p.poll() is not None:raise RuntimeError('本轮Krita已退出')
    info=identity(CTX['pid'])
    if info['ppid']!=os.getpid() or info['starttime']!=CTX['birth'] or Path(info['exe']).name.lower()!='krita':raise RuntimeError('本轮Krita进程身份改变')
    return info


def windows():
    result=[]
    for line in run(['wmctrl','-lpG']).splitlines():
        parts=line.split(None,8)
        if len(parts)==9:result.append(dict(id=parts[0],pid=int(parts[2]),x=int(parts[3]),y=int(parts[4]),width=int(parts[5]),height=int(parts[6]),title=parts[8]))
    return result


def find_window(title_keyword,exclude_keyword='',modal=False):
    owned();matches=[]
    for w in windows():
        if w['pid']!=CTX['pid'] or title_keyword.lower() not in w['title'].lower() or (exclude_keyword and exclude_keyword.lower() in w['title'].lower()):continue
        raw=run(['xprop','-id',w['id'],'_NET_WM_PID','WM_CLASS','_NET_WM_WINDOW_TYPE','WM_TRANSIENT_FOR'])
        if not re.search(r'_NET_WM_PID\(CARDINAL\)\s*=\s*'+str(CTX['pid'])+r'\b',raw):raise RuntimeError('窗口PID属性不匹配')
        classes=re.search(r'WM_CLASS\(STRING\).*',raw)
        if not classes or not re.search(r'"krita"',classes.group(),re.I):continue
        target='_NET_WM_WINDOW_TYPE_DIALOG' if modal else '_NET_WM_WINDOW_TYPE_NORMAL'
        if target not in raw:continue
        if modal:
            transient=re.search(r'WM_TRANSIENT_FOR[^\n]*(0x[0-9a-fA-F]+)',raw)
            if not transient or int(transient.group(1),16)!=int(CTX['wid'],16):continue
        if 'IsViewable' not in run(['xwininfo','-id',w['id']]):continue
        w['xproperties']=raw;matches.append(w)
    if len(matches)>1:
        if modal:raise RuntimeError('本轮对话框候选不唯一')
        matches.sort(key=lambda w:w['width']*w['height'],reverse=True)
        if matches[0]['width']*matches[0]['height']==matches[1]['width']*matches[1]['height']:raise RuntimeError('本轮主窗口面积不唯一')
        matches=matches[:1]
    return matches[0] if matches else None


def wait_until(probe,timeout,description):
    deadline=min(time.monotonic()+timeout,CTX.get('shutdown_deadline',float('inf')));last=None;unresponsive_since=None
    while True:
        check_stop();owned()
        try:
            value=probe()
            if value:return value
        except (GuiPending,subprocess.TimeoutExpired) as e:
            last=repr(e)
            if isinstance(e,subprocess.TimeoutExpired):
                unresponsive_since=unresponsive_since or time.monotonic()
                if time.monotonic()-unresponsive_since>=CTX['settings']['unresponsive_timeout_s']:raise TimeoutError('Krita/窗口查询持续无响应：'+description)
        else:unresponsive_since=None
        if time.monotonic()>=deadline:raise TimeoutError(description+'；最后诊断='+str(last))
        time.sleep(CTX['settings']['poll_s'])


def wait_for_window(title_keyword,timeout=10,exclude_keyword='',modal=False):
    return wait_until(lambda:find_window(title_keyword,exclude_keyword,modal),timeout,'等待窗口超时：'+title_keyword)


def wait_window_disappear(wid,timeout=10):
    return wait_until(lambda:not any(int(w['id'],16)==int(wid,16) for w in windows()),timeout,'窗口未关闭')


def focus(wid):
    owned()
    # EWMH activation can be rejected by an XWayland WM. Use the exact owned
    # client as the fallback, without clicking or drawing on the canvas.
    try:run(['xdotool','windowactivate','--sync',wid],timeout=3)
    except (RuntimeError,subprocess.TimeoutExpired):run(['xdotool','windowfocus','--sync',wid],timeout=3)
    active=run(['xdotool','getactivewindow'])
    if int(active,0)!=int(wid,16):raise RuntimeError('窗口焦点未激活')


def click(x,y):
    owned();active=run(['xdotool','getactivewindow']);raw=run(['xprop','-id',active,'_NET_WM_PID'])
    if not re.search(r'=\s*'+str(CTX['pid'])+r'\s*$',raw):raise RuntimeError('拒绝向其他进程输入')
    run(['xdotool','mousemove',str(x),str(y),'click','1'])


def submit_paths(dialog,paths):
    """Replace a remembered Qt path in full; never append to it."""
    if not paths or any(any(c in p for c in ('"','\n','\r')) for p in paths):raise ValueError('ambiguous dialog paths')
    focus(dialog['id'])
    run(['xdotool','key','--clearmodifiers','ctrl+l']);time.sleep(.3)
    run(['xdotool','key','--clearmodifiers','ctrl+a']);time.sleep(.2)
    text=paths[0] if len(paths)==1 else ' '.join('"'+p+'"' for p in paths)
    run(['xdotool','type','--clearmodifiers','--delay','1',text],timeout=20)
    run(['xdotool','key','--clearmodifiers','Return'])


def zoom_canvas(steps):
    focus(CTX['wid'])
    raw=run(['xwininfo','-id',CTX['wid']])
    values={k:int(re.search(pattern,raw).group(1)) for k,pattern in {
        'x':r'Absolute upper-left X:\s*(-?\d+)','y':r'Absolute upper-left Y:\s*(-?\d+)',
        'width':r'Width:\s*(\d+)','height':r'Height:\s*(\d+)'}.items()}
    # Move only: a focus click here would paint on the document.
    run(['xdotool','mousemove',str(values['x']+values['width']//2),str(values['y']+values['height']//2)])
    for button in steps:
        run(['xdotool','click',button])
    return values


def zoom_relative():
    values=zoom_canvas('44455')
    emit('CANVAS_ZOOM_DONE',method='owned-window-relative wheel sequence; no canvas click',geometry=values)


def prepare_window():
    focus(CTX['wid'])
    def usable():
        window=find_window('Krita','Open Images')
        return window if window and window['id']==CTX['wid'] and window['width']>=900 and window['height']>=600 else None
    window=wait_until(usable,CTX['settings']['startup_timeout_s'],'本轮主窗口尺寸不足或不可见')
    emit('WINDOW_LAYOUT_READY',window=window,method='owned visible geometry; maximization not required')
    return window


def main_window():
    window=find_window('Krita','Open Images')
    # Krita's 640x537 startup/helper window also has NORMAL type and the same
    # PID. Never bind it as the main window, even if its geometry is stable.
    return window if window and window['width']>=900 and window['height']>=600 else None


def import_dialog():
    """Invoke the named menu action, independent of menu pixel coordinates."""
    focus(CTX['wid']);logpath=Path(CTX['record']).with_name('import-action.log') if CTX.get('record') else None
    with (logpath.open('w') if logpath else open(os.devnull,'w')) as log:
        action=subprocess.Popen([CTX['settings']['accessibility_python'],str(Path(__file__).with_name('krita_action.py')),
                                 '--pid',str(CTX['pid'])],stdout=log,stderr=subprocess.STDOUT)
    CTX['action_process']=action
    # Qt's accessibility action may block until the file dialog closes.
    return wait_for_window('',CTX['settings']['import_timeout_s'],modal=True)


def capture_window(submitted_ns,duration_s):
    """Elapsed time never implies verified layer count or import completion."""
    emit('CAPTURE_WINDOW_START',origin_monotonic_ns=submitted_ns,duration_s=duration_s,completion_mode='timed_window')
    deadline=submitted_ns+int(duration_s*1e9)
    while True:
        check_stop();owned()
        remaining=(deadline-time.monotonic_ns())/1e9
        if remaining<=0:break
        time.sleep(min(.2,remaining))
    emit('CAPTURE_WINDOW_DONE',origin_monotonic_ns=submitted_ns,duration_s=duration_s,
         actual_elapsed_s=(time.monotonic_ns()-submitted_ns)/1e9,import_verified=False)


def probe_state():
    owned()
    timed=CTX['settings'].get('completion_mode')=='timed_window'
    helper=Path(__file__).with_name('krita_action.py' if timed else 'krita_accessibility.py')
    command=[CTX['settings']['accessibility_python'],str(helper),'--pid',str(CTX['pid'])]+(['--snapshot'] if timed else [])
    p=subprocess.run(command,capture_output=True,text=True,timeout=min(5,max(.01,CTX.get('shutdown_deadline',time.monotonic()+5)-time.monotonic())))
    try:data=json.loads(p.stdout.splitlines()[-1])
    except (ValueError,IndexError):raise GuiPending('可访问性诊断无有效JSON：'+p.stderr)
    if CTX.get('record'):
        out=Path(CTX['record']).with_name('accessibility-last.json');temp=out.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False));temp.replace(out)
    emit('ACCESSIBILITY_QUERY',pid=CTX['pid'],ok=data.get('ok'),retryable=data.get('retryable'),candidates=data.get('candidates',[]),selected_application=data.get('selected_application'),diagnostic=data.get('error'))
    if not data.get('ok'):
        if data.get('retryable') is False:raise RuntimeError(data.get('error','AT-SPI应用选择失败'))
        raise GuiPending(data.get('error','AT-SPI未就绪'))
    if data.get('pid')!=CTX['pid']:raise RuntimeError('可访问性PID不匹配')
    return data


def layer_count():
    state=probe_state();views=state.get('layer_views',[])
    if len(views)!=1:raise GuiPending('没有唯一的Layers可访问性表：'+json.dumps(state,ensure_ascii=False))
    return views[0]['row_count']


def expected_layers(count):
    actual=layer_count()
    if actual>count:raise RuntimeError(f'图层数量超过预期：{actual}/{count}')
    return actual==count


def normalize_button_label(name):
    return re.sub(r'\s*[（(][A-Za-z][)）]\s*$','',name.replace('&','')).strip().casefold()


def discard_target(state,basename):
    choices=[]
    labels={"don't save",'dont save','discard','no','不保存','放弃','否','不儲存'}
    for dialog in state.get('dialogs',[]):
        text=' '.join(dialog.get('text',[]))
        if not any(re.search(r'(?<![\w.])'+re.escape(name)+r'(?![\w.])',text,re.I) for name in {basename,Path(basename).stem}) or not re.search(r'save|保存|儲存',text,re.I):continue
        choices.extend(b for b in dialog.get('buttons',[]) if normalize_button_label(b.get('name','')) in labels and len(b.get('box',[]))==4 and min(b['box'][2:])>0)
    if len(choices)!=1:raise GuiPending('没有唯一的本轮文档不保存按钮')
    return choices[0]['box']


def document_named(window):
    if window['pid']!=CTX['pid']:return False
    stem=Path(CTX['asset']).stem
    return bool(re.search(r'(?<![\w.])'+re.escape(stem)+r'(?:\.ora)?(?![\w.])',window['title'],re.I))


def open_document(asset=None,submitted_kind=None):
    timeout=CTX['settings']['open_timeout_s']
    if asset is not None:
        if CTX['document_open']:raise RuntimeError('切换素材前必须关闭当前文档')
        CTX['asset']=asset
    focus(CTX['wid']);run(['xdotool','key','ctrl+o'])
    dialog=wait_for_window('Open Images',timeout,modal=True)
    submit_paths(dialog,[CTX['asset']])
    if submitted_kind:emit(submitted_kind,asset=CTX['asset'])
    wait_window_disappear(dialog['id'],timeout)
    wait_until(lambda:any(document_named(w) for w in windows()),timeout,'素材加载超时')
    CTX['document_open']=True


def review_canvas(label,duration_s,interval_s):
    """Bounded zoom in/out cycles on the owned blank document."""
    start=emit(label+'_START',duration_s=duration_s,pid=CTX['pid'])['monotonic_ns']
    deadline=start+round(duration_s*1e9)
    cadence=round(interval_s*1e9)
    next_action=start
    count=0
    while True:
        check_stop();owned()
        now=time.monotonic_ns()
        if now>=deadline:
            break
        if now>=next_action:
            if not any(document_named(window) for window in windows()):
                raise RuntimeError('轻量浏览文档未打开')
            zoom_canvas('45')
            count+=1
            next_action=start+((time.monotonic_ns()-start)//cadence+1)*cadence
        else:
            time.sleep(min(.2,(next_action-now)/1e9,(deadline-now)/1e9))
    emit(label+'_DONE',duration_s=duration_s,pid=CTX['pid'],zoom_cycles=count)


def close_document():
    focus(CTX['wid']);run(['xdotool','key','ctrl+w'])
    def prompt_or_closed():
        if not any(document_named(w) for w in windows()):return 'closed'
        if CTX['settings'].get('prepared_document') and not find_window('',modal=True):
            return None
        return discard_target(probe_state(),Path(CTX['asset']).name)
    box=wait_until(prompt_or_closed,CTX['settings']['close_timeout_s'],'保存提示无法验证')
    if box!='closed':
        if CTX['settings'].get('completion_mode')=='timed_window':
            # Let the actual, document-bound button perform its action. Qt's
            # reported global extents need not match XWayland frame offsets.
            owned();path=Path(CTX['record']).with_name('discard-action.log') if CTX.get('record') else Path(os.devnull)
            with path.open('w') as log:
                CTX['discard_process']=subprocess.Popen([CTX['settings']['accessibility_python'],str(Path(__file__).with_name('krita_action.py')),
                    '--pid',str(CTX['pid']),'--discard-document',Path(CTX['asset']).name],stdout=log,stderr=subprocess.STDOUT)
        else:
            current=discard_target(probe_state(),Path(CTX['asset']).name)
            if current!=box:raise RuntimeError('保存对话框几何已变化')
            click(box[0]+box[2]//2,box[1]+box[3]//2)
        wait_until(lambda:not any(document_named(w) for w in windows()),CTX['settings']['close_timeout_s'],'文档未关闭')
    CTX['document_open']=False


def graceful_shutdown():
    """Only owned-window shortcuts; no signals or broad process-name cleanup."""
    if not CTX.get('process') or CTX['process'].poll() is not None:return True
    control=CTX.get('control');CTX['control']=None
    deadline=time.monotonic()+CTX['settings'].get('graceful_stop_timeout_s',10)
    CTX['shutdown_deadline']=deadline
    try:
        if CTX.get('document_open'):
            try:close_document()
            except Exception as e:emit('GRACEFUL_CLOSE_DIAGNOSTIC',error_message=repr(e))
        if time.monotonic()<deadline and CTX.get('wid'):
            focus(CTX['wid']);run(['xdotool','key','ctrl+q'])
            CTX['process'].wait(timeout=max(.1,deadline-time.monotonic()))
        return CTX['process'].poll() is not None
    except Exception as e:emit('GRACEFUL_EXIT_DIAGNOSTIC',error_message=repr(e));return False
    finally:CTX['control']=control;CTX.pop('shutdown_deadline',None)


@contextmanager
def phase(number,name):
    print(f'\n[{number}/8] {name}...',flush=True);start=time.monotonic_ns()
    emit('phase_start',phase=number,phase_name=name,start_timestamp_ns=start,status='RUNNING')
    try:
        check_stop();yield
    except Exception as e:
        end=time.monotonic_ns();emit('phase_end',phase=number,phase_name=name,start_timestamp_ns=start,end_timestamp_ns=end,status='STOPPED' if isinstance(e,StopRequested) else 'FAILED',duration_ms=(end-start)/1e6,error_message=repr(e));raise
    else:
        end=time.monotonic_ns();emit('phase_end',phase=number,phase_name=name,start_timestamp_ns=start,end_timestamp_ns=end,status='PASS',duration_ms=(end-start)/1e6,error_message=None)


def start_krita(env,timed,settings,event,record):
    prepared=settings.get('prepared_document')
    process=subprocess.Popen(['krita']+(['--nosplash'] if timed else []),env=env)
    CTX.update(process=process,pid=process.pid,birth=identity(process.pid)['starttime'],wid=None,document_open=False)
    window=wait_until(main_window,settings['startup_timeout_s'],'本轮Krita主窗口未出现');CTX['wid']=window['id'];focus(window['id'])
    stable={}
    def ready():
        current=main_window()
        if not current:return False
        # Krita replaces its initial normal window during startup.
        # Rebind only within the already owned PID, then restabilize.
        if current['id']!=CTX['wid']:
            CTX['wid']=current['id'];stable.clear()
        geometry=tuple(current[k] for k in ('x','y','width','height'))
        if stable.get('geometry')!=geometry:
            stable.update(geometry=geometry,since=time.monotonic());return False
        if time.monotonic()-stable['since']<1:return False
        focus(CTX['wid']);info=owned();maps=(Path('/proc')/str(CTX['pid'])/'maps').read_text()
        if 'libqxcb.so' not in maps:return False
        if 'libqwayland-generic.so' in maps:raise RuntimeError('检测到Wayland平台插件')
        if not timed:probe_state()
        plugins=sorted({line.split()[-1] for line in maps.splitlines() if 'libqxcb.so' in line or 'libqwayland' in line})
        if any('libqwayland' in p for p in plugins):raise RuntimeError('实际平台插件含Wayland')
        info.update(schema_version=1,qt_platform='xcb',libqxcb_verified=True,qt_plugins=plugins,window_id=CTX['wid'],window=current,focus_verified=True)
        if prepared:
            info.update(krita_config_home=env['XDG_CONFIG_HOME'],
                        tile_memory_percent=settings['tile_memory_percent'])
        if record:
            path=Path(record);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(info));tmp.replace(path)
        emit(event,**info);return True
    wait_until(ready,settings['startup_timeout_s'],'Krita未就绪')


def quit_krita(event):
    focus(CTX['wid']);run(['xdotool','key','ctrl+q'])
    process=CTX['process'];process.wait(timeout=CTX['settings']['close_timeout_s'])
    if process.returncode!=0:raise RuntimeError('Krita异常退出')
    emit(event,pid=CTX['pid'],returncode=process.returncode)


def main(argv=None):
    # Kept from the current experiment design; collector reads these literals by AST.
    default_asset_path='/home/mxt/OOM_assets/krita_8000_manual/blank_8000x8000.ora'
    layer_dir='/home/mxt/OOM_assets/krita_8000_manual/layers/'
    total_layers=45
    keep_duration_s=1800
    parser=argparse.ArgumentParser();parser.add_argument('asset',nargs='?',default=default_asset_path)
    parser.add_argument('--layers-dir',default=layer_dir);parser.add_argument('--settings');parser.add_argument('--assets-manifest');parser.add_argument('--control-file');parser.add_argument('--process-record')
    args=parser.parse_args(argv);settings=dict(DEFAULTS)
    if args.settings:settings.update(json.loads(Path(args.settings).read_text())['automation'])
    timed=settings.get('completion_mode')=='timed_window'
    profile=settings.get('pressure_profile')
    prepared=settings.get('prepared_document')
    tail=settings.get('tail_document')
    if profile is not None and not timed:raise ValueError('pressure profile requires timed capture')
    if prepared and (not profile or type(settings.get('tile_memory_percent')) is not int
                     or not 1<=settings['tile_memory_percent']<=100):
        raise ValueError('prepared ORA needs a pressure profile and an explicit Krita tile budget')
    if tail and not prepared:raise ValueError('tail ORA requires a separate post-peak Krita instance')
    if timed and (type(settings.get('capture_window_s')) not in (int,float) or not 0<settings['capture_window_s']<86400):raise ValueError('invalid capture window')
    CTX.update(process=None,pid=None,wid=None,birth=None,document_open=False)
    CTX.update(settings=settings,control=args.control_file,record=args.process_record,asset=args.asset)
    # The manifest, not an invented count, selects the complete existing PNG set.
    if args.assets_manifest:
        manifest=json.loads(Path(args.assets_manifest).read_text())
        paths=[p['path'] for p in manifest['png_files']]
        contract=manifest['script_contract']
        if prepared:
            if contract.get('prepared_document')!=prepared:raise RuntimeError('预组装文档与素材契约不一致')
            if contract.get('tail_document')!=tail:raise RuntimeError('尾段文档与素材契约不一致')
            if contract.get('tile_memory_percent')!=settings['tile_memory_percent']:
                raise RuntimeError('Krita 瓦片预算与素材契约不一致')
        elif contract['import_count']!=total_layers:raise RuntimeError('素材清单与脚本设计不一致')
        if timed:
            if contract.get('completion_mode')!='timed_window' or contract.get('capture_window_s')!=settings['capture_window_s']:raise RuntimeError('采集窗口与素材契约不一致')
            if contract.get('pressure_profile')!=profile:raise RuntimeError('三阶段采集与素材契约不一致')
        elif contract.get('hold_duration_s')!=keep_duration_s:raise RuntimeError('保持时长与素材契约不一致')
    else:paths=[] if prepared else [str(p.resolve()) for p in sorted(Path(args.layers_dir).iterdir()) if p.suffix.lower()=='.png']
    if any(any(ch in p for ch in ('\"','\n','\r')) for p in paths):raise RuntimeError('素材路径无法安全传入多文件选择框')
    if not Path(args.asset).is_file() or any(not Path(doc['path']).is_file() for doc in (prepared,tail) if doc):
        raise RuntimeError('ORA素材缺失')
    if not prepared and (len(paths)!=total_layers or not all(Path(p).is_file() for p in paths)):
        raise RuntimeError('PNG素材缺失或数量与脚本设计不一致')
    config_tmp=None
    try:
        with phase(1,'启动Krita'):
            # Do not attach to or close a pre-existing desktop Krita.
            if any('krita' in w['title'].lower() for w in windows()):raise RuntimeError('已有Krita窗口，拒绝启动')
            env=dict(os.environ,QT_QPA_PLATFORM='xcb',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1');env.pop('NO_AT_BRIDGE',None)
            if prepared:
                if args.process_record:
                    config_home=Path(args.process_record).resolve().parent/'isolated-krita-config'
                    config_home.mkdir(mode=0o700)
                else:
                    config_tmp=tempfile.TemporaryDirectory(prefix='oomlab-krita-config-')
                    config_home=Path(config_tmp.name)
                (config_home/'kritarc').write_text(f"memoryHardLimitPercent={settings['tile_memory_percent']}\n")
                env['XDG_CONFIG_HOME']=str(config_home)
            start_krita(env,timed,settings,'KRITA_PROCESS',args.process_record)
        with phase(2,'核对主窗口布局' if timed else '最大化窗口'):
            if timed:prepare_window()
            else:
                run(['xdotool','windowsize',CTX['wid'],'100%','100%']);run(['xdotool','windowmove',CTX['wid'],'0','0'])
                screen=[int(n) for n in run(['xdotool','getdisplaygeometry']).split()]
                wait_until(lambda:any(w['id']==CTX['wid'] and w['width']>=screen[0]*.9 and w['height']>=screen[1]*.85 for w in windows()),settings['startup_timeout_s'],'窗口尺寸未达到预期')
        with phase(3,'打开素材文件'):
            emit('DOCUMENT_OPEN_START');open_document()
            if not timed:wait_until(lambda:expected_layers(1),settings['open_timeout_s'],'空白画布图层数未验证')
            emit('DOCUMENT_OPEN_DONE',canvas=[manifest['ora']['width'],manifest['ora']['height']] if args.assets_manifest else None,
                 base_layers=1,verification='document_title_and_input_manifest' if timed else 'accessible_layer_table')
        with phase(4,'缩放画布'):
            emit('CANVAS_ZOOM_START');zoom_relative()
            if profile:
                review_canvas('PRE_IMPORT_REVIEW',profile['pre_import_review_s'],profile['review_interval_s'])
        if prepared:
            with phase(5,'打开预组装多图层文档'):
                close_document()
                emit('HIGH_DOCUMENT_OPEN_START',asset=prepared['path'])
                open_document(prepared['path'],'HIGH_DOCUMENT_SUBMITTED')
                opened=emit('HIGH_DOCUMENT_OPEN_DONE',asset=prepared['path'],verification='owned_document_title')
                capture_window(opened['monotonic_ns'],settings['capture_window_s'])
        else:
            capture_import(paths,total_layers,timed,keep_duration_s,settings)
        with phase(6,'关闭文件不保存'):
            emit('DOCUMENT_CLOSE_START');close_document();emit('DOCUMENT_CLOSE_DONE')
            if prepared:
                quit_krita('HIGH_INSTANCE_EXIT')
                post_record=Path(args.process_record).with_name('krita-post-process.json') if args.process_record else None
                start_krita(env,timed,settings,'KRITA_POST_PROCESS',post_record)
            if profile:
                open_document(tail['path'] if tail else args.asset)
                if tail:
                    emit('TAIL_DOCUMENT_OPEN_DONE',asset=tail['path'],pid=CTX['pid'],
                         verification='owned_document_title')
                review_canvas('POST_CLOSE_REVIEW',profile['post_close_review_s'],profile['review_interval_s'])
                close_document()
        with phase(7,'退出Krita'):
            quit_krita('KRITA_EXIT')
        with phase(8,'完成'):print('自动化流程结束。',flush=True)
        return 0
    except (Exception,KeyboardInterrupt) as e:
        print('[错误] '+repr(e),flush=True);traceback.print_exc()
        emit('GRACEFUL_CLEANUP_DONE',ok=graceful_shutdown(),error_message=repr(e));return 2 if isinstance(e,StopRequested) else 1
    finally:
        for key in ('action_process','discard_process'):
            action=CTX.pop(key,None)
            if action and action.poll() is None:action.terminate();action.wait(timeout=5)
        if config_tmp:config_tmp.cleanup()


def capture_import(paths,total_layers,timed,keep_duration_s,settings):
    with phase(5,'批量导入与定时采集' if timed else '批量导入图层并保持峰值'):
        focus(CTX['wid']);emit('LAYER_IMPORT_START',import_count=total_layers)
        dlg=import_dialog();submit_paths(dlg,paths)
        submitted=emit('LAYER_IMPORT_SUBMITTED',import_count=total_layers,verification='file_dialog_submission')
        wait_window_disappear(dlg['id'],settings['import_timeout_s'])
        # Qt can keep the Action D-Bus call pending while importing files.
        # The owned dialog and its submission are the evidence here; do
        # not turn the action reply into another import-completion wait.
        if timed:capture_window(submitted['monotonic_ns'],settings['capture_window_s'])
        else:
            wait_until(lambda:expected_layers(1+total_layers),settings['import_timeout_s'],'导入图层未完成/应用无响应')
            emit('LAYER_IMPORT_DONE',verified_total_layers=1+total_layers);emit('HOLD_START',duration_s=keep_duration_s)
            until=time.monotonic()+keep_duration_s;last_probe=0;last_ok=time.monotonic()
            while time.monotonic()<until:
                check_stop();owned()
                if time.monotonic()-last_probe>=5:
                    try:
                        if not expected_layers(1+total_layers):raise GuiPending('保持时图层数不符')
                        last_ok=time.monotonic()
                    except (GuiPending,subprocess.TimeoutExpired):
                        if time.monotonic()-last_ok>=settings['unresponsive_timeout_s']:raise TimeoutError('Krita持续无响应')
                    last_probe=time.monotonic()
                time.sleep(.2)
            emit('HOLD_DONE')


if __name__=='__main__':raise SystemExit(main())
