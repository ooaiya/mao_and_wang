import csv
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'基线并发'))
from common.timeline import Timeline,load_plan,wait_until_ns
from common.monitor import MemoryMonitor,meminfo,process_memory
from common.cgroup_manager import CgroupManager


class TimelineTests(unittest.TestCase):
    def test_deadlines_are_absolute_and_cancellable(self):
        began=time.monotonic_ns();planned=[began+i*5_000_000 for i in range(1,8)]
        actual=[]
        for deadline in planned:wait_until_ns(deadline);actual.append(time.monotonic_ns())
        self.assertTrue(all(a>=p for a,p in zip(actual,planned)))
        stop=threading.Event();stop.set();self.assertFalse(wait_until_ns(time.monotonic_ns()+1_000_000_000,stop))

    def test_bad_duplicate_operation_is_rejected(self):
        plan=load_plan(ROOT/'基线并发/baseline_timeline_plan.json');plan['schedule'][1]['operation']='array'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text(json.dumps(plan))
            with self.assertRaises(ValueError):load_plan(p)


class AccountingTests(unittest.TestCase):
    def fixture(self,d,available):
        p=Path(d);(p/'pressure').mkdir(exist_ok=True)
        (p/'meminfo').write_text(f'MemTotal: 16327443 kB\nMemFree: 1000000 kB\nMemAvailable: {available} kB\nSwapTotal: 2097152 kB\nSwapFree: 1048576 kB\nBuffers: 10 kB\nCached: 20 kB\n')
        (p/'vmstat').write_text('oom_kill 2\npgfault 123\n')
        for resource in ['memory','cpu','io']:(p/'pressure'/resource).write_text('some avg10=1.25 avg60=0.2 avg300=0.0 total=55\nfull avg10=0.1 avg60=0.0 avg300=0.0 total=5\n')
        return p

    def test_bytes_and_scopes_and_missing_cgroup_are_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.fixture(Path(d)/'proc' if False else d,1000000);out=p/'out';out.mkdir();log=Timeline(out,'test')
            log.homepage_ready(0,method='unit fixture')
            collector=MemoryMonitor(out,log,{'xz':{'cgroup_path':str(p/'missing'),'pid':None}},proc=p);collector.sample();stats=collector.stop();log.close()
            self.assertEqual(stats['samples'],1);self.assertLessEqual(stats['system_resident_allocated_peak_bytes'],meminfo(p/'meminfo')['MemTotal'])
            with (out/'task_memory.csv').open() as h:row=next(csv.DictReader(h))
            self.assertEqual(row['memory_current_bytes'],'');self.assertEqual(row['sample_status'],'cgroup_unreadable')
            self.assertIsNone(stats['global_oom_count'])

    def test_low_memory_counts_episodes_and_real_time(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.fixture(d,40);out=p/'out';out.mkdir();log=Timeline(out,'test');collector=MemoryMonitor(out,log,{},low_memory_bytes=100*1024,proc=p)
            log.homepage_ready(0,method='unit fixture')
            with mock.patch('common.monitor.time.monotonic_ns',side_effect=[1_000_000_000,1_200_000_000,1_700_000_000,2_000_000_000]):
                collector.sample();collector.sample();self.fixture(d,300);collector.sample();self.fixture(d,30);collector.sample()
            stats=collector.stop();log.close();self.assertEqual(stats['low_memory_events'],2);self.assertAlmostEqual(stats['low_memory_duration_s'],.7)

    def test_VmPeak_is_explicitly_virtual(self):
        raw='VmRSS:\t1024 kB\nVmHWM:\t2048 kB\nVmSize:\t16000000 kB\nVmPeak:\t17000000 kB\n'
        with mock.patch('common.monitor.read_text',side_effect=[raw,None]):p=process_memory(123)
        self.assertEqual(p['rss_bytes'],1048576);self.assertEqual(p['virtual_high_water_bytes'],17000000*1024);self.assertNotIn('memory_peak',p)

    def test_16258_GB_is_below_historical_MemTotal(self):
        self.assertLess(16.258*1e9,16719261696)

    def test_report_parser_excludes_pre_T0_samples(self):
        from common.data_parser import DataParser
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'system_memory.csv').write_text('relative_T0_s,resident_allocated_bytes\n-1,9000000000\n1,5000000000\n')
            self.assertEqual(DataParser(d).get_peak_memory(),(5.0,1.0))


class FreezerContractTests(unittest.TestCase):
    def manager_fixture(self,d):
        mount=Path(d);parent=mount/'delegated';parent.mkdir();cm=CgroupManager(parent,'oomlab_test',mount=mount);group=cm.root/'xz';group.mkdir();(group/'cgroup.freeze').write_text('0');(group/'cgroup.events').write_text('populated 1\nfrozen 0\n');cm.groups['xz']=(group,group.stat().st_ino);return cm,group
    def test_shaped_raster_can_create_an_owned_group(self):
        with tempfile.TemporaryDirectory() as d:
            cm,_=self.manager_fixture(d)
            for filename in ('cgroup.subtree_control','cgroup.controllers'):
                (cm.root/filename).write_text('memory cpu io\n')
            mkdir=Path.mkdir

            def create_with_controls(group,*args,**kwargs):
                mkdir(group,*args,**kwargs)
                for name in ('memory.current','memory.events','cgroup.freeze','cgroup.events'):
                    (group/name).touch()

            with mock.patch.object(Path,'mkdir',create_with_controls):
                group=cm.create('raster')
            self.assertEqual(cm.checked('raster'),group)

    def test_freeze_requires_observed_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            cm,g=self.manager_fixture(d)
            with self.assertRaises(TimeoutError):cm.set_frozen('xz',True,timeout=.02)
            def confirm():time.sleep(.03);(g/'cgroup.events').write_text('populated 1\nfrozen 1\n')
            thread=threading.Thread(target=confirm);thread.start();r=cm.set_frozen('xz',True,timeout=.2);thread.join();self.assertTrue(r['frozen']);self.assertGreaterEqual(r['confirmed_monotonic_ns'],r['requested_monotonic_ns'])
    def test_foreground_and_runner_cannot_be_frozen_or_attached(self):
        with tempfile.TemporaryDirectory() as d:
            cm,g=self.manager_fixture(d)
            with self.assertRaises(ValueError):cm.set_frozen('foreground_krita',True)
            with self.assertRaises(ValueError):cm.attach('xz',os.getpid())
    def test_inode_replacement_invalidates_ownership(self):
        with tempfile.TemporaryDirectory() as d:
            cm,g=self.manager_fixture(d);old=g.with_name('old');g.rename(old);g.mkdir()
            with self.assertRaises(RuntimeError):cm.checked('xz')


