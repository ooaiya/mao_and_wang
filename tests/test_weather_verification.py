"""Small synthetic unit fixtures; never used as experimental observations."""
import csv,gzip,json,subprocess,sys,tempfile,unittest,datetime,importlib.util
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/'tools/real_app_candidates/verify_weather.py'

class WeatherVerificationTests(unittest.TestCase):
    def check_case(self,corrupt=None,date_to=None,parquet=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'synthetic_test_only.csv.gz';out=root/'output.csv';report=root/'report.json'
            with gzip.open(source,'wt',newline='') as f:
                csv.writer(f).writerows([['A','20240102','TMAX','100','','','S',''],['A','20240101','PRCP','23','','','S',''],['A','20240101','SNOW','10','','','S',''],['A','20240101','TMIN','-50','','X','S','']])
            rows=[['A','2024-01-01','PRCP','23','','2.3','mm'],['A','2024-01-02','TMAX','100','','10.0','degC']]
            if date_to:rows=[r for r in rows if r[1].replace('-','')<=date_to]
            if corrupt=='unit':rows[0][-1]='degC'
            if corrupt=='record':rows[1][0]='B'
            if corrupt=='conversion':rows[1][-2]='1000'
            if corrupt=='integer_division':rows[0][-2]='2.0'
            if corrupt=='order':rows.reverse()
            if parquet:
                import pyarrow as pa
                import pyarrow.parquet as pq
                out=root/'output.parquet'
                records=[dict(ID=r[0],DATE=datetime.date.fromisoformat(r[1]),ELEMENT=r[2],DATA_VALUE=int(r[3]),Q_FLAG=None,CONVERTED_VALUE=float(r[5]),UNIT=r[6]) for r in rows]
                pq.write_table(pa.Table.from_pylist(records),out)
            else:
                with out.open('w',newline='') as f:
                    w=csv.writer(f);w.writerow(['ID','DATE','ELEMENT','DATA_VALUE','Q_FLAG','CONVERTED_VALUE','UNIT']);w.writerows(rows)
            args=[sys.executable,str(SCRIPT),'--input-gzip',str(source),'--output-parquet' if parquet else '--output-csv',str(out),'--report',str(report)]
            if date_to:args+=['--date-to',date_to]
            result=subprocess.run(args,capture_output=True,text=True)
            return result.returncode,json.loads(report.read_text()) if report.exists() else None
    def test_filters_and_units_and_exact_records(self):
        code,report=self.check_case();self.assertEqual(code,0);self.assertEqual(report['counts']['input'],4);self.assertEqual(report['counts']['actual_output'],2);self.assertEqual(report['counts']['excluded_quality_within_selected_elements'],1)
    def test_wrong_unit_rejected(self):self.assertNotEqual(self.check_case('unit')[0],0)
    def test_changed_record_identity_rejected(self):self.assertNotEqual(self.check_case('record')[0],0)
    def test_wrong_numeric_conversion_rejected(self):self.assertNotEqual(self.check_case('conversion')[0],0)
    def test_hop_integer_division_truncation_rejected(self):self.assertNotEqual(self.check_case('integer_division')[0],0)
    def test_contiguous_date_subset_does_not_count_the_rest_of_year(self):
        code,report=self.check_case(date_to='20240101');self.assertEqual(code,0);self.assertEqual(report['counts']['source_rows'],4);self.assertEqual(report['counts']['input'],3);self.assertEqual(report['counts']['actual_output'],1)
    @unittest.skipUnless(importlib.util.find_spec('pyarrow'),'optional Parquet verification dependency unavailable')
    def test_parquet_native_dates_and_null_flags(self):
        code,report=self.check_case(parquet=True);self.assertEqual(code,0);self.assertEqual(report['counts']['actual_output'],2)
    @unittest.skipUnless(importlib.util.find_spec('pyarrow'),'optional Parquet verification dependency unavailable')
    def test_parquet_unsorted_rows_rejected(self):self.assertNotEqual(self.check_case('order',parquet=True)[0],0)
    @unittest.skipUnless(importlib.util.find_spec('pyarrow'),'optional Parquet verification dependency unavailable')
    def test_parquet_wrong_units_rejected(self):self.assertNotEqual(self.check_case('unit',parquet=True)[0],0)
if __name__=='__main__':unittest.main()
