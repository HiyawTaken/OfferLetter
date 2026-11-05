import asyncio,json,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
import app
class FakePage:
 def is_closed(self):return False
class Request:
 def __init__(self,job_id):self.path_params={'job_id':job_id}
class GmailFlowTests(unittest.TestCase):
 def test_verification_requires_opt_in_and_active_job(self):
  async def run():
   isolated=Path('test-data')/('mail-flow-'+uuid.uuid4().hex+'.db')
   with patch.object(app,'DB',isolated),patch.dict(app.pages,{1:FakePage()}),patch.dict(app.page_opened_at,{1:int(time.time())}):
    app.initialize()
    with app.db() as c:
     c.execute("INSERT INTO jobs(id,url,title) VALUES(1,'https://boards.greenhouse.io/example/jobs/1','Engineer')")
     c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
     c.execute("INSERT INTO settings VALUES('gmail',?)",(json.dumps({'codes':False,'links':False}),))
    self.assertEqual((await app.gmail_verification(Request(1))).status_code,403)
    with app.db() as c:c.execute("UPDATE settings SET value=? WHERE key='gmail'",(json.dumps({'codes':True,'links':False}),))
    credentials=json.dumps({'access_token':'private-token','expires_at':time.time()+1000})
    with patch('keyring.get_password',return_value=credentials),patch('gmail_connector.search_verification',return_value=[{'codes':['123456']}]) as search:
     result=await app.gmail_verification(Request(1));self.assertEqual(result.status_code,200)
     self.assertEqual(search.call_args.args[1],['greenhouse.io']);self.assertTrue(search.call_args.args[3]);self.assertFalse(search.call_args.args[4])
    with app.db() as c:log=' '.join(r['detail'] for r in c.execute('SELECT detail FROM events'))
    self.assertNotIn('private-token',log);self.assertNotIn('123456',log)
  asyncio.run(run())
