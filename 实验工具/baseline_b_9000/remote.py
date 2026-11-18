"""Local SSH transport; reuses the existing external askpass helper, no credentials."""
import base64
import os
from pathlib import Path
import subprocess
import sys


def ssh(script, timeout=45):
    helper = Path(os.environ['TEMP']) / 'sshhelper'
    env = os.environ.copy()
    env.update(SSH_ASKPASS=str(helper/'askpass.exe'), SSH_ASKPASS_REQUIRE='force', DISPLAY=':0')
    return subprocess.run(['ssh', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'UserKnownHostsFile='+str(helper/'known_hosts'), 'ooaiya@192.168.160.130',
        'python3 -'], input=script, env=env, capture_output=True,
        text=True, encoding='utf-8', timeout=timeout)


if __name__ == '__main__':
    result = ssh(Path(sys.argv[1]).read_text(encoding='utf-8'), 60)
    sys.stdout.buffer.write(result.stdout.encode('utf-8'))
    sys.stderr.buffer.write(result.stderr.encode('utf-8'))
    sys.exit(result.returncode)
