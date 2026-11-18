import argparse
import json
import os
import sys
import uuid
from datetime import datetime,timezone
from pathlib import Path
from .common import ROOT,GUI,load,save,fresh,outside_repo,digest,source_identity
from .common import measurement_lock
from .config import read
from .environment import check
from .engine import run_one,recipe
from .validation import report,validate_run


def collect(c,args):
    pilot=c.get('mode')=='pilot'
    if pilot and (args.operation!='krita' or args.smoke or args.resume_session or args.rounds!=1 or args.target_valid_rounds is not None or args.approve_first_summary_sha256 or args.data):raise ValueError('PILOT is exactly one Krita run; no smoke/background/resume/formal continuation')
    base=outside_repo(args.results);base.mkdir(parents=True,exist_ok=True)
    env=check(c,base,require_gui=not args.smoke)
    if not env['ok']:raise RuntimeError(json.dumps(env,ensure_ascii=False))
    # Shared cross-process lock also used by concurrent baseline. Never bypass
    # the old background collector lock: that collector is not invoked at all.
    with measurement_lock():
        op='smoke' if args.smoke else args.operation
        spec=recipe(op,c,args.data,args.profile)
        source=source_identity()
        if args.resume_session:
            raw_session=Path(args.resume_session).absolute()
            session=raw_session.resolve()
            if session!=raw_session or session.stat().st_uid!=os.getuid():raise ValueError('unowned or symlink resume session')
            if not session.is_relative_to(base) or session.is_symlink():raise ValueError('resume session is outside results root')
            old=load(session/'session.json')
            if old.get('asset_identity')!=env.get('asset'):raise ValueError('asset identity changed since first round')
            if old['config']!=c or old['recipe']!=spec or old['source']!=source or old['classification']!='FORMAL':raise ValueError('resume provenance mismatch')
            state=report(session)
            if state['status']!='VALIDATED' or not 1<=state['valid_rounds']<10:raise ValueError('resume requires only valid existing rounds, less than ten')
            marker=load(session/'first-round.json')
            if not __import__('re').fullmatch('[0-9a-f]{32}',marker['run_id']):raise ValueError('unsafe first-round identity')
            first=session/marker['run_id']
            if digest(first/'summary.json')!=marker['summary_sha256']:raise ValueError('first-round evidence changed')
            if args.approve_first_summary_sha256!=digest(first/'summary.json'):raise ValueError('explicit first-round review hash required')
            if args.target_valid_rounds!=10:raise ValueError('explicit target-valid-rounds 10 required')
            remaining=10-state['valid_rounds']
            fresh(session/'continuations') if not (session/'continuations').exists() else None
            save(session/'continuations'/('review-'+uuid.uuid4().hex+'.json'),dict(first_summary_sha256=args.approve_first_summary_sha256,target_valid_rounds=10))
        else:
            if args.rounds!=1 or args.target_valid_rounds is not None:raise ValueError('first formal invocation permits only --rounds 1')
            name=(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-' if pilot else '')+uuid.uuid4().hex
            session=fresh(base/name);remaining=1
            save(session/'session.json',dict(operation=op,recipe=spec,source=source,config=c,classification='TEST_ONLY' if args.smoke else 'PILOT' if pilot else 'FORMAL',asset_identity=env.get('asset')))
        for _ in range(remaining):
            # Repeat the complete read-only preflight before EVERY new round.
            env=check(c,base,require_gui=not args.smoke)
            if not env['ok']:raise RuntimeError('preflight failed before next round: '+str(env['errors']))
            if env.get('source')!=source:raise ValueError('source changed during session')
            if load(session/'session.json').get('asset_identity')!=env.get('asset'):raise ValueError('ORA identity changed during session')
            run,result=run_one(session,c,{op:spec},env,test_only=args.smoke)
            if not args.resume_session and not pilot:save(session/'first-round.json',dict(run_id=run.name,summary_sha256=digest(run/'summary.json')))
            print(json.dumps(dict(session=str(session),run=str(run),result=result),ensure_ascii=False,indent=2))
            if not result['valid'] or (not args.smoke and not pilot and not result['formal_eligible']):return 1
        print(json.dumps(report(session),ensure_ascii=False,indent=2));return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description='Independent Krita/user-cgroup evidence collection; no policy execution')
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('preflight');p.add_argument('--config',required=True);p.add_argument('--results',required=True)
    p=sub.add_parser('collect');p.add_argument('--config',required=True);p.add_argument('--results',required=True)
    p.add_argument('--operation',choices=['krita','xz','table','array_processing'],default='krita');p.add_argument('--data');p.add_argument('--profile',default='small')
    p.add_argument('--rounds',type=int,default=1);p.add_argument('--resume-session');p.add_argument('--target-valid-rounds',type=int)
    p.add_argument('--approve-first-summary-sha256');p.add_argument('--smoke',action='store_true',help='sleep only; always TEST_ONLY')
    p=sub.add_parser('validate');p.add_argument('run')
    p=sub.add_parser('report');p.add_argument('session');p.add_argument('--output',help='new report JSON; raw evidence remains immutable')
    args=parser.parse_args(argv)
    try:
        if args.action=='validate':
            result=validate_run(args.run);print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['valid'] else 1
        if args.action=='report':
            result=report(args.session)
            if args.output:
                out=Path(args.output)
                if out.resolve().is_relative_to(Path(args.session).resolve()):raise ValueError('report output must be outside immutable session')
                if out.exists():raise FileExistsError(str(out))
                with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0
        c=read(args.config)
        if args.action=='preflight':
            result=check(c,args.results)
            if c.get('mode')=='pilot':
                out=outside_repo(args.results);out.mkdir(parents=True,exist_ok=True)
                save(out/('preflight-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex+'.json'),result)
            print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ok'] else 2
        if args.operation!='krita' and not args.smoke and not args.data:raise ValueError('background operation requires --data')
        return collect(c,args)
    except (Exception,KeyboardInterrupt) as e:
        print(type(e).__name__+': '+str(e),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
