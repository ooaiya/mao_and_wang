import argparse
import sys
import uuid
from pathlib import Path
from .common import ROOT, GIB, profile, positive, resource_check, save_json, load_json
from .environment import check_environment
from .workloads import prepare, estimated_disk
from .collect import collect_session
from .report import generate
from .services import ServiceError, stop_owned


def parser():
    parser = argparse.ArgumentParser(description='OOM 阶段 A 单操作采集（普通用户运行）')
    sub = parser.add_subparsers(dest='action', required=True)
    env = sub.add_parser('check-env')
    env.add_argument('--directory', default='.')
    env.add_argument('--safety-gib', type=positive, default=8)
    for action in ['prepare', 'collect']:
        a = sub.add_parser(action)
        a.add_argument('--operation', choices=['xz', 'table', 'array_processing'], required=True)
        a.add_argument('--profile', default='small')
        a.add_argument('--config', default=str(ROOT / 'configs/profiles.json'))
        a.add_argument('--data', required=True, help='单个操作的独立样本目录')
    for a in [sub.choices['collect'], sub.add_parser('smoke')]:
        a.add_argument('--results', default='/home/mxt/TeamOOM/results')
        a.add_argument('--rounds', type=int, default=3)
        a.add_argument('--interval', type=positive, default=.05)
        a.add_argument('--safety-gib', type=positive, default=8)
        a.add_argument('--timeout', type=positive, default=3600)
    report = sub.add_parser('report')
    report.add_argument('session')
    report.add_argument('--interval', type=positive, default=.05)
    cleanup = sub.add_parser('cleanup', help='只停止与指定 metadata 精确匹配的工具服务，保留文件')
    cleanup.add_argument('metadata')
    return parser


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == 'check-env':
            import json
            info = check_environment(args.directory, args.safety_gib)
            print(json.dumps(info, ensure_ascii=False, indent=2))
            return 0 if info['ok'] else 2
        if args.action == 'prepare':
            p = profile(args.config, args.operation, args.profile)
            target = Path(args.data).resolve()
            if target.exists():
                raise ValueError('样本目录已存在，拒绝覆盖')
            target.parent.mkdir(parents=True, exist_ok=True)
            resource_check(target.parent, GIB, estimated_disk(args.operation, p) + GIB)
            prepare(args.operation, p, target)
            print(target)
            return 0
        if args.action in ('collect', 'smoke'):
            if args.rounds <= 0:
                raise ValueError('rounds 必须为正整数')
            smoke = args.action == 'smoke'
            p = {} if smoke else profile(args.config, args.operation, args.profile)
            session, runs = collect_session(args.results, 'smoke' if smoke else args.operation,
                          'sleep' if smoke else args.profile, p, None if smoke else args.data,
                          args.rounds, args.interval, args.safety_gib, args.timeout, smoke)
            generate(session, args.interval)
            print(session)
            return 0 if len(runs) == args.rounds and all(m['success'] for m in runs) else 1
        if args.action == 'report':
            r = generate(args.session, args.interval)
            print(r['status'])
            return 0
        if args.action == 'cleanup':
            m = load_json(args.metadata)
            run = Path(args.metadata).resolve().parent
            if m['run_directory'] != str(run) or m['unit'] != 'oomlab-a-' + run.name + '.service':
                raise ValueError('metadata 与目录身份不匹配')
            evidence = run / ('cleanup-retry-' + uuid.uuid4().hex + '.json')
            try:
                cleanup = stop_owned(m['unit'], run, creation_failed=m.get('creation_failed') is True)
            except ServiceError as e:
                save_json(evidence, {'status': 'refused_or_failed', 'error': str(e),
                                    'diagnostic': e.diagnostic})
                raise
            save_json(evidence, cleanup)
            print(cleanup['message'] + '；所有证据及样本保留；诊断：' + str(evidence))
            return 0
    except Exception as e:
        print(f'错误：{type(e).__name__}: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
