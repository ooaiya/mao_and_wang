import re
import json
from .common import SCHEMA

ERROR = re.compile(r'\[错误\]|^Traceback \(most recent call last\)|^(?:Error|ERROR|FAILED|[A-Za-z_]+Error|Exception)(?::|\s|$)|自动化失败|素材加载超时|BadWindow|\[cmd\].*\bNone\b')


def observe(line,stamp,wall):
    event=dict(schema_version=SCHEMA,monotonic_ns=stamp,wall_time_ns=wall,line=line.rstrip(),error=bool(ERROR.search(line.lstrip())))
    if line.startswith('@@OOM_EVENT '):
        try:
            emitted=json.loads(line[len('@@OOM_EVENT '):]);event.update(emitted)
            event['received_monotonic_ns']=stamp;event['received_wall_time_ns']=wall
            if emitted.get('schema_version')!=SCHEMA or type(emitted.get('monotonic_ns')) is not int or emitted['monotonic_ns']>stamp:raise ValueError('invalid event clock/schema')
            event['error']=event.get('error',False) or emitted.get('status') in ('FAILED','STOPPED')
        except (ValueError,TypeError):event.update(error=True,kind='invalid_protocol')
        event.setdefault('phase',None);return event
    match=re.match(r'^\s*\[([1-8])/8\]',line)
    event['phase']=int(match.group(1)) if match else None
    return event


def validate(events,structured=False):
    protocol=[e for e in events if e.get('kind') in ('phase_start','phase_end')]
    if protocol or structured:return validate_structured(events)
    marked=[e for e in events if e.get('phase') is not None]
    return ([e['phase'] for e in marked]==list(range(1,9)) and not any(e.get('error') for e in events)
            and all(e.get('schema_version')==SCHEMA for e in events)
            and all(b['monotonic_ns']>a['monotonic_ns'] for a,b in zip(marked,marked[1:])))


def validate_structured(events):
    if any(e.get('error') for e in events):return False
    records=[e for e in events if e.get('kind') in ('phase_start','phase_end')]
    if [(e.get('phase'),e.get('kind')) for e in records]!=[(n,k) for n in range(1,9) for k in ('phase_start','phase_end')]:return False
    for start,end in zip(records[::2],records[1::2]):
        a=start.get('start_timestamp_ns');b=end.get('end_timestamp_ns')
        if not isinstance(a,int) or not isinstance(b,int) or b<a or end.get('start_timestamp_ns')!=a:return False
        if end.get('phase_name')!=start.get('phase_name') or end.get('status')!='PASS' or end.get('error_message'):return False
        if abs(end.get('duration_ms',-1)-(b-a)/1e6)>1e-6:return False
    return all(e.get('schema_version')==SCHEMA for e in records) and all(b['monotonic_ns']>=a['monotonic_ns'] for a,b in zip(records,records[1:]))
