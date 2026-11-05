import asyncio, json, os, pathlib, subprocess, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
root=pathlib.Path(__file__).resolve().parents[1]
class ModelHandler(BaseHTTPRequestHandler):
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  assert body['model']=='test-model'
  response={'result':'pass','requirements':[{'requirement':'Python','assessment':'met','reason':'Resume mentions Python','evidence':'Python SQL software engineer'}]}
  data=json.dumps({'choices':[{'message':{'content':json.dumps(response)}}]}).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def log_message(self,*args): pass
server=HTTPServer(('127.0.0.1',18766),ModelHandler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
env=os.environ.copy();env['OFFERLETTER_DATA']=str(root/('test-model-'+str(os.getpid())))
proc=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port','18767'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(50):
  try: urllib.request.urlopen('http://127.0.0.1:18767/api/session',timeout=1);break
  except Exception: time.sleep(.2)
 else: raise RuntimeError('Server did not start')
 import httpx
 async def run():
  async with httpx.AsyncClient(base_url='http://127.0.0.1:18767',timeout=30) as c:
   h={'x-offerletter-token':(await c.get('/api/session')).json()['token']}
   bad=await c.post('/api/settings/model',headers=h,json={'provider':'openai','model':'test'})
   assert bad.status_code==400
   cfg=await c.post('/api/settings/model',headers=h,json={'provider':'local','model':'test-model','base_url':'http://127.0.0.1:18766/v1'})
   assert cfg.status_code==200,cfg.text
   data=(root/'tests'/'sample-resume.pdf').read_bytes()
   resume=await c.post('/api/resumes',headers=h,files={'file':('resume.pdf',data,'application/pdf')},data={'titles':'Engineer'}); assert resume.status_code==201,resume.text
   job=await c.post('/api/jobs',headers=h,json={'url':'https://example.com/job','title':'Engineer','description':'Python required'}); assert job.status_code==201
   fit=await c.post('/api/jobs/'+str(job.json()['id'])+'/fit',headers=h,json={'resume_id':resume.json()['id']})
   assert fit.status_code==200,fit.text
   assert fit.json()['result']=='pass' and fit.json()['requirements'][0]['evidence']=='Python SQL software engineer'
   print('Local model settings, cloud consent, fit and evidence validation passed')
 asyncio.run(run())
finally:
 proc.terminate();proc.wait(timeout=10);server.shutdown();server.server_close()
