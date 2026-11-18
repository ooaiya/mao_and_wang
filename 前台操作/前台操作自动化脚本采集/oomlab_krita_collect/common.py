import hashlib
import json
import math
import os
import subprocess
from pathlib import Path

SCHEMA = 1
BUDGET = 16 * 1024**3
ROOT = Path(__file__).resolve().parents[3]
GUI = ROOT / '前台操作/前台操作自动化脚本采集'
BACKGROUND = ROOT / '后台操作'


def save(path, value):
    path = Path(path)
    payload = {'schema_version': SCHEMA, **value}
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    temp.replace(path)


def load(path):
    value = json.loads(Path(path).read_text())
    if type(value.get('schema_version')) is not int or value['schema_version'] != SCHEMA:
        raise ValueError('unsupported schema_version: ' + str(path))
    return value


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024**2), b''): h.update(block)
    return h.hexdigest()


def positive(value):
    if isinstance(value, bool): raise ValueError('boolean is not a number')
    n = float(value)
    if not math.isfinite(n) or n <= 0: raise ValueError('expected finite positive number')
    return n


def command(args, timeout=20, check=True):
    p = subprocess.run([str(x) for x in args], capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f'{args[0]} exit={p.returncode}: {p.stderr.strip()}')
    return p


def fresh(path):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink(): raise FileExistsError(str(path))
    path.mkdir(parents=True, mode=0o700, exist_ok=False)
    return path


def outside_repo(path):
    path = Path(path).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError('formal results must be outside repository')
    return path


def fingerprint(path):
    path = Path(path).resolve(); a = path.stat()
    value = dict(path=str(path),sha256=digest(path),size_bytes=a.st_size,mtime_ns=a.st_mtime_ns)
    b = path.stat()
    if (a.st_size,a.st_mtime_ns) != (b.st_size,b.st_mtime_ns): raise ValueError('file changed during hashing')
    return value


def source_identity():
    paths = [GUI/'scripts/krita_auto.py', GUI/'scripts/pick_coords.py', GUI/'scripts/krita_accessibility.py', GUI/'scripts/krita_action.py', GUI/'requirements.txt', BACKGROUND/'oomlab/workloads.py', BACKGROUND/'oomlab/common.py', BACKGROUND/'configs/profiles.json', BACKGROUND/'requirements.txt']
    paths += sorted((GUI/'oomlab_krita_collect').glob('*.py'))+sorted((GUI/'configs').glob('collection*.json'))
    files = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    dirty=bool(command(['git','-C',ROOT,'diff','--name-only','HEAD','--','前台操作/前台操作自动化脚本采集/oomlab_krita_collect','前台操作/前台操作自动化脚本采集/scripts','前台操作/前台操作自动化脚本采集/configs','前台操作/前台操作自动化脚本采集/requirements.txt','后台操作']).stdout.strip())
    dirty=dirty or bool(command(['git','-C',ROOT,'ls-files','--others','--exclude-standard','--','前台操作/前台操作自动化脚本采集/oomlab_krita_collect','前台操作/前台操作自动化脚本采集/scripts','前台操作/前台操作自动化脚本采集/configs','前台操作/前台操作自动化脚本采集/requirements.txt','后台操作']).stdout.strip())
    return dict(source_dirty=dirty,git_sha=command(['git','-C',ROOT,'rev-parse','HEAD']).stdout.strip(),
                git_branch=command(['git','-C',ROOT,'branch','--show-current']).stdout.strip(),files=files)


def seal(run):
    run = Path(run)
    paths = sorted(p for p in run.rglob('*') if p.is_file() and p.name != 'manifest.sha256')
    (run/'manifest.sha256').write_text('# schema_version=1\n' + ''.join(digest(p)+'  '+str(p.relative_to(run))+'\n' for p in paths))


def verify_seal(run):
    run=Path(run); lines=(run/'manifest.sha256').read_text().splitlines()
    if lines[0] != '# schema_version=1': raise ValueError('manifest schema missing')
    names=[]
    for line in lines[1:]:
        h,name=line.split('  ',1); rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts or (run/rel).is_symlink() or not (run/rel).resolve().is_relative_to(run.resolve()): raise ValueError('unsafe manifest path')
        if digest(run/rel)!=h: raise ValueError('evidence digest mismatch: '+name)
        names.append(name)
    actual={str(p.relative_to(run)) for p in run.rglob('*') if p.is_file() and p.name!='manifest.sha256'}
    if len(names)!=len(set(names)) or set(names)!=actual: raise ValueError('incomplete manifest')


from contextlib import contextmanager


@contextmanager
def measurement_lock():
    import fcntl
    import stat
    path=Path(os.getenv('XDG_RUNTIME_DIR','/tmp'))/('oomcollect-'+str(os.getuid())+'.lock')
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        st=os.fstat(fd)
        if st.st_uid!=os.getuid() or not stat.S_ISREG(st.st_mode) or st.st_mode&0o022:raise ValueError('unsafe collector lock')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:os.close(fd)
