from jobspy_discovery import search_site
import time
for site in ['linkedin','indeed','glassdoor','google','zip_recruiter']:
 try:
  started=time.monotonic(); result=search_site(site,'software engineer','Remote',3,None,False)
  print(site,'found',len(result['jobs']),'error',bool(result['error']),'seconds',round(time.monotonic()-started,1),flush=True)
 except Exception as exc:print(site,type(exc).__name__,str(exc)[:120],flush=True)
