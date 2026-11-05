import asyncio,json,os,pathlib,subprocess,sys,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,HTTPServer
root=pathlib.Path(__file__).resolve().parents[1]
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  body=self.rfile.read(int(self.headers['Content-Length']))
  response={'choices':[{'message':{'content':json.dumps({'quotes':['Python SQL software engineer']})}}]}
  data=json.dumps(response).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def log_message(self,*a):pass
server=HTTPServer(('127.0.0.1',18768),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
env=os.environ.copy();env['OFFERLETTER_DATA']=str(root/('test-cover-'+str(os.getpid())))
proc=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port','18769'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(50):
  try:urllib.request.urlopen('http://127.0.0.1:18769/api/session',timeout=1);break
  except Exception:time.sleep(.2)
 else:raise RuntimeError('Server did not start')
 import httpx
 async def run():
  async with httpx.AsyncClient(base_url='http://127.0.0.1:18769',timeout=60) as c:
   h={'x-offerletter-token':(await c.get('/api/session')).json()['token']}
   cfg=await c.post('/api/settings/model',headers=h,json={'provider':'local','model':'test','base_url':'http://127.0.0.1:18768/v1'});assert cfg.status_code==200,cfg.text
   pdf=(root/'tests'/'sample-resume.pdf').read_bytes();resume=await c.post('/api/resumes',headers=h,files={'file':('resume.pdf',pdf,'application/pdf')},data={'titles':'Engineer'});assert resume.status_code==201,resume.text
   await c.post('/api/profile',headers=h,json={'first_name':'Ada','email':'ada@example.test'})
   opened=await c.post('/api/browser/open',headers=h);assert opened.status_code==200,opened.text
   for suffix in ('file','covertext'):
    job=await c.post('/api/jobs',headers=h,json={'url':'http://127.0.0.1:18769/static/fixture-test.html?'+suffix,'title':'Engineer '+suffix,'description':'Python required'});jid=job.json()['id']
    assert (await c.post(f'/api/jobs/{jid}/open',headers=h)).status_code==200
    draft=await c.post(f'/api/jobs/{jid}/cover-letter',headers=h,json={'resume_id':resume.json()['id']});assert draft.status_code==200,draft.text
    assert draft.json()['quotes']==['Python SQL software engineer']
    attached=await c.post(f'/api/jobs/{jid}/cover-letter/attach',headers=h,json={'cover_id':draft.json()['id']});assert attached.status_code==200,attached.text
    fields=(await c.get(f'/api/jobs/{jid}/fields')).json()['fields'];cover=next(f for f in fields if 'cover letter' in f['label'].lower())
    assert ('Python SQL software engineer' in cover['value']) if suffix=='covertext' else cover['value']=='cover-letter.pdf'
   print('Cover letter evidence, PDF attachment and text attachment passed')
 asyncio.run(run())
finally:
 proc.terminate();proc.wait(timeout=10);server.shutdown();server.server_close()
