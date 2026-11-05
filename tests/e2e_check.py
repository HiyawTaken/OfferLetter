import asyncio, os, pathlib, subprocess, sys, time, urllib.request
root=pathlib.Path(__file__).resolve().parents[1]
env=os.environ.copy(); env['OFFERLETTER_DATA']=str(root/('test-e2e-'+str(os.getpid())))
proc=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port','18765'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(50):
  try:
   urllib.request.urlopen('http://127.0.0.1:18765/api/session',timeout=1); break
  except Exception: time.sleep(.2)
 else: raise RuntimeError('Server did not start')
 import httpx
 from playwright.async_api import async_playwright
 async def run():
  async with httpx.AsyncClient(base_url='http://127.0.0.1:18765',timeout=60) as c:
   s=(await c.get('/api/session')).json(); h={'x-offerletter-token':s['token']}
   assert (await c.post('/api/profile',headers=h,json={'first_name':'Ada','email':'ada@example.test'})).status_code==200
   assert (await c.post('/api/rules',headers=h,json={'titles':'Engineer','salary_mode':'fixed','fixed_salary':'95000','tab_limit':2})).status_code==200
   assert (await c.get('/api/rules')).json()['tab_limit']==2
   pdf=(root/'tests'/'sample-resume.pdf').read_bytes()
   resume=await c.post('/api/resumes',headers=h,files={'file':('resume.pdf',pdf,'application/pdf')},data={'titles':'Engineer'})
   assert resume.status_code==201,resume.text
   job=await c.post('/api/jobs',headers=h,json={'url':'http://127.0.0.1:18765/static/fixture-test.html','title':'Fixture','description':'Python SQL engineer','salary_currency':'USD','salary_period':'year'})
   if job.status_code==409: job_id=next(j['id'] for j in (await c.get('/api/jobs')).json() if j['title']=='Fixture')
   else: job_id=job.json()['id']
   matched=await c.get(f'/api/jobs/{job_id}/resume-match'); assert matched.status_code==200,matched.text
   assert matched.json()['ranking'][0]['id']==resume.json()['id']
   duplicate_a=await c.post('/api/jobs',headers=h,json={'url':'https://example.com/first','company':'Acme Inc.','title':'Data Engineer','location':'Remote'})
   duplicate_b=await c.post('/api/jobs',headers=h,json={'url':'https://other.example/second','company':'ACME INC','title':'Data-Engineer','location':'remote'})
   assert duplicate_a.status_code==201 and duplicate_b.status_code==409,(duplicate_a.text,duplicate_b.text)
   opened=await c.post('/api/browser/open',headers=h); assert opened.status_code==200,opened.text
   opened=await c.post(f'/api/jobs/{job_id}/open',headers=h); assert opened.status_code==200,opened.text
   filled=await c.post(f'/api/jobs/{job_id}/fields',headers=h); assert filled.status_code==200,filled.text
   values={f['label'].strip():f['value'] for f in filled.json()['fields']}
   assert values['First name']=='Ada' and values['Email']=='ada@example.test'
   assert values['Desired annual salary']=='95000'
   pending=(await c.get('/api/questions')).json()
   question=next(q for q in pending if 'hear about' in q['label'])
   answered=await c.post('/api/questions/'+str(question['id'])+'/answer',headers=h,json={'answer':'Company website','scope':'global'})
   assert answered.status_code==200,answered.text
   attached=await c.post(f'/api/jobs/{job_id}/attach-resume',headers=h,json={'resume_id':resume.json()['id']}); assert attached.status_code==200,attached.text
   review=await c.post(f'/api/jobs/{job_id}/review',headers=h); assert review.status_code==200,review.text
   assert any(f['value']=='resume.pdf' for f in review.json()['snapshot']['fields'])
   assert review.json()['snapshot']['salary_notes'][0]['source']=='fixed annual salary'
   shot=await c.get(review.json()['screenshot']); assert shot.status_code==200 and shot.headers['content-type'].startswith('image/png')
   assert (await c.post(f'/api/jobs/{job_id}/review')).status_code==403
   submit_url=f'/api/jobs/{job_id}/approve-submit'
   assert (await c.post(submit_url,headers=h,json={'review_id':review.json()['id']})).status_code==400
   submitted=await c.post(submit_url,headers=h,json={'review_id':review.json()['id'],'approve':True}); assert submitted.status_code==200,submitted.text
   assert submitted.json()['status']=='submitted',submitted.text
   again=await c.post(submit_url,headers=h,json={'review_id':review.json()['id'],'approve':True}); assert again.status_code==409,again.text
   second=await c.post('/api/jobs',headers=h,json={'url':'http://127.0.0.1:18765/static/fixture-test.html?next=1','title':'Fixture 2','salary_currency':'USD','salary_period':'year'}); second_id=second.json()['id']
   assert (await c.post(f'/api/jobs/{second_id}/open',headers=h)).status_code==200
   second_fields=(await c.post(f'/api/jobs/{second_id}/fields',headers=h)).json()['fields']
   assert next(f for f in second_fields if 'hear about' in f['label'])['value']=='Company website'
   assert (await c.post(f'/api/jobs/{second_id}/attach-resume',headers=h,json={'resume_id':resume.json()['id']})).status_code==200
   second_review=await c.post(f'/api/jobs/{second_id}/review',headers=h); assert second_review.status_code==200,second_review.text
   blocked=await c.post(f'/api/jobs/{second_id}/approve-submit',headers=h,json={'review_id':second_review.json()['id'],'approve':True})
   assert blocked.status_code==409,blocked.text
   advanced=await c.post(f'/api/jobs/{second_id}/next',headers=h); assert advanced.status_code==200,advanced.text
   final_review=await c.post(f'/api/jobs/{second_id}/review',headers=h); assert final_review.status_code==200,final_review.text
   history=final_review.json()['snapshot']['previous_pages']; assert len(history)==1
   assert any('hear about' in f['label'] for f in history[0]['snapshot']['fields'])
   assert history[0]['snapshot']['salary_notes'][0]['source']=='fixed annual salary'
   assert (await c.get(history[0]['screenshot'])).status_code==200
   print('Multi-page navigation retains the prior page for review')
   print('Next button is not treated as final submission')
   print('Unknown question answered and reused on second application')
   print('Explicit approval, confirmation and duplicate prevention passed')
   print('End-to-end: profile, job, visible Chrome, fill, review screenshot and access guard passed')
 asyncio.run(run())
finally:
 proc.terminate()
 try: proc.wait(timeout=10)
 except subprocess.TimeoutExpired: proc.kill()
