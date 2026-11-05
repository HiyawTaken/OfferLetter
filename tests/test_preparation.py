import unittest
from app import preparation_policy
class PolicyTests(unittest.TestCase):
 def fit(self,result='pass',checks=None):return {'result':result,'rule_checks':checks or []}
 def test_skip_and_borderline(self):
  self.assertEqual(preparation_policy(self.fit('fail'),{}),'skip')
  self.assertEqual(preparation_policy(self.fit('borderline'),{'strictness':'flag'}),'review fit')
  self.assertEqual(preparation_policy(self.fit('borderline'),{'strictness':'apply'}),'prepare')
 def test_unevaluated_explicit_rules_pause(self):
  self.assertEqual(preparation_policy(self.fit(),{'salary_floor':'100000'}),'review fit')
  self.assertEqual(preparation_policy(self.fit(checks=[{'result':'flag'}]),{}),'review fit')
