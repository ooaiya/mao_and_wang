import csv
import fcntl
import stat
import os
import pwd
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .common import ROOT, GIB, load_json, save_json, privileged, resource_check, command
from .environment import check_environment, check_controls
from .metrics import FIELDS, snapshot, event_delta, is_populated
from . import services
from .workloads import validate_input, verify, estimated_disk
from .telemetry import Collector
from .events import Events


def collect_one(session, operation, name, p, data, interval=.05, safety_gib=8,
                timeout=3600, smoke=False):
    run_id = uuid.uuid4().hex
    run = Path(session).resolve() / run_id
    run.mkdir()
    unit = 'oomlab-a-' + run_id + '.service'
    user = pwd.getpwuid(os.getuid())
    meta = {'schema_version': 1, 'run_id': run_id, 'operation': operation,
            'profile': name, 'parameters': p, 'unit': unit, 'slice': services.SLICE,
            'run_directory': str(run), 'user': user.pw_name, 'uid': user.pw_uid,
            'interval_s': interval, 'safety_limit_bytes': int(safety_gib * GIB),
            'scheduler_budget_bytes_reference_only': 16 * GIB,
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'success': False, 'reason': '未完成', 'cleanup_ok': False,
            'verified': False, 'events_delta': {}, 'pid': None, 'cgroup': None}
    save_json(run / 'metadata.json', meta)
    with open(run / 'raw.csv', 'w', newline='') as f:
        csv.DictWriter(f, FIELDS).writeheader()
    creation_attempted = False
    creation_failed = False
    rows = []
    start_ns = None
    telemetry = None
    kernel_cursor = None
    kernel_started = False
    try:
        if user.pw_uid == 0:
            raise RuntimeError('请以普通实验用户运行 CLI，sudo 仅由工具调用 systemd')
        disk = GIB if smoke else max(GIB, estimated_disk(operation, p) * 2)
        meta['resources'] = resource_check(run, (safety_gib + 2) * GIB, disk)
        if not smoke:
            meta['input_manifest'] = validate_input(data, operation, p)
        workload = ['/usr/bin/sleep', '0.25'] if smoke else [sys.executable, '-m',
                   'oomlab.workloads', str(Path(data).resolve()), str(run),'--operation-id',operation+'-'+name]
        meta['command'] = workload
        creation_attempted = True
        creation_failed = True  # Even a failed command may have created the unit.
        meta['service_start'] = services.start(unit, run, user.pw_name, int(safety_gib * GIB), timeout,
                                              sys.executable, ROOT, workload)
        creation_failed = False
        save_json(run / 'metadata.json', meta)
        deadline = time.monotonic() + 20
        while not (run / 'ready.json').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('服务启动超时；检查 journal.log、用户路径及 Python 权限')
            time.sleep(.02)
        status = services.show(unit)
        meta['initial_systemd_status'] = status
        services.validate_ownership(unit, run, status)
        if status.get('MemoryMax') != str(int(safety_gib * GIB)):
            raise RuntimeError('服务 MemoryMax 与配置不一致')
        path = Path('/sys/fs/cgroup') / status['ControlGroup'].lstrip('/')
        if not path.resolve().is_relative_to(Path('/sys/fs/cgroup').resolve()) or services.SLICE not in path.parts:
            raise RuntimeError('systemd 返回非法或非实验 slice 的 cgroup 路径')
        meta['cgroup'] = str(path)
        meta['supervisor_pid'] = int(status['MainPID'])
        check_controls(path)
        baseline = snapshot(path, time.monotonic_ns())
        meta['baseline'] = baseline
        telemetry = Collector(run)
        telemetry.sample({operation: path})
        from .oom_evidence import begin
        kernel_started = True
        kernel_cursor = begin(run)
        save_json(run / 'metadata.json', meta)
        (run / 'go').touch(exist_ok=False)
        deadline = time.monotonic() + 10
        while not (run / 'started.json').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('未收到操作开始标记')
            time.sleep(.001)
        meta['start'] = load_json(run / 'started.json')
        start_ns = meta['start']['monotonic_ns']
        deadline = time.monotonic() + timeout
        next_tick = time.monotonic()
        last_privilege_refresh = next_tick
        with open(run / 'raw.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, FIELDS)
            writer.writeheader()
            while True:
                row = snapshot(path, start_ns)
                telemetry.sample({operation: path})
                rows.append(row)
                writer.writerow(row)
                f.flush()
                if (run / 'finished.json').exists():
                    meta['finish'] = load_json(run / 'finished.json')
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError('工作负载超时')
                # Avoid a D-Bus subprocess every 50 ms, but detect service OOM/death.
                if not is_populated(path):
                    raise RuntimeError('服务进程消失，可能 OOM；以 events/journal 为准')
                if os.geteuid() != 0 and time.monotonic() - last_privilege_refresh >= 60:
                    command(['sudo', '-n', '-v'])
                    last_privilege_refresh = time.monotonic()
                next_tick += interval
                delay = next_tick - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_tick = time.monotonic()
        meta['pid'] = load_json(run / 'pid.json')['pid'] if (run / 'pid.json').exists() else None
        meta['returncode'] = meta['finish']['returncode']
        meta['duration_s'] = meta['finish']['duration_s']
        if meta['returncode'] != 0 or meta['finish'].get('error'):
            raise RuntimeError(f"操作退出失败：{meta['finish']}")
        # Verification happens AFTER sampling; does not contribute to this service's curve.
        with Events(run/'phase_trace.jsonl', operation_id=operation).phase('VERIFY'):
            meta['verification'] = {'ok': True, 'method': 'sleep exit code'} if smoke else verify(data, run)
        meta['verified'] = True
        meta['success'] = True
        meta['reason'] = None
    except (Exception, KeyboardInterrupt) as e:
        meta['success'] = False
        meta['reason'] = f'{type(e).__name__}: {e}'
        meta['interrupted'] = isinstance(e, KeyboardInterrupt)
        if isinstance(e, services.ServiceError):
            meta['failure_diagnostic'] = e.diagnostic
            if creation_failed:
                meta['service_start'] = e.diagnostic
    finally:
        if telemetry is not None:
            meta['collector'] = telemetry.close()
        if kernel_started:
            from .oom_evidence import finish
            meta['kernel_oom'] = finish(run, kernel_cursor)
        meta['collector_end_monotonic_ns'] = time.monotonic_ns()
        meta['collector_end_wall_ns'] = time.time_ns()
        meta['creation_attempted'] = creation_attempted
        meta['creation_failed'] = creation_failed
        if creation_attempted:
            evidence_errors = []
            try:
                inspection = services.inspect_unit(unit)
                meta['systemd_inspection'] = inspection
                meta['systemd_status'] = inspection['properties']
                save_json(run / 'systemctl-show.json', inspection)
                if inspection['existence'] == 'unknown':
                    evidence_errors.append('systemd 服务状态无法确认')
            except Exception as e:
                evidence_errors.append('systemd show: ' + repr(e))
            try:
                if meta.get('cgroup') and start_ns:
                    meta['final_snapshot'] = snapshot(meta['cgroup'], start_ns)
            except Exception as e:
                evidence_errors.append('final cgroup read: ' + repr(e))
            try:
                log = privileged(['journalctl', '-u', unit, '--no-pager', '-o', 'short-iso'], check=False)
                (run / 'journal.log').write_text(log.stdout + log.stderr)
                if log.returncode != 0:
                    evidence_errors.append('journalctl exit ' + str(log.returncode))
            except Exception as e:
                evidence_errors.append('journalctl: ' + repr(e))
            if evidence_errors:
                meta['evidence_error'] = '; '.join(evidence_errors)
            try:
                cleanup = services.stop_owned(unit, run, creation_failed=creation_failed)
                meta['cleanup'] = cleanup
                save_json(run / 'cleanup.json', cleanup)
                meta['cleanup_ok'] = True
            except Exception as e:
                meta['cleanup_error'] = repr(e)
                if isinstance(e, services.ServiceError):
                    meta['cleanup_diagnostic'] = e.diagnostic
                    save_json(run / 'cleanup.json', {'status': 'refused_or_failed',
                              'error': str(e), 'diagnostic': e.diagnostic})
        else:
            meta['cleanup_ok'] = True
        if (run / 'pid.json').exists():
            meta['pid'] = load_json(run / 'pid.json')['pid']
        samples = rows + ([meta['final_snapshot']] if meta.get('final_snapshot') else [])
        if samples:
            meta['peak_bytes'] = max(r['memory_peak'] for r in samples)
            meta['sampled_current_peak_bytes'] = max(r['memory_current'] for r in samples)
            meta['anon_sampled_peak_bytes'] = max((r['stat_anon'] for r in samples if r['stat_anon'] is not None), default=None)
            if operation == 'array_processing':
                swap_samples = [r.get('swap_current') for r in samples]
                meta['swap_sampled_peak_bytes'] = max(swap_samples) if all(v is not None for v in swap_samples) else None
            try:
                meta['events_delta'] = event_delta(meta.get('baseline', samples[0]), samples[-1])
            except ValueError as e:
                meta.update(success=False, reason=str(e))
        if meta['success'] and any(meta['events_delta'].get(k) is None for k in ('oom', 'oom_kill')):
            meta.update(success=False, reason='OOM 计数缺失，证据不完整')
        if meta['events_delta'].get('max', 0):
            meta.update(success=False, reason='触及 service 安全 MemoryMax，曲线可能受限')
        if meta['events_delta'].get('oom', 0) or meta['events_delta'].get('oom_kill', 0):
            meta.update(success=False, reason='观察到 cgroup OOM 事件，轮次无效')
        if operation == 'array_processing':
            meta['target_peak_limit_bytes'] = 3_000_000_000
            if meta.get('peak_bytes', 0) > 3_000_000_000:
                meta.update(success=False, reason='数组操作 memory.peak 超过3,000,000,000 Bytes')
            if meta.get('swap_sampled_peak_bytes') is None or meta.get('swap_sampled_peak_bytes', 0) > 0:
                meta.update(success=False, reason=meta.get('reason') or '数组操作Swap证据缺失或观察到Swap使用')
        if meta.get('evidence_error') or not meta['cleanup_ok']:
            meta.update(success=False, reason=meta.get('reason') or '证据或清理不完整')
        save_json(run / 'metadata.json', meta)
    return meta


def _collect_session(base, operation, name, p, data, rounds=3, interval=.05,
                    safety_gib=8, timeout=3600, smoke=False):
    base = Path(base).resolve()
    base.mkdir(parents=True, exist_ok=True)
    session = base / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex)
    session.mkdir()
    env = check_environment(session, safety_gib)
    save_json(session / 'environment.json', env)
    save_json(session / 'session.json', {'schema_version': 1, 'operation': operation,
              'profile': name, 'parameters': p, 'requested_rounds': rounds,
              'interval_s': interval, 'safety_gib': safety_gib, 'timeout_s': timeout,
              'status': 'RUNNING' if env['ok'] else 'PREFLIGHT_FAILED'})
    if not env['ok']:
        from .report import generate
        generate(session, interval)
        raise RuntimeError(f"环境检查失败，证据保存在 {session}: " + '; '.join(env['errors']))
    results = []
    for _ in range(rounds):
        results.append(collect_one(session, operation, name, p, data, interval,
                                   safety_gib, timeout, smoke))
        if not results[-1]['cleanup_ok'] or results[-1].get('interrupted'):
            break  # Do not start another operation while an earlier one may still run.
    session_config = load_json(session / 'session.json')
    session_config['status'] = 'COLLECTED' if all(r['success'] for r in results) else 'FAILED'
    save_json(session / 'session.json', session_config)
    return session, results


def collect_session(*args, **kwargs):
    # One collector per ordinary user, across different result roots/checkouts.
    lock = Path('/tmp') / f'oomlab-stage-a-{os.getuid()}.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        st = os.fstat(fd)
        if st.st_uid != os.getuid() or not stat.S_ISREG(st.st_mode):
            raise RuntimeError('采集锁文件归属或类型不安全')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise RuntimeError('同一用户已有阶段 A 采集运行，拒绝并发独立测量') from e
        return _collect_session(*args, **kwargs)
    finally:
        os.close(fd)
