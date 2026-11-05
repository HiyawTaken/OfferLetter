"""Exercise search, partial failures, deduplication, and scheduled searches offline."""
import asyncio, gc, os, pathlib, tempfile
from unittest.mock import patch

with tempfile.TemporaryDirectory(prefix='offerletter-jobspy-') as directory:
 os.environ['OFFERLETTER_DATA']=directory
 import app, httpx
 from jobspy_discovery import normalize_records
 app.initialize()
 rows=normalize_records([
  {'job_url':'https://example.com/jobs/1','title':'Engineer','company':'Acme','location':'Remote','date_posted':'2026-01-02','currency':'USD','interval':'yearly','min_amount':100000,'max_amount':120000},
  {'job_url':'https://example.com/jobs/2','title':'Designer','currency':'USD','interval':'hourly','min_amount':50,'max_amount':70},
  {'job_url':'not a url','title':'Invalid'},
 ],'linkedin')
 assert len(rows)==2 and rows[0]['salary_min']=='100000' and rows[0]['posted_date']=='2026-01-02'
 assert rows[1]['salary_min']=='' and rows[1]['salary_period']==''
 def search(site,query,location,limit,hours,fetch_description):
  if site=='google': raise RuntimeError('upstream failure')
  return {'jobs':rows, 'error':None, 'warnings':False}
 async def run():
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),base_url='http://localhost') as client:
   token=(await client.get('/api/session')).json()['token']; headers={'x-offerletter-token':token}
   assert (await client.post('/api/discover/jobspy',headers=headers,json={'query':'engineer'})).status_code==409
   assert (await client.post('/api/rules',headers=headers,json={'titles':'Engineer','locations':'Remote'})).status_code==200
   assert (await client.post('/api/discover/jobspy',headers=headers,json={'query':'','sites':['linkedin']})).status_code==400
   assert (await client.post('/api/discover/jobspy',headers=headers,json={'query':'engineer','sites':['unknown']})).status_code==400
   with patch('jobspy_discovery.search_site',side_effect=search) as mocked:
    request={'query':'engineer','location':'Remote','sites':['linkedin','google','linkedin'],'limit':2}
    result=await client.post('/api/discover/jobspy',headers=headers,json=request)
    assert result.status_code==200, result.text
    sources=result.json()['sources']; assert len(sources)==2 and sources[0]['added']==1 and sources[1]['error']
    again=await client.post('/api/discover/jobspy',headers=headers,json=request)
    assert again.json()['sources'][0]['added']==0
    assert (await client.post('/api/rules',headers=headers,json={'titles':'Engineer, Developer','locations':'Remote, Seattle'})).status_code==200
    schedule=await client.post('/api/schedule',headers=headers,json={'boards':[{'provider':'jobspy','board':'linkedin'}], 'interval_minutes':60})
    assert schedule.status_code==200,schedule.text
    scheduled=await client.post('/api/schedule/run',headers=headers)
    assert scheduled.status_code==200 and scheduled.json()['boards'][0]['found']==2,scheduled.text
    assert mocked.call_args.args[:3]==('linkedin','Engineer','Remote')
   assert len((await client.get('/api/jobs')).json())==1
   with patch('simplify.fetch_list',return_value=rows) as fetch:
    rejected=await client.post('/api/discover/simplify',headers=headers,json={'list':'new_grad'})
    assert rejected.status_code==409 and not fetch.called
    await client.post('/api/rules',headers=headers,json={'titles':'Engineer','career_stage':'internship'})
    await client.post('/api/schedule',headers=headers,json={'boards':[{'provider':'simplify','board':'new_grad'}]})
    skipped=await client.post('/api/schedule/run',headers=headers)
    assert 'skipped' in skipped.json()['boards'][0] and not fetch.called
    await client.post('/api/rules',headers=headers,json={'titles':'Engineer','career_stage':'new_grad'})
    allowed=await client.post('/api/discover/simplify',headers=headers,json={'list':'new_grad'})
    assert allowed.status_code==200 and fetch.call_count==1
    assert len((await client.get('/api/jobs')).json())==1
  print('JobSpy normalization, validation, partial failure, deduplication and scheduling passed')
 asyncio.run(run())
 gc.collect()  # Close SQLite connections before Windows removes the temporary directory.
