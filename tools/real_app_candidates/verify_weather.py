"""Stream independent NOAA input and native KNIME output AFTER computation.

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
def main():
    p=argparse.ArgumentParser();p.add_argument('--input-gzip',type=Path,required=True);p.add_argument('--output-csv',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--date-from',default='00000000');p.add_argument('--date-to',default='99999999');a=p.parse_args()
    counts=collections.Counter();input_elements=collections.Counter();kept_elements=collections.Counter();wanted=[0,0];actual=[0,0];dates=[]
    with gzip.open(a.input_gzip,'rt',newline='') as f:
        for row in csv.reader(f):
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
    with a.output_csv.open(newline='') as f:
        reader=csv.DictReader(f);required={'ID','DATE','ELEMENT','DATA_VALUE','Q_FLAG','CONVERTED_VALUE','UNIT'}
        if not required.issubset(reader.fieldnames or []):raise ValueError('Missing output columns: '+repr(reader.fieldnames))
        for row in reader:
            station=row['ID'];date=datetime.date.fromisoformat(row['DATE']);element=row['ELEMENT'];raw=int(row['DATA_VALUE']);value=float(row['CONVERTED_VALUE']);unit=row['UNIT']
            if element not in ELEMENTS or row['Q_FLAG'].strip():raise ValueError('Unexpected element or quality flag in output')
            if unit!=('mm' if element=='PRCP' else 'degC'):raise ValueError('Incorrect unit')
            if not math.isclose(value,raw/10.,rel_tol=1e-12,abs_tol=1e-9):raise ValueError('Incorrect business conversion')
            key=(station,date,element)
            if last is not None and key<last:raise ValueError('Not sorted by station/date/element')
            last=key;minimum=date if minimum is None else min(minimum,date);maximum=date if maximum is None else max(maximum,date)
            counts['actual_output']+=1;seen_elements[element]+=1;add_fingerprint(actual,[station,date.isoformat(),element,str(raw)])
            if len(examples)<8:examples.append(row)
    if counts['expected_output']!=counts['actual_output'] or seen_elements!=kept_elements or wanted!=actual:raise ValueError('Input/output record identity mismatch')
    result={'status':'PASS','counts':dict(counts),'input_elements':dict(input_elements),'output_elements':dict(seen_elements),'date_range':[minimum.isoformat(),maximum.isoformat()],'field_types':{'ID':'station string','DATE':'ISO LocalDate (native workflow type verified separately)','ELEMENT':'string','DATA_VALUE':'integer','CONVERTED_VALUE':'double','UNIT':'string'},'all_rows_conversion_checked':True,'all_rows_sort_checked':True,'fingerprint':'SHA256 of station|ISOdate|element|raw; sum mod2^256 and xor match (order independent)','input_fingerprint':[hex(v) for v in wanted],'output_fingerprint':[hex(v) for v in actual],'examples':examples,'output_bytes':a.output_csv.stat().st_size}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2));print(json.dumps({k:result[k] for k in ['status','counts','output_elements','date_range','output_bytes']},indent=2))
if __name__=='__main__':main()
