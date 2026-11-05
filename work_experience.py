"""Validate user-entered work history and derive the legacy summary fields."""
from datetime import date
import re

def month(value):
 if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}',value):raise ValueError('Use a month and year for employment dates.')
 try: parsed=date.fromisoformat(value+'-01')
 except ValueError:raise ValueError('Enter a valid employment date.')
 return parsed.year*12+parsed.month

def validate(entries):
 if not isinstance(entries,list) or len(entries)>20:raise ValueError('Add up to 20 work experience entries.')
 output=[]
 for entry in entries:
  if not isinstance(entry,dict):raise ValueError('Invalid work experience entry.')
  row={}
  for key,limit in [('employer',300),('title',300),('location',300),('employment_type',100),('description',10000),('start_date',7),('end_date',7)]:
   value=entry.get(key,'')
   if not isinstance(value,str) or len(value)>limit:raise ValueError('Work experience contains an invalid or overly long field.')
   row[key]=value.strip()
  current=entry.get('currently_working',False)
  if not isinstance(current,bool):raise ValueError('Choose whether this is your current job.')
  row['currently_working']=current
  if not row['employer'] or not row['title']:raise ValueError('Enter an employer and job title for each experience entry.')
  start=month(row['start_date'])
  if current:row['end_date']=''
  elif not row['end_date']:raise ValueError('Enter an end date or select that you currently work here.')
  end=month(row['end_date']) if row['end_date'] else date.today().year*12+date.today().month
  if end<start:raise ValueError('The end date must be on or after the start date.')
  output.append(row)
 return output

def summary(entries):
 now=date.today().year*12+date.today().month;covered=set()
 for row in entries:
  end=month(row['end_date']) if row['end_date'] else now
  covered.update(range(month(row['start_date']),min(end,now)))
 latest=max(entries,key=lambda r:(r['currently_working'],r['end_date'] or '9999-12',r['start_date'])) if entries else {}
 return {'current_company':latest.get('employer',''),'current_title':latest.get('title',''),'years_experience':str(len(covered)//12)}
