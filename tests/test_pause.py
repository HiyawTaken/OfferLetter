import asyncio,unittest,uuid
from pathlib import Path
from unittest.mock import patch
import app
from starlette.responses import JSONResponse
class PauseTests(unittest.TestCase):
 def test_terminal_run_does_not_resume_queued_work(self):
  isolated=Path('test-data')/('pause-'+uuid.uuid4().hex+'.db')
  with patch.object(app,'DB',isolated):
   app.initialize()
   with app.db() as c:run_id=c.execute("INSERT INTO runs(status) VALUES ('running')").lastrowid
   self.assertFalse(app.run_is_pausing(run_id))
   for status in ('pausing','paused','completed','failed','interrupted'):
    with app.db() as c:c.execute('UPDATE runs SET status=? WHERE id=?',(status,run_id))
    self.assertTrue(app.run_is_pausing(run_id),status)
 def test_pause_during_model_wait_does_not_open_browser(self):
  async def run():
   isolated=Path('test-data')/('pause-'+uuid.uuid4().hex+'.db')
   with patch.object(app,'DB',isolated):
    app.initialize()
    with app.db() as c:
     c.execute("INSERT INTO resumes(name,path,titles,extracted_text) VALUES('r','none','engineer','python')")
     c.execute("INSERT INTO jobs(url,title,description) VALUES('https://pause.example/job','engineer','python')")
     c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
     c.execute("INSERT INTO settings(key,value) VALUES('model','{}')")
    entered=asyncio.Event();release=asyncio.Event();opened=[]
    async def slow_fit(request):
     entered.set();await release.wait();return JSONResponse({'result':'pass','rule_checks':[]})
    async def fake_open(request):opened.append(True);return JSONResponse({'ok':True})
    with patch.object(app,'fit_check',slow_fit),patch.object(app,'open_browser',fake_open):
     result=await app.start_preparation_run();await asyncio.wait_for(entered.wait(),5)
     response=await app.pause_preparation(None);self.assertEqual(response.status_code,200)
     release.set();await asyncio.wait_for(app.preparation_task,5)
    with app.db() as c:state=c.execute('SELECT status FROM runs WHERE id=?',(result['id'],)).fetchone()
    self.assertEqual(state['status'],'paused');self.assertEqual(opened,[])
  asyncio.run(run())
