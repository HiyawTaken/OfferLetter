from form_engine import match_profile,select_label
import unittest
class MappingTests(unittest.TestCase):
 def test_exact_mapping(self):
  self.assertEqual(match_profile('First name *',{'first_name':'A'}),'A')
  self.assertIsNone(match_profile('Are you authorized to work?',{'work_authorization':'Yes'}))
  self.assertIsNone(match_profile('First name of reference',{'first_name':'A'}))
 def test_high_stakes_require_specific_question_and_explicit_answer(self):
  q='Are you legally authorized to work in the United States?'
  self.assertEqual(match_profile(q,{'work_authorization':'Yes'}),'Yes')
  self.assertIsNone(match_profile(q,{'work_authorization':'Citizen'}))
  self.assertIsNone(match_profile('Are you authorized to work in Canada?',{'work_authorization':'Yes'}))
  self.assertEqual(select_label('yes',['Select one','Yes','No']),'Yes')
  self.assertIsNone(select_label('yes',['Yes - I am authorized','No']))
