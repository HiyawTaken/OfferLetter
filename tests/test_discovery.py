import unittest
from discovery import board_url, parse_jobs
class DiscoveryTests(unittest.TestCase):
 def test_providers(self):
  greenhouse={'jobs':[{'title':'Engineer','absolute_url':'https://example.com/1','location':{'name':'Remote'}}]}
  lever=[{'text':'Engineer','hostedUrl':'https://example.com/2','categories':{'location':'NY'}}]
  ashby={'jobs':[{'title':'Engineer','jobUrl':'https://example.com/3','location':'SF'}]}
  for provider,payload in [('greenhouse',greenhouse),('lever',lever),('ashby',ashby)]:
   self.assertEqual(parse_jobs(provider,payload,'Acme')[0]['title'],'Engineer')
 def test_bad_board(self):
  with self.assertRaises(ValueError): board_url('greenhouse','../../bad')
 def test_salary_and_posting_date_use_declared_units(self):
  lever=[{'text':'Engineer','hostedUrl':'https://example.com/job','createdAt':1793491200000,'salaryRange':{'min':90000,'max':120000,'currency':'USD','interval':'yearly'}}]
  row=parse_jobs('lever',lever,'Acme')[0]
  self.assertEqual(row['salary_min'],'90000');self.assertEqual(row['salary_period'],'year');self.assertEqual(row['posted_date'],'2026-11-01')
  lever[0]['salaryRange']['interval']='hourly'
  self.assertEqual(parse_jobs('lever',lever,'Acme')[0]['salary_min'],'')
  greenhouse={'jobs':[{'title':'Engineer','absolute_url':'https://example.com/x','first_published':'2026-11-02T12:00:00Z'}]}
  self.assertEqual(parse_jobs('greenhouse',greenhouse,'Acme')[0]['posted_date'],'2026-11-02')
