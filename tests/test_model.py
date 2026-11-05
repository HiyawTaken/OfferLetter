import json, unittest
from unittest.mock import patch
from model_client import endpoint,prepare,validate_response
class ModelTests(unittest.TestCase):
 def test_local_endpoint_rejects_remote(self):
  with self.assertRaises(ValueError): endpoint({'provider':'local','base_url':'http://evil.example/v1'})
 def test_cloud_endpoint_is_fixed(self):
  req=prepare({'provider':'gemini','model':'test','base_url':'https://bad.example'},'secret','job','resume')
  self.assertTrue(req.full_url.startswith('https://generativelanguage.googleapis.com/'))
 def test_evidence_must_exist(self):
  raw=json.dumps({'result':'pass','requirements':[{'requirement':'Python','assessment':'met','reason':'yes','evidence':'invented'}]})
  out=validate_response(raw,'Python engineer')
  self.assertEqual(out['requirements'][0]['assessment'],'unclear')  # fabricated quote never counts as a met requirement
  self.assertEqual(out['requirements'][0]['evidence'],'')
  self.assertEqual(out['result'],'borderline')
 def test_pass_with_unclear_is_downgraded(self):
  raw=json.dumps({'result':'pass','requirements':[{'requirement':'Python','assessment':'unclear','reason':'not shown','evidence':''}]})
  self.assertEqual(validate_response(raw,'Python engineer')['result'],'borderline')
