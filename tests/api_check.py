import asyncio, os, pathlib
os.environ['OFFERLETTER_DATA']=str(pathlib.Path('test-data').resolve())
import app, httpx
async def main():
 app.initialize()
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),base_url='http://localhost',timeout=5) as c:
  s=await c.get('/api/session'); assert s.status_code==200
  h={'x-offerletter-token':s.json()['token']}
  assert (await c.post('/api/profile',json={'first_name':'Ada'},headers=h)).status_code==200
  assert (await c.get('/api/profile')).json()['first_name']=='Ada'
  assert (await c.post('/api/answers',json={'question':'When?','answer':'Soon'},headers=h)).status_code==201
  assert (await c.post('/api/answers',json={'question':'No token','answer':'X'})).status_code==403
  print('API profile, answer memory and request authentication passed')
asyncio.run(main())
