"""Local credential generation and cautious registration-form detection."""
import hashlib,re,secrets,string
from urllib.parse import urlparse
SERVICE='OfferLetter ATS'

def account_host(url):
 parsed=urlparse(url)
 host=(parsed.hostname or '').lower().rstrip('.')
 if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or not re.fullmatch(r'[a-z0-9.-]+',host) or '.' not in host:raise ValueError('Account pages must use HTTPS on a named domain using the standard port.')
 return host

def credential_ref(host,email):
 return hashlib.sha256((host+'\0'+email.strip().casefold()).encode()).hexdigest()

def generate_password():
 groups=[string.ascii_lowercase,string.ascii_uppercase,string.digits,'!@#$%^-_']
 chars=[secrets.choice(group) for group in groups]
 chars.extend(secrets.choice(''.join(groups)) for _ in range(20))
 secrets.SystemRandom().shuffle(chars)
 return ''.join(chars)

async def registration_form(page):
 """Require one visible form with an unambiguous account-creation button."""
 candidates=[]
 forms=page.locator('form')
 for i in range(await forms.count()):
  form=forms.nth(i);buttons=form.get_by_role('button',name=re.compile(r'^(create account|create an account|sign up|register)$',re.I),exact=True)
  visible=[]
  for j in range(await buttons.count()):
   button=buttons.nth(j)
   if await button.is_visible() and await button.is_enabled():visible.append(button)
  if len(visible)!=1:continue
  emails=form.locator('input[type=email]');passwords=form.locator('input[type=password]')
  email_inputs=[emails.nth(j) for j in range(await emails.count()) if await emails.nth(j).is_visible() and not await emails.nth(j).is_disabled()]
  password_inputs=[passwords.nth(j) for j in range(await passwords.count()) if await passwords.nth(j).is_visible() and not await passwords.nth(j).is_disabled()]
  if len(email_inputs)==1 and len(password_inputs) in (1,2):candidates.append({'form':form,'button':visible[0],'email':email_inputs[0],'passwords':password_inputs})
 if len(candidates)!=1:raise ValueError('Could not identify one account-creation form.')
 return candidates[0]

async def login_form(page):
 candidates=[];forms=page.locator('form')
 for i in range(await forms.count()):
  form=forms.nth(i);buttons=form.get_by_role('button',name=re.compile(r'^(sign in|log in|login)$',re.I),exact=True)
  visible=[buttons.nth(j) for j in range(await buttons.count()) if await buttons.nth(j).is_visible() and await buttons.nth(j).is_enabled()]
  emails=form.locator('input[type=email]');passwords=form.locator('input[type=password]')
  email_inputs=[emails.nth(j) for j in range(await emails.count()) if await emails.nth(j).is_visible() and not await emails.nth(j).is_disabled()]
  password_inputs=[passwords.nth(j) for j in range(await passwords.count()) if await passwords.nth(j).is_visible() and not await passwords.nth(j).is_disabled()]
  if len(visible)==len(email_inputs)==len(password_inputs)==1:candidates.append({'form':form,'button':visible[0],'email':email_inputs[0],'password':password_inputs[0]})
 if len(candidates)!=1:raise ValueError('Could not identify one sign-in form.')
 return candidates[0]
