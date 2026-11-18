import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('serial',Path(__file__).with_name('run_serial.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class SerialTests(unittest.TestCase):
    def test_overlap_or_missing_task_is_rejected(self):
        r={op:dict(start_ns=i*10,empty_confirmed_ns=i*10+9) for i,op in enumerate(m.ORDER)}
        self.assertTrue(m.validate_sequence(r));r['xz']['start_ns']=8;self.assertFalse(m.validate_sequence(r));r.pop('array');self.assertFalse(m.validate_sequence(r))
if __name__=='__main__':unittest.main()
