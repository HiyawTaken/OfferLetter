import unittest
from answer_memory import select_answer,may_reuse
class MemoryTests(unittest.TestCase):
 def row(self,**kw): return {'question':'How did you hear about us?','answer':'Website','scope':'global','job_id':None,'role_type':None,'expires_at':None,**kw}
 def test_scope_and_matching(self):
  self.assertEqual(select_answer('How did you hear about us?', [self.row()],1,'Engineer'),'Website')
  self.assertIsNone(select_answer('How did you find us?', [self.row()],1,'Engineer'))
  self.assertIsNone(select_answer('How did you hear about us?', [self.row(scope='job',job_id=2)],1,'Engineer'))
  self.assertIsNone(select_answer('How did you hear about us?', [self.row(scope='role',role_type='Designer')],1,'Engineer'))
 def test_sensitive_and_company_specific(self):
  self.assertFalse(may_reuse('Will you need sponsorship?','global'))
  self.assertFalse(may_reuse('Why do you want to work here?','global'))
 def test_expired(self):
  self.assertIsNone(select_answer('How did you hear about us?', [self.row(expires_at='2020-01-01T00:00:00+00:00')],1,'Engineer'))
