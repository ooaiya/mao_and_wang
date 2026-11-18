import re
from pathlib import Path
from .common import load, positive

SAFETY = ('max_sample_gap_s','max_other_process_rss_bytes','min_available_bytes','min_swap_free_bytes','min_disk_free_bytes',
          'max_cgroup_bytes','max_global_full_avg10','cooldown_cgroup_bytes',
          'cooldown_min_available_bytes','cooldown_max_full_avg10','cooldown_timeout_s',
          'cooldown_stable_s','run_timeout_s')


def read(path):
    c=load(path)
    pilot=c.get('mode')=='pilot'
    extra={'mode','pilot','automation'} if pilot else set()
    if set(c)-extra!={'schema_version','interval_s','asset','display_size','safety','acceptance','forbidden_processes','forbidden_units','forbidden_sockets'}:
        raise ValueError('unknown or missing collection config fields')
    if type(c['interval_s']) not in (int,float):raise ValueError('numeric interval required')
    positive(c['interval_s'])
    if set(c['safety'])!=set(SAFETY): raise ValueError('explicit safety thresholds required')
    for key in SAFETY:
        value=c['safety'][key]
        if value is None or isinstance(value,bool): raise ValueError('safety threshold is unset: '+key)
        if key.endswith('_bytes'):
            if type(value) is not int or value<0: raise ValueError('byte thresholds must be nonnegative integers')
        else:
            if type(value) not in (int,float):raise ValueError('numeric safety threshold required')
            positive(value)
    for key in ['max_global_full_avg10','cooldown_max_full_avg10']:
        if c['safety'][key]>100: raise ValueError('PSI threshold exceeds 100%')
    if (pilot and c['acceptance']!={}) or (not pilot and set(c['acceptance'])!={'krita','xz','table','array_processing'}):raise ValueError('PILOT acceptance must be empty; formal needs per-operation bounds')
    for bounds in c['acceptance'].values():
        if set(bounds)!={'min_peak_bytes','max_peak_bytes'} or any(type(v) is not int or v<0 for v in bounds.values()):raise ValueError('integer acceptance bytes required')
        if not bounds['min_peak_bytes']<=bounds['max_peak_bytes']<c['safety']['max_cgroup_bytes']:raise ValueError('acceptance must lie below safety stop threshold')
    if len(c['display_size'])!=2 or any(type(n) is not int or n<=0 for n in c['display_size']): raise ValueError('explicit display size required')
    for key in ['forbidden_processes','forbidden_units','forbidden_sockets']:
        if not isinstance(c[key],list) or not c[key] or not all(isinstance(x,str) and x for x in c[key]): raise ValueError('explicit conflict inventory required: '+key)
    asset=c['asset']
    if set(asset)!={'path','sha256','width','height','layers'}: raise ValueError('asset contract incomplete')
    if not isinstance(asset['path'],str) or not Path(asset['path']).is_absolute() or not re.fullmatch(r'[A-Za-z0-9_./-]+',asset['path']):
        raise ValueError('asset path must be absolute shell-safe ASCII')
    if not (pilot and asset['sha256'] is None) and not re.fullmatch('[0-9a-f]{64}',asset['sha256'] or ''): raise ValueError('pin existing ORA SHA256')
    timed=pilot and c['automation'].get('completion_mode')=='timed_window'
    expected=(9000,9000,1) if timed else (8000,8000,1) if pilot else (4096,4096,208)
    if (asset['width'],asset['height'],asset['layers'])!=expected:raise ValueError('asset contract mismatch: '+str(expected))
    if pilot:validate_pilot(c)
    return c


