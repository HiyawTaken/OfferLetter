import unittest
from ats_navigation import application_target
class NavigationTests(unittest.TestCase):
 def test_known_apply_paths_only(self):
  self.assertEqual(application_target('https://jobs.lever.co/acme/123','/acme/123/apply'),'https://jobs.lever.co/acme/123/apply')
  self.assertEqual(application_target('https://jobs.ashbyhq.com/acme/123','/acme/123/application'),'https://jobs.ashbyhq.com/acme/123/application')
  self.assertIsNone(application_target('https://jobs.lever.co/acme/123','https://evil.example/acme/123/apply'))
  self.assertIsNone(application_target('https://jobs.lever.co/acme/123','/acme/456/apply'))
  self.assertIsNone(application_target('http://jobs.lever.co/acme/123','/acme/123/apply'))
