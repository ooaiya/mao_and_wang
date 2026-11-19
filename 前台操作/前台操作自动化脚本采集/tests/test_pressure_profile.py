from pathlib import Path
import unittest

from oomlab_krita_collect.common import GUI
from oomlab_krita_collect.config import read
from oomlab_krita_collect.pilot_assets import script_contract
from oomlab_krita_collect.validation import assess_pressure_profile, verify_pilot_events
from test_timed import fixture


class PressureProfileTests(unittest.TestCase):
    def setUp(self):
        self.config=read(Path(__file__).parent/'fixtures/collection.timed-9000-low-high-low.json')
        self.contract=script_contract(config=self.config)
        self.profile=self.contract['pressure_profile']
        _,self.events=fixture()
        self.events.insert(0,dict(kind='KRITA_PROCESS',monotonic_ns=0,pid=42))
        for label,before,duration in (
            ('PRE_IMPORT_REVIEW','LAYER_IMPORT_START',self.profile['pre_import_review_s']),
            ('POST_CLOSE_REVIEW','KRITA_EXIT',self.profile['post_close_review_s']),
        ):
            index=next(i for i,event in enumerate(self.events) if event['kind']==before)
            start=self.events[index]['monotonic_ns']
            elapsed=int(duration*1e9)
            for event in self.events[index:]:
                event['monotonic_ns']+=elapsed
                if 'origin_monotonic_ns' in event and label=='PRE_IMPORT_REVIEW':
                    event['origin_monotonic_ns']+=elapsed
            self.events[index:index]=[
                dict(kind=label+'_START',monotonic_ns=start,duration_s=duration,pid=42),
                dict(kind=label+'_DONE',monotonic_ns=start+elapsed,duration_s=duration,pid=42,zoom_cycles=5),
            ]

    def samples(self,post_charge=2**30,peak=None,post_pid=42):
        by={event['kind']:event['monotonic_ns'] for event in self.events}
        windows=[
            ('PRE_IMPORT_REVIEW_START','PRE_IMPORT_REVIEW_DONE',2**30,42,0),
            ('LAYER_IMPORT_SUBMITTED','CAPTURE_WINDOW_DONE',peak or self.profile['peak_reference_bytes'],42,0),
            ('POST_CLOSE_REVIEW_START','POST_CLOSE_REVIEW_DONE',post_charge,post_pid,
             by['DOCUMENT_CLOSE_DONE']+15_000_000_000),
        ]
        for start,end,charge,pid,settle in windows:
            for stamp in (max(by[start],settle),by[end]):
                yield dict(scope='krita',krita_pid=pid,monotonic_ns=stamp,memory_current=charge,
                           mem_total_bytes=16*2**30,mem_available_bytes=16*2**30-charge,
                           swap_total_bytes=2**30,swap_free_bytes=2**30)

    def test_three_stage_contract_requires_review_and_same_process(self):
        verify_pilot_events(self.events,self.contract)
        self.events[-2]['pid']=43
        with self.assertRaisesRegex(ValueError,'process mismatch'):
            verify_pilot_events(self.events,self.contract)

    def test_live_peak_and_low_tail_acceptance(self):
        valid=assess_pressure_profile(self.samples(),self.events,self.contract,.5)
        self.assertTrue(valid['valid'],valid['errors'])
        invalid=assess_pressure_profile(self.samples(post_charge=9*2**30,peak=8*2**30),
                                        self.events,self.contract,.5)
        self.assertEqual(invalid['errors'],['high-phase charge peak outside reference tolerance',
                                            'low-pressure bound exceeded: post_close'])
        invalid=assess_pressure_profile(self.samples(post_pid=43),self.events,self.contract,.5)
        self.assertIn('incomplete live Krita samples: post_close',invalid['errors'])

    def test_prepared_document_requires_sequential_owned_instances(self):
        config=read(Path(__file__).parent/'fixtures/collection.rapid-9000.json')
        medium=script_contract(config=read(GUI/'configs/collection.rapid-9000-medium-tail-extended.json'))
        low_duration=medium['pressure_profile']['pre_import_review_s']
        config['automation']['pressure_profile']['pre_import_review_s']=low_duration
        config['automation']['prepared_document']['path']=medium['prepared_document']['path']
        contract=script_contract(config=config)
        asset=contract['prepared_document']['path']
        duration=contract['capture_window_s']
        events=[]
        low_start=5
        low_end=low_start+low_duration
        high_open=low_end+55
        capture_origin=high_open*1_000_000_000

        def event(kind,seconds,**fields):
            events.append(dict(kind=kind,monotonic_ns=int(seconds*1e9),**fields))

        event('KRITA_PROCESS',0,pid=42)
        for second,kind in enumerate(('DOCUMENT_OPEN_START','DOCUMENT_OPEN_DONE',
                                      'CANVAS_ZOOM_START','CANVAS_ZOOM_DONE'),1):
            event(kind,second)
        event('PRE_IMPORT_REVIEW_START',low_start,pid=42,duration_s=low_duration)
        event('PRE_IMPORT_REVIEW_DONE',low_end,pid=42,duration_s=low_duration,zoom_cycles=126)
        event('HIGH_DOCUMENT_OPEN_START',low_end+1,asset=asset)
        event('HIGH_DOCUMENT_SUBMITTED',low_end+3,asset=asset)
        event('HIGH_DOCUMENT_OPEN_DONE',high_open,asset=asset,verification='owned_document_title')
        event('CAPTURE_WINDOW_START',high_open,duration_s=duration,origin_monotonic_ns=capture_origin)
        high_end=high_open+duration
        event('CAPTURE_WINDOW_DONE',high_end,duration_s=duration,
              origin_monotonic_ns=capture_origin,import_verified=False)
        event('DOCUMENT_CLOSE_START',high_end+1)
        event('DOCUMENT_CLOSE_DONE',high_end+2)
        event('HIGH_INSTANCE_EXIT',high_end+3,pid=42,returncode=0)
        event('KRITA_POST_PROCESS',high_end+7,pid=43)
        tail_start=high_end+9
        event('POST_CLOSE_REVIEW_START',tail_start,pid=43,duration_s=90)
        event('POST_CLOSE_REVIEW_DONE',tail_start+90,pid=43,duration_s=90,zoom_cycles=18)
        event('KRITA_EXIT',tail_start+92,pid=43,returncode=0)
        verify_pilot_events(events,contract)
        events[-4]['pid']=42
        with self.assertRaisesRegex(ValueError,'exit/restart identity mismatch'):
            verify_pilot_events(events,contract)
        events[-4]['pid']=43

        tail=dict(kind='TAIL_DOCUMENT_OPEN_DONE',monotonic_ns=(tail_start-1)*1_000_000_000,
                  asset=medium['tail_document']['path'],pid=43,verification='owned_document_title')
        events.insert(-3,tail)
        verify_pilot_events(events,medium)

        def sample(second,pid,charge):
            return dict(scope='krita',krita_pid=pid,monotonic_ns=int(second*1e9),
                        memory_current=charge,mem_total_bytes=16*2**30,
                        mem_available_bytes=16*2**30-charge,swap_total_bytes=0,swap_free_bytes=0)

        samples=[sample(t,42,2**30) for t in (low_start,low_end)]
        samples.extend(sample(t,42,12*2**30) for t in (low_end+3,high_end))
        samples.extend(sample(t,43,5*2**29) for t in (tail_start,tail_start+39,tail_start+90))
        result=assess_pressure_profile(samples,events,medium,.5)
        self.assertTrue(result['valid'],result['errors'])
        self.assertEqual(result['windows']['post_close']['window_s'],90)
        samples[4]['memory_current']=2*2**30-1
        result=assess_pressure_profile(samples,events,medium,.5)
        self.assertIn('tail review charge outside the configured range',result['errors'])
        tail['asset']=asset
        with self.assertRaisesRegex(ValueError,'tail document evidence mismatch'):
            verify_pilot_events(events,medium)
