#!/usr/bin/env python3
"""Install versioned policy hooks in this checkout only."""
from pathlib import Path
import subprocess

root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).decode().strip())
hooks = Path(subprocess.check_output(['git', 'rev-parse', '--git-path', 'hooks']).decode().strip()).resolve()
for name in ('pre-commit', 'pre-push'):
    target = hooks / name
    target.write_bytes((root / 'tools/git-hooks' / name).read_bytes())
    target.chmod(0o755)
subprocess.run(['git', 'config', '--local', 'core.hooksPath', str(hooks)], check=True)
print('Installed TeamOOM pre-commit and pre-push hooks:', hooks)
