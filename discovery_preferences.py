"""Filter public listings against explicit search preferences before tracking."""
import re

def terms(value):
 return [x.strip() for x in str(value or '').split(',') if x.strip()]

def words(value):
 return re.findall(r'[a-z0-9]+',str(value).casefold())

def contains(text,phrase):
 haystack=' '+' '.join(words(text))+' '
 return ' '+' '.join(words(phrase))+' ' in haystack

def ready(rules):
 return bool(terms(rules.get('titles')))

def repository_allowed(name,rules):
 return ready(rules) and name=={'internship':'internships','new_grad':'new_grad'}.get(rules.get('career_stage'))

def matches(job,rules):
 return classify(job,rules)[0]=='clear'

# Word forms that mean the same role word, so "Software Engineering Internship" matches "Software Engineer Intern".
STEMS={'engineering':'engineer','engineers':'engineer','internship':'intern','internships':'intern','interns':'intern','developers':'developer','development':'developer',
       'designers':'designer','design':'designer','analysts':'analyst','analytics':'analyst','scientists':'scientist','science':'scientist','managers':'manager','management':'manager'}
# Words that change what the job is; when the posting has one the target lacks, a person should look.
ROLE_CHANGERS={'manager','director','head','lead','principal','staff','vp','chief','president','architect','recruiter','sales','teacher','instructor','professor'}
GENERIC={'engineer','intern','developer','analyst','associate','specialist','assistant','coordinator','junior','senior','technician','consultant','manager','lead','staff','programmer','trainee','apprentice','co','op','student','entry','level'}
NOISE={'and','or','the','a','an','of','for','to','in','at','with','i','ii','iii','iv','summer','fall','winter','spring','us','usa','remote','hybrid','onsite','new','grad','graduate','full','time','part'}
STATES={'alabama':'al','alaska':'ak','arizona':'az','arkansas':'ar','california':'ca','colorado':'co','connecticut':'ct','delaware':'de','florida':'fl','georgia':'ga','hawaii':'hi','idaho':'id','illinois':'il','indiana':'in','iowa':'ia','kansas':'ks','kentucky':'ky','louisiana':'la','maine':'me','maryland':'md','massachusetts':'ma','michigan':'mi','minnesota':'mn','mississippi':'ms','missouri':'mo','montana':'mt','nebraska':'ne','nevada':'nv','new hampshire':'nh','new jersey':'nj','new mexico':'nm','new york':'ny','north carolina':'nc','north dakota':'nd','ohio':'oh','oklahoma':'ok','oregon':'or','pennsylvania':'pa','rhode island':'ri','south carolina':'sc','south dakota':'sd','tennessee':'tn','texas':'tx','utah':'ut','vermont':'vt','virginia':'va','washington':'wa','west virginia':'wv','wisconsin':'wi','wyoming':'wy','district of columbia':'dc'}

def role_words(text):
 return {STEMS.get(w,w) for w in words(text) if w not in NOISE and not w.isdigit()}

def state_of(location):
 """Two-letter US state named at the end of a location such as 'Austin, TX' or 'Austin, Texas, US'; '' when unclear."""
 parts=[p.strip().casefold() for p in str(location or '').split(',') if p.strip()]
 if parts and parts[-1] in ('us','usa','united states'):parts=parts[:-1]
 if len(parts)<2:return ''
 last=parts[-1]
 return last if last in STATES.values() else STATES.get(last,'')

def as_state(text):
 t=str(text).strip().casefold()
 return t if t in STATES.values() else STATES.get(t,'')

def location_terms(value):
 """'San Francisco, CA, New York, NY' -> [('San Francisco','ca'),('New York','ny')]. A state written after a city belongs to that city."""
 out=[];parts=terms(value)
 for i,part in enumerate(parts):
  # 'New York, NY': a place name followed by a state code is a city, even when it is also a state name.
  following=parts[i+1].strip().casefold() if i+1<len(parts) else ''
  city_named=part.strip().casefold() in ('new york','washington')  # usually meant as the city
  state='' if (following in STATES.values() and len(part.strip())>2) or city_named else as_state(part)
  if state and out and not out[-1][1] and out[-1][0]:out[-1]=(out[-1][0],state)
  elif state:out.append(('',state))
  else:out.append((part,''))
 return out

ABBREVIATIONS={'sf':'san francisco','nyc':'new york','la':'los angeles','dc':'washington'}
# Cities people usually accept for a search in the metro's main city. Only these count as nearby.
METROS={
 'san francisco':('san francisco','south san francisco','oakland','berkeley','emeryville','san mateo','redwood city','menlo park','palo alto','east palo alto','mountain view','sunnyvale','santa clara','san jose','cupertino','milpitas','fremont','foster city','burlingame','san bruno','san carlos','los gatos','pleasanton','san ramon','walnut creek','hayward','san leandro','newark','los altos','belmont','brisbane'),
 'new york':('new york','manhattan','brooklyn','queens','bronx','jersey city','hoboken','newark','stamford','white plains','long island city'),
 'seattle':('seattle','bellevue','redmond','kirkland','bothell','tacoma','everett','renton','issaquah'),
 'los angeles':('los angeles','santa monica','culver city','el segundo','pasadena','burbank','glendale','irvine','long beach','torrance','manhattan beach','playa vista','redondo beach','hawthorne','venice'),
 'boston':('boston','cambridge','somerville','waltham','burlington','lexington','quincy','woburn','bedford'),
 'austin':('austin','round rock','cedar park','georgetown','pflugerville'),
 'chicago':('chicago','evanston','oak brook','schaumburg','naperville'),
 'washington':('washington','arlington','alexandria','reston','mclean','herndon','bethesda','rockville','tysons','silver spring'),
 'denver':('denver','boulder','aurora','englewood','broomfield','lakewood'),
 'san diego':('san diego','la jolla','carlsbad','del mar'),
}

