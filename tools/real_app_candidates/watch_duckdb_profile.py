"""Observe a real native COPY profile after a GUI query; never starts SQL."""
import argparse,json,time
from pathlib import Path
from capture import event

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--profile',type=Path,required=True);p.add_argument('--artifact',type=Path,required=True);a=p.parse_args()
    cg=Path(json.loads((a.directory/'environment.json').read_text())['cgroup']);previous=time.monotonic_ns()
    while cg.exists():
        now=time.monotonic_ns()
        try:
            profile=json.loads(a.profile.read_text())
            if profile.get('query_name','').lstrip().upper().startswith('COPY (') and a.artifact.is_file() and a.artifact.stat().st_size>0:
                (a.directory/'duckdb_copy_profile.json').write_text(json.dumps(profile,indent=2))
                event(a.directory,'task_complete',dict(source='native DuckDB COPY profiling JSON complete and actual Parquet exists',profile=str(a.profile),artifact=str(a.artifact),native_latency_s=profile.get('latency'),previous_poll_ns=previous,first_confirmed_ns=now,poll_uncertainty_s=(now-previous)/1e9,limitation='Profile flush follows native query completion; GUI and independent output verification required'))
                return
        except (OSError,ValueError):pass
        previous=now;time.sleep(.1)
    raise SystemExit('Application ended before a successful COPY profile was observed')
if __name__=='__main__':main()
