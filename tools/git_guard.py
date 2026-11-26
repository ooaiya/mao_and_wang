#!/usr/bin/env python3
"""Validate staged files and every outgoing commit without changing Git state."""
import argparse
import hashlib
from pathlib import PurePosixPath
import re
import subprocess
import sys

# Explicit user-authorized export, pinned to reviewed report-only bytes.
REPORT_ARCHIVES = {'codex_reports/app_candidates/TeamOOM_round3_20261126_170421_gui_round3_reports.zip': 'e2770694a59b336e120d7b6955b131febdf48d84f65719db17718d92de0f940a', 'codex_reports/app_candidates/TeamOOM_reports_20261126.zip': '1fa71b0b475b9a2a03ca06368bfae67fc382aa527234cf894951db78434748df'}

ALLOWED = {'refs/heads/mxt', 'refs/heads/mxt_codex'}
REMOTES = {'git@github.com:ooaiya/mao_and_wang.git',
           'https://github.com/ooaiya/mao_and_wang.git'}
DATA_DIRS = {'assets', 'data_collection', 'results', 'runtime', 'build', 'venv',
             '.venv', 'logs', 'outputs', '__pycache__', '.pytest_cache'}
DATA_SUFFIXES = ('.npz', '.npy', '.csv', '.csv.gz', '.jsonl', '.log', '.ora',
                 '.kra', '.bin', '.tar', '.tar.gz', '.zip', '.pyc', '.parquet', '.gpkg', '.dat', '.pkl', '.joblib', '.lgb', '.ipynb',
                 '.raw', '.arw', '.cr2', '.cr3', '.nef', '.raf', '.rw2', '.orf', '.dng',
                 '.crw', '.nrw', '.sr2', '.srf', '.mp4', '.mov', '.mkv', '.avi',
                 '.blend', '.blend1', '.blend2', '.kdenlive', '.kdenlivetitle', '.pto',
                 '.tif', '.tiff', '.7z', '.rar', '.xz', '.tar.xz')
CAPTURE_NAMES = {'samples.json', 'summary.json', 'environment.json', 'phase-events.json',
                 'raw.json', 'output.json', 'task_memory.json', 'model_metrics.json'}
