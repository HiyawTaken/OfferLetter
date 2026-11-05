import unittest
from identity import same_job
class IdentityTests(unittest.TestCase):
 def test_normalization(self):
  a={'company':'ACME, Inc.','title':'Software Engineer','location':'New York, NY'}
  self.assertTrue(same_job(a,{'company':'acme inc','title':'software-engineer','location':'new york ny'}))
 def test_missing_location_conservative(self):
  self.assertTrue(same_job({'company':'Acme','title':'Engineer','location':''},{'company':'acme','title':'engineer','location':'Remote'}))
 def test_different_location_and_incomplete_identity(self):
  a={'company':'Acme','title':'Engineer','location':'NY'}
  self.assertFalse(same_job(a,{'company':'Acme','title':'Engineer','location':'SF'}))
  self.assertFalse(same_job(a,{'company':'','title':'Engineer','location':'NY'}))
