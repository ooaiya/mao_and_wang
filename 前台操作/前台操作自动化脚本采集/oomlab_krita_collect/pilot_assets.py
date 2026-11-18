"""Read-only PILOT inventory; experiment count/duration come from source literals."""
import ast
from pathlib import Path
from .common import GUI,fingerprint
from .asset import inspect


def script_contract(path=None,config=None):
    tree=ast.parse(Path(path or GUI/'scripts/krita_auto.py').read_text());values={}
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign):
            for target in node.targets:
                if isinstance(target,ast.Name) and target.id in ('total_layers','keep_duration_s'):
                    if target.id in values:raise ValueError('ambiguous automation design: '+target.id)
                    values[target.id]=ast.literal_eval(node.value)
    if set(values)!={'total_layers','keep_duration_s'} or any(type(v) is not int or v<=0 for v in values.values()):raise ValueError('literal script design missing')
    if config and config.get('automation',{}).get('completion_mode')=='timed_window':
        automation=config['automation']
        contract=dict(import_count=values['total_layers'],completion_mode='timed_window',
                      capture_window_s=automation['capture_window_s'],capture_origin='import_submit')
        if 'prepared_document' in automation:
            contract.pop('import_count')
            contract.update(prepared_document=automation['prepared_document'],
                            tile_memory_percent=automation['tile_memory_percent'],
                            capture_origin='prepared_document_open')
        if 'tail_document' in automation:
            contract.update(tail_document=automation['tail_document'],
                            tail_charge_range_bytes=automation['tail_charge_range_bytes'])
        if 'pressure_profile' in automation:contract['pressure_profile']=automation['pressure_profile']
        return contract
    return dict(import_count=values['total_layers'],hold_duration_s=values['keep_duration_s'])


def inventory(c):
    from PIL import Image
    ora=inspect(c['asset']['path'],verify_zip=True)
    if any(ora[k]!=c['asset'][k] for k in ('width','height','layers')):raise ValueError('PILOT ORA dimensions/base layers mismatch')
    if c['asset']['sha256'] and ora['sha256']!=c['asset']['sha256']:raise ValueError('PILOT pinned ORA SHA256 mismatch')
    contract=script_contract(config=c)
    if 'prepared_document' in contract:
        result=dict(schema_version=1,ora=dict(ora,filename=Path(ora['path']).name,format='ORA',zip_crc_verified=True),
                    png_count=0,png_files=[],script_contract=contract)
        for config_key,manifest_key in (('prepared_document','prepared_ora'),('tail_document','tail_ora')):
            if config_key not in contract:continue
            expected=contract[config_key]
            actual=inspect(expected['path'],verify_zip=True)
            if any(actual[k]!=expected[k] for k in ('sha256','width','height','layers')):
                raise ValueError(config_key+' differs from its pinned asset contract')
            result[manifest_key]=dict(actual,filename=Path(actual['path']).name,format='ORA',zip_crc_verified=True)
        return result
    directory=Path(c['pilot']['layers_dir']).resolve()
    if not directory.is_dir():raise ValueError('existing layers directory missing')
    files=[]
    entries=sorted(directory.iterdir())
    for p in entries:
        if p.suffix.lower()!='.png':continue
        if p.is_symlink() or not p.is_file():raise ValueError('PNG must be an existing regular file: '+str(p))
        if any(ch in str(p) for ch in ('\"','\n','\r')):raise ValueError('ambiguous multi-file dialog path: '+p.name)
        before=fingerprint(p)
        with Image.open(p) as image:
            details=dict(width=image.width,height=image.height,format=image.format,color_mode=image.mode)
            if image.format!='PNG' or (image.width,image.height)!=(c['asset']['width'],c['asset']['height']):raise ValueError('PNG format/dimensions mismatch: '+p.name)
            image.verify()  # stream PNG CRCs, without expanding 45 full 8000x8000 images
        if fingerprint(p)!=before:raise ValueError('PNG changed while verifying: '+p.name)
        files.append(dict(before,filename=p.name,**details,verified=True))
    if len(files)!=contract['import_count']:raise ValueError(f"PNG count {len(files)} differs from script {contract['import_count']}")
    return dict(schema_version=1,ora=dict(ora,filename=Path(ora['path']).name,format='ORA',zip_crc_verified=True),
                layers_dir=str(directory),png_count=len(files),png_files=files,script_contract=contract,
                directory_entries=[dict(name=p.name,is_file=p.is_file(),size_bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns) for p in entries])
