import unittest
from work_experience import validate,summary

class ExperienceTests(unittest.TestCase):
 def entry(self,**changes):return {'employer':'Example Company','title':'Data Intern','location':'Phoenix, AZ','employment_type':'Internship','start_date':'2025-01','end_date':'2025-09','currently_working':False,'description':'Built data pipelines.',**changes}
 def test_multiple_jobs_and_overlapping_dates(self):
  rows=validate([self.entry(),self.entry(start_date='2025-03',end_date='2026-01',title='Engineer')])
  self.assertEqual(len(rows),2);self.assertEqual(summary(rows)['years_experience'],'1')
  self.assertEqual(summary(rows)['current_title'],'Engineer')
 def test_current_job_clears_end_and_is_summary(self):
  rows=validate([self.entry(currently_working=True),self.entry(title='Previous')])
  self.assertEqual(rows[0]['end_date'],'');self.assertEqual(summary(rows)['current_title'],'Data Intern')
 def test_bad_dates_and_missing_details(self):
  for change in [{'end_date':'2024-01'},{'start_date':'2025-13'},{'end_date':''},{'employer':''},{'currently_working':'yes'},{'description':'a'*10001}]:
   with self.subTest(change=change),self.assertRaises(ValueError):validate([self.entry(**change)])
 def test_empty_is_valid(self):self.assertEqual(validate([]),[])
