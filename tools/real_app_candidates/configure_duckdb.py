"""Write native weather SQL for GUI execution; never opens a database."""
import argparse,subprocess
from pathlib import Path

def literal(value):
    return "'"+str(value).replace("'","''")+"'"

def weather_query(source,output):
    return f"""COPY (
    SELECT ID, CAST(strptime(DATE, '%Y%m%d') AS DATE) AS DATE,
           ELEMENT, DATA_VALUE, Q_FLAG,
           CAST(DATA_VALUE AS DOUBLE) / 10.0 AS CONVERTED_VALUE,
           CASE WHEN ELEMENT = 'PRCP' THEN 'mm' ELSE 'degC' END AS UNIT
    FROM read_csv({literal(source)}, header = true, nullstr = '',
        columns = {{'ID':'VARCHAR','DATE':'VARCHAR','ELEMENT':'VARCHAR',
                    'DATA_VALUE':'INTEGER','M_FLAG':'VARCHAR','Q_FLAG':'VARCHAR',
                    'S_FLAG':'VARCHAR','OBS_TIME':'VARCHAR'}})
    WHERE (Q_FLAG IS NULL OR trim(Q_FLAG) = '')
      AND ELEMENT IN ('TMAX','TMIN','TAVG','PRCP')
    ORDER BY ID, DATE, ELEMENT
) TO {literal(output)} (FORMAT PARQUET, COMPRESSION ZSTD);
"""

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--sql',type=Path,required=True);a=p.parse_args()
    if not a.input.is_file():raise ValueError('Real header CSV missing')
    if a.output.exists() or a.sql.exists():raise ValueError('Refuse to overwrite output or SQL')
    for target in [a.output,a.sql]:
        parent=target.resolve().parent
        while not parent.exists():parent=parent.parent
        if subprocess.run(['git','-C',str(parent),'rev-parse','--show-toplevel'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:raise ValueError('Generated real SQL and output must be outside Git')
    a.sql.parent.mkdir(parents=True,exist_ok=True);a.sql.write_text(weather_query(a.input.resolve(),a.output.resolve()));print(a.sql)
if __name__=='__main__':main()
