"""Stream independent NOAA input and native CSV/Parquet output AFTER computation.

Checks counts, units, every numeric conversion, order and order-independent
record fingerprints. Never prepares transformed input or allocates a full table.
"""
import argparse,csv,gzip,hashlib,json,datetime,collections,math
from pathlib import Path
ELEMENTS={'TMAX','TMIN','TAVG','PRCP'}
MOD=1<<256
def add_fingerprint(state,values):
    digest=int.from_bytes(hashlib.sha256(('|'.join(values)).encode()).digest(),'big')
    state[0]=(state[0]+digest)%MOD;state[1]^=digest
def output_rows(csv_path,parquet_path):
    required={'ID','DATE','ELEMENT','DATA_VALUE','Q_FLAG','CONVERTED_VALUE','UNIT'}
    if parquet_path:
        import pyarrow.parquet as pq
        source=pq.ParquetFile(parquet_path)
        if not required.issubset(source.schema_arrow.names):raise ValueError('Missing Parquet columns')
        for batch in source.iter_batches(batch_size=32768):
            yield from batch.to_pylist()
    else:
        with csv_path.open(newline='') as f:
            reader=csv.DictReader(f)
            if not required.issubset(reader.fieldnames or []):raise ValueError('Missing output columns: '+repr(reader.fieldnames))
            yield from reader
def main():
    p=argparse.ArgumentParser();inputs=p.add_mutually_exclusive_group(required=True);inputs.add_argument('--input-gzip',type=Path);inputs.add_argument('--input-csv',type=Path);outputs=p.add_mutually_exclusive_group(required=True);outputs.add_argument('--output-csv',type=Path);outputs.add_argument('--output-parquet',type=Path);p.add_argument('--report',type=Path,required=True);p.add_argument('--date-from',default='00000000');p.add_argument('--date-to',default='99999999');a=p.parse_args()
    counts=collections.Counter();input_elements=collections.Counter();kept_elements=collections.Counter();wanted=[0,0];actual=[0,0]
    with (gzip.open(a.input_gzip,'rt',newline='') if a.input_gzip else a.input_csv.open(newline='')) as f:
        reader=csv.reader(f)
        if a.input_csv and next(reader,None)!=['ID','DATE','ELEMENT','DATA_VALUE','M_FLAG','Q_FLAG','S_FLAG','OBS_TIME']:raise ValueError('Unexpected prepared input header')
        for row in reader:
            if len(row)!=8:raise ValueError('Unexpected NOAA field count')
            station,date,element,value,mflag,qflag,sflag,obstime=row;counts['source_rows']+=1
            if not a.date_from<=date<=a.date_to:continue
            counts['input']+=1;input_elements[element]+=1
            bad=bool(qflag.strip());selected=element in ELEMENTS
            if bad:counts['quality_flagged_all_elements']+=1
            if not selected:counts['excluded_element']+=1
            elif bad:counts['excluded_quality_within_selected_elements']+=1
            else:
                counts['expected_output']+=1;kept_elements[element]+=1
                normalized_date=datetime.date(int(date[:4]),int(date[4:6]),int(date[6:8])).isoformat()
                add_fingerprint(wanted,[station,normalized_date,element,str(int(value))])
    seen_elements=collections.Counter();last=None;minimum=None;maximum=None;examples=[]
    for row in output_rows(a.output_csv,a.output_parquet):
        station=row['ID'];date=row['DATE'] if isinstance(row['DATE'],datetime.date) else datetime.date.fromisoformat(row['DATE']);element=row['ELEMENT'];raw=int(row['DATA_VALUE']);value=float(row['CONVERTED_VALUE']);unit=row['UNIT']
        if element not in ELEMENTS or (row['Q_FLAG'] or '').strip():raise ValueError('Unexpected element or quality flag in output')
        if unit!=('mm' if element=='PRCP' else 'degC'):raise ValueError('Incorrect unit')
        if not math.isclose(value,raw/10.,rel_tol=1e-12,abs_tol=1e-9):raise ValueError('Incorrect business conversion')
        key=(station,date,element)
        if last is not None and key<last:raise ValueError('Not sorted by station/date/element')
        last=key;minimum=date if minimum is None else min(minimum,date);maximum=date if maximum is None else max(maximum,date)
        counts['actual_output']+=1;seen_elements[element]+=1;add_fingerprint(actual,[station,date.isoformat(),element,str(raw)])
        if len(examples)<8:examples.append(row)
    if counts['expected_output']!=counts['actual_output'] or seen_elements!=kept_elements or wanted!=actual:raise ValueError('Input/output record identity mismatch')
    result={'status':'PASS','counts':dict(counts),'input_elements':dict(input_elements),'output_elements':dict(seen_elements),'date_range':[minimum.isoformat(),maximum.isoformat()],'field_types':{'ID':'station string','DATE':'ISO LocalDate (native workflow type verified separately)','ELEMENT':'string','DATA_VALUE':'integer','CONVERTED_VALUE':'double','UNIT':'string'},'all_rows_conversion_checked':True,'all_rows_sort_checked':True,'fingerprint':'SHA256 of station|ISOdate|element|raw; sum mod2^256 and xor match (order independent)','input_fingerprint':[hex(v) for v in wanted],'output_fingerprint':[hex(v) for v in actual],'examples':examples,'output_bytes':(a.output_csv or a.output_parquet).stat().st_size}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2,default=str));print(json.dumps({k:result[k] for k in ['status','counts','output_elements','date_range','output_bytes']},indent=2))
if __name__=='__main__':main()
