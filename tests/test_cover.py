import json,unittest
from cover_letter import validate_quotes
class CoverTests(unittest.TestCase):
 def test_accepts_exact_line_and_rejects_invention(self):
  resume='Python SQL software engineer\nBuilt APIs'
  self.assertEqual(validate_quotes(json.dumps({'quotes':['Python SQL software engineer']}),resume),['Python SQL software engineer'])
  with self.assertRaises(ValueError): validate_quotes(json.dumps({'quotes':['Led a large engineering team']}),resume)
  with self.assertRaises(ValueError): validate_quotes(json.dumps({'quotes':['engineer\nBuilt APIs']}),resume)
