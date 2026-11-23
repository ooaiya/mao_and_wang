"""Fake-kernel lifecycle tests: no VM, GUI, Swap, or real cgroup operations."""
import io,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from priority_policy import policy_from_plan
from segmented_runner import SegmentedFreezer
from segmented_scheduler import TaskClock,SegmentPolicy,audit_decisions
from test_segmented import model,config

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);p=Path(self.temp.name)
        (p/'memory.current').write_text('100');(p/'cpu.stat').write_text('usage_usec 20\n')
        (p/'memory.stat').write_text('anon 80\n')
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
        self.assertEqual([x['anonymous_bytes'] for x in r.freeze_rows],[80,80,80])
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
        r.records['xz']['actual_start_ns']=10_200_000_000
        r.cm.set_frozen.assert_not_called()
        self.now=11
        r.transition('xz',True,'priority_pressure')
        self.now=12
        r.transition('xz',False,'priority_admission',lease_until=0)
        self.assertEqual(r.records['xz']['release_confirmed_ns'],10_000_000_000)
        self.assertEqual(r.records['xz']['frozen_s'],1)
        self.assertEqual([event['action'] for event in r.freeze_rows],['freeze','resume'])
        self.assertAlmostEqual(r.prediction_age('xz',12_500_000_000,0),1.3)
    def test_priority_runner_requests_predicted_freeze_and_logs_the_kernel_proof(self):
        r=self.r
        r.timeline=Mock(t0_ns=9_000_000_000)
        r.background_ops=('xz',)
        r.high_exit_ns=None
        r.last_decision=0
        r.policy_config['guard_interval_s']=.2
        r.clocks['xz'].resumed(9,0)
        r.records['xz'].update(release_confirmed_ns=9_000_000_000,
                               running_intervals_ns=[[9_000_000_000,None]],pause_intervals_ns=[])
        r.cm.checked.return_value=r.out
        (r.out/'memory.stat').write_text('anon 100\n')
        r.decision_stream=io.StringIO()
        r.plan=dict(alignment=dict(offsets_s={'xz':0}),priority_peaks_bytes={'xz':200},
                    budget=dict(reserve_bytes=20,foreground_only_floor_bytes=10),
                    models={'xz':dict(curve=[[0,100],[2000,200],[4000,0]],duration_ms=4000)},
                    priority=dict(task_priorities={'xz':10},max_sample_gap_s=.6,resume_stable_s=.5,
                                  freeze_prediction=dict(horizon_s=2.5,confirmation_s=.7,
                                                         phase_search_s={'default':0},
                                                         level_tolerance_bytes=0,
                                                         reserve_bytes=20,resume_margin_bytes=10)))
        r.priority_policy=policy_from_plan(r.plan)
        with patch('segmented_runner.memory',return_value={'MemAvailable':100}):
            r.schedule_priority()
        decision=json.loads(r.decision_stream.getvalue())
        self.assertEqual(decision['tasks']['xz']['age_s'],1.)
        self.assertEqual(decision['decision']['freeze_prediction']['continued']['first_risk_in_s'],1.)
        self.assertEqual(decision['decision']['freeze_prediction']['reserve_bytes'],20)
        self.assertNotIn('applied_memory_high',decision)
        r.cm.set_frozen.assert_called_once_with('xz',True,timeout=r.policy_config['freeze_timeout_s'])
        self.assertEqual(r.clocks['xz'].state,'FROZEN')
        self.assertEqual(r.freeze_rows[-1]['reason'],'priority_forecast')
    def test_peak_reservation_freezes_shaped_task_only_after_first_batch(self):
        r=self.r
        r.timeline=Mock(t0_ns=9_000_000_000)
        r.background_ops=('table',)
        r.high_exit_ns=None
        r.foreground_events=[]
        r.last_decision=0
        r.policy_config['guard_interval_s']=.2
        r.clocks['table']=r.clocks.pop('xz')
        r.clocks['table'].resumed(9,0)
        r.records['table']=dict(release_confirmed_ns=9_000_000_000,actual_start_ns=9_050_000_000,
                                running_intervals_ns=[[9_000_000_000,None]],pause_intervals_ns=[])
        r.processes['table']=r.processes.pop('xz')
        r.groups=dict(table=dict(cgroup_path=str(r.out)),foreground_krita=dict(cgroup_path=str(r.out)))
        r.cm.checked.return_value=r.out
        r.decision_stream=io.StringIO()
        r.plan=dict(workload_kind='shaped',alignment=dict(offsets_s={'table':0}),
                    priority_peaks_bytes={'table':200,'foreground_krita':160},
                    budget=dict(reserve_bytes=20),
                    models={'table':dict(curve=[[0,100],[2000,200],[4000,0]],duration_ms=4000,
                                         phase_markers_s={'prepare':0.,'grown:1':1.}),
                            'foreground_krita':dict(curve=[[0,100],[8000,160],[10000,0]],duration_ms=10000)},
                    priority=dict(task_priorities={},max_sample_gap_s=.6,resume_stable_s=.5,
                                  freeze_prediction=dict(horizon_s=2.5,confirmation_s=.7,
                                                         phase_search_s={'default':0},level_tolerance_bytes=0,
                                                         reserve_bytes=20,resume_margin_bytes=10,
                                                         reserve_foreground_peak=True)))
        r.priority_policy=policy_from_plan(r.plan)
        trace=r.out/'table'/'phase_trace.jsonl'
        trace.parent.mkdir()
        trace.write_text(json.dumps(dict(event_type='phase_start',phase='prepare',monotonic_ns=9_100_000_000))+'\n',
                         encoding='utf-8')
        with patch('segmented_runner.memory',return_value={'MemAvailable':150}):
            r.schedule_priority()
            r.cm.set_frozen.assert_not_called()
            with trace.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(dict(event_type='phase_start',phase='grown:1',monotonic_ns=10_100_000_000))+'\n')
            self.now=10.3
            r.schedule_priority()
        before,after=map(json.loads,r.decision_stream.getvalue().splitlines())
        self.assertFalse(before['tasks']['table']['freeze_eligible'])
        self.assertTrue(after['tasks']['table']['freeze_eligible'])
        self.assertEqual(after['decision']['freeze'],['table'])
        r.cm.set_frozen.assert_called_once_with('table',True,timeout=r.policy_config['freeze_timeout_s'])
    def test_phase_anchor_advances_only_during_running_intervals(self):
        r=self.r
        r.records['xz'].update(release_confirmed_ns=1_000_000_000,
                               running_intervals_ns=[[1_000_000_000,10_000_000_000],
                                                     [20_000_000_000,None]])
        r.plan=dict(models={'xz':dict(phase_markers_s={'START':4.,'NEXT':12.})})
        r.prediction_events=lambda op:iter((dict(event_type='phase_start',phase='START',
                                                monotonic_ns=8_000_000_000),))
        self.assertEqual(r.prediction_position('xz',21_000_000_000,0),(7.,4.,11.999999999,'START'))
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
