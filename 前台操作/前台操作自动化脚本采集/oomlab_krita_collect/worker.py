"""Unbuffered tee supervisor, held alive for final kernel snapshots."""
import json
import codecs
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path
from .common import save,load,SCHEMA
from .phases import observe


def output_lines(process):
    """A failed automation's surviving GUI must not hold the tee open forever."""
    decoder=codecs.getincrementaldecoder('utf-8')(errors='replace');pending='';exited_at=None
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout,selectors.EVENT_READ)
        while True:
            ready=selector.select(.1)
            if ready:
                block=os.read(process.stdout.fileno(),65536)
                if not block:break
                pending+=decoder.decode(block)
                while '\n' in pending:
                    line,pending=pending.split('\n',1);yield line+'\n'
            if process.poll() is not None:
                exited_at=exited_at or time.monotonic()
                if not ready or time.monotonic()-exited_at>=1:break
    pending+=decoder.decode(b'',final=True)
    if pending:yield pending


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv;run=Path(args[0]); hold='--hold' in args
    classification=load(run.parent/'metadata.json')['classification']
    save(run/'ready.json',dict(pid=os.getpid(),hold=hold,classification=classification))
    if hold:
        while True: time.sleep(1)
    deadline=time.monotonic()+60
    while not (run/'go.json').exists():
        if time.monotonic()>deadline: raise TimeoutError('start gate not released')
        time.sleep(.01)
    gate=load(run/'go.json');target=gate['start_monotonic_ns']
    while time.monotonic_ns()<target:time.sleep(max(0,min(.01,(target-time.monotonic_ns())/1e9)))
    spec=load(run/'command.json');start=time.monotonic_ns()
    save(run/'started.json',dict(monotonic_ns=start,wall_time_ns=time.time_ns(),classification=classification))
    code=None;error=None
    try:
        with open(run/'automation.log','w',buffering=1) as log,open(run/'phase-events.jsonl','w',buffering=1) as events:
            log.write('# schema_version=1\n')
            events.write(json.dumps(dict(schema_version=SCHEMA,event='stream_open',monotonic_ns=time.monotonic_ns()))+'\n')
            p=subprocess.Popen(spec['command'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0)
            save(run/'workload-pid.json',dict(pid=p.pid,classification=classification))
            for line in output_lines(p):
                log.write(line);print(line,end='',flush=True)
                event=observe(line,time.monotonic_ns(),time.time_ns());event['classification']=classification
                if event['phase'] is not None or event['error'] or event.get('kind'): events.write(json.dumps(event,ensure_ascii=False)+'\n')
            code=p.wait()
            p.stdout.close()
    except Exception as e:error=repr(e)
    save(run/'finished.json',dict(classification=classification,returncode=code,error=error,start_monotonic_ns=start,end_monotonic_ns=time.monotonic_ns(),wall_time_ns=time.time_ns()))
    while True:time.sleep(1)


if __name__=='__main__':main()
