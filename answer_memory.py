"""Exact answer reuse and explicit question resolution."""
import re
from datetime import datetime, timezone
from form_engine import normalize,LABEL_JS,SELF_ID_LABEL,same_meaning_option,profile_key

SENSITIVE=('sponsor','authoriz','citizenship','citizen','visa','immigration','disab','gender','race','ethnic','hispanic','latino','veteran','salary','compensation','pay expectation','pronoun','criminal','convict','felony','clearance','eligib','relocat')
PERSONAL=('why ','why do you','why are you','why would you','why this','why our','why us','why join','why work','motivation','cover letter','what excites','interest in','about our company','at our company')
TIME_SENSITIVE=('start date','availability','available to start','notice period')
def may_reuse(label,scope):
    text=normalize(label)
    if any(x in text for x in SENSITIVE): return False
    if scope!='job' and any(x in text for x in PERSONAL): return False
    return bool(text)

def select_answer(label,answers,job_id,role):
    key=normalize(label)
    now=datetime.now(timezone.utc).isoformat()
    for a in answers:
        if normalize(a['question'])!=key or not may_reuse(label,a['scope']): continue
        if a['expires_at'] and a['expires_at']<=now: continue
        if any(x in key for x in TIME_SENSITIVE) and not a['expires_at']: continue
        if a['scope']=='job' and a['job_id']!=job_id: continue
        if a['scope']=='role' and normalize(a['role_type'] or '')!=normalize(role): continue
        return a['answer']
    return None

def _core(text):
    """Option text without a trailing dial code such as ' +1', which Greenhouse country lists add."""
    return normalize(re.sub(r'\s*\+\d+\s*$','',text))

def pick_range(answer,options):
    """A number such as a GPA of 3.6 -> the one option whose range holds it ('3.50 - 3.74', '3.5+', 'Below 3.0')."""
    try:n=float(str(answer).strip())
    except ValueError:return None
    found=[]
    for o in options:
        nums=[float(x) for x in re.findall(r'\d+(?:\.\d+)?',o)]
        t=normalize(o)
        if len(nums)==2 and nums[0]<=n<=nums[1]:found.append(o)
        elif len(nums)==1 and ((('+' in o or 'above' in t or 'higher' in t or 'or more' in t) and n>=nums[0]) or (('below' in t or 'less' in t or 'under' in t) and n<nums[0])):found.append(o)
    return found[0] if len(found)==1 else None

def pick_place(answer,options):
    """'Phoenix, AZ' -> the one option naming that city in that state, such as 'Phoenix, Arizona, United States'."""
    from discovery_preferences import STATES,as_state
    parts=[p.strip() for p in str(answer).split(',') if p.strip()]
    if not parts:return None
    city=normalize(parts[0]);state=as_state(parts[1]) if len(parts)>1 else ''
    names={state,next((n for n,a in STATES.items() if a==state),'')}-{''}
    found=[o for o in options if normalize(o.split(',')[0])==city and (not state or names&{normalize(x) for x in o.split(',')[1:]})]
    return found[0] if len(found)==1 else None

def pick_option(answer,options,self_id=False):
    """Exact option text wins; otherwise one unique option that matches once any trailing dial code is ignored.
    For self-identification questions, also the one option with the same meaning. Never a partial guess."""
    exact=[o for o in options if normalize(o)==normalize(answer) and normalize(o)]
    if len(exact)==1:return exact[0]
    loose=[o for o in options if _core(o)==_core(answer) and _core(o)]
    if len(loose)==1:return loose[0]
    return same_meaning_option(answer,options) if self_id and not exact and not loose else None

async def combobox_options(page,field,limit=300):
    """Open a combobox, read its choices, close it without selecting. Returns [] when they cannot be read."""
    try:
        item=await locate(page,field)
        if await item.get_attribute('role')!='combobox':return []
        await item.click()
        boxes=page.frames[field['frame']].get_by_role('listbox')
        await boxes.first.wait_for(state='visible',timeout=3000)
        texts=[t.strip() for t in await boxes.first.get_by_role('option').all_inner_texts()]
        await page.keyboard.press('Escape')
        return [t for t in texts if t][:limit]
    except Exception:
        try:await page.keyboard.press('Escape')
        except Exception:pass
        return []

