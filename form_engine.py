"""Conservative native form inspection and profile-based filling."""
import re

import random
CURSOR_SCRIPT="""(() => {if (window.__olCursor) return; window.__olCursor=1;
const make=()=>{if(document.getElementById('__ol_cursor')||!document.documentElement)return;const d=document.createElement('div');d.id='__ol_cursor';
d.style.cssText='position:fixed;z-index:2147483647;width:18px;height:18px;border-radius:50%;background:rgba(220,38,38,.75);border:2px solid #fff;box-shadow:0 0 6px rgba(0,0,0,.5);pointer-events:none;left:-40px;top:-40px;transform:translate(-50%,-50%);transition:left .02s linear,top .02s linear';
document.documentElement.appendChild(d)};
addEventListener('mousemove',e=>{make();const d=document.getElementById('__ol_cursor');if(d){d.style.left=e.clientX+'px';d.style.top=e.clientY+'px'}},true);
addEventListener('DOMContentLoaded',make)})();"""

async def install_cursor(context):
 """Show a visible marker that follows the automation pointer so the user can follow along."""
 await context.add_init_script(CURSOR_SCRIPT)

_last={}
async def move_cursor(page,x,y):
 """Move along a slightly varied curve (quadratic Bezier) rather than a straight jump."""
 sx,sy=_last.get(id(page),(max(5,x-120),max(5,y-80)))
 cx=(sx+x)/2+random.uniform(-60,60);cy=(sy+y)/2+random.uniform(-40,40)
 steps=random.randint(14,22)
 for i in range(1,steps+1):
  t=i/steps;u=1-t
  await page.mouse.move(u*u*sx+2*u*t*cx+t*t*x,u*u*sy+2*u*t*cy+t*t*y)
  await page.wait_for_timeout(random.randint(6,16))
 _last[id(page)]=(x,y)
LABEL_JS="""e => {const lever=e.closest('label')?.querySelector('.application-label');if(lever)return lever.textContent.trim();
const group=e.type==='file' ? e.closest('[role=group][aria-labelledby]') : null;
const ids=(group?.getAttribute('aria-labelledby') || e.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean);
const referenced=ids.map(id=>e.ownerDocument.getElementById(id)?.textContent || '').join(' ').trim();
const label=referenced || e.getAttribute('aria-label') || (e.labels && [...e.labels].map(x=>{const c=x.cloneNode(true);c.querySelectorAll('input,select,textarea,button').forEach(n=>n.remove());return c.textContent}).join(' ').trim()) || e.placeholder || e.name || e.id || '';
const legend=(e.type==='radio'||e.type==='checkbox') ? e.closest('fieldset')?.querySelector('legend, .ashby-application-form-question-title')?.textContent.trim() : '';
return legend && !label.includes(legend) ? legend+' — '+label : label}"""
ALIASES={
 'first_name':('first name','given name'), 'last_name':('last name','family name','surname'),
 'email':('email','email address'), 'phone':('phone','phone number','telephone'),
 'location':('location','city','location city','current location','city state','current city'), 'country':('country','country of residence','country region','current country'), 'linkedin':('linkedin','linkedin profile','linkedin url'),
 'school':('school','school name','university','college','institution','school or university','name of school','university name'),
 'degree':('degree','degree type','highest degree','degree level','highest level of education','level of education','education level'),
 'discipline':('discipline','major','field of study','area of study','major field of study','degree discipline'),
 'grad_year':('end date year','graduation year','expected graduation year','graduation date year','year of graduation'),
 'grad_month':('end date month','graduation month','expected graduation month'),
 'gpa':('gpa','cumulative gpa','what is your cumulative gpa','overall gpa','what is your gpa','undergraduate gpa','gpa on a 4 0 scale'),
 'current_company':('current company','current employer','most recent employer','most recent company','current or most recent employer'),
 'current_title':('current title','current job title','most recent job title','current role'),
 'years_experience':('years of experience','how many years of experience do you have','years of relevant experience','total years of experience'),
 'website':('website','portfolio','personal website','portfolio url','other website'),
 'work_authorization':('are you legally authorized to work in the united states','are you authorized to work in the united states','are you legally authorized to work in the us'),
 'sponsorship':('will you now or in the future require sponsorship for employment visa status','will you now or in the future require sponsorship to work in the united states','do you now or in the future require sponsorship for employment'),
 'eeo_gender':('gender','gender identity'), 'eeo_hispanic':('are you hispanic or latino','are you hispanic latino','hispanic or latino','hispanic latino','are you hispanic or latino a'),
 'eeo_race':('race ethnicity','race or ethnicity','race','ethnicity','race and ethnicity'),
 'eeo_veteran':('veteran status','protected veteran status'), 'eeo_disability':('disability status',),
}
HIGH_STAKES={'work_authorization','sponsorship','eeo_gender','eeo_hispanic','eeo_race','eeo_veteran','eeo_disability'}
def normalize(text):return re.sub(r'[^a-z0-9]+',' ',text.lower()).strip()
def profile_key(label):
 key=normalize(label).replace(' required','').strip()
 for field,aliases in ALIASES.items():
  if key in aliases:return field
 # Long yes/no wordings of the two eligibility questions, such as "Do you now, or will you in the future, require sponsorship ... (e.g., H-1B ...)".
 # Only when the question names the United States: the saved answers are about the US, not any other country.
 words=set(key.split());us=' united states ' in ' '+key+' ' or 'us' in words or 'usa' in words
 if not us:return None
 if 'sponsorship' in words and words&{'require','need','requires'}:return 'sponsorship'
 if ('authorized' in words or 'eligible' in words) and 'work' in words and 'sponsorship' not in words:return 'work_authorization'
 return None