def validate_pilot(c):
    from .common import positive
    from .pilot_assets import script_contract
    p=c['pilot'];a=c['automation']
    if set(p)!={'layers_dir','psi_full_sustained_s','graceful_stop_timeout_s'}:raise ValueError('explicit PILOT settings required')
    if not isinstance(p['layers_dir'],str) or not Path(p['layers_dir']).is_absolute():raise ValueError('absolute existing layers directory required')
    if c['interval_s']!=.05:raise ValueError('PILOT requires 50ms sampling')
    if c['safety']['min_available_bytes']<1610612736 or c['safety']['min_swap_free_bytes']<322122547:raise ValueError('PILOT safety reserves must not be relaxed')
    keys={'startup_timeout_s','open_timeout_s','import_timeout_s','close_timeout_s','unresponsive_timeout_s','poll_s','accessibility_python','graceful_stop_timeout_s'}
    timed=a.get('completion_mode')=='timed_window'
    prepared=a.get('prepared_document')
    tail=a.get('tail_document')
    if timed:
        keys|={'completion_mode','capture_window_s'}
        keys.add('prepared_document' if prepared is not None else 'timing_basis')
        if prepared is not None:keys.add('tile_memory_percent')
        if prepared is not None and tail is not None:keys.update(('tail_document','tail_charge_range_bytes'))
    profile=a.get('pressure_profile')
    if timed and 'pressure_profile' in a:
        keys.add('pressure_profile')
        validate_pressure_profile(profile)
    if set(a)!=keys:raise ValueError('explicit automation deadlines required')
    for k,v in a.items():
        if k not in ('accessibility_python','completion_mode','timing_basis','pressure_profile',
                     'prepared_document','tail_document','tail_charge_range_bytes'):
            if type(v) not in (int,float):raise ValueError('numeric automation deadline required')
            positive(v)
    if not Path(a['accessibility_python']).is_absolute():raise ValueError('absolute system accessibility Python required')
    for key in ('psi_full_sustained_s','graceful_stop_timeout_s'):
        if type(p[key]) not in (int,float):raise ValueError('numeric PILOT deadline required')
        positive(p[key])
    if a['graceful_stop_timeout_s']>=p['graceful_stop_timeout_s']:raise ValueError('collector grace must exceed GUI grace')
    if prepared is not None:
        if not profile:raise ValueError('prepared ORA needs a three-stage profile')
        validate_layered_ora(prepared)
        if (Path(prepared['path']).parent!=Path(c['asset']['path']).parent
            or prepared['path']==c['asset']['path']):
            raise ValueError('prepared ORA must be distinct and beside the light ORA')
        if type(a['tile_memory_percent']) is not int or not 1<=a['tile_memory_percent']<=100:
            raise ValueError('prepared ORA requires an explicit integer Krita tile memory percentage')
        if tail is not None:
            validate_layered_ora(tail)
            if tail['path'] in (c['asset']['path'],prepared['path']):
                raise ValueError('tail ORA must be a distinct asset')
            bounds=a['tail_charge_range_bytes']
            if (not isinstance(bounds,list) or len(bounds)!=2 or any(type(n) is not int for n in bounds)
                or not 0<bounds[0]<bounds[1]<=profile['max_low_charge_bytes']):
                raise ValueError('explicit tail charge range within the review ceiling required')
    elif timed:
        b=a['timing_basis']
        if not isinstance(b,dict) or set(b)!={'curve_sha256','import_duration_s','post_import_observation_s'}:raise ValueError('auditable timing basis required')
        if not re.fullmatch('[0-9a-f]{64}',b['curve_sha256']):raise ValueError('timing curve SHA256 required')
        for key in ('import_duration_s','post_import_observation_s'):positive(b[key])
        if a['capture_window_s']<b['import_duration_s']+b['post_import_observation_s']:raise ValueError('capture window excludes measured import and observation')
    contract=script_contract(config=c)
    duration=contract.get('capture_window_s',contract.get('hold_duration_s',0))
    if profile:
        duration+=profile['pre_import_review_s']+profile['post_close_review_s']
        duration+=a['open_timeout_s']+a['close_timeout_s']
    if prepared is not None:
        duration+=a['open_timeout_s']+a['close_timeout_s']
    if c['safety']['run_timeout_s']<=duration+sum(a[k] for k in ('startup_timeout_s','open_timeout_s','import_timeout_s','close_timeout_s')):raise ValueError('run timeout excludes capture/GUI deadlines')


def validate_layered_ora(asset):
    if not isinstance(asset,dict) or set(asset)!={'path','sha256','width','height','layers'}:
        raise ValueError('complete layered ORA asset contract required')
    path=asset['path']
    if not isinstance(path,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',path) or not Path(path).is_absolute():
        raise ValueError('absolute shell-safe layered ORA path required')
    if (not isinstance(asset['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',asset['sha256'])
        or (asset['width'],asset['height'])!=(9000,9000)
        or type(asset['layers']) is not int or not 2<=asset['layers']<=64):
        raise ValueError('invalid layered ORA hash, dimensions or layer count')


def validate_pressure_profile(profile):
    seconds=('pre_import_review_s','post_close_review_s','review_interval_s','post_close_settle_s')
    byte_limits=('peak_reference_bytes','max_low_charge_bytes','max_low_pressure_bytes')
    if not isinstance(profile,dict) or set(profile)!=set((*seconds,*byte_limits,'peak_tolerance_fraction')):
        raise ValueError('explicit three-stage timings and memory acceptance required')
    for key in (*seconds,'peak_tolerance_fraction'):
        if type(profile[key]) not in (int,float):raise ValueError('numeric three-stage setting required')
        positive(profile[key])
    if any(type(profile[key]) is not int or profile[key]<=0 for key in byte_limits):
        raise ValueError('positive integer byte bounds required')
    cadence=profile['review_interval_s']
    if (profile['pre_import_review_s']<2*cadence
        or profile['post_close_review_s']-profile['post_close_settle_s']<2*cadence):
        raise ValueError('each low-pressure interval must cover multiple review actions')
    tolerance=profile['peak_tolerance_fraction']
    if not 0<tolerance<1 or profile['max_low_charge_bytes']>=profile['peak_reference_bytes']*(1-tolerance):
        raise ValueError('low foreground charge must be below the accepted high peak')
