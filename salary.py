"""Explicit annual-USD salary choices; ambiguous fields remain unanswered."""
import json, math, re, urllib.request
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from form_engine import normalize

ANNUAL_LABELS={'desired annual salary','expected annual salary','annual salary expectation','annual salary expectations','desired annual base salary','expected annual base salary','desired salary usd per year','annual salary requirement'}
def is_annual_salary(label):return normalize(label) in ANNUAL_LABELS
def currency_confirmed(label,job):
 return 'usd' in label.casefold() or (job.get('salary_currency','').upper()=='USD' and job.get('salary_period','').lower()=='year')

def amount(value):
 try:
  n=Decimal(str(value).replace(',','').strip())
  if not n.is_finite() or n<=0 or n>Decimal('100000000'):return None
  return n
 except (InvalidOperation,ValueError,TypeError):return None

def parse_roles(value):
 result={}
 for line in value.splitlines():
  if not line.strip():continue
  parts=line.rsplit('=',1)
  if len(parts)!=2 or not normalize(parts[0]) or amount(parts[1]) is None:raise ValueError('Use one role=annual amount per line.')
  key=normalize(parts[0])
  if key in result:raise ValueError('Duplicate role salary.')
  result[key]=str(amount(parts[1]))
 return result

def bls_series(soc):
 code=re.sub(r'-','',soc or '')
 if not re.fullmatch(r'\d{6}',code):raise ValueError('Enter a six-digit SOC occupation code.')
 return 'OEUN0000000000000'+code+'13'

def fetch_bls(soc):
 series=bls_series(soc);url='https://api.bls.gov/publicAPI/v2/timeseries/data/'+series
 req=urllib.request.Request(url,headers={'User-Agent':'OfferLetter/0.1'})
 with urllib.request.urlopen(req,timeout=15) as response:raw=response.read(1000001)
 if len(raw)>1000000:raise ValueError('BLS response too large')
 data=json.loads(raw)
 if data.get('status')!='REQUEST_SUCCEEDED':raise ValueError('BLS request failed')
 series_data=data.get('Results',{}).get('series',[])
 if len(series_data)!=1 or series_data[0].get('seriesID')!=series:raise ValueError('Unexpected BLS response')
 years=[x for x in series_data[0].get('data',[]) if x.get('period')=='A01' and amount(x.get('value')) is not None]
 if not years:raise ValueError('No annual wage data')
 latest=max(years,key=lambda x:int(x['year']))
 return {'amount':str(amount(latest['value'])),'year':int(latest['year']),'series':series,'source':'BLS national annual median; coarse for entry-level roles'}

def resolve_salary(rules,job,market=None,required=True,field_type='text'):
 first=rules.get('salary_mode','ask');fallback=rules.get('salary_fallback','ask')
 order=[]
 for item in [first]+[x.strip() for x in fallback.split(',')]:
  if item in ('fixed','role','posting','market','ask','optional') and item not in order:order.append(item)
 for mode in order:
  value=None;reason=''
  if mode=='fixed':value=amount(rules.get('fixed_salary'));reason='fixed annual salary'
  elif mode=='role':
   roles=parse_roles(rules.get('role_salaries',''));value=amount(roles.get(normalize(job.get('title',''))));reason='role-specific annual salary'
  elif mode=='posting':
   low=amount(job.get('salary_min'));high=amount(job.get('salary_max'))
   if low and high and low<=high and job.get('salary_currency','').upper()=='USD' and job.get('salary_period','').lower()=='year':value=(low+high)/2;reason='posting annual range midpoint'
  elif mode=='market':
   if market:value=amount(market.get('amount'));reason=market.get('source','BLS estimate')+' ('+str(market.get('year',''))+')'
  elif mode=='ask':return {'value':None,'reason':'Ask the user'}
  elif mode=='optional':
   if not required and field_type in ('text','textarea'):return {'value':'Negotiable','reason':'Optional field: negotiable'}
   return {'value':None,'reason':'Ask the user; field is required or numeric'}
  if value:return {'value':str(value.quantize(Decimal('1'),rounding=ROUND_HALF_UP)),'reason':reason}
 return {'value':None,'reason':'No usable salary source; ask the user'}


# Display-only pay text for job cards. The annual columns above stay strict because they drive the
# salary floor and form filling; this is just what a person reads, so hourly and monthly pay count too.
PERIODS={'hour':'/hr','hourly':'/hr','day':'/day','daily':'/day','week':'/wk','weekly':'/wk','month':'/mo','monthly':'/mo','year':'/yr','yearly':'/yr','annual':'/yr','annually':'/yr'}
def _money(n,period):
 n=float(n)
 if period=='/yr' and n>=1000:return f'${n/1000:,.0f}k' if n>=100000 else f'${n/1000:,.1f}'.replace('.0','',1).rstrip()+'k' if (n/1000)%1 else f'${n/1000:,.0f}k'
 return f'${n:,.0f}' if n==int(n) else f'${n:,.2f}'
def pay_label(low,high,period,currency='USD'):
 """'$40–$55/hr', '$105k–$135k/yr', or '' when the numbers can't be trusted."""
 word=str(period or '').strip().lower()
 period=PERIODS.get(word) or next((v for k,v in PERIODS.items() if k in word.replace('-',' ').split()),'')  # Lever: 'per-hour-wage'
 if str(currency or 'USD').upper()!='USD' or not period:return ''
 low,high=amount(low),amount(high)
 if low and high and low>high:return ''
 if not (low or high):return ''
 if low and high and low!=high:return f'{_money(low,period)}–{_money(high,period)}{period}'
 return f'{_money(low or high,period)}{period}'

_NUM=r'\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?\s?(k|K)?'
_RANGE=re.compile(_NUM+r'(?:\s*(?:-|–|—|to)\s*'+_NUM+r')?(?:\s*(?:USD|usd))?\s*(?:/|per\s+|an\s+|a\s+)?\s*(hourly|hour|hr|yearly|year|yr|annum|annually|annual|monthly|month|mo|weekly|week|wk)?\b',re.I)
def _value(whole,cents,k):
 n=float(whole.replace(',','')+('.'+cents if cents else ''))
 return n*1000 if k else n
def pay_from_text(text):
 """Pay range written in a posting, only when the period is stated or the numbers can only be annual."""
 for m in _RANGE.finditer(text or ''):
  low=_value(m.group(1),m.group(2),m.group(3))
  high=_value(m.group(4),m.group(5),m.group(6)) if m.group(4) else None
  word=(m.group(7) or '').lower()
  period={'hour':'hour','hourly':'hour','hr':'hour','month':'month','monthly':'month','mo':'month','week':'week','weekly':'week','wk':'week'}.get(word,'year' if word else '')
  if not period and low>=20000 and (high is None or high>=low):period='year'  # bare 'base pay $120,000 - $150,000'
  if not period:continue
  if high is None and period=='year':continue  # one bare yearly number is too often a bonus or a fund size
  if (period=='hour' and not 10<=low<=500) or (period=='year' and not 15000<=low<=2000000):continue
  label=pay_label(low,high,period)
  if label:return label
 return ''
def pay_text(job):
 if job.get('pay'):return job['pay']
 if job.get('salary_min') or job.get('salary_max'):
  label=pay_label(job.get('salary_min'),job.get('salary_max'),job.get('salary_period') or 'year',job.get('salary_currency') or 'USD')
  if label:return label
 return pay_from_text(job.get('description',''))