def match_profile(label,profile):
 if normalize(label)=='full name':
  first=str(profile.get('first_name','')).strip();last=str(profile.get('last_name','')).strip()
  return (first+' '+last) if first and last else None
 field=profile_key(label);value=str(profile.get(field,'')).strip() if field else ''
 if field=='country' and not value:
  # A US state in the saved location ('Phoenix, AZ') means the country is the United States.
  from discovery_preferences import state_of
  value='United States' if state_of(profile.get('location','')) else ''
 if not value:return None
 if field in ('work_authorization','sponsorship') and normalize(value) not in ('yes','no'):return None
 if field and field.startswith('eeo_') and normalize(value) in ('not set','self describe'):return None
 return value

SELF_ID_LABEL=re.compile(r'\b(gender|race|ethnic|ethnicity|hispanic|latino|veteran|disability)\b')
_DECLINE=re.compile(r'\b(decline|declined|not wish|not want|don t wish|don t want|prefer not|choose not|rather not|not to (answer|disclose|say|identify|self identify)|not declared)\b')
def self_id_meaning(text):
 """What a self-identification answer means, so 'Decline To Self Identify' and 'I do not wish to self-identify' count as the same choice. None when unsure."""
 t=normalize(text)
 if not t:return None
 if _DECLINE.search(t):return 'decline'
 t=re.sub(r'\bnot hispanic or latino\b|\bunited states of america\b','',t).strip()
 if t in ('male','man'):return 'male'
 if t in ('female','woman'):return 'female'
 if t in ('non binary','nonbinary'):return 'nonbinary'
 if 'veteran' in t:
  if re.search(r'\bidentify as one or more\b',t):return 'protected_veteran'
  if re.search(r'\bnot a protected veteran\b',t) and not re.search(r'\bbut not\b|\bi am a veteran\b',t):return 'not_protected_veteran'
  return None  # 'not a veteran' and 'veteran but not protected' are different facts: ask
 if 'disability' in t:
  return 'disability_yes' if t.startswith('yes') else 'disability_no' if t.startswith('no') else None
 for meaning,pattern in (('two_or_more',r'\btwo or more\b'),('american_indian',r'\bamerican indian\b|\balaska n?native\b|\balaskan native\b'),('pacific_islander',r'\bnative hawaiian\b|\bpacific islander\b'),
                         ('black',r'\bblack\b|\bafrican american\b'),('asian',r'\basian\b'),('white',r'\bwhite\b'),('hispanic',r'\bhispanic\b|\blatino\b|\blatina\b|\blatinx\b')):
  if re.search(pattern,t):return meaning
 return None

def same_meaning_option(answer,options):
 """The one option that means the same as a self-identification answer, or None when there is not exactly one."""
 meaning=self_id_meaning(answer)
 if not meaning:return None
 matches=[option for option in options if self_id_meaning(option)==meaning]
 return matches[0] if len(matches)==1 else None

def select_label(answer,options,self_id=False):
 matches=[option for option in options if normalize(option)==normalize(answer) and normalize(option)]
 if len(matches)==1:return matches[0]
 return same_meaning_option(answer,options) if self_id and not matches else None

