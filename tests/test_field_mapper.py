import json,unittest
from field_mapper import allowed_keys,prepare_fields,validate_mappings,value_for
class FieldMapperTests(unittest.TestCase):
 def setUp(self):self.profile={'first_name':'Ada','last_name':'Lovelace','email':'ada@example.test','phone':'555','linkedin':'https://linkedin.example/ada','website':'https://example.test'}
 def test_never_map_sensitive_or_other_people(self):
  for label in ('First name of references','Your work email','Sponsor contact phone','Email address or phone','Manager email address','Preferred first name'):
   self.assertEqual(prepare_fields([{'label':label,'type':'text','value':''}],self.profile),[],label)
 def test_only_whitelisted_profile_keys(self):
  fields=prepare_fields([{'label':'Your given name (as displayed)','type':'text','value':''}],self.profile)
  self.assertEqual(fields[0]['allowed_keys'],['first_name'])
  valid=json.dumps({'mappings':[{'field_id':0,'key':'first_name','confidence':0.98}]})
  self.assertEqual(validate_mappings(valid,fields),{0:'first_name'})
  with self.assertRaises(ValueError):validate_mappings(json.dumps({'mappings':[{'field_id':0,'key':'email','confidence':1}]}),fields)
  with self.assertRaises(ValueError):validate_mappings(json.dumps({'mappings':[{'field_id':2,'key':'first_name','confidence':1}]}),fields)
  self.assertEqual(value_for('full_name',self.profile),'Ada Lovelace')
 def test_confidence_and_duplicates(self):
  fields=[{'field_id':0,'allowed_keys':['first_name']}]
  self.assertEqual(validate_mappings(json.dumps({'mappings':[{'field_id':0,'key':'first_name','confidence':0.7}]}),fields),{})
  with self.assertRaises(ValueError):validate_mappings(json.dumps({'mappings':[{'field_id':0,'key':'first_name','confidence':1},{'field_id':0,'key':'first_name','confidence':1}]}),fields)
