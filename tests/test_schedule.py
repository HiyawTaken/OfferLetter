import asyncio, json, unittest
from unittest.mock import patch
import app
class Request:
 method='POST'
 def __init__(self,data):self.data=data
 async def json(self):return self.data
class ScheduleTests(unittest.TestCase):
 def test_schedule_and_source_failure(self):
  async def run():
   app.initialize()
   await app.rules_endpoint(Request({'titles':'Tester','career_stage':'new_grad'}))
   bad=await app.schedule_settings(Request({'enabled':True,'interval_minutes':0,'boards':[]}));self.assertEqual(bad.status_code,400)
   saved=await app.schedule_settings(Request({'enabled':True,'prepare_jobs':True,'interval_minutes':5,'boards':[{'provider':'greenhouse','board':'test'},{'provider':'lever','board':'broken'},{'provider':'simplify','board':'new_grad'}]}));self.assertEqual(saved.status_code,200)
   def fetch(provider,board):
    if board=='broken': raise RuntimeError()
    return [{'url':'https://example.com/schedule-job','company':'TestCo','title':'Tester','location':'Remote','description':'A job','source':provider}]
   with patch('discovery.fetch_board',side_effect=fetch), patch('simplify.fetch_list',return_value=[]):
    result=await app.run_discovery_schedule()
    self.assertEqual(result['boards'][0]['added'],1)
    self.assertIn('error',result['boards'][1])
    again=await app.run_discovery_schedule();self.assertEqual(again['boards'][0]['added'],0)
   state=await app.schedule_settings(type('R',(),{'method':'GET'})()); self.assertTrue(json.loads(state.body)['last_run']); self.assertTrue(json.loads(state.body)['prepare_jobs'])
  asyncio.run(run())
