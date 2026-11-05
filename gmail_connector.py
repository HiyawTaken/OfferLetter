"""Gmail OAuth and narrowly scoped message inspection. No email is executed as instructions."""
import base64, hashlib, json, re, secrets, time, urllib.parse, urllib.request
from email.utils import parseaddr
from model_client import NoRedirect

SCOPE='https://www.googleapis.com/auth/gmail.readonly'
AUTH='https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL='https://oauth2.googleapis.com/token'
API='https://gmail.googleapis.com/gmail/v1/users/me/messages'
KEY_SERVICE='OfferLetter';KEY_NAME='gmail-oauth'

def parse_client(value):
 data=json.loads(value) if isinstance(value,str) else value
 cfg=data.get('installed',{}) if isinstance(data,dict) else {}
 client_id=cfg.get('client_id',''); secret=cfg.get('client_secret','')
 if not isinstance(client_id,str) or not client_id.endswith('.apps.googleusercontent.com') or not isinstance(secret,str) or len(client_id)>300 or len(secret)>300: raise ValueError('Use a Google desktop OAuth client JSON.')
 return {'client_id':client_id,'client_secret':secret}

def begin_auth(client,port):
 state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
 challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
 redirect=f'http://127.0.0.1:{int(port)}/api/gmail/callback'
 params={'client_id':client['client_id'],'redirect_uri':redirect,'response_type':'code','scope':SCOPE,'access_type':'offline','prompt':'consent','state':state,'code_challenge':challenge,'code_challenge_method':'S256'}
 return {'url':AUTH+'?'+urllib.parse.urlencode(params),'state':state,'verifier':verifier,'client':client,'redirect':redirect,'created':time.time()}

def request_json(url,data=None,headers=None):
 req=urllib.request.Request(url,data=data,headers=headers or {})
 with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=20) as response: raw=response.read(2000001)
 if len(raw)>2000000:raise ValueError('Response too large')
 return json.loads(raw)

def exchange(pending,code):
 payload={'client_id':pending['client']['client_id'],'client_secret':pending['client']['client_secret'],'code':code,'code_verifier':pending['verifier'],'grant_type':'authorization_code','redirect_uri':pending['redirect']}
 result=request_json(TOKEN_URL,urllib.parse.urlencode(payload).encode(),{'Content-Type':'application/x-www-form-urlencoded'})
 if not result.get('refresh_token') or not result.get('access_token'):raise ValueError('Google did not return an offline token')
 return {'client_id':payload['client_id'],'client_secret':payload['client_secret'],'refresh_token':result['refresh_token'],'access_token':result['access_token'],'expires_at':time.time()+int(result.get('expires_in',3600))-60}

def access_token(store):
 if store.get('access_token') and float(store.get('expires_at',0))>time.time():return store['access_token'],store
 form={'client_id':store['client_id'],'client_secret':store['client_secret'],'refresh_token':store['refresh_token'],'grant_type':'refresh_token'}
 result=request_json(TOKEN_URL,urllib.parse.urlencode(form).encode(),{'Content-Type':'application/x-www-form-urlencoded'})
 store={**store,'access_token':result['access_token'],'expires_at':time.time()+int(result.get('expires_in',3600))-60}
 return store['access_token'],store

def allowed_domains(job_url):
 host=(urllib.parse.urlparse(job_url).hostname or '').lower().rstrip('.')
 if not re.fullmatch(r'[a-z0-9.-]+',host) or '.' not in host:return []
 # Use known provider-owned domains only for known provider application hosts.
 providers={'greenhouse.io':'greenhouse.io','lever.co':'lever.co','ashbyhq.com':'ashbyhq.com','myworkdayjobs.com':'myworkday.com'}
 for suffix,mail_domain in providers.items():
  if host==suffix or host.endswith('.'+suffix):return [mail_domain]
 return [host]

def sender_matches(sender,domains):
 address=parseaddr(sender)[1].lower()
 if address.count('@')!=1:return False
 domain=address.rsplit('@',1)[-1].rstrip('.')
 return any(domain==allowed or domain.endswith('.'+allowed) for allowed in domains)

