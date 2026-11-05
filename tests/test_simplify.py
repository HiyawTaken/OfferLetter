import unittest
from simplify import parse_list
class SimplifyTests(unittest.TestCase):
 def test_table_repeat_company_and_closed(self):
  html='''<table><tr><td><a href="https://simplify.jobs/c/a">Acme</a></td><td>Engineer</td><td>Remote</td><td><a href="https://example.com/apply"><img alt="Apply"></a><a href="https://simplify.jobs/p/1">Simplify</a></td></tr><tr><td>↳</td><td>Analyst</td><td>NY</td><td><a href="https://example.com/two">Apply</a></td></tr><tr><td>↳</td><td>Closed</td><td>NY</td><td>🔒</td></tr></table>'''
  jobs=parse_list(html);self.assertEqual(len(jobs),2);self.assertEqual(jobs[1]['company'],'Acme');self.assertEqual(jobs[0]['url'],'https://example.com/apply')
