import unittest
from matching import rank
class ResumeRankingTests(unittest.TestCase):
 def test_relevant_resume_ranks_first(self):
  rows=[{'id':1,'name':'design','titles':'Designer','extracted_text':'Figma illustration'}, {'id':2,'name':'python','titles':'Engineer','extracted_text':'Python SQL engineering'}]
  self.assertEqual(rank({'title':'Python Engineer','description':'Python and SQL experience'},rows)[0]['id'],2)
