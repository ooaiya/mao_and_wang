"""TEST_ONLY: fake AT-SPI objects, never a real desktop or PILOT result."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
from oomlab_krita_collect.common import GUI


def module(name, filename):
    spec=importlib.util.spec_from_file_location(name, GUI/'scripts'/filename)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


helper=module('accessibility_test', 'krita_accessibility.py')
auto=module('automation_accessibility_test', 'krita_auto.py')
PID=4117  # Fixture identity only; never used to signal/query a real process.
APP,FRAME,TREE,DIALOG,CHOOSER,ALERT,BUTTON=range(7)
SHOWING,DEFUNCT=1,2


class Node:
    def __init__(self, name='', role=FRAME, children=(), pid=PID, rows=None,
                 path=None, bus_name='fixture-bus', showing=True, defunct=False):
        self.name=name;self.role=role;self.children=list(children);self.pid=pid
        self.rows=rows;self.path=path;self.bus_name=bus_name
        self.showing=showing;self.defunct=defunct
    @property
    def childCount(self):return len(self.children)
    def getChildAtIndex(self,index):return self.children[index]
    def getRole(self):return self.role
    def getRoleName(self):return {APP:'application',FRAME:'frame',TREE:'tree'}.get(self.role,'other')
    def get_process_id(self):return self.pid
    def getState(self):return types.SimpleNamespace(contains=lambda value:self.showing if value==SHOWING else self.defunct if value==DEFUNCT else False)
    def getRelationSet(self):return []
    def queryTable(self):return types.SimpleNamespace(nRows=self.rows)


def application(rows=1, tables=1, pid=PID, empty=False):
    views=[Node('Layers',TREE,rows=rows,path=f'/table/{i}') for i in range(tables)]
    children=[] if empty else [Node('Krita',FRAME,views,path='/window')]
    return Node('krita',APP,children,pid=pid,path='/org/a11y/atspi/accessible/root')


def api_for(apps):
    desktop=Node('Desktop',children=apps)
    return types.SimpleNamespace(Registry=types.SimpleNamespace(getDesktop=Mock(return_value=desktop)),
        ROLE_APPLICATION=APP,ROLE_TREE=TREE,ROLE_TREE_TABLE=10,ROLE_TABLE=11,
        ROLE_DIALOG=DIALOG,ROLE_FILE_CHOOSER=CHOOSER,ROLE_ALERT=ALERT,
        ROLE_PUSH_BUTTON=BUTTON,STATE_SHOWING=SHOWING,STATE_DEFUNCT=DEFUNCT,
        RELATION_LABELLED_BY=12)


class SelectionTests(unittest.TestCase):
    def query(self,apps):
        api=api_for(apps)
        with patch.dict(sys.modules,pyatspi=api):return helper.snapshot(PID)
    def test_one_valid_and_one_empty_same_pid_name_path_select_valid(self):
        result=self.query([application(),application(empty=True)])
        self.assertTrue(result['ok']);self.assertEqual(result['selected_application']['index'],0)
        self.assertEqual([c['selection'] for c in result['candidates']],['selected','rejected_empty'])
    def test_empty_first_does_not_hide_valid(self):
        result=self.query([application(empty=True),application()]);self.assertEqual(result['selected_application']['index'],1)
    def test_two_empty_applications_are_retryable(self):
        with self.assertRaises(helper.AccessibilityPending) as caught:self.query([application(empty=True),application(empty=True)])
        self.assertTrue(caught.exception.retryable);self.assertTrue(all(c['selection']=='rejected_empty' for c in caught.exception.candidates))
    def test_two_valid_same_identity_are_ambiguous_not_merged(self):
        with self.assertRaises(helper.AccessibilityAmbiguous) as caught:self.query([application(),application()])
        self.assertFalse(caught.exception.retryable);self.assertEqual(len(caught.exception.candidates),2)
    def test_different_pid_rejected_even_when_name_path_match(self):
        with self.assertRaises(helper.AccessibilityPending) as caught:self.query([application(pid=PID+1)])
        self.assertEqual(caught.exception.candidates[0]['selection'],'rejected_pid')
    def test_wrong_role_rejected(self):
        wrong=application();wrong.role=FRAME
        with self.assertRaises(helper.AccessibilityPending) as caught:self.query([wrong])
        self.assertEqual(caught.exception.candidates[0]['selection'],'rejected_role')
    def test_tree_exception_cannot_succeed(self):
        bad=application();bad.children[0].getChildAtIndex=Mock(side_effect=RuntimeError('disconnected'))
        with self.assertRaises(helper.AccessibilityPending) as caught:self.query([bad])
        self.assertIn('disconnected',caught.exception.candidates[0]['error'])
    def test_valid_plus_unreadable_candidate_does_not_guess(self):
        bad=application();bad.getChildAtIndex=Mock(side_effect=RuntimeError('stale'))
        with self.assertRaises(helper.AccessibilityPending):self.query([application(),bad])
    def test_stale_application_reacquires_desktop_next_call(self):
        bad=application();bad.defunct=True;api=api_for([])
        api.Registry.getDesktop.side_effect=[Node(children=[bad]),Node(children=[application(),application(empty=True)])]
        with patch.dict(sys.modules,pyatspi=api):
            with self.assertRaises(helper.AccessibilityPending):helper.snapshot(PID)
            self.assertTrue(helper.snapshot(PID)['ok'])
        self.assertEqual(api.Registry.getDesktop.call_count,2)
    def test_empty_then_populated_reacquires_instead_of_caching_empty(self):
        api=api_for([]);api.Registry.getDesktop.side_effect=[Node(children=[application(empty=True)]),Node(children=[application()])]
        with patch.dict(sys.modules,pyatspi=api):
            with self.assertRaises(helper.AccessibilityPending):helper.snapshot(PID)
            self.assertTrue(helper.snapshot(PID)['ok'])
    def test_unavailable_advertised_child_is_not_empty(self):
        bad=application();bad.getChildAtIndex=Mock(return_value=None)
        with self.assertRaises(helper.AccessibilityPending):self.query([bad])
    def test_nonempty_but_offscreen_tree_is_not_valid_gui(self):
        bad=application();bad.children[0].showing=False
        with self.assertRaises(helper.AccessibilityPending):self.query([bad])
    def test_root_dies_during_traversal_is_retryable(self):
        bad=application();bad.get_process_id=Mock(side_effect=[PID,PID+1])
        with self.assertRaises(helper.AccessibilityPending):self.query([bad])
    def test_valid_plus_defunct_empty_still_rejects_empty(self):
        empty=application(empty=True);empty.defunct=True
        self.assertTrue(self.query([application(),empty])['ok'])
    def test_duplicate_table_paths_are_not_unconditionally_merged(self):
        app=application(tables=2);app.children[0].children[1].path=app.children[0].children[0].path
        self.assertEqual(len(self.query([app])['layer_views']),2)
    def test_candidate_diagnostics_have_all_requested_fields(self):
        result=self.query([application(),application(empty=True),application(pid=PID+1)])
        for c in result['candidates']:self.assertTrue({'name','pid','role','path','childCount','selection'}<=c.keys())
    def test_unique_layers_table_is_retained(self):
        result=self.query([application(rows=46),application(empty=True)])
        self.assertEqual(len(result['layer_views']),1);self.assertEqual(result['layer_views'][0]['row_count'],46)
        self.assertEqual(result['gui_nodes'][0]['role'],'frame')
    def test_duplicate_layers_are_not_deduplicated_by_name(self):
        self.assertEqual(len(self.query([application(tables=2)])['layer_views']),2)
    def test_layers_read_exception_never_returns_partial_success(self):
        bad=application();bad.children[0].children[0].queryTable=Mock(side_effect=RuntimeError('table gone'))
        with self.assertRaises(helper.AccessibilityPending):self.query([bad])


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.prior=copy.deepcopy(auto.CTX);auto.CTX.update(pid=PID,record=None,settings=dict(auto.DEFAULTS))
    def tearDown(self):auto.CTX.clear();auto.CTX.update(self.prior)
    def probe(self,data):
        response=subprocess.CompletedProcess([],0,json.dumps(data),'')
        with patch.object(auto,'owned'),patch.object(auto.subprocess,'run',return_value=response),contextlib.redirect_stdout(io.StringIO()):return auto.probe_state()
    def test_helper_empty_maps_to_gui_pending(self):
        with self.assertRaises(auto.GuiPending):self.probe(dict(ok=False,pid=PID,retryable=True,error='empty'))
    def test_helper_ambiguity_stops_without_retry(self):
        with self.assertRaises(RuntimeError) as caught:self.probe(dict(ok=False,pid=PID,retryable=False,error='ambiguous'))
        self.assertNotIsInstance(caught.exception,auto.GuiPending)
    def test_helper_wrong_pid_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'PID'):self.probe(dict(ok=True,pid=PID+1))
    def test_probe_restarts_helper_and_rechecks_owner_every_call(self):
        values=[dict(ok=False,pid=PID,retryable=True,error='stale'),dict(ok=True,pid=PID)]
        responses=[subprocess.CompletedProcess([],0,json.dumps(x),'') for x in values]
        with patch.object(auto,'owned') as owned,patch.object(auto.subprocess,'run',side_effect=responses) as call,contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(auto.GuiPending):auto.probe_state()
            self.assertTrue(auto.probe_state()['ok'])
        self.assertEqual(call.call_count,2);self.assertEqual(owned.call_count,2)
    def test_candidate_log_and_last_diagnostic_survive_failed_query(self):
        with tempfile.TemporaryDirectory() as t:
            auto.CTX['record']=str(Path(t)/'krita-process.json');output=io.StringIO()
            data=dict(ok=False,pid=PID,retryable=True,candidates=[dict(name='krita',pid=PID,role='application',path='/root',childCount=0,selection='rejected_empty')])
            with patch.object(auto,'owned'),patch.object(auto.subprocess,'run',return_value=subprocess.CompletedProcess([],1,json.dumps(data),'')),contextlib.redirect_stdout(output):
                with self.assertRaises(auto.GuiPending):auto.probe_state()
            self.assertEqual(json.loads((Path(t)/'accessibility-last.json').read_text())['candidates'],data['candidates'])
            event=json.loads(output.getvalue().split('@@OOM_EVENT ')[1]);self.assertEqual(event['candidates'],data['candidates'])
    def test_base_one_layer_passes(self):
        with patch.object(auto,'probe_state',return_value=dict(layer_views=[dict(row_count=1)])):self.assertTrue(auto.expected_layers(1))
    def test_import_forty_six_layers_passes(self):
        with patch.object(auto,'probe_state',return_value=dict(layer_views=[dict(row_count=46)])):self.assertTrue(auto.expected_layers(46))
    def test_duplicate_layers_fail(self):
        with patch.object(auto,'probe_state',return_value=dict(layer_views=[dict(row_count=46),dict(row_count=46)])):
            with self.assertRaises(auto.GuiPending):auto.expected_layers(46)
    def test_too_few_layers_do_not_pass(self):
        with patch.object(auto,'probe_state',return_value=dict(layer_views=[dict(row_count=45)])):self.assertFalse(auto.expected_layers(46))
    def test_too_many_layers_fail(self):
        with patch.object(auto,'probe_state',return_value=dict(layer_views=[dict(row_count=47)])):
            with self.assertRaises(RuntimeError):auto.expected_layers(46)
    def test_independent_readonly_cli_checks_layers_one(self):
        api=api_for([application(),application(empty=True)]);output=io.StringIO()
        with patch.dict(sys.modules,pyatspi=api),contextlib.redirect_stdout(output):self.assertEqual(helper.main(['--pid',str(PID),'--expect-layers','1']),0)
        self.assertTrue(json.loads(output.getvalue())['layers_validation']['passed'])
    def test_independent_readonly_cli_rejects_unavailable_layers(self):
        api=api_for([application(tables=0)]);output=io.StringIO()
        with patch.dict(sys.modules,pyatspi=api),contextlib.redirect_stdout(output):self.assertEqual(helper.main(['--pid',str(PID),'--expect-layers','1']),1)
        self.assertFalse(json.loads(output.getvalue())['ok'])
    def test_independent_cli_pending_is_explicit(self):
        api=api_for([application(empty=True)]);output=io.StringIO()
        with patch.dict(sys.modules,pyatspi=api),contextlib.redirect_stdout(output):self.assertEqual(helper.main(['--pid',str(PID)]),1)
        self.assertTrue(json.loads(output.getvalue())['retryable'])


if __name__=='__main__':unittest.main()
