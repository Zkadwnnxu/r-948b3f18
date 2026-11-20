import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import quality as q
class QualityRules(unittest.TestCase):
 def sample(self,target=60,first=2,elapsed=60):
  return {'cover':{'ok':True},'decode':{'returncode':0,'first_frame_seconds':first,'decoded_seconds':target,'frames':target*25,'audio_stream':True,'max_progress_gap_seconds':.5,'errors':[],'completion_wall_seconds':first+elapsed}}
 def accepted(self,key='a',first=2):
  return {'key':key,'site':{'key':key,'api':'https://example.test/api'},'samples':[q.grade(self.sample(first=first),60),q.grade(self.sample(first=first),60),q.grade(self.sample(120,first,120),120)]}
 def test_complete_audio_video_sample_passes(self):self.assertTrue(q.grade(self.sample(),60)['passed'])
 def test_slow_progress_is_not_hidden_by_clean_exit(self):self.assertFalse(q.grade(self.sample(elapsed=90),60)['passed'])
 def test_bad_cover_and_missing_audio_are_not_preferred(self):
  s=self.sample();s['cover']['ok']=False;self.assertFalse(q.grade(s,60)['passed'])
  s=self.sample();s['decode']['audio_stream']=False;self.assertFalse(q.grade(s,60)['passed'])
 def test_two_baselines_cannot_replace_confirmation(self):
  r=self.accepted();self.assertTrue(q.qualifies(r));r['samples'].pop();self.assertFalse(q.qualifies(r))
 def test_fastest_qualifying_source_first(self):
  result=q.choose([self.accepted('a',6),self.accepted('b',2)],[],{})
  self.assertEqual(result['keys'],['b','a']);self.assertFalse(result['retained_snapshot'])
 def test_unknown_failed_source_cannot_enter(self):
  result=q.choose([{'key':'x','site':{'key':'x'},'samples':[]}],[{'key':'a'}],{})
  self.assertEqual(result['keys'],['a']);self.assertTrue(result['retained_snapshot'])
 def test_individual_failures_have_bounded_grace(self):
  previous=[{'key':'a'}];old={}
  for i in range(3):
   result=q.choose([{'key':'a','samples':[]},self.accepted('b')],previous,old)
   old=result['state'];previous=result['sites']
   self.assertEqual('a'in result['keys'],i<2)
 def test_daily_due_uses_last_attempt_even_if_degraded(self):
  self.assertTrue(q.due(None,100000))
  self.assertFalse(q.due({'attempted_epoch':99000},100000))
  self.assertTrue(q.due({'attempted_epoch':1000},100000))
 def test_decode_command_cannot_use_audio_output_devices(self):
  args=q.command('ffmpeg','https://example.test/a.m3u8',60)
  self.assertEqual(args[-3:],['-f','null','-']);self.assertIn('-nostdin',args);self.assertIn('0:a:0?',args)
  self.assertIn('http,https,tcp,tls,crypto',args);self.assertNotIn('sdl',args)
if __name__=='__main__':unittest.main()
