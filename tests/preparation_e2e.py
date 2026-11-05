import asyncio,json,os,pathlib,subprocess,sys,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,HTTPServer
root=pathlib.Path(__file__).resolve().parents[1]
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  self.rfile.read(int(self.headers['Content-Length']))
  result={'result':'pass','requirements':[{'requirement':'Python','assessment':'met','reason':'Shown','evidence':'Python SQL software engineer'}]}
  data=json.dumps({'choices':[{'message':{'content':json.dumps(result)}}]}).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def log_message(self,*a):pass
server=HTTPServer(('127.0.0.1',18770),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
env=os.environ.copy();env['OFFERLETTER_DATA']=str(root/('test-run-'+str(os.getpid())))
proc=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port','18771'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(50):
  try:urllib.request.urlopen('http://127.0.0.1:18771/api/session',timeout=1);break
  except Exception:time.sleep(.2)
 else:raise RuntimeError('Server did not start')
 import httpx
 async def run():
  async with httpx.AsyncClient(base_url='http://127.0.0.1:18771',timeout=60) as c:
   h={'x-offerletter-token':(await c.get('/api/session')).json()['token']}
   assert (await c.post('/api/settings/model',headers=h,json={'provider':'local','model':'test','base_url':'http://127.0.0.1:18770/v1'})).status_code==200
   data=(root/'tests'/'sample-resume.pdf').read_bytes();r=await c.post('/api/resumes',headers=h,files={'file':('resume.pdf',data,'application/pdf')},data={'titles':'Engineer'});assert r.status_code==201,r.text
   await c.post('/api/profile',headers=h,json={'first_name':'Ada','email':'ada@example.test'})
   j=await c.post('/api/jobs',headers=h,json={'url':'http://127.0.0.1:18771/static/fixture-test.html','title':'Python Engineer','description':'Python required'});assert j.status_code==201,j.text
   started=await c.post('/api/runs',headers=h);assert started.status_code==202,started.text
   for _ in range(100):
    state=(await c.get('/api/runs')).json()
    if state['status'] not in ('running','pausing'):break
    await asyncio.sleep(.2)
   assert state['status']=='complete',state
   assert state['summary']['prepared']==1,state
   questions=(await c.get('/api/questions')).json();assert any('hear about' in q['label'] for q in questions),questions
   jobs=(await c.get('/api/jobs')).json();assert jobs[0]['status']=='waiting on user'
   events=(await c.get('/api/events')).json();assert not any(e['kind']=='submit_clicked' for e in events)
   print('Run chose resume, checked fit, filled Chrome and stopped for questions without submitting')
 asyncio.run(run())
finally:
 proc.terminate();proc.wait(timeout=10);server.shutdown();server.server_close()