def expand(location):
 """Location text with shorthand like 'SF' or 'NYC' spelled out, so it can be matched."""
 return ' '.join(ABBREVIATIONS.get(w,w) for w in words(location))

def metro_of(city):
 c=' '.join(words(city))
 return next((m for m,cities in METROS.items() if c in cities),None)

METRO_STATES={'new york':{'ny','nj','ct'},'washington':{'dc','va','md'}}  # metros that cross state lines

def nearby_city(location,places):
 """The first city in a job's location that sits in the metro of one of the user's cities, or ''."""
 text=' '+expand(location)+' ';named=states_in(location)
 for place,state in places:
  metro=metro_of(place) if place else None
  if not metro:continue
  allowed=METRO_STATES.get(metro,{state} if state else set())
  if allowed and named and not named&allowed:continue  # same city name, different state
  for city in METROS[metro]:
   if ' '+city+' ' in text:return city
 return ''

def nearby_metro(city,places):
 metro=metro_of(city)
 return next((c for c,_ in places if c and metro_of(c)==metro),metro or 'your locations')

def states_in(location):
 """Every state named after a comma, so 'Seattle, WA San Francisco, CA' gives {'wa','ca'}."""
 found={as_state(m) for m in re.findall(r',\s*([A-Za-z][A-Za-z ]{1,20}?)(?=\s*(?:,|$|\s[A-Z]|\s*\d))',str(location))}
 return found-{''}

def place_matches(location,city,state):
 if city and not contains(expand(location),city):return False
 named=states_in(location)
 return not state or not named or state in named

def title_fit(title,target):
 want=role_words(target);have=role_words(title)
 if not want:return 'miss'
 if contains(title,target):return 'clear'
 shared=want&have
 if shared==want:return 'gray' if (have-want)&ROLE_CHANGERS else 'clear'
 # Close only when a specific word is shared: 'Software Developer Intern' is close to 'Software Engineer Intern', 'Electrical Engineer Intern' is not.
 if not shared-GENERIC:return 'miss'
 return 'gray' if len(want)>=2 and len(shared)>=max(2,len(want)-1) else 'miss'

# Role families: words that point at the same kind of work, so 'Analytics Engineer' counts as related to 'Data Engineer'.
FAMILIES=[{'data','analyst','database','etl','bi','sql'},
          {'software','developer','programmer','backend','frontend','fullstack','full','stack','web','swe','platform','cloud','devops','sre','reliability'},
          {'machine','ml','ai','learning','scientist','research'},
          {'sales','account','accounts','business','bdr','sdr','representative','rep','partnerships','partner','revenue','solutions'},
          {'product'},{'designer','ux','ui'},{'security','cybersecurity','infosec'}]
WEAK={'associate','assistant','specialist','coordinator','junior','senior','intern','trainee','apprentice','co','op','student','entry','level','staff','lead','principal','head','i','ii','iii'}
def related(title,targets):
 """Remotely related: shares a role word (beyond seniority words) or a role family with any target title. The model judges the rest."""
 have=role_words(title)-WEAK
 for target in targets:
  want=role_words(target)-WEAK
  if have&want:return True
  if any(have&f and want&f for f in FAMILIES):return True
 return False

def classify(job,rules,loose=False):
 """('clear'|'gray'|'miss', reason). Clear jobs are prepared automatically, gray ones are shown to the user to decide, misses are dropped.
 loose=True only drops titles that are not even remotely related; the model screens the rest from the description."""
 if not ready(rules):return 'miss','Add target job titles first'
 if any(contains(job.get('company',''),company) for company in terms(rules.get('excluded_companies'))):return 'miss','Company is on your never-apply list'
 if loose:title='clear' if related(job.get('title',''),terms(rules.get('titles'))) else 'miss'
 else:
  fits=[title_fit(job.get('title',''),t) for t in terms(rules.get('titles'))]
  title='clear' if 'clear' in fits else 'gray' if 'gray' in fits else 'miss'
 if title=='miss':return 'miss','Title does not match your target titles'
 reasons=[] if title=='clear' else ['Title is close to, but not the same as, your target titles']
 location=str(job.get('location','')).strip()
 remote=str(rules.get('remote','')).strip().casefold() in ('remote','remote only')
 is_remote=contains(location,'remote')
 if remote and not is_remote:
  if location:return 'miss','Not remote'
  reasons.append('Location not listed, so it may not be remote')
 locations=location_terms(rules.get('locations'))
 if locations and not remote and not any(place_matches(location,city,state) for city,state in locations):
  near=nearby_city(location,locations)
  if not location:reasons.append('Location not listed')
  elif is_remote:reasons.append('Remote, not in your locations')
  elif near:reasons.append(f'In {near.title()}, near {nearby_metro(near,locations)}')
  else:return 'miss','Outside your locations'
 # One uncertain thing is worth asking about; two (a close title somewhere else) is not a match.
 if len(reasons)>1:return 'miss','; '.join(reasons)
 return ('gray',reasons[0]) if reasons else ('clear','')
