"""Fake-kernel lifecycle tests: no VM, GUI, Swap, or real cgroup operations."""
import json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from segmented_runner import SegmentedFreezer
from segmented_scheduler import TaskClock,SegmentPolicy,audit_decisions
from test_segmented import model,config

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);p=Path(self.temp.name)
        (p/'memory.current').write_text('100');(p/'cpu.stat').write_text('usage_usec 20\n')
        self.r=object.__new__(SegmentedFreezer);r=self.r
        r.out=p;r.lock=threading.RLock();r.done=set();r.clocks={'xz':TaskClock()};r.policy_config=config()
        r.records={'xz':dict(freeze_confirmed_ns=0,state='FROZEN',pause_intervals_ns=[[0,None]],running_intervals_ns=[])}
        r.processes={'xz':Mock()};r.processes['xz'].poll.return_value=None;r.groups={'xz':dict(cgroup_path=str(p))}
        r.freeze_rows=[];r.tick_id=1;r.event=Mock();r.cm=Mock();self.now=10.0
        def confirm(op,frozen,timeout):
            return dict(requested_monotonic_ns=int((self.now-.001)*1e9),confirmed_monotonic_ns=int(self.now*1e9),events=dict(frozen=int(frozen),populated=1),frozen=frozen,cgroup=str(p))
        r.cm.set_frozen.side_effect=confirm
        self.p1=patch('segmented_runner.time.monotonic',side_effect=lambda:self.now);self.p1.start();self.addCleanup(self.p1.stop)
        self.p2=patch('segmented_runner.time.monotonic_ns',side_effect=lambda:int(self.now*1e9));self.p2.start();self.addCleanup(self.p2.stop)
    def test_multiple_kernel_confirmations_preserve_first_start_and_residency(self):
        r=self.r;r.transition('xz',False,'approved_next_segment',lease_until=20)
        first=r.records['xz']['release_confirmed_ns'];self.now=15;r.transition('xz',True,'next_segment_budget_denied')
        self.assertEqual(r.clocks['xz'].state,'FROZEN');age=r.clocks['xz'].age(99)
        self.now=100;r.transition('xz',False,'approved_next_segment',lease_until=110)
        self.assertEqual(r.records['xz']['release_confirmed_ns'],first)
        self.assertAlmostEqual(r.records['xz']['frozen_s'],95)
        self.assertGreaterEqual(r.clocks['xz'].age(100),age)
        self.assertEqual([x['memory_current_bytes'] for x in r.freeze_rows],[100,100,100])
    def test_priority_task_starts_on_submit_then_can_freeze_and_resume(self):
        r=self.r
        r.serial_run=Path('serial')
        r.serial_policy='priority'
        r.records['xz']={'release_confirmed_ns':10_000_000_000}
        with patch('segmented_runner.Freezer.launch') as launch:
            r.launch('xz')
        launch.assert_called_once_with('xz',freeze_on_submit=False)
        self.assertEqual(r.clocks['xz'].state,'RUNNING')
        self.assertEqual(r.records['xz']['running_intervals_ns'],[[10_000_000_000,None]])
        r.cm.set_frozen.assert_not_called()
        self.now=11
        r.transition('xz',True,'priority_pressure')
        self.now=12
        r.transition('xz',False,'priority_admission',lease_until=0)
        self.assertEqual(r.records['xz']['release_confirmed_ns'],10_000_000_000)
        self.assertEqual(r.records['xz']['frozen_s'],1)
        self.assertEqual([event['action'] for event in r.freeze_rows],['freeze','resume'])
    def test_failed_confirmation_does_not_advance_state(self):
        self.r.cm.set_frozen.side_effect=TimeoutError('not confirmed')
        with self.assertRaises(TimeoutError):self.r.transition('xz',False,'approved_next_segment',lease_until=20)
        self.assertEqual(self.r.clocks['xz'].state,'FROZEN');self.assertEqual(self.r.freeze_rows,[])
    def test_watchdog_freezes_expired_running_task_without_main_loop(self):
        r=self.r;r.transition('xz',False,'approved_next_segment',lease_until=11);self.now=12
        r.watch_stop=Mock();r.watch_stop.wait.side_effect=[False,True];r.watch_error=None
        r.watchdog()
        self.assertIsNone(r.watch_error);self.assertEqual(r.clocks['xz'].state,'FROZEN')
        self.assertEqual(r.freeze_rows[-1]['reason'],'offline_planned_deadline_watchdog')
    def test_racing_lease_renewal_is_rechecked_before_freezing(self):
        r=self.r;r.transition('xz',False,'approved_next_segment',lease_until=20)
        r.transition('xz',True,'lease_expired_watchdog',expired_only=True)
        self.assertEqual(r.clocks['xz'].state,'RUNNING');self.assertEqual(len(r.freeze_rows),1)
    def test_exited_child_is_not_claimed_as_frozen(self):
        r=self.r;r.processes['xz'].poll.return_value=0
        r.transition('xz',False,'approved_next_segment',lease_until=20)
        self.assertEqual(r.freeze_rows,[]);r.cm.set_frozen.assert_not_called()
    def test_transition_during_memory_read_invalidates_snapshot(self):
        r=self.r;r.clocks['xz'].resumed(1,20)
        def changed():
            r.clocks['xz'].frozen(10);return {'MemAvailable':1000}
        with patch('segmented_runner.memory',side_effect=changed):self.assertIsNone(r.snapshot())
    def test_slow_read_cannot_renew_a_lease(self):
        with patch('segmented_runner.time.monotonic',side_effect=[10,10.3]),patch('segmented_runner.memory',return_value={'MemAvailable':1000}):
            self.assertIsNone(self.r.snapshot())
    def test_foreground_alone_startup_is_not_extrapolated_as_background_risk(self):
        r=self.r;r.guard_history=[];r.offline={'budget':{'reserve_bytes':3}};r.policy_config['model_error_bytes']=0
        r.live_guard(9,100,{'foreground_krita':0,'xz':0},r.clocks)
        self.assertTrue(r.live_guard(10,100,{'foreground_krita':500,'xz':0},r.clocks)['allowed'])
    def test_retained_background_enables_live_reaction_protection(self):
        r=self.r;r.guard_history=[];r.offline={'budget':{'reserve_bytes':3}};r.policy_config['model_error_bytes']=0;r.clocks['xz'].ever_started=True
        r.live_guard(9,100,{'foreground_krita':0,'xz':0},r.clocks)
        self.assertFalse(r.live_guard(10,100,{'foreground_krita':500,'xz':0},r.clocks)['allowed'])
    def test_post_foreground_native_peak_admission_does_not_extrapolate_startup_rates(self):
        r=self.r;r.guard_history=[];r.offline={'budget':{'reserve_bytes':3}};r.policy_config['model_error_bytes']=0
        r.done.add('foreground_krita');r.clocks['xz'].resumed(9,20)
        r.live_guard(9,100,{'foreground_krita':0,'xz':0},r.clocks)
        self.assertTrue(r.live_guard(10,100,{'foreground_krita':0,'xz':500},r.clocks)['allowed'])

class AuditTests(unittest.TestCase):
    def test_replay_and_arithmetic_detect_tampered_approval(self):
        models={'foreground_krita':model(list(range(20,121))),'xz':model(list(range(101))),'table':model([0]*101),'array':model([0]*101)}
        cfg=config();p=SegmentPolicy(models,cfg,3);rows=[]
        for tick,now in enumerate([100.,101.],1):
            current={'foreground_krita':30,'xz':0};clocks={'xz':TaskClock(frozen_since=0)}
            p.observe(now,current);d=p.decide(now,10,1000,current,clocks)
            rows.append(dict(tick=tick,monotonic_s=now,elapsed_s=10,available_bytes=1000,current_bytes=current,clocks={op:vars(c) for op,c in clocks.items()},foreground_done=False,
                freeze=d.freeze,resume=d.resume,leases=d.leases,evidence=d.evidence,parking_deficit=d.parking_deficit,retention_hold=d.retention_hold,emergency_deficit=d.emergency_deficit))
        self.assertEqual(audit_decisions(rows,models,cfg,3)['errors'],[])
        rows[0]['evidence']['xz']['parking_required_bytes']=0
        self.assertTrue(audit_decisions(rows,models,cfg,3)['errors'])

if __name__=='__main__':unittest.main()