def body_text(payload):
 parts=[]
 def walk(part):
  if part.get('filename'):return
  mime=part.get('mimeType','')
  if mime=='text/plain':
   data=part.get('body',{}).get('data','')
   if data:
    try:parts.append(base64.urlsafe_b64decode(data+'='*(-len(data)%4)).decode('utf-8','replace'))
    except Exception:pass
  for child in part.get('parts',[]):walk(child)
 walk(payload);return '\n'.join(parts)[:30000]

def safe_links(text,domains):
 result=[]
 for value in re.findall(r'https://[^\s<>"\']+',text):
  url=value.rstrip('.,;:!?)');p=urllib.parse.urlparse(url);host=(p.hostname or '').lower().rstrip('.')
  if (not p.username and not p.password and any(host==d or host.endswith('.'+d) for d in domains)
      and re.search(r'verif|confirm|activat|token|auth|code',p.path+'?'+p.query,re.I)):result.append(url)
 return list(dict.fromkeys(result))[:5]

def inspect_message(message,domains,after_ms,include_codes,include_links):
 if int(message.get('internalDate',0))<after_ms:return None
 payload=message.get('payload',{});headers={h.get('name','').lower():h.get('value','') for h in payload.get('headers',[])}
 if not sender_matches(headers.get('from',''),domains):return None
 body=body_text(payload)
 codes=re.findall(r'(?i)(?:verification|security|one.time|confirmation|code|otp)[^\d\n]{0,30}(\d{4,8})\b',body) if include_codes else []
 links=safe_links(body,domains) if include_links else []
 if not codes and not links:return None
 return {'sender':headers.get('from',''),'subject':headers.get('subject',''),'codes':list(dict.fromkeys(codes))[:5],'links':links}

def search_verification(token,domains,after_seconds,include_codes,include_links):
 headers={'Authorization':'Bearer '+token}
 query='after:'+str(after_seconds)+' {'+' '.join('from:@'+x for x in domains)+'}'
 search=request_json(API+'?'+urllib.parse.urlencode({'q':query,'maxResults':10}),headers=headers)
 results=[]
 for ref in search.get('messages',[])[:10]:
  mid=ref.get('id','')
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',mid):continue
  message=request_json(API+'/'+mid+'?format=full',headers=headers)
  match=inspect_message(message,domains,after_seconds*1000,include_codes,include_links)
  if match:results.append(match)
 return results

def classify_status(message,domains,after_ms,title):
 if int(message.get('internalDate',0))<after_ms:return None
 payload=message.get('payload',{});headers={h.get('name','').lower():h.get('value','') for h in payload.get('headers',[])}
 if not sender_matches(headers.get('from',''),domains):return None
 subject=headers.get('subject','');body=body_text(payload)
 if len(title.strip())<5 or title.casefold() not in (subject+'\n'+body).casefold():return None
 subject_key=' '.join(subject.casefold().split())
 # Only unambiguous subject lines are acted on; other mail remains unclassified.
 if re.search(r'\b(interview invitation|invitation to interview|schedule (?:an|your) interview)\b',subject_key):status='interview'
 elif re.search(r'\b(application unsuccessful|not selected|not moving forward|application declined)\b',subject_key):status='rejected'
 else:return None
 return {'status':status,'sender':headers.get('from',''),'subject':subject,'received_ms':int(message['internalDate'])}

def search_status(token,domains,after_seconds,title):
 headers={'Authorization':'Bearer '+token};query='after:'+str(after_seconds)+' {'+' '.join('from:@'+x for x in domains)+'}'
 search=request_json(API+'?'+urllib.parse.urlencode({'q':query,'maxResults':25}),headers=headers);matches=[]
 for ref in search.get('messages',[])[:25]:
  mid=ref.get('id','')
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',mid):continue
  result=classify_status(request_json(API+'/'+mid+'?format=full',headers=headers),domains,after_seconds*1000,title)
  if result:matches.append({'id':mid,**result})
 return sorted(matches,key=lambda x:x['received_ms'])
