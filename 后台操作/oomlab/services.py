import re
from pathlib import Path
from .common import privileged, save_json

UNIT_RE = re.compile(r'oomlab-a-[0-9a-f]{32}\.service\Z')
SLICE = 'oomlab-a.slice'
CGROUP_PREFIX = '/oomlab.slice/' + SLICE


class ServiceError(RuntimeError):
    """Keep command/manager evidence without replacing the original failure."""

    def __init__(self, message, diagnostic):
        super().__init__(message)
        self.diagnostic = diagnostic


def valid_unit(unit):
    if not UNIT_RE.fullmatch(unit):
        raise ValueError('拒绝清理非本工具 UUID service')
    return unit


def run_diagnostic(args):
    """A missing executable/permission failure has unknown, not zero, exit status."""
    record = {'command': args, 'stdout': '', 'stderr': '', 'returncode': None}
    try:
        result = privileged(args, check=False)
        record.update(stdout=result.stdout, stderr=result.stderr, returncode=result.returncode)
    except OSError as e:
        record['execution_error'] = f'{type(e).__name__}: {e}'
    return record


def inspect_unit(unit):
    valid_unit(unit)
    record = run_diagnostic(['systemctl', 'show', unit, '--no-pager', '--all',
        '--property=Id,LoadState,ControlGroup,MainPID,ActiveState,SubState,Result,ExecMainCode,ExecMainStatus,Description,Slice,MemoryMax'])
    status = dict(line.split('=', 1) for line in record['stdout'].splitlines() if '=' in line)
    record.update(properties=status, existence='unknown')
    # systemctl show can return 1 for not-found. Only the manager's explicit
    # LoadState + exact Id establish absence, never stderr text or exit code alone.
    if status.get('Id') == unit and record['returncode'] in (0, 1, 4):
        if (status.get('LoadState') == 'not-found' and status.get('ControlGroup') == ''
                and status.get('MainPID') == '0'
                and status.get('ActiveState') in ('inactive', 'failed')):
            record['existence'] = 'absent'
        elif record['returncode'] == 0 and status.get('LoadState') in ('loaded', 'error', 'bad-setting', 'masked'):
            record['existence'] = 'present'
    return record


def show(unit):
    record = inspect_unit(unit)
    if record['existence'] != 'present':
        raise ServiceError('无法确认目标服务存在：' +
                           (record.get('execution_error') or record['stderr'] or record['existence']), record)
    return record['properties']


def validate_ownership(unit, run, status):
    valid_unit(unit)
    if status.get('Id') != unit:
        raise ValueError('服务名称归属不匹配，拒绝停止')
    if status.get('Description') != 'oomlab-stage-a:' + str(Path(run).resolve()):
        raise ValueError('服务归属不匹配，拒绝停止')
    if status.get('Slice') != SLICE:
        raise ValueError('服务不在本工具 slice，拒绝停止')
    if status.get('ControlGroup') != CGROUP_PREFIX + '/' + unit:
        raise ValueError('服务 cgroup 归属无法确认，拒绝停止')


def stop_owned(unit, run, creation_failed=False):
    """Stop only a verified service; manager-confirmed absence is a safe no-op."""
    valid_unit(unit)
    record = inspect_unit(unit)
    if record['existence'] == 'absent':
        return {'status': 'not_created' if creation_failed else 'already_absent',
                'message': '服务未创建，无需停止' if creation_failed else '服务不存在，无需停止',
                'inspection': record}
    if record['existence'] != 'present':
        raise ServiceError('服务归属无法确认，拒绝停止：' +
                           (record.get('execution_error') or record['stderr'] or 'manager 查询不完整'), record)
    try:
        validate_ownership(unit, run, record['properties'])
    except ValueError as e:
        raise ServiceError(str(e), record) from e
    stop = run_diagnostic(['systemctl', 'stop', unit])
    diagnostic = {'inspection': record, 'stop': stop}
    if stop['returncode'] != 0:
        raise ServiceError('停止服务失败：' + (stop.get('execution_error') or stop['stderr']), diagnostic)
    # Reset exactly this already-verified unit; it may have unloaded after stop.
    diagnostic['reset_failed'] = run_diagnostic(['systemctl', 'reset-failed', unit])
    return dict(status='stopped', message='已停止指定服务', **diagnostic)


def start(unit, run, user, safety_bytes, timeout, python, root, workload):
    valid_unit(unit)
    args = ['systemd-run', '--quiet', '--unit=' + unit, '--slice=' + SLICE,
            '--description=oomlab-stage-a:' + str(run), '--service-type=exec',
            '--property=User=' + user, '--property=WorkingDirectory=' + str(root),
            '--property=MemoryAccounting=yes', '--property=MemoryMax=' + str(safety_bytes),
            '--property=CPUAccounting=yes', '--property=IOAccounting=yes',
            '--property=MemorySwapMax=0', '--property=OOMPolicy=continue',
            '--property=KillMode=control-group', '--property=TimeoutStopSec=10s',
            '--property=RuntimeMaxSec=' + str(timeout + 120),
            '--property=Environment=PYTHONUNBUFFERED=1',
            '--property=Environment=OOMLAB_GATE_TIMEOUT=' + str(timeout),
            str(python), '-m', 'oomlab.worker', str(run)] + workload
    record = run_diagnostic(args)
    save_json(Path(run) / 'systemd-run.json', record)
    if record['returncode'] != 0:
        detail = record.get('execution_error') or record['stderr'].strip() or record['stdout'].strip()
        raise ServiceError(f"systemd-run 创建失败（退出码 {record['returncode']}）：{detail}", record)
    return record
