import unittest
from discovery_preferences import matches,repository_allowed

class PreferencesTest(unittest.TestCase):
 def test_requires_target_and_filters_before_tracking(self):
  job={'title':'Senior Software Engineer','location':'Seattle, WA','company':'Acme'}
  self.assertFalse(matches(job,{}))
  self.assertTrue(matches(job,{'titles':'Software Engineer, Designer','locations':'Seattle'}))
  self.assertFalse(matches(job,{'titles':'Data Scientist'}))
  self.assertFalse(matches(job,{'titles':'Engineer','locations':'Austin'}))
  self.assertFalse(matches(job,{'titles':'Engineer','excluded_companies':'Acme'}))
  self.assertFalse(matches(job,{'titles':'Engineer','remote':'remote only'}))
  self.assertFalse(matches({'title':'Engineering Manager'}, {'titles':'Engineer'}))
 def test_repositories_require_relevant_stage(self):
  self.assertFalse(repository_allowed('internships',{'titles':'Engineer'}))
  self.assertFalse(repository_allowed('new_grad',{'titles':'Engineer','career_stage':'experienced'}))
  self.assertTrue(repository_allowed('internships',{'titles':'Engineer','career_stage':'internship'}))
  self.assertFalse(repository_allowed('new_grad',{'titles':'Engineer','career_stage':'internship'}))
