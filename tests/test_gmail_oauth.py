import asyncio,json,unittest,uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import app
class Request:
 def __init__(self,data=None,query=None):self.data=data or {};self.query_params=query or {};self.url=SimpleNamespace(port=8765)
 async def json(self):return self.data
class OAuthTests(unittest.TestCase):
 def test_callback_state_one_use_and_secrets_not_in_database(self):
  async def run():
   isolated=Path('test-data')/('gmail-'+uuid.uuid4().hex+'.db')
   with patch.object(app,'DB',isolated):
    app.initialize();client={'installed':{'client_id':'123.apps.googleusercontent.com','client_secret':'client_secret_test'}}
    response=await app.gmail_begin(Request({'client_json':json.dumps(client)}));self.assertEqual(response.status_code,200)
    self.assertNotIn('client_secret_test',response.body.decode())
    self.assertEqual((await app.gmail_callback(Request(query={'state':'wrong','code':'x'}))).status_code,400)
    from urllib.parse import urlparse,parse_qs
    state=parse_qs(urlparse(json.loads(response.body)['authorization_url']).query)['state'][0]
    fake={'refresh_token':'refresh_secret_test','access_token':'access_secret_test'}
    with patch('gmail_connector.exchange',return_value=fake),patch('keyring.set_password') as stored:
     callback=await app.gmail_callback(Request(query={'state':state,'code':'code_secret_test'}));self.assertEqual(callback.status_code,200);stored.assert_called_once()
    self.assertEqual((await app.gmail_callback(Request(query={'state':state,'code':'x'}))).status_code,400)
    with app.db() as c:dump='\n'.join(c.iterdump())
    for secret in ('client_secret_test','refresh_secret_test','access_secret_test','code_secret_test'):self.assertNotIn(secret,dump)
  asyncio.run(run())
