import importlib.util,json,unittest
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
if __name__=='__main__':unittest.main()
