"""Keep generated analysis outside every Git worktree."""
from pathlib import Path
import os
import subprocess

DEFAULT_OUTPUT = Path('/home/mxt/TeamOOM/results/analysis')


def external_output(path):
    path = Path(path).expanduser().resolve()
    repo = Path(__file__).resolve().parents[2]
    if path == repo or repo in path.parents:
        raise ValueError('analysis output must be outside the code repository')
    # Ask Git to validate metadata, including worktree .git files. Empty sandbox
    # placeholders are not repositories. Inspect ancestors as well, so an invalid
    # nested marker cannot hide a genuine containing worktree.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    for parent in (path, *path.parents):
        if not parent.is_dir():
            continue
        result = subprocess.run(['git', '-C', str(parent), 'rev-parse', '--show-toplevel'],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True)
        if result.returncode == 0:
            top = Path(result.stdout.strip()).resolve()
            if path == top or top in path.parents:
                raise ValueError('analysis output must be outside Git worktrees')
    path.mkdir(parents=True, exist_ok=True)
    return path


def source_file(root, name):
    root = Path(root).expanduser().resolve(strict=True)
    path = Path(name)
    path = (path if path.is_absolute() else root / path).resolve(strict=True)
    if root not in path.parents or not path.is_file():
        raise ValueError('sample source must be inside the explicit source root')
    return path
