import unittest
from datetime import date
from salary import resolve_salary,bls_series,is_annual_salary,currency_confirmed,parse_roles
from rule_checks import evaluate
class SalaryTests(unittest.TestCase):
 def test_fixed_and_fallback(self):
  self.assertEqual(resolve_salary({'salary_mode':'fixed','fixed_salary':'95000'}, {},None)['value'],'95000')
  self.assertEqual(resolve_salary({'salary_mode':'role','role_salaries':'Engineer=90000','salary_fallback':'fixed,ask','fixed_salary':'80000'},{'title':'Designer'})['value'],'80000')
  self.assertIsNone(resolve_salary({'salary_mode':'ask','fixed_salary':'80000'}, {})['value'])
 def test_posting_midpoint_requires_units(self):
  rules={'salary_mode':'posting'};job={'salary_min':'80000','salary_max':'120001','salary_currency':'USD','salary_period':'year'}
  self.assertEqual(resolve_salary(rules,job)['value'],'100001')
  self.assertIsNone(resolve_salary(rules,{**job,'salary_period':'hour'})['value'])
 def test_optional_never_puts_text_in_required_or_numeric_field(self):
  self.assertEqual(resolve_salary({'salary_mode':'optional'}, {},required=False)['value'],'Negotiable')
  self.assertIsNone(resolve_salary({'salary_mode':'optional'}, {},required=True)['value'])
  self.assertIsNone(resolve_salary({'salary_mode':'optional'}, {},required=False,field_type='number')['value'])
 def test_specific_labels_and_soc(self):
  self.assertTrue(is_annual_salary('Desired annual salary'))
  self.assertFalse(is_annual_salary('Desired salary'))
  self.assertFalse(currency_confirmed('Desired annual salary',{}))
  self.assertTrue(currency_confirmed('Desired salary USD per year',{}))
  self.assertEqual(bls_series('15-1252'),'OEUN000000000000015125213')
  with self.assertRaises(ValueError):parse_roles('Engineer=not money')
 def test_rule_checks(self):
  job={'company':'Acme','title':'Engineer','location':'Remote','salary_min':'90000','salary_max':'120000','salary_currency':'USD','salary_period':'year','posted_date':'2026-11-01'}
  rules={'salary_floor':'100000','max_age_days':'10','remote':'remote only'}
  results={c['rule']:c['result'] for c in evaluate(job,rules,date(2026,11,3))}
  self.assertEqual(results['Salary floor'],'flag');self.assertEqual(results['Posting age'],'pass');self.assertEqual(results['Remote preference'],'pass')
  job['salary_max']='95000';self.assertEqual(next(c for c in evaluate(job,rules,date(2026,11,3)) if c['rule']=='Salary floor')['result'],'fail')
