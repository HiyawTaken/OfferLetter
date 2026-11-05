import asyncio,json,os,pathlib,subprocess,sys,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,HTTPServer
root=pathlib.Path(__file__).resolve().parents[1];seen=[]
class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));seen.append(body)
  vectors=[]
  for i,text in enumerate(body['input']):
   v=([.99,.141067,0,0,0,0,0,0] if text.startswith('Where') else [.9,.435889,0,0,0,0,0,0] if text.startswith('How did you hear about our') else [1,0,0,0,0,0,0,0])
   vectors.append({'index':i,'embedding':v})
  data=json.dumps({'data':vectors}).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def log_message(self,*a):pass
server=HTTPServer(('127.0.0.1',18773),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
env=os.environ.copy();env['OFFERLETTER_DATA']=str(root/('test-semantic-'+str(os.getpid())))
proc=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port','18774'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(50):
  try:urllib.request.urlopen('http://127.0.0.1:18774/api/session',timeout=1);break
  except Exception:time.sleep(.2)
 else:raise RuntimeError('Server did not start')
 import httpx
 async def run():
  async with httpx.AsyncClient(base_url='http://127.0.0.1:18774',timeout=60) as c:
   h={'x-offerletter-token':(await c.get('/api/session')).json()['token']}
   s=await c.post('/api/settings/embeddings',headers=h,json={'enabled':True,'base_url':'http://127.0.0.1:18773/v1','model':'test'});assert s.status_code==200,s.text
   a=await c.post('/api/answers',headers=h,json={'question':'How did you hear about us?','answer':'Company website'});assert a.status_code==201,a.text
   j=await c.post('/api/jobs',headers=h,json={'url':'http://127.0.0.1:18774/static/semantic-fixture.html','title':'Example'});jid=j.json()['id']
   assert (await c.post('/api/browser/open',headers=h)).status_code==200
   assert (await c.post(f'/api/jobs/{jid}/open',headers=h)).status_code==200
   result=await c.post(f'/api/jobs/{jid}/fields',headers=h);assert result.status_code==200,result.text
   fields=result.json()['fields'];assert fields[0]['value']=='Company website' and fields[1]['value']=='',fields
   questions=(await c.get('/api/questions')).json();suggestion=next(q for q in questions if q['label'].startswith('How did'))
   assert suggestion['suggestion']['answer']=='Company website',suggestion
   confirmed=await c.post('/api/questions/'+str(suggestion['id'])+'/answer',headers=h,json={'answer':suggestion['suggestion']['answer'],'scope':'global'});assert confirmed.status_code==200,confirmed.text
   assert all('Company website' not in json.dumps(body) for body in seen)
   print('Local semantic auto-match, uncertain confirmation and question-only payload passed')
 asyncio.run(run())
finally:
 proc.terminate();proc.wait(timeout=10);server.shutdown();server.server_close()
