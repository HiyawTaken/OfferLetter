"""JobSpy job search, isolated per source and normalized for the tracker."""
import math
from datetime import date,datetime
SITES=('linkedin','indeed','glassdoor','google','zip_recruiter')

def clean(value):
 if value is None:return ''
 try:
  if value!=value:return ''
 except Exception:pass
 text=str(value).strip()
 return '' if text.lower() in ('nan','nat','none','<na>') else text

def normalize_records(records,site):
 from salary import amount,pay_label
 out=[]
 for row in records:
  url=clean(row.get('job_url'));title=clean(row.get('title'))
  if not url.startswith(('https://','http://')) or not title:continue
  raw_date=row.get('date_posted');posted=''
  if isinstance(raw_date,(date,datetime)):
   try:posted=raw_date.date().isoformat() if isinstance(raw_date,datetime) else raw_date.isoformat()
   except ValueError:pass
  else:
   try:posted=date.fromisoformat(clean(raw_date)[:10]).isoformat()
   except ValueError:pass
  low,high=amount(row.get('min_amount')),amount(row.get('max_amount'))
  direct=clean(row.get('job_url_direct'))  # the employer's own application page, when the board links out to one
  pay=pay_label(row.get('min_amount'),row.get('max_amount'),clean(row.get('interval')),clean(row.get('currency')))
  currency=clean(row.get('currency')).upper();interval=clean(row.get('interval')).lower()
  if currency!='USD' or interval not in ('year','yearly','annual') or (low and high and low>high):low=high=None
  out.append({'url':url,'title':title[:300],'company':clean(row.get('company'))[:300],'location':clean(row.get('location'))[:300], 'description':clean(row.get('description'))[:30000], 'source':'jobspy:'+site,'posted_date':posted,'salary_min':str(low or ''),'salary_max':str(high or ''),'salary_currency':'USD' if low or high else '','salary_period':'year' if low or high else '','pay':pay,'apply_url':direct if direct.startswith('https://') else ''})
 return out

def search_site(site,query,location='',limit=20,hours_old=None,fetch_description=False):
 if site not in SITES:raise ValueError('Unsupported JobSpy source.')
 if not query.strip() or len(query)>200 or len(location)>200 or not 1<=limit<=100:raise ValueError('Enter a search and a valid result limit.')
 from jobspy import scrape_jobs
 kwargs={'site_name':[site],'search_term':query,'location':location or None,'results_wanted':limit,'country_indeed':'USA','verbose':0,'fetch_description':bool(fetch_description)}
 if site=='google':kwargs['google_search_term']=query+' jobs '+location
 if hours_old is not None:kwargs['hours_old']=hours_old
 frame=scrape_jobs(**kwargs)
 records=normalize_records(frame.to_dict('records'),site)
 errors=frame.attrs.get('errors',{})
 return {'jobs':records,'error':'Source reported an error or blocked the request.' if errors else None,'warnings':bool(frame.attrs.get('warnings',{}))}