# Synthetic fixtures are allowed by path, never exempt from secret scanning.
FIXTURE = re.compile(r'(^|/)(tests/fixtures|tests/resources)/')
RESOURCE = re.compile(r'^docs/resources/[\w.-]+\.(png|jpg|jpeg|svg)$')
SECRET_PATTERNS = [
    re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----'),
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(rb'github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(rb'AKIA[0-9A-Z]{16}'),
    re.compile(rb'(?:sk-proj-|sk-)[A-Za-z0-9_-]{32,}'),
    re.compile(rb'(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)'
               rb'\s*[=:]\s*[\"\x27]([A-Za-z0-9_+/=-]{20,})[\"\x27]'),
]


def git(*args, input=None):
    return subprocess.check_output(['git', *args], input=input)


def paths(raw):
    return [x.decode('utf-8') for x in raw.split(b'\0') if x]


def violation(path, data, mode='100644'):
    p = PurePosixPath(path)
    parts = set(p.parts)
    name = p.name.lower()
    if name.endswith(('.pdf', '.docx', '.pptx')):
        return 'paper or assignment material; retain source documentation instead'
    if mode in {'120000', '160000'}:
        return 'symlinks and submodules need explicit policy review'
    if parts & {'.aws', '.ssh', '.gnupg'} or name in {
        '.env', '.netrc', '.git-credentials', 'credentials', 'credentials.json',
        'id_rsa', 'id_ed25519', 'authorized_keys', 'known_hosts'} or name.endswith(('.pem', '.key', '.p12', '.pfx')):
        return 'credential or authentication file'
    if name.startswith('.env.') and name not in {'.env.example', '.env.template'}:
        return 'environment credentials'
    if any(pattern.search(data) for pattern in SECRET_PATTERNS):
        return 'possible secret (value redacted)'
    if path in REPORT_ARCHIVES:
        return None if hashlib.sha256(data).hexdigest() == REPORT_ARCHIVES[path] else 'report archive digest differs from explicitly authorized export'
    fixture = bool(FIXTURE.search(path))
    if not fixture and (parts & DATA_DIRS or name.endswith(DATA_SUFFIXES)
                        or name in CAPTURE_NAMES or name.endswith('_model.txt')):
        return 'experiment data, output, material or cache'
    if not fixture and name.endswith(('.png', '.jpg', '.jpeg')) and not RESOURCE.fullmatch(path):
        return 'generated image; documentation resources require docs/resources/'
    if len(data) > 5 * 1024 * 1024 and not name.endswith(('.pdf', '.docx')):
        return 'large file requires explicit resource policy review'
    return None


def entries(ref):
    raw = git('ls-files', '--stage', '-z') if ref == ':' else git('ls-tree', '-rz', ref)
    result = {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        meta, path = record.split(b'\t', 1)
        fields = meta.decode().split()
        if ref == ':' and fields[2] != '0':
            raise ValueError('unmerged index')
        result[path.decode()] = (fields[0], fields[1] if ref == ':' else fields[2])
    return result


def scan(ref):
    problems = []
    for path, (mode, oid) in entries(ref).items():
        reason = violation(path, git('cat-file', 'blob', oid), mode)
        if reason:
            problems.append(f'{path}: {reason}')
    if problems:
        raise ValueError('\n'.join(problems))


def ancestor(old, new):
    return subprocess.run(['git', 'merge-base', '--is-ancestor', old, new],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def report_only(names):
    return all((name.startswith('codex_reports/') and name.endswith('.md')) or name in REPORT_ARCHIVES for name in names)


def code_projection(ref):
    return {p: v for p, v in entries(ref).items() if not p.startswith('codex_reports/')}


def validate_commit_scope(commit, branch):
    if branch != 'refs/heads/mxt_codex':
        return
    mxt = git('rev-parse', 'refs/heads/mxt').decode().strip()
    # Synchronized mxt commits are code ancestry, not independent report commits.
    if ancestor(commit, mxt):
        return
    parents = git('rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
    if len(parents) == 2 and ancestor(parents[1], mxt):
        if code_projection(commit) != code_projection(parents[1]):
            raise ValueError('sync merge code must exactly match its mxt parent')
        if not report_only(paths(git('diff', '--name-only', '-z', parents[1], commit))):
            raise ValueError('sync merge must preserve reports only')
        return
    if len(parents) != 1 or not report_only(paths(git('diff', '--name-only', '-z', parents[0], commit))):
        raise ValueError('mxt_codex independent commits may modify codex_reports/*.md only')


def pre_commit():
    branch = git('symbolic-ref', 'HEAD').decode().strip()
    if branch not in ALLOWED:
        raise ValueError('commits allowed on mxt and mxt_codex only')
    scan(':')
    if branch == 'refs/heads/mxt_codex':
        merge_file = git('rev-parse', '--git-path', 'MERGE_HEAD').decode().strip()
        from pathlib import Path
        if Path(merge_file).exists():
            heads = Path(merge_file).read_text().split()
            mxt = git('rev-parse', 'refs/heads/mxt').decode().strip()
            if heads != [mxt] or code_projection(':') != code_projection(mxt):
                raise ValueError('only an exact mxt code synchronization merge is allowed')
            # Reports may be preserved, not silently altered in the sync merge.
            current = entries('HEAD')
            staged = entries(':')
            reports = lambda tree: {p: v for p, v in tree.items() if p.startswith('codex_reports/')}
            if reports(current) != reports(staged):
                raise ValueError('sync merge must preserve existing reports unchanged')
        elif not report_only(paths(git('diff', '--cached', '--name-only', '-z'))):
            raise ValueError('mxt_codex ordinary commits may modify reports only')


def check_push(remote_url, updates):
    if remote_url not in REMOTES:
        raise ValueError('unapproved remote')
    for line in updates.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise ValueError('malformed push update')
        local, new, remote, old = fields
        if local not in ALLOWED or remote != local:
            raise ValueError('only matching mxt/mxt_codex branch pushes are allowed')
        if set(new) == {'0'}:
            raise ValueError('remote branch deletion forbidden')
        if git('rev-parse', local).decode().strip() != new:
            raise ValueError('local branch SHA mismatch')
        if set(old) != {'0'} and not ancestor(old, new):
            raise ValueError('non-fast-forward push forbidden; no automatic override')
        scan(new)
        revision = new if set(old) == {'0'} else f'{old}..{new}'
        if set(old) == {'0'}:
            # Inspect branch-exclusive commits, without rescanning inherited main history.
            revision = f'refs/heads/main..{new}'
        for commit in git('rev-list', revision).decode().split():
            scan(commit)
            validate_commit_scope(commit, local)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['index', 'tree', 'pre-commit', 'pre-push'])
    parser.add_argument('arguments', nargs='*')
    args = parser.parse_args()
    try:
        if args.mode == 'index':
            scan(':')
        elif args.mode == 'tree':
            scan(args.arguments[0] if args.arguments else 'HEAD')
        elif args.mode == 'pre-commit':
            pre_commit()
        else:
            if len(args.arguments) != 2:
                raise ValueError('pre-push expects remote name and URL')
            check_push(args.arguments[1], sys.stdin.read())
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f'TeamOOM Git guard rejected: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