async def locate(page,field):
    """Find the control for a field. Answering one field can add or remove controls and shift positions, so fall back to a label search, accepted only when exactly one visible control has that label."""
    if field['frame']>=len(page.frames): raise ValueError('Page changed')
    controls=page.frames[field['frame']].locator('input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select')
    count=await controls.count()
    if field['index']<count:
        item=controls.nth(field['index'])
        if normalize(await item.evaluate(LABEL_JS))==normalize(field['label']):return item
    found=[]
    for i in range(count):
        try:
            candidate=controls.nth(i)
            if normalize(await candidate.evaluate(LABEL_JS))==normalize(field['label']) and await candidate.is_visible():found.append(candidate)
        except Exception:continue
    if len(found)!=1:raise ValueError('Page changed')
    return found[0]

async def fill_field(page,field,answer):
    item=await locate(page,field)
    label=await item.evaluate(LABEL_JS)
    if normalize(label)!=normalize(field['label']) or not await item.is_visible() or await item.is_disabled(): raise ValueError('Page changed')
    self_id=bool(SELF_ID_LABEL.search(normalize(field['label'])))
    if field['type']=='combobox':
        if await item.get_attribute('role')!='combobox':raise ValueError('Page changed')
        await item.click()
        frame=page.frames[field['frame']]
        boxes=frame.get_by_role('listbox')
        await boxes.first.wait_for(state='visible',timeout=3000)
        visible=[]
        for i in range(await boxes.count()):
            if await boxes.nth(i).is_visible():visible.append(boxes.nth(i))
        if len(visible)!=1:raise ValueError('Could not identify one dropdown')
        texts=[t.strip() for t in await visible[0].get_by_role('option').all_inner_texts()]
        chosen=pick_option(str(answer),texts,self_id)
        place=profile_key(field['label'])=='location'
        if chosen is None:
            # Search-as-you-type pickers (such as a city field) list nothing until text is typed: type the answer, then require one exact match.
            # For a city, type just the city name and pick the one result in the right state.
            await item.press_sequentially((str(answer).split(',')[0] if place else str(answer))[:60],delay=40)
            await page.wait_for_timeout(2000)
            for i in range(await boxes.count()):
                if await boxes.nth(i).is_visible():
                    texts=[t.strip() for t in await boxes.nth(i).get_by_role('option').all_inner_texts()]
                    visible=[boxes.nth(i)];break
            chosen=pick_option(str(answer),texts,self_id) or (pick_place(answer,texts) if place else None)
        if chosen is None and profile_key(field['label'])=='gpa':chosen=pick_range(answer,texts)
        if chosen is None:raise ValueError('Answer is not an available option')
        options=visible[0].get_by_role('option',name=chosen,exact=True)
        if await options.count()!=1 or not await options.first.is_visible():raise ValueError('Answer is not an available option')
        await options.first.click()
        selected=await item.evaluate("e => e.closest('.select__container')?.querySelector('.select__single-value')?.textContent.trim() || e.value || ''")
        dial=re.search(r'\+\d+\s*$',chosen)
        shown_dial_only=bool(dial) and selected.strip()==dial.group().strip()  # phone-country pickers show just the dial code
        if normalize(selected)!=normalize(chosen) and _core(selected)!=_core(chosen) and not shown_dial_only:raise ValueError(f'Could not verify selected answer (shows {selected[:40]!r})')
        return chosen
    elif field['type'] in ('text','email','tel','url','textarea','number'):
        await item.fill(str(answer))
    elif field['type'] in ('select-one','select-multiple'):
        chosen=pick_option(str(answer),field.get('options',[]),self_id)
        if chosen is None and profile_key(field['label'])=='gpa':chosen=pick_range(answer,field.get('options',[]))
        if chosen is None: raise ValueError('Answer is not an available option')
        await item.select_option(label=chosen)
        return chosen
    else: raise ValueError('This field type requires manual completion')
    return answer
