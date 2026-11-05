"""Local-only question embeddings for answer suggestions; never sends answers."""
import json, math, re, urllib.request
from urllib.parse import urlparse
from model_client import NoRedirect
from answer_memory import may_reuse,TIME_SENSITIVE
from form_engine import normalize
from datetime import datetime,timezone

NEGATION={'no','not','never','without','cannot','cant','unable','unwilling','ineligible','unauthorized','none','neither','nor','dont','doesnt','wont','isnt','arent','t'}
OPPOSITES=[({'remote','remoteonly'},{'onsite','on-site','office','inperson'}),({'before','prior'},{'after','later'}),({'fulltime'},{'parttime'}),({'weekend','weekends'},{'weekday','weekdays'})]
GENERIC={'what','where','when','which','this','that','your','with','from','have','will','would','could','please','about','question','answer','position','role','job','the','and','for','you','are','did','how'}
SEMANTIC_BLOCKS=('location','country','remote','onsite','linkedin','github','portfolio','email','phone')

def endpoint(base):
 u=base.rstrip('/');p=urlparse(u)
 if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost','::1') or p.username or p.password or p.query or p.fragment:raise ValueError('Embeddings require an HTTP loopback server.')
 return u+'/embeddings'

def embed(base,model,texts):
 if not model or len(model)>200 or not 1<=len(texts)<=150 or any(not isinstance(t,str) or len(t)>1000 for t in texts):raise ValueError('Invalid embedding request')
 req=urllib.request.Request(endpoint(base),data=json.dumps({'model':model,'input':texts}).encode(),headers={'Content-Type':'application/json'},method='POST')
 with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=60) as res:raw=res.read(5000001)
 if len(raw)>5000000:raise ValueError('Embedding response too large')
 data=json.loads(raw).get('data',[])
 if len(data)!=len(texts):raise ValueError('Missing embeddings')
 indices=[row.get('index') for row in data]
 if sorted(indices)!=list(range(len(texts))):raise ValueError('Invalid embedding indexes')
 rows=sorted(data,key=lambda r:r['index']);vectors=[r.get('embedding') for r in rows]
 if not vectors or not all(isinstance(v,list) and 8<=len(v)<=8192 and len(v)==len(vectors[0]) and all(isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n) for n in v) for v in vectors):raise ValueError('Invalid embedding vectors')
 return vectors

def eligible(label,answers,job_id,role):
 now=datetime.now(timezone.utc).isoformat();query=normalize(label)
 if not may_reuse(label,'global') or any(term in query for term in SEMANTIC_BLOCKS):return []
 out=[]
 for row in answers:
  a=dict(row);q=normalize(a['question'])
  if not may_reuse(a['question'],a['scope']) or any(term in q for term in SEMANTIC_BLOCKS) or q==query:continue
  if a.get('expires_at') and a['expires_at']<=now:continue
  if any(x in q or x in query for x in TIME_SENSITIVE) and not a.get('expires_at'):continue
  if a['scope']=='job' and a.get('job_id')!=job_id:continue
  if a['scope']=='role' and normalize(a.get('role_type') or '')!=normalize(role):continue
  left=set(query.split());right=set(q.split())
  if len(left)<4 or len(right)<4 or len(left&right)<2:continue
  informative_left=left-GENERIC;informative_right=right-GENERIC
  if not (informative_left&informative_right):continue
  if bool(left&NEGATION)!=bool(right&NEGATION):continue
  if re.findall(r'\d+',query)!=re.findall(r'\d+',q):continue
  if any(bool(left&a1 and right&a2) or bool(left&a2 and right&a1) for a1,a2 in OPPOSITES):continue
  out.append(a)
 return out[:100]

def cosine(a,b):
 denom=math.sqrt(sum(x*x for x in a))*math.sqrt(sum(x*x for x in b))
 return sum(x*y for x,y in zip(a,b))/denom if denom else -1.0

def choose(query_vector,answers,vectors,automatic=0.95,suggest=0.65):
 scored=sorted(((cosine(query_vector,v),a) for a,v in zip(answers,vectors)),key=lambda x:x[0],reverse=True)
 if not scored or scored[0][0]<suggest:return None
 score,best=scored[0];conflicting=any(s>=suggest and a['answer']!=best['answer'] for s,a in scored[1:])
 return {'answer_id':best['id'],'score':score,'automatic':score>=automatic and not conflicting}
