import unittest
from semantic_memory import eligible,choose,endpoint
class SemanticTests(unittest.TestCase):
 def row(self,**extra):return {'id':1,'question':'How did you hear about us?','answer':'Website','scope':'global','job_id':None,'role_type':None,'expires_at':None,**extra}
 def test_local_only(self):
  with self.assertRaises(ValueError):endpoint('http://attacker.example/v1')
 def test_scope_and_safety(self):
  self.assertTrue(eligible('Where did you hear about this role?', [self.row()],1,'Engineer'))
  self.assertFalse(eligible('Where did you not hear about this role?', [self.row()],1,'Engineer'))
  self.assertFalse(eligible('Why did you choose this company?', [self.row()],1,'Engineer'))
  self.assertFalse(eligible('Where did you hear about this role?', [self.row(scope='job',job_id=2)],1,'Engineer'))
  self.assertFalse(eligible('Are you unwilling to work weekends?', [self.row(question='Are you willing to work weekends?')],1,'Engineer'))
  self.assertFalse(eligible('What is your LinkedIn profile URL?', [self.row(question='What is your GitHub profile URL?')],1,'Engineer'))
 def test_thresholds_and_conflicts(self):
  a=self.row();self.assertTrue(choose([1,0],[a],[[1,0]])['automatic'])
  self.assertFalse(choose([1,0],[a],[[0.9,0.435889]])['automatic'])
  b=self.row(id=2,answer='Referral');self.assertFalse(choose([1,0],[a,b],[[1,0],[0.95,0.31225]])['automatic'])
