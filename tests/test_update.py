import importlib.util,json,unittest,tempfile,io,contextlib
from unittest import mock
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('updater',Path(__file__).parents[1]/'scripts/update.py')
u=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(u)
class Rules(unittest.TestCase):
 def test_extract_only_cms_and_normalize(self):
  body='https://good.example/api.php/provide/vod/from/m3u8/at/xml/?ac=list https://bad.example/play.js https://good.example/api.php/provide/vod/from/yun/'
  self.assertEqual(u.discover(body),['https://good.example/api.php/provide/vod/from/m3u8/'])
 def test_validate_requires_direct_hls(self):
  self.assertTrue(u.has_hls([{'vod_play_url':'1$https://cdn.example/x.m3u8?key=2#2$https://cdn.example/y.m3u8'}]))
  self.assertFalse(u.has_hls([{'vod_play_url':'1$https://parser.example/?url=hidden'}]))
 def test_last_good_survives_two_failures(self):
  site={'key':'a','name':'A','type':1,'api':'https://a.example/api'}
  out,state=u.reconcile([{'key':'a','ok':False}],[site],{})
  self.assertEqual(out,[site]);self.assertEqual(state['a']['failures'],1)
  out,state=u.reconcile([{'key':'a','ok':False}],out,state)
  self.assertEqual(out,[site]);self.assertEqual(state['a']['failures'],2)
 def test_third_failure_removes_only_failed_entry(self):
  a={'key':'a','api':'https://a.example/api'};b={'key':'b','api':'https://b.example/api'}
  out,state=u.reconcile([{'key':'a','ok':False},{'key':'b','ok':True,'site':b}],[a,b],{'a':{'failures':2}})
  self.assertEqual(out,[b]);self.assertEqual(state['a']['last_good'],a)
 def test_total_outage_preserves_nonempty_snapshot(self):
  a={'key':'a','api':'https://a.example/api'}
  out,state=u.reconcile([{'key':'a','ok':False}],[a],{'a':{'failures':9}})
  self.assertEqual(out,[a]);self.assertTrue(state['a']['retained_outage'])
 def test_recovery_readds_and_resets(self):
  a={'key':'a','api':'https://new.example/api'}
  out,state=u.reconcile([{'key':'a','ok':True,'site':a}],[],{'a':{'failures':5}})
  self.assertEqual(out,[a]);self.assertEqual(state['a']['failures'],0)
class Selection(unittest.TestCase):
 def test_quality_order_excludes_unreviewed_sites(self):
  a={'key':'a'};b={'key':'b'};unknown={'key':'x'}
  actual,stale=u.apply_selection([unknown,b,a],[],{'preferred_keys':['a','b']})
  self.assertEqual(actual,[a,b]);self.assertFalse(stale)
 def test_metadata_outage_retains_only_last_preferred_snapshot(self):
  a={'key':'a'}
  actual,stale=u.apply_selection([{'key':'x'}],[a],{'preferred_keys':['a']})
  self.assertEqual(actual,[a]);self.assertTrue(stale)
 def test_empty_selection_cannot_publish_unreviewed_data(self):
  with self.assertRaises(ValueError):u.apply_selection([{'key':'x'}],[],{'preferred_keys':[]})
 def test_cli_preserves_reviewed_order_after_all_metadata_turns_healthy(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);out=root/'data';out.mkdir();catalog=root/'catalog.json'
   catalog.write_text(json.dumps([{'key':'a'},{'key':'b'},{'key':'x'}]),encoding='utf-8')
   (out/'selection.json').write_text(json.dumps({'preferred_keys':['b','a'],'checked_at':'fixture'}),encoding='utf-8')
   def checked(entry,previous):return {'key':entry['key'],'ok':True,'site':{'key':entry['key']}}
   with mock.patch.object(u,'check',checked),mock.patch('sys.argv',['update.py','--catalog',str(catalog),'--output',str(out)]),contextlib.redirect_stdout(io.StringIO()):u.main()
   self.assertEqual([v['key']for v in json.loads((out/'vod.json').read_text(encoding='utf-8'))['sites']],['b','a'])
   health=json.loads((out/'health.json').read_text(encoding='utf-8'));self.assertEqual(health['healthy'],3);self.assertEqual(health['published'],2);self.assertTrue(health['quality_review_applied'])
 def test_inspect_only_preserves_original_endpoint(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);catalog=root/'catalog.json';catalog.write_text('[{"key":"a"}]')
   old={'sites':[{'key':'a','api':'https://old.test/api'}]};u.write(root/'vod.json',old)
   def checked(entry,previous):return {'key':'a','ok':True,'site':{'key':'a','api':'https://new.test/api'}}
   with mock.patch.object(u,'check',checked),mock.patch('sys.argv',['update.py','--catalog',str(catalog),'--output',str(root),'--inspect-only']),contextlib.redirect_stdout(io.StringIO()):u.main()
   self.assertEqual(u.load(root/'vod.json',None),old)
 def test_missing_selection_preserves_metadata_mode(self):
  sites=[{'key':'x'}]
  self.assertEqual(u.apply_selection(sites,[],None),(sites,False))
if __name__=='__main__':unittest.main()
