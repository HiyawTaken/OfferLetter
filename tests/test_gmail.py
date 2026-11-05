import base64,json,time,unittest
from gmail_connector import parse_client,begin_auth,allowed_domains,sender_matches,inspect_message,classify_status
class GmailFilterTests(unittest.TestCase):
 def message(self,from_header='Recruiting <jobs@greenhouse.io>',date=100000,body='Your verification code is 123456. https://greenhouse.io/verify?token=abc'):
  encoded=base64.urlsafe_b64encode(body.encode()).decode().rstrip('=')
  return {'internalDate':str(date),'payload':{'mimeType':'text/plain','headers':[{'name':'From','value':from_header},{'name':'Subject','value':'Verify'}],'body':{'data':encoded}}}
 def test_pkce_and_desktop_client(self):
  client=parse_client({'installed':{'client_id':'123.apps.googleusercontent.com','client_secret':'secret'}})
  flow=begin_auth(client,8765);self.assertIn('code_challenge_method=S256',flow['url']);self.assertNotIn('secret',flow['url']);self.assertNotIn(flow['verifier'],flow['url'])
  with self.assertRaises(ValueError):parse_client({'web':{'client_id':'bad'}})
 def test_sender_and_time_are_checked(self):
  domains=allowed_domains('https://boards.greenhouse.io/acme/jobs/1')
  self.assertEqual(domains,['greenhouse.io'])
  self.assertTrue(sender_matches('Job <hr@sub.greenhouse.io>',domains))
  self.assertFalse(sender_matches('Job <hr@greenhouse.io.attacker.example>',domains))
  self.assertIsNone(inspect_message(self.message('hr@evil.example'),domains,90000,True,True))
  self.assertIsNone(inspect_message(self.message(date=100),domains,90000,True,True))
 def test_toggle_and_link_allowlist(self):
  msg=self.message(body='Verification code 123456. https://greenhouse.io/verify?token=abc https://greenhouse.io@evil.example/verify?token=x https://greenhouse.io/unrelated')
  found=inspect_message(msg,['greenhouse.io'],90000,True,True)
  self.assertEqual(found['codes'],['123456']);self.assertEqual(found['links'],['https://greenhouse.io/verify?token=abc'])
  self.assertIsNone(inspect_message(msg,['greenhouse.io'],90000,False,False))
 def test_status_needs_known_sender_title_and_clear_subject(self):
  msg=self.message(body='Regarding Python Engineer');msg['payload']['headers'][1]['value']='Interview invitation'
  self.assertEqual(classify_status(msg,['greenhouse.io'],90000,'Python Engineer')['status'],'interview')
  self.assertIsNone(classify_status(msg,['greenhouse.io'],90000,'Designer'))
  msg['payload']['headers'][1]['value']='News about your application'
  self.assertIsNone(classify_status(msg,['greenhouse.io'],90000,'Python Engineer'))
