import unittest, asyncio
from types import SimpleNamespace
import app
class Request:
 def __init__(self, data=None,method='POST',params=None): self.data=data or {}; self.method=method; self.path_params=params or {}
 async def json(self): return self.data
class WorkflowTests(unittest.TestCase):
 def test_answer_lifecycle(self):
  async def go():
   app.initialize()
   r=await app.answer_memory(Request({'question':'Availability?','answer':'Two weeks'})); self.assertEqual(r.status_code,201)
   import json
   aid=json.loads(r.body)['id']
   listed=await app.answer_memory(Request(method='GET')); self.assertIn('Availability?',listed.body.decode())
   deleted=await app.delete_answer(Request(params={'answer_id':aid})); self.assertEqual(deleted.status_code,200)
  asyncio.run(go())
