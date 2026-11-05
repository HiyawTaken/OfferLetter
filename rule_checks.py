"""Deterministic rule checks. Unknown data is flagged rather than guessed."""
from datetime import date
from salary import amount

def evaluate(job,rules,today=None):
 today=today or date.today();checks=[]
 def add(name,result,reason):checks.append({'rule':name,'result':result,'reason':reason})
 excluded=[x.strip().casefold() for x in rules.get('excluded_companies','').split(',') if x.strip()]
 company=job.get('company','').strip().casefold()
 add('Excluded companies','flag' if excluded and not company else 'fail' if company in excluded else 'pass','Company is unavailable.' if excluded and not company else 'Compared with excluded companies.')
 for key,label,jobkey in [('titles','Titles','title'),('locations','Locations','location')]:
  terms=[x.strip().casefold() for x in rules.get(key,'').split(',') if x.strip()]; value=job.get(jobkey,'').strip().casefold()
  if not terms:add(label,'pass','No restriction set.')
  elif not value:add(label,'flag','Posting does not provide this information.')
  elif any(x in value for x in terms):add(label,'pass','Posting matches a configured term.')
  else:add(label,'flag','Posting does not match a configured term.')
 floor=amount(rules.get('salary_floor'))
 if not rules.get('salary_floor'):add('Salary floor','pass','No salary floor set.')
 elif not floor:add('Salary floor','flag','Salary floor is invalid.')
 elif job.get('salary_currency','').upper()!='USD' or job.get('salary_period','').lower()!='year':add('Salary floor','flag','Comparable annual USD pay is unavailable.')
 else:
  low=amount(job.get('salary_min'));high=amount(job.get('salary_max'))
  if low and high and low>high:add('Salary floor','flag','Posting salary range is invalid.')
  elif high and high<floor:add('Salary floor','fail','The top of the posted range is below your floor.')
  elif low and low>=floor:add('Salary floor','pass','The bottom of the posted range meets your floor.')
  else:add('Salary floor','flag','Posted pay is missing or overlaps your floor.')
 maximum=rules.get('max_age_days','')
 if not maximum:add('Posting age','pass','No posting-age limit set.')
 else:
  try:
   days=int(maximum);posted=date.fromisoformat(job.get('posted_date',''));age=(today-posted).days
   if days<0 or age<0:raise ValueError()
   add('Posting age','pass' if age<=days else 'fail',f'Posting is {age} days old.')
  except (TypeError,ValueError):add('Posting age','flag','A valid posting date is unavailable.')
 remote=rules.get('remote','').strip().casefold();location=job.get('location','').casefold()
 if not remote or remote in ('any','no preference'):add('Remote preference','pass','No remote restriction set.')
 elif remote in ('remote','remote only') and 'remote' in location:add('Remote preference','pass','Posting location says remote.')
 else:add('Remote preference','flag','Confirm the remote arrangement in the posting.')
 return checks