async def inspect(page,profile,fill=False):
 """Read visible native controls in each frame; never infer or generate profile answers."""
 fields=[]
 for frame_index,frame in enumerate(page.frames):
  controls=frame.locator('input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select')
  for index in range(await controls.count()):
   control=controls.nth(index)
   try:
    if await control.get_attribute('aria-hidden')=='true':continue
    visible=await control.is_visible()
    if not visible and await control.get_attribute('type')!='file':continue
    if not visible and not await control.evaluate("e => {const g=e.closest('[role=group]');return !!g && !!g.getClientRects().length}"):continue
    info=await control.evaluate('''e => {const selected=e.tagName==='SELECT' && e.selectedOptions.length ? e.selectedOptions[0] : null;const sel=selected ? selected.textContent.trim() : '';const placeholder=selected && (selected.disabled || !selected.value || /^(select|choose|please select|please choose|--)/i.test(sel));const combo=e.getAttribute('role')==='combobox';const leverLocation=e.getAttribute('data-qa')==='location-input' && !!e.closest('label')?.querySelector('input[name=selectedLocation]');let locationSelected=false;if(leverLocation){try{const v=JSON.parse(e.closest('label').querySelector('input[name=selectedLocation]').value);locationSelected=typeof v.name==='string' && !!v.name.trim() && v.name.trim()===e.value.trim()}catch(_){}}const chosen=combo ? (e.closest('.select__container')?.querySelector('.select__single-value')?.textContent.trim() || '') : '';const group=e.type==='file' ? e.closest('[role=group]') : null;const leverRequired=e.closest('label')?.querySelector('.application-label .required');return {label:'',type:combo ? 'combobox' : leverLocation ? 'location-autocomplete' : e.type,required:e.required || e.getAttribute('aria-required')==='true' || group?.getAttribute('aria-required')==='true' || !!leverRequired,value:e.type==='password' ? '[redacted]' : e.type==='file' ? [...e.files].map(f=>f.name).join(', ') : combo ? chosen : leverLocation ? (locationSelected ? e.value : '') : (e.type==='checkbox'||e.type==='radio' ? (e.checked ? 'Checked' : 'Not checked') : e.tagName==='SELECT' ? (placeholder ? '' : sel) : e.value),files:e.type==='file' ? [...e.files].map(f=>({name:f.name,size:f.size,lastModified:f.lastModified})) : [],disabled:e.disabled,options:e.tagName==='SELECT' ? [...e.options].map(o=>o.textContent.trim()) : []}}''')
    info['label']=await control.evaluate(LABEL_JS)
    info['valid']=await control.evaluate('e => !e.willValidate || e.validity.valid')
    if info['required'] and not info['disabled'] and not info['value']:info['valid']=False
    key=profile_key(info['label']);info.update(frame=frame_index,index=index,filled=False,high_stakes=key in HIGH_STAKES or bool(re.search(r'\b(salary|compensation|wage)\b',normalize(info['label']))))
    answer=match_profile(info['label'],profile)
    if fill and answer and not info['disabled'] and not info['value']:
     if info['type'] in ('text','email','tel','url','textarea'):
      await control.scroll_into_view_if_needed();box=await control.bounding_box()
      if box:await move_cursor(page,box['x']+box['width']/2,box['y']+box['height']/2)
      await control.fill(answer);info['value']=answer;info['filled']=True;info['valid']=await control.evaluate('e => !e.willValidate || e.validity.valid')
     elif info['type']=='select-one':
      label=select_label(answer,info['options'],bool(key and key.startswith('eeo_')))
      if label:
       await control.scroll_into_view_if_needed();box=await control.bounding_box()
       if box:await move_cursor(page,box['x']+box['width']/2,box['y']+box['height']/2)
       await control.select_option(label=label);info['value']=label;info['filled']=True;info['valid']=await control.evaluate('e => !e.willValidate || e.validity.valid')
    fields.append(info)
   except Exception:fields.append({'label':'Unable to inspect field','frame':frame_index,'index':index,'error':True})
 return fields

async def _challenge_visible(el):
 """An invisible reCAPTCHA badge (size=invisible) is not a challenge the user must solve."""
 if not await el.is_visible():return False
 src=(await el.get_attribute('src')) or ''
 return 'size=invisible' not in src

async def captcha_present(page):
 """Identify common visible challenges; do not attempt to solve them."""
 groups=[('iframe[src*="recaptcha"], .g-recaptcha','textarea[name="g-recaptcha-response"]'),('iframe[src*="hcaptcha"], .h-captcha','textarea[name="h-captcha-response"]'),('iframe[src*="challenges.cloudflare.com"], .cf-turnstile','input[name="cf-turnstile-response"]'),('[data-captcha-challenge]',None)]
 for selector,token_selector in groups:
  challenges=page.locator(selector)
  visible=any([await _challenge_visible(challenges.nth(i)) for i in range(await challenges.count())])
  if not visible:continue
  if token_selector:
   tokens=page.locator(token_selector)
   if await tokens.count()==1 and (await tokens.first.input_value()).strip():continue
  return True
 return False

async def final_submit_controls(page):
 """Recognize explicitly labeled final-submit buttons; never invoke them here."""
 candidates=page.get_by_role('button',name=re.compile(r'^(submit application|submit your application|send application)$',re.I),exact=True)
 result=[]
 for i in range(await candidates.count()):
  button=candidates.nth(i)
  if not await button.is_visible():continue
  details=await button.evaluate("e => ({label:(e.innerText || e.value || e.getAttribute('aria-label') || '').trim().toLowerCase(), tag:e.tagName, type:e.getAttribute('type') || '', id:e.id || '', action:e.form?.action || ''})")
  result.append((button,details))
 return result
