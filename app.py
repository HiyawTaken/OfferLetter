import asyncio, json, os, re, sqlite3, secrets, sys, time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
if (ROOT/'.deps').is_dir(): sys.path.insert(0,str(ROOT/'.deps'))
DATA=Path(os.environ.get('OFFERLETTER_DATA',ROOT/'data')); DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'offerletter.db'; TOKEN=secrets.token_urlsafe(32)
browser=None; playwright=None; pages={}; page_sessions={}; page_opened_at={}; lock=asyncio.Lock()

def db():
    conn=sqlite3.connect(DB); conn.row_factory=sqlite3.Row; conn.execute('PRAGMA foreign_keys=ON'); return conn

def initialize():
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, kind TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, company TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'found', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS answers (id INTEGER PRIMARY KEY, question TEXT NOT NULL, answer TEXT NOT NULL, scope TEXT NOT NULL DEFAULT 'global', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS approvals (id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id), review_id TEXT NOT NULL, approved_at TEXT DEFAULT CURRENT_TIMESTAMP, outcome TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS resumes (id INTEGER PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL, titles TEXT NOT NULL, extracted_text TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS rules (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY,job_id INTEGER NOT NULL REFERENCES jobs(id),page_url TEXT NOT NULL,frame_index INTEGER NOT NULL,field_index INTEGER NOT NULL,label TEXT NOT NULL,field_type TEXT NOT NULL,options TEXT NOT NULL DEFAULT '[]',status TEXT NOT NULL DEFAULT 'pending',created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(job_id,page_url,frame_index,field_index));
CREATE TABLE IF NOT EXISTS schedule (id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 0,interval_minutes INTEGER NOT NULL DEFAULT 60,boards TEXT NOT NULL DEFAULT '[]',next_run TEXT,last_run TEXT,last_result TEXT);
CREATE TABLE IF NOT EXISTS page_history (id TEXT PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id), session_id TEXT NOT NULL, snapshot TEXT NOT NULL, screenshot TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, status TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '{}', started_at TEXT DEFAULT CURRENT_TIMESTAMP, finished_at TEXT);
CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY,domain TEXT NOT NULL,email TEXT NOT NULL,key_ref TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'staged',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(domain,email));
CREATE TABLE IF NOT EXISTS salary_notes (job_id INTEGER NOT NULL REFERENCES jobs(id),page_url TEXT NOT NULL,frame_index INTEGER NOT NULL,field_index INTEGER NOT NULL,value TEXT NOT NULL,source TEXT NOT NULL,PRIMARY KEY(job_id,page_url,frame_index,field_index));
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
''')
        answer_columns={row['name'] for row in c.execute('PRAGMA table_info(answers)')}
        for name,definition in [('job_id','INTEGER'),('role_type','TEXT'),('expires_at','TEXT')]:
            if name not in answer_columns: c.execute(f'ALTER TABLE answers ADD COLUMN {name} {definition}')
        question_columns={row['name'] for row in c.execute('PRAGMA table_info(questions)')}
        for name,definition in [('suggestion_id','INTEGER'),('suggestion_score','REAL')]:
            if name not in question_columns:c.execute(f'ALTER TABLE questions ADD COLUMN {name} {definition}')
        columns={row['name'] for row in c.execute('PRAGMA table_info(jobs)')}
        for name in ('location','description','source','salary_min','salary_max','salary_currency','salary_period','posted_date','match_note','pay','apply_url'):
            if name not in columns: c.execute(f"ALTER TABLE jobs ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
        schedule_columns={row['name'] for row in c.execute('PRAGMA table_info(schedule)')}
        if 'prepare_jobs' not in schedule_columns: c.execute('ALTER TABLE schedule ADD COLUMN prepare_jobs INTEGER NOT NULL DEFAULT 0')
        c.execute("UPDATE runs SET status='interrupted',finished_at=CURRENT_TIMESTAMP WHERE status IN ('running','pausing')")

def event(kind,detail):
    with db() as c: c.execute('INSERT INTO events(kind,detail) VALUES (?,?)',(kind,detail))

def valid_url(url):
    p=urlparse(url); return p.scheme in ('http','https') and bool(p.hostname) and not p.username and not p.password

@asynccontextmanager
async def lifespan(app):
    initialize()
    worker=asyncio.create_task(scheduler_loop())
    mail_worker=asyncio.create_task(gmail_status_monitor())
    yield
    worker.cancel()
    mail_worker.cancel()
    try: await worker
    except asyncio.CancelledError: pass
    try: await mail_worker
    except asyncio.CancelledError: pass
    if preparation_task and not preparation_task.done():
        preparation_task.cancel()
        try: await preparation_task
        except asyncio.CancelledError: pass
    global browser,playwright
    if browser: await browser.close()
    if playwright: await playwright.stop()

async def index(request): return FileResponse(ROOT/'static'/'index.html',headers={'Cache-Control':'no-cache'})
class NoCacheStatic(StaticFiles):
    # Revalidate every load so an updated UI shows up after a restart instead of a stale cached copy.
    def file_response(self,*args,**kwargs):
        response=super().file_response(*args,**kwargs); response.headers['Cache-Control']='no-cache'; return response
async def session(request): return JSONResponse({'token':TOKEN,'browser_open':browser is not None})
async def open_browser(request):
    global browser,playwright
    async with lock:
        if browser: return JSONResponse({'status':'already open'})
        try:
            if playwright: await playwright.stop()
            playwright=await async_playwright().start()
            browser=await playwright.chromium.launch_persistent_context(str(DATA/'chrome-profile'),channel='chrome',headless=False)
            def closed(_):
                global browser
                browser=None; pages.clear(); page_sessions.clear(); page_opened_at.clear()
            from form_engine import install_cursor
            await install_cursor(browser)
            browser.on('close',closed); event('browser_opened','Dedicated Chrome profile opened')
            return JSONResponse({'status':'opened'})
        except Exception:
            if playwright: await playwright.stop(); playwright=None
            return JSONResponse({'error':'Could not open Chrome. Check that Chrome is installed and the OfferLetter profile is not in use.'},status_code=500)

async def profile(request):
    if request.method=='GET':
        with db() as c: row=c.execute('SELECT data FROM profile WHERE id=1').fetchone()
        return JSONResponse(json.loads(row['data']) if row else {})
    data=await request.json()
    allowed=('first_name','last_name','email','phone','location','linkedin','website','work_authorization','sponsorship','education','school','degree','discipline','grad_month','grad_year','gpa','current_company','current_title','years_experience','country','eeo_gender','eeo_hispanic','eeo_race','eeo_veteran','eeo_disability')
    clean={k:str(data.get(k,''))[:1000] for k in allowed}
    from work_experience import validate,summary
    if 'experience' in data:
        try:clean['experience']=validate(data['experience'])
        except ValueError as exc:return JSONResponse({'error':str(exc)},status_code=400)
        clean.update(summary(clean['experience']))
    else:
        with db() as c:previous=c.execute('SELECT data FROM profile WHERE id=1').fetchone()
        clean['experience']=json.loads(previous['data']).get('experience',[]) if previous else []
        if clean['experience']:clean.update(summary(clean['experience']))
    with db() as c: c.execute('INSERT INTO profile(id,data) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(json.dumps(clean),))
    event('profile_updated','Profile saved'); return JSONResponse({'ok':True})

async def jobs(request):
    if request.method=='GET':
        from salary import pay_text
        with db() as c: rows=c.execute('SELECT * FROM jobs ORDER BY id DESC').fetchall()
        return JSONResponse([{**dict(r),'pay':pay_text(dict(r))} for r in rows])
    data=await request.json(); url=str(data.get('url','')).strip()
    if not valid_url(url): return JSONResponse({'error':'Enter a valid http or https job link.'},status_code=400)
    from identity import find_duplicate
    candidate={'company':str(data.get('company',''))[:300],'title':str(data.get('title',''))[:300],'location':str(data.get('location',''))[:300]}
    try:
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            duplicate=find_duplicate(candidate,c.execute('SELECT id,company,title,location FROM jobs').fetchall())
            if duplicate: return JSONResponse({'error':'A job with the same company, title and location is already tracked.','existing_id':duplicate['id']},status_code=409)
            from salary import amount
            low,high=amount(data.get('salary_min')),amount(data.get('salary_max'))
            if (data.get('salary_min') and not low) or (data.get('salary_max') and not high) or (low and high and low>high):return JSONResponse({'error':'Enter a valid salary range.'},status_code=400)
            currency=str(data.get('salary_currency','')).strip().upper();period=str(data.get('salary_period','')).strip().lower()
            if (low or high) and (currency!='USD' or period!='year'):return JSONResponse({'error':'Enter salary ranges in annual USD.'},status_code=400)
            posted=str(data.get('posted_date','')).strip()
            if posted:
                from datetime import date
                try:date.fromisoformat(posted)
                except ValueError:return JSONResponse({'error':'Enter a valid posting date.'},status_code=400)
            cur=c.execute('INSERT INTO jobs(url,company,title,location,description,source,salary_min,salary_max,salary_currency,salary_period,posted_date) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(url,candidate['company'],candidate['title'],candidate['location'],str(data.get('description',''))[:30000],'direct',str(low or ''),str(high or ''),currency,period,posted)); job_id=cur.lastrowid
        event('job_added',f'Job {job_id} added'); return JSONResponse({'id':job_id},status_code=201)
    except sqlite3.IntegrityError: return JSONResponse({'error':'This link is already in the tracker.'},status_code=409)

async def open_job(request):
    job_id=int(request.path_params['job_id'])
    with db() as c: job=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not job: return JSONResponse({'error':'Job not found'},status_code=404)
    if not browser: return JSONResponse({'error':'Open Chrome first.'},status_code=409)
    try:
        if job_id in pages and not pages[job_id].is_closed():
            await pages[job_id].bring_to_front(); return JSONResponse({'ok':True,'existing':True})
        with db() as c: rule=c.execute('SELECT data FROM rules WHERE id=1').fetchone()
        limit=json.loads(rule['data']).get('tab_limit',3) if rule else 3
        for stale in [key for key,value in pages.items() if value.is_closed()]: pages.pop(stale,None)
        if len(pages)>=limit: return JSONResponse({'error':'Tab limit reached. Close an application tab to continue.'},status_code=409)
        # Open the employer's application when the board gave one, not the board's listing page.
        page=await browser.new_page(); await page.goto(job['apply_url'] or job['url'],wait_until='domcontentloaded',timeout=30000)
        from ats_navigation import follow_application_link,follow_board_apply,on_job_board
        if on_job_board(page.url):
            try:await page.wait_for_load_state('networkidle',timeout=10000)
            except Exception:pass
            if await follow_board_apply(page):event('application_page_opened',f'Job {job_id}: followed the listing to the employer application')
        if (urlparse(page.url).hostname or '').lower() in ('jobs.lever.co','jobs.ashbyhq.com'):
            await page.wait_for_timeout(1000)
            if await follow_application_link(page):event('application_page_opened',f'Job {job_id}: followed the public application link')
        pages[job_id]=page; page_sessions[job_id]=secrets.token_hex(16); page_opened_at[job_id]=int(time.time())
        event('job_opened',f'Job {job_id} opened'); return JSONResponse({'ok':True})
    except Exception: return JSONResponse({'error':'Could not load the job page in Chrome.'},status_code=502)

async def events(request):
    with db() as c: rows=c.execute('SELECT created_at,kind,detail FROM events ORDER BY id DESC LIMIT 50').fetchall()
    return JSONResponse([dict(r) for r in rows])

routes=[Route('/',index),Route('/api/session',session),Route('/api/browser/open',open_browser,methods=['POST']),Route('/api/profile',profile,methods=['GET','POST']),Route('/api/jobs',jobs,methods=['GET','POST']),Route('/api/jobs/{job_id:int}/open',open_job,methods=['POST']),Route('/api/events',events),Mount('/static',app=NoCacheStatic(directory=ROOT/'static'))]
app=Starlette(routes=routes,lifespan=lifespan)
from guard import LocalGuard
app.add_middleware(LocalGuard, token=TOKEN)

async def inspect_job(request):
    from form_engine import inspect, profile_key, match_profile
    from answer_memory import select_answer, fill_field
    from salary import is_annual_salary,currency_confirmed,resolve_salary,fetch_bls
    from semantic_memory import eligible,embed,choose
    from field_mapper import prepare_fields,map_fields,value_for
    job_id=int(request.path_params['job_id']); page=pages.get(job_id)
    if page is None or page.is_closed(): return JSONResponse({'error':'Open this job in Chrome first.'},status_code=409)
    paused=await require_no_captcha(page,job_id)
    if paused: return paused
    with db() as c: row=c.execute('SELECT data FROM profile WHERE id=1').fetchone()
    profile_data=json.loads(row['data']) if row else {}
    original_url=page.url
    fields=await inspect(page,profile_data,fill=request.method=='POST')
    if request.method=='POST':
        with db() as c:
            answers=c.execute('SELECT * FROM answers ORDER BY id DESC').fetchall()
            job=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            rule=c.execute('SELECT data FROM rules WHERE id=1').fetchone()
            embedding_row=c.execute("SELECT value FROM settings WHERE key='embeddings'").fetchone()
            model_row=c.execute("SELECT value FROM settings WHERE key='model'").fetchone()
        rules=json.loads(rule['data']) if rule else {}
        model_mappings={}
        model_config=json.loads(model_row['value']) if model_row else {}
        candidates=prepare_fields(fields,profile_data) if model_config.get('map_fields') else []
        if candidates:
            try:
                import keyring
                model_key=keyring.get_password('OfferLetter','model:'+model_config['provider']) if model_config['provider']!='local' else ''
                if model_config['provider']!='local' and not model_key:raise ValueError('Missing model key')
                model_mappings=await asyncio.to_thread(map_fields,model_config,model_key,candidates)
            except Exception:event('field_mapping_unavailable',f'Job {job_id}: model field mapping unavailable')
        embedding_settings_data=json.loads(embedding_row['value']) if embedding_row else {}
        semantic={}
        if embedding_settings_data.get('enabled'):
            candidates={};questions=[]
            for index,f in enumerate(fields):
                if f.get('disabled') or f.get('error') or f.get('value') or f.get('type') not in ('text','email','tel','url','textarea','number','select-one','combobox') or not f.get('label') or len(f['label'])>1000:continue
                if select_answer(f['label'],answers,job_id,job['title'] if job else '') is not None:continue
                options=eligible(f['label'],answers,job_id,job['title'] if job else '')
                if options:
                    questions.append((index,f,options))
                    for a in options:candidates[a['id']]=a
                if len(questions)>=50:break
            if questions and candidates:
                saved=list(candidates.values())[:100]; saved_ids={a['id'] for a in saved}
                try:
                    texts=[f['label'] for _,f,_ in questions]+[a['question'] for a in saved]
                    vectors=await asyncio.to_thread(embed,embedding_settings_data['base_url'],embedding_settings_data['model'],texts)
                    answer_vectors={a['id']:v for a,v in zip(saved,vectors[len(questions):])}
                    for n,(index,f,options) in enumerate(questions):
                        chosen=[a for a in options if a['id'] in saved_ids]
                        result=choose(vectors[n],chosen,[answer_vectors[a['id']] for a in chosen])
                        if result:semantic[index]=result
                except Exception:event('embedding_unavailable',f'Job {job_id}: local answer matching unavailable')
        market=None
        salary_fields=[f for f in fields if not f.get('value') and is_annual_salary(f.get('label','')) and f.get('type') in ('text','textarea','number') and currency_confirmed(f.get('label',''),dict(job))]
        order=[rules.get('salary_mode','ask')]+[x.strip() for x in rules.get('salary_fallback','').split(',')]
        need_market=False
        for mode in order:
            if mode in ('ask','optional'):break
            if mode=='market':need_market=True;break
            if mode in ('fixed','role','posting') and resolve_salary({**rules,'salary_mode':mode,'salary_fallback':''},dict(job))['value'] is not None:break
        if salary_fields and need_market and rules.get('bls_soc'):
            try:market=await asyncio.to_thread(fetch_bls,rules['bls_soc'])
            except Exception:market=None
        current=await inspect(page,{},False)
        def signature(items):return [(x.get('frame'),x.get('index'),x.get('label'),x.get('type'),x.get('value'),x.get('required')) for x in items]
        if page.url!=original_url or signature(fields)!=signature(current):return JSONResponse({'error':'The page changed while preparing answers. Inspect it again.'},status_code=409)
        for field_index,field in enumerate(fields):
            if field.get('value') and field.get('value')!='Not checked':
                with db() as c:
                    c.execute("UPDATE questions SET status='answered' WHERE job_id=? AND page_url=? AND frame_index=? AND field_index=?",(job_id,page.url,field['frame'],field['index']))
            if field.get('disabled') or field.get('error') or field.get('value') or not field.get('label'): continue
            if field.get('type') not in ('text','email','tel','url','textarea','number','select-one','combobox'): continue
            key=profile_key(field['label'])
            if field['type']=='combobox' and key:  # a dropdown whose answer is in the profile
                value=match_profile(field['label'],profile_data)
                if value:
                    try:
                        field['value']=await fill_field(page,field,value);field['filled']=True
                        event('profile_choice_filled',f'Job {job_id}: {field["label"][:60]} filled from profile')
                        continue
                    except Exception:pass
            if field_index in model_mappings:
                value=value_for(model_mappings[field_index],profile_data)
                if value:
                    try:
                        field['value']=await fill_field(page,field,value);field['filled']=True
                        event('model_profile_field_filled',f'Job {job_id}: mapped profile field {model_mappings[field_index]}')
                        continue
                    except Exception:pass
            if is_annual_salary(field['label']) and field['type'] in ('text','textarea','number'):
                currency_known=currency_confirmed(field['label'],dict(job))
                resolution=resolve_salary(rules,dict(job),market,field.get('required',False),field['type']) if currency_known else {'value':None,'reason':'Currency is not confirmed as USD; ask the user'}
                field['salary_source']=resolution['reason']
                if resolution['value'] is not None:
                    try:
                        await fill_field(page,field,resolution['value']);field['value']=resolution['value'];field['filled']=True
                        with db() as c:c.execute('INSERT OR REPLACE INTO salary_notes(job_id,page_url,frame_index,field_index,value,source) VALUES(?,?,?,?,?,?)',(job_id,page.url,field['frame'],field['index'],resolution['value'],resolution['reason']))
                        event('salary_filled',f'Job {job_id}: salary field filled using {resolution["reason"]}')
                        continue
                    except Exception:pass
            answer=select_answer(field['label'],answers,job_id,job['title'] if job else '')
            if answer is not None:
                try:
                    field['value']=await fill_field(page,field,answer); field['filled']=True
                    with db() as c: c.execute("UPDATE questions SET status='answered' WHERE job_id=? AND page_url=? AND frame_index=? AND field_index=?",(job_id,page.url,field['frame'],field['index']))
                    event('answer_reused',f'Job {job_id}: saved answer reused')
                    continue
                except Exception: pass
            match=semantic.get(field_index)
            if match and match['automatic']:
                candidate=next((a for a in answers if a['id']==match['answer_id']),None)
                if candidate:
                    try:
                        field['value']=await fill_field(page,field,candidate['answer']);field['filled']=True
                        with db() as c:c.execute("UPDATE questions SET status='answered',suggestion_id=NULL,suggestion_score=NULL WHERE job_id=? AND page_url=? AND frame_index=? AND field_index=?",(job_id,page.url,field['frame'],field['index']))
                        event('semantic_answer_reused',f'Job {job_id}: local high-confidence answer match used')
                        continue
                    except Exception:pass
            if field['type']=='combobox' and not field.get('options'):
                from answer_memory import combobox_options
                field['options']=await combobox_options(page,field)
            with db() as c:
                c.execute('''INSERT INTO questions(job_id,page_url,frame_index,field_index,label,field_type,options,suggestion_id,suggestion_score)
                    VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id,page_url,frame_index,field_index)
                    DO UPDATE SET label=excluded.label,field_type=excluded.field_type,options=excluded.options,status='pending',suggestion_id=excluded.suggestion_id,suggestion_score=excluded.suggestion_score ''',
                    (job_id,page.url,field['frame'],field['index'],field['label'],field['type'],json.dumps(field.get('options',[])),match['answer_id'] if match else None,match['score'] if match else None))
                c.execute("UPDATE jobs SET status='waiting on user',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status NOT IN ('submitted','submission pending','submission uncertain')",(job_id,))
    event('form_filled' if request.method=='POST' else 'form_inspected',f'Job {job_id}: {len(fields)} fields inspected')
    return JSONResponse({'fields':fields,'url':page.url})
app.router.routes.insert(-1, Route('/api/jobs/{job_id:int}/fields',inspect_job,methods=['GET','POST']))

async def answer_memory(request):
    if request.method=='GET':
        with db() as c: rows=c.execute('SELECT id,question,answer,scope,created_at FROM answers ORDER BY id DESC').fetchall()
        return JSONResponse([dict(r) for r in rows])
    data=await request.json(); question=str(data.get('question','')).strip(); answer=str(data.get('answer','')).strip()
    if not question or not answer: return JSONResponse({'error':'Question and answer are required.'},status_code=400)
    if len(question)>1000 or len(answer)>10000: return JSONResponse({'error':'Answer is too long.'},status_code=400)
    with db() as c: cur=c.execute("INSERT INTO answers(question,answer,scope) VALUES (?,?,'global')",(question,answer))
    event('answer_saved',f'Answer {cur.lastrowid} saved'); return JSONResponse({'id':cur.lastrowid},status_code=201)

async def delete_answer(request):
    answer_id=int(request.path_params['answer_id'])
    with db() as c: deleted=c.execute('DELETE FROM answers WHERE id=?',(answer_id,)).rowcount
    if not deleted: return JSONResponse({'error':'Answer not found.'},status_code=404)
    event('answer_deleted',f'Answer {answer_id} deleted'); return JSONResponse({'ok':True})

async def update_job(request):
    job_id=int(request.path_params['job_id']); data=await request.json(); status=data.get('status')
    if status not in ('found','approved','check match','review fit','skipped','waiting on user','ready for review','submitted','failed','rejected','interview'): return JSONResponse({'error':'Invalid status'},status_code=400)
    # Manual tracker updates are not evidence that OfferLetter submitted an application.
    with db() as c: changed=c.execute('UPDATE jobs SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,job_id)).rowcount
    if not changed: return JSONResponse({'error':'Job not found'},status_code=404)
    event('tracker_updated',f'Job {job_id}: manually marked {status}'); return JSONResponse({'ok':True})

app.router.routes.insert(-1,Route('/api/answers',answer_memory,methods=['GET','POST']))
app.router.routes.insert(-1,Route('/api/answers/{answer_id:int}',delete_answer,methods=['DELETE']))
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/status',update_job,methods=['POST']))


async def create_review(request):
    from form_engine import inspect,final_submit_controls
    job_id=int(request.path_params['job_id']); page=pages.get(job_id)
    if page is None or page.is_closed(): return JSONResponse({'error':'Open this job in Chrome first.'},status_code=409)
    paused=await require_no_captcha(page,job_id)
    if paused: return paused
    fields=await inspect(page,{},False)
    if not fields or any(f.get('error') for f in fields): return JSONResponse({'error':'Cannot review: fields could not be inspected.'},status_code=409)
    if any(f.get('type')=='password' for f in fields): return JSONResponse({'error':'Complete sign-in in Chrome before reviewing the application.'},status_code=409)
    incomplete=[f for f in fields if not f.get('valid',True) or (f.get('required') and f.get('type')=='select-one' and not f.get('value'))]
    if incomplete:
        labels=[str(f.get('label') or 'Unlabeled field')[:120] for f in incomplete[:5]]
        return JSONResponse({'error':'Complete required fields in Chrome before review: '+', '.join(labels)+'.','fields':labels},status_code=409)
    review_dir=DATA/'reviews'; review_dir.mkdir(exist_ok=True)
    review_id=secrets.token_hex(16); shot=review_dir/(review_id+'.png')
    await page.screenshot(path=str(shot),full_page=True)
    with db() as c:
        try: fit=c.execute('SELECT result FROM fit_checks WHERE job_id=? ORDER BY id DESC LIMIT 1',(job_id,)).fetchone()
        except sqlite3.OperationalError: fit=None
        history=c.execute('SELECT id,snapshot FROM page_history WHERE job_id=? AND session_id=? ORDER BY rowid',(job_id,page_sessions.get(job_id,''))).fetchall()
        salary_rows=c.execute('SELECT frame_index,field_index,value,source FROM salary_notes WHERE job_id=? AND page_url=?',(job_id,page.url)).fetchall()
        try: cover=c.execute('SELECT text,quotes,resume_id FROM cover_letters WHERE job_id=? AND page_url=? AND attached=1 ORDER BY rowid DESC LIMIT 1',(job_id,page.url)).fetchone()
        except sqlite3.OperationalError: cover=None
    submits=await final_submit_controls(page)
    submit_controls=[descriptor for _,descriptor in submits]
    previous=[{'id':row['id'],'snapshot':json.loads(row['snapshot']),'screenshot':'/api/history/'+row['id']+'/screenshot'} for row in history]
    letter={'text':cover['text'],'quotes':json.loads(cover['quotes']),'resume_id':cover['resume_id']} if cover else None
    salary_notes=[{'label':f['label'],'source':r['source']} for r in salary_rows for f in fields if f.get('frame')==r['frame_index'] and f.get('index')==r['field_index'] and f.get('value')==r['value']]
    snapshot=json.dumps({'url':page.url,'fields':fields,'fit':json.loads(fit['result']) if fit else None,'submit_controls':submit_controls,'previous_pages':previous,'cover_draft':letter,'salary_notes':salary_notes},ensure_ascii=False)
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id), snapshot TEXT NOT NULL, screenshot TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        c.execute('INSERT INTO reviews(id,job_id,snapshot,screenshot) VALUES (?,?,?,?)',(review_id,job_id,snapshot,str(shot)))
        c.execute("UPDATE jobs SET status='ready for review', updated_at=CURRENT_TIMESTAMP WHERE id=?",(job_id,))
    event('review_created',f'Job {job_id}: review {review_id} created')
    return JSONResponse({'id':review_id,'snapshot':json.loads(snapshot),'screenshot':'/api/reviews/'+review_id+'/screenshot'})

async def review_screenshot(request):
    review_id=request.path_params['review_id']
    with db() as c:
        try: row=c.execute('SELECT screenshot FROM reviews WHERE id=?',(review_id,)).fetchone()
        except sqlite3.OperationalError: row=None
    if not row: return JSONResponse({'error':'Review not found'},status_code=404)
    return FileResponse(row['screenshot'],media_type='image/png',headers={'Cache-Control':'no-store'})

app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/review',create_review,methods=['POST']))
app.router.routes.insert(-1,Route('/api/reviews/{review_id:str}/screenshot',review_screenshot,methods=['GET']))

def discovery_preferences():
    with db() as c: row=c.execute('SELECT data FROM rules WHERE id=1').fetchone()
    return json.loads(row['data']) if row else {}

def discovery_setup_error():
    from discovery_preferences import ready
    if not ready(discovery_preferences()):return JSONResponse({'error':'Save your target job titles in Search rules before discovering jobs.'},status_code=409)
    return None

def store_discovered(found,counts=None,screen=False):
    """Keep clear matches as 'found' (prepared automatically) and close ones as 'check match' for the user to decide; drop the rest.
    screen=True keeps every remotely related job as 'screening', for the model to judge from the description."""
    from identity import find_duplicate,build_index,identity_key
    from discovery_preferences import classify
    preferences=discovery_preferences();kept=[]
    for job in found:
        tier,reason=classify(job,preferences,loose=screen)
        if counts is not None:counts[tier]=counts.get(tier,0)+1
        if tier!='miss':kept.append((job,'screening' if screen else 'found' if tier=='clear' else 'check match',reason))
    added=0
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        existing=build_index(c.execute('SELECT id,company,title,location FROM jobs'))
        for job,status,reason in kept:
            if not valid_url(job['url']): continue
            key=identity_key(job)
            if key and find_duplicate(job,existing.get(key,[])): continue
            cur=c.execute('INSERT OR IGNORE INTO jobs(url,company,title,location,description,source,salary_min,salary_max,salary_currency,salary_period,posted_date,status,match_note,pay,apply_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(job['url'],job['company'],job['title'],job['location'],job['description'],job['source'],job.get('salary_min',''),job.get('salary_max',''),job.get('salary_currency',''),job.get('salary_period',''),job.get('posted_date',''),status,reason,job.get('pay',''),job.get('apply_url','') if valid_url(job.get('apply_url','')) else ''))
            added+=cur.rowcount
            if cur.rowcount and key: existing.setdefault(key,[]).append({'id':cur.lastrowid,**job})
    return added

async def discover_board(request):
    from discovery import fetch_board
    setup=discovery_setup_error()
    if setup:return setup
    data=await request.json(); provider=str(data.get('provider','')); slug=str(data.get('board',''))
    try: found=await asyncio.to_thread(fetch_board,provider,slug)
    except ValueError as exc: return JSONResponse({'error':str(exc)},status_code=400)
    except Exception: return JSONResponse({'error':'Could not retrieve this board. Check the board identifier and connection.'},status_code=502)
    added=store_discovered(found)
    event('discovery',f'{provider} board {slug}: {len(found)} found, {added} added')
    return JSONResponse({'found':len(found),'added':added})
app.router.routes.insert(-1,Route('/api/discover',discover_board,methods=['POST']))

async def approve_and_submit(request):
    """Consume one approval for the reviewed snapshot, then make at most one click."""
    from form_engine import inspect,final_submit_controls
    job_id=int(request.path_params['job_id']); payload=await request.json(); review_id=payload.get('review_id')
    if not isinstance(review_id,str) or payload.get('approve') is not True:
        return JSONResponse({'error':'Explicit approval of a review is required.'},status_code=400)
    async with lock:
        page=pages.get(job_id)
        if page is None or page.is_closed(): return JSONResponse({'error':'Open the application and create a new review.'},status_code=409)
        paused=await require_no_captcha(page,job_id)
        if paused: return paused
        with db() as c:
            review=c.execute('SELECT snapshot FROM reviews WHERE id=? AND job_id=?',(review_id,job_id)).fetchone()
            existing=c.execute('SELECT id FROM approvals WHERE job_id=?',(job_id,)).fetchone()
            job=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            attempted=c.execute("SELECT j.id,j.company,j.title,j.location FROM jobs j LEFT JOIN approvals a ON a.job_id=j.id WHERE a.id IS NOT NULL OR j.status IN ('submitted','submission pending','submission uncertain')").fetchall()
        if not review or not job: return JSONResponse({'error':'Review not found.'},status_code=404)
        if existing or job['status'] in ('submitted','submission pending','submission uncertain'):
            return JSONResponse({'error':'A submission has already been attempted or recorded for this job.'},status_code=409)
        from identity import find_duplicate
        if find_duplicate(dict(job),attempted,exclude_id=job_id):
            return JSONResponse({'error':'A matching company and role has already been submitted or attempted.'},status_code=409)
        reviewed=json.loads(review['snapshot'])
        fields=await inspect(page,{},False)
        with db() as c:
            current_history=[r['id'] for r in c.execute('SELECT id FROM page_history WHERE job_id=? AND session_id=? ORDER BY rowid',(job_id,page_sessions.get(job_id,'')))]
        if page.url!=reviewed['url'] or fields!=reviewed['fields'] or current_history!=[p['id'] for p in reviewed.get('previous_pages',[])]:
            return JSONResponse({'error':'The application changed since review. Create a new review.'},status_code=409)
        buttons=await final_submit_controls(page)
        if len(buttons)!=1 or not await buttons[0][0].is_enabled():
            return JSONResponse({'error':'Could not identify one available submit button. Submit manually in Chrome.'},status_code=409)
        if reviewed.get('submit_controls')!=[buttons[0][1]]: return JSONResponse({'error':'The submit control changed since review. Create a new review.'},status_code=409)
        try:
            before=(await page.locator('body').inner_text(timeout=5000)).lower()
        except Exception:
            return JSONResponse({'error':'Could not inspect the application page. Create a new review.'},status_code=409)
        try:
            with db() as c:
                c.execute('INSERT INTO approvals(job_id,review_id) VALUES (?,?)',(job_id,review_id))
                c.execute("UPDATE jobs SET status='submission pending',updated_at=CURRENT_TIMESTAMP WHERE id=?",(job_id,))
                c.execute('INSERT INTO events(kind,detail) VALUES (?,?)',('approval_given',f'Job {job_id}: approved review {review_id}'))
        except sqlite3.IntegrityError: return JSONResponse({'error':'This job already has an approval.'},status_code=409)
        try:
            event('submit_attempt_started',f'Job {job_id}: submit attempt started after approval')
            await buttons[0][0].click(timeout=10000)
            event('submit_clicked',f'Job {job_id}: submit control clicked after approval')
            await page.wait_for_timeout(1200)
            # An unknown page is not confirmation; never retry automatically.
            body=(await page.locator('body').inner_text(timeout=5000)).lower()
            confirmed=any(phrase in body and phrase not in before for phrase in ('application has been submitted','application was submitted','thank you for applying','application submitted successfully'))
            outcome='submitted' if confirmed else 'submission uncertain'
        except Exception:
            outcome='submission uncertain'
        with db() as c:
            c.execute('UPDATE approvals SET outcome=? WHERE job_id=?',(outcome,job_id))
            c.execute('UPDATE jobs SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(outcome,job_id))
            c.execute('INSERT INTO events(kind,detail) VALUES (?,?)',('submit_outcome',f'Job {job_id}: {outcome}'))
        return JSONResponse({'status':outcome,'message':'Check the application page before taking any further action.'})
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/approve-submit',approve_and_submit,methods=['POST']))

async def resume_collection(request):
    if request.method=='GET':
        with db() as c: rows=c.execute('SELECT id,name,titles,created_at FROM resumes ORDER BY id DESC').fetchall()
        return JSONResponse([dict(row) for row in rows])
    from io import BytesIO
    from pypdf import PdfReader
    try:
        form=await request.form(max_files=1,max_fields=2,max_part_size=10*1024*1024)
        upload=form.get('file'); titles=str(form.get('titles','')).strip()[:1000]
        if not upload or not hasattr(upload,'read'): return JSONResponse({'error':'Choose a PDF resume.'},status_code=400)
        content=await upload.read(10*1024*1024+1)
        if len(content)>10*1024*1024 or not content.startswith(b'%PDF-'): return JSONResponse({'error':'Provide a PDF under 10 MB.'},status_code=400)
        def extract():
            reader=PdfReader(BytesIO(content),strict=False)
            if reader.is_encrypted or len(reader.pages)>30: raise ValueError('PDF must be unlocked and at most 30 pages.')
            return '\n'.join(page.extract_text() or '' for page in reader.pages).strip()[:200000]
        extracted=await asyncio.to_thread(extract)
        if not extracted: return JSONResponse({'error':'No readable text was found in this PDF.'},status_code=400)
    except Exception: return JSONResponse({'error':'Could not read this PDF. Use an unlocked, text-based PDF of at most 30 pages.'},status_code=400)
    folder=DATA/'resumes'; folder.mkdir(exist_ok=True)
    path=folder/(secrets.token_hex(16)+'.pdf'); path.write_bytes(content)
    name=Path(str(upload.filename or 'resume.pdf').replace('\\','/')).name[:200]
    try:
        with db() as c: cur=c.execute('INSERT INTO resumes(name,path,titles,extracted_text) VALUES (?,?,?,?)',(name,str(path),titles,extracted))
    except Exception:
        path.unlink(missing_ok=True); raise
    event('resume_added',f'Resume {cur.lastrowid} added'); return JSONResponse({'id':cur.lastrowid,'name':name},status_code=201)

async def delete_resume(request):
    rid=int(request.path_params['resume_id'])
    with db() as c:
        row=c.execute('SELECT path FROM resumes WHERE id=?',(rid,)).fetchone()
        if row: c.execute('DELETE FROM resumes WHERE id=?',(rid,))
    if not row: return JSONResponse({'error':'Resume not found.'},status_code=404)
    path=Path(row['path'])
    if path.parent.resolve()==(DATA/'resumes').resolve(): path.unlink(missing_ok=True)
    event('resume_deleted',f'Resume {rid} deleted'); return JSONResponse({'ok':True})

async def rules_endpoint(request):
    if request.method=='GET':
        with db() as c: row=c.execute('SELECT data FROM rules WHERE id=1').fetchone()
        return JSONResponse(json.loads(row['data']) if row else {'salary_mode':'ask','strictness':'flag','tab_limit':3})
    data=await request.json()
    clean={k:str(data.get(k,''))[:2000] for k in ('titles','locations','remote','salary_floor','max_age_days','excluded_companies','fixed_salary','role_salaries','salary_fallback','bls_soc')}
    clean['salary_mode']=data.get('salary_mode','ask') if data.get('salary_mode','ask') in ('ask','fixed','role','posting','market','optional') else 'ask'
    clean['career_stage']=data.get('career_stage','') if data.get('career_stage','') in ('','internship','new_grad','experienced') else ''
    from salary import amount,parse_roles,bls_series
    try:
        if clean['salary_floor'] and amount(clean['salary_floor']) is None:raise ValueError('Salary floor must be a positive annual USD amount.')
        if clean['max_age_days'] and (not clean['max_age_days'].isdigit() or int(clean['max_age_days'])>3650):raise ValueError('Posting age must be a whole number of days.')
        if clean['fixed_salary'] and amount(clean['fixed_salary']) is None:raise ValueError('Fixed salary must be a positive annual USD amount.')
        parse_roles(clean['role_salaries'])
        if clean['bls_soc']:bls_series(clean['bls_soc'])
        if clean['salary_mode']=='fixed' and not clean['fixed_salary']:raise ValueError('Enter the fixed annual salary.')
        if clean['salary_mode']=='role' and not clean['role_salaries'].strip():raise ValueError('Enter at least one role salary.')
        if clean['salary_mode']=='market' and not clean['bls_soc']:raise ValueError('Enter the BLS occupation code.')
        if any(x.strip() not in ('fixed','role','posting','market','ask','optional') for x in clean['salary_fallback'].split(',') if x.strip()):raise ValueError('Invalid salary fallback.')
    except ValueError as exc:return JSONResponse({'error':str(exc)},status_code=400)
    clean['strictness']=data.get('strictness','flag') if data.get('strictness','flag') in ('skip','flag','apply') else 'flag'
    try: clean['screen_parallel']=min(16,max(0,int(data.get('screen_parallel') or 0)))  # 0: automatic
    except (ValueError,TypeError): return JSONResponse({'error':'Model calls at once must be a number.'},status_code=400)
    try: clean['tab_limit']=min(10,max(1,int(data.get('tab_limit',3))))
    except (ValueError,TypeError): return JSONResponse({'error':'Tab limit must be a number.'},status_code=400)
    with db() as c: c.execute('INSERT INTO rules(id,data) VALUES (1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(json.dumps(clean),))
    event('rules_updated','Search rules saved'); return JSONResponse(clean)

app.router.routes.insert(-1,Route('/api/resumes',resume_collection,methods=['GET','POST']))
app.router.routes.insert(-1,Route('/api/resumes/{resume_id:int}',delete_resume,methods=['DELETE']))
app.router.routes.insert(-1,Route('/api/rules',rules_endpoint,methods=['GET','POST']))

async def resume_recommendation(request):
    from matching import rank
    job_id=int(request.path_params['job_id'])
    with db() as c:
        job=c.execute('SELECT title,description FROM jobs WHERE id=?',(job_id,)).fetchone()
        resumes=c.execute('SELECT id,name,titles,extracted_text FROM resumes').fetchall()
    if not job: return JSONResponse({'error':'Job not found.'},status_code=404)
    if not job['description']: return JSONResponse({'error':'A job description is needed to compare resumes.'},status_code=409)
    if not resumes: return JSONResponse({'error':'Add a resume first.'},status_code=409)
    return JSONResponse({'method':'Keyword overlap; review the choice and qualifications yourself.','ranking':rank(dict(job),[dict(r) for r in resumes])})
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/resume-match',resume_recommendation,methods=['GET']))

async def attach_resume(request):
    job_id=int(request.path_params['job_id']); data=await request.json()
    try: resume_id=int(data.get('resume_id'))
    except (ValueError,TypeError): return JSONResponse({'error':'Select a resume.'},status_code=400)
    page=pages.get(job_id)
    if page is None or page.is_closed(): return JSONResponse({'error':'Open the job in Chrome first.'},status_code=409)
    paused=await require_no_captcha(page,job_id)
    if paused: return paused
    with db() as c: resume=c.execute('SELECT path,name FROM resumes WHERE id=?',(resume_id,)).fetchone()
    if not resume or not Path(resume['path']).is_file(): return JSONResponse({'error':'Resume file not found.'},status_code=404)
    matches=[]
    for frame in page.frames:
        inputs=frame.locator('input[type=file]')
        for i in range(await inputs.count()):
            item=inputs.nth(i)
            label=await item.evaluate("e => [e.id,e.name,e.getAttribute('aria-label'),...(e.labels ? [...e.labels].map(x=>x.innerText) : []),e.closest('[role=group]')?.getAttribute('aria-labelledby')].filter(Boolean).join(' ').toLowerCase()")
            if 'resume' in label or 'résumé' in label or __import__('re').search(r'\bcv\b',label): matches.append(item)
    if len(matches)!=1: return JSONResponse({'error':'Could not identify one resume upload field.'},status_code=409)
    try: await matches[0].set_input_files({'name':resume['name'],'mimeType':'application/pdf','buffer':Path(resume['path']).read_bytes()})
    except Exception: return JSONResponse({'error':'Could not attach the resume in Chrome.'},status_code=502)
    event('resume_attached',f'Job {job_id}: resume {resume_id} attached')
    return JSONResponse({'ok':True,'name':resume['name']})
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/attach-resume',attach_resume,methods=['POST']))

async def model_settings(request):
    import keyring
    with db() as c: c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    if request.method=='GET':
        with db() as c: row=c.execute("SELECT value FROM settings WHERE key='model'").fetchone()
        return JSONResponse(json.loads(row['value']) if row else {'provider':'local','model':'','base_url':'http://127.0.0.1:11434/v1'})
    from model_client import endpoint
    data=await request.json(); provider=data.get('provider'); model=str(data.get('model','')).strip()[:200]
    if provider not in ('local','openai','openrouter','claude','gemini') or not model: return JSONResponse({'error':'Choose a provider and enter a model name.'},status_code=400)
    if provider!='local' and data.get('cloud_consent') is not True: return JSONResponse({'error':'Cloud models receive resume and job text. Confirm this choice.'},status_code=400)
    settings={'provider':provider,'model':model,'base_url':str(data.get('base_url','http://127.0.0.1:11434/v1')).strip() if provider=='local' else '', 'map_fields':data.get('map_fields') is True}
    try: endpoint(settings)
    except ValueError as exc: return JSONResponse({'error':str(exc)},status_code=400)
    key=str(data.get('api_key','')).strip()
    if provider!='local':
        try:
            if key: keyring.set_password('OfferLetter','model:'+provider,key)
            elif not keyring.get_password('OfferLetter','model:'+provider): return JSONResponse({'error':'Enter an API key for this provider.'},status_code=400)
        except Exception: return JSONResponse({'error':'Could not access the system credential store.'},status_code=503)
    with db() as c: c.execute("INSERT INTO settings(key,value) VALUES ('model',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(settings),))
    event('model_settings_saved',f'Model provider set to {provider}')
    return JSONResponse(settings)

async def fit_check(request):
    import keyring
    from model_client import assess
    job_id=int(request.path_params['job_id']); payload=await request.json()
    try: resume_id=int(payload.get('resume_id'))
    except (TypeError,ValueError): return JSONResponse({'error':'Choose a resume.'},status_code=400)
    with db() as c:
        job=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        resume=c.execute('SELECT extracted_text FROM resumes WHERE id=?',(resume_id,)).fetchone()
        try: config=c.execute("SELECT value FROM settings WHERE key='model'").fetchone()
        except sqlite3.OperationalError: config=None
        rule=c.execute('SELECT data FROM rules WHERE id=1').fetchone()
    if not job or not resume: return JSONResponse({'error':'Job or resume not found.'},status_code=404)
    if not job['description'] or not config: return JSONResponse({'error':'A job description and configured model are required.'},status_code=409)
    cfg=json.loads(config['value']); rules=json.loads(rule['data']) if rule else {}
    try:
        key=keyring.get_password('OfferLetter','model:'+cfg['provider']) if cfg['provider']!='local' else ''
        if cfg['provider']!='local' and not key: return JSONResponse({'error':'API key not found in the credential store.'},status_code=409)
        result=await asyncio.to_thread(assess,cfg,key,job['description'],resume['extracted_text'])
    except Exception: return JSONResponse({'error':'Model request failed or returned unsupported evidence. Check the model and try again.'},status_code=502)
    from rule_checks import evaluate
    checks=evaluate(dict(job),rules)
    if any(x['result']=='fail' for x in checks): result['result']='fail'
    result.update(rule_checks=checks,resume_id=resume_id,provider=cfg['provider'],strictness=rules.get('strictness','flag'))
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS fit_checks (id INTEGER PRIMARY KEY,job_id INTEGER NOT NULL REFERENCES jobs(id),resume_id INTEGER NOT NULL,result TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        c.execute('INSERT INTO fit_checks(job_id,resume_id,result) VALUES (?,?,?)',(job_id,resume_id,json.dumps(result)))
    event('fit_checked',f'Job {job_id}: {result["result"]}')
    return JSONResponse(result)
app.router.routes.insert(-1,Route('/api/settings/model',model_settings,methods=['GET','POST']))
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/fit',fit_check,methods=['POST']))

async def pending_questions(request):
    from semantic_memory import eligible
    with db() as c:
        rows=c.execute("SELECT q.id,q.job_id,q.label,q.field_type,q.options,q.created_at,q.suggestion_id,q.suggestion_score,j.company,j.title FROM questions q JOIN jobs j ON j.id=q.job_id WHERE q.status='pending' ORDER BY q.id").fetchall()
        answers={r['id']:dict(r) for r in c.execute('SELECT * FROM answers')}
    result=[]
    for row in rows:
        item={**dict(row),'options':json.loads(row['options'])};candidate=answers.get(row['suggestion_id'])
        item['suggestion']={'question':candidate['question'],'answer':candidate['answer'],'scope':candidate['scope']} if candidate and eligible(row['label'],[candidate],row['job_id'],row['title']) else None
        result.append(item)
    return JSONResponse(result)

async def resolve_question(request):
    from answer_memory import fill_field, may_reuse, TIME_SENSITIVE
    from form_engine import normalize
    qid=int(request.path_params['question_id']); data=await request.json()
    answer=str(data.get('answer','')).strip(); scope=data.get('scope','job'); role=str(data.get('role_type','')).strip(); expiry=data.get('expires_at') or None
    if not answer or len(answer)>10000 or scope not in ('global','role','job') or (scope=='role' and not role): return JSONResponse({'error':'Provide an answer and a valid scope.'},status_code=400)
    with db() as c: q=c.execute('SELECT * FROM questions WHERE id=? AND status=\'pending\'',(qid,)).fetchone()
    if not q: return JSONResponse({'error':'Question is no longer pending.'},status_code=404)
    label=q['label']
    if scope!='job' and not may_reuse(label,scope): return JSONResponse({'error':'This question must be saved for this job only.'},status_code=400)
    if scope!='job' and any(x in normalize(label) for x in TIME_SENSITIVE) and not expiry: return JSONResponse({'error':'Time-sensitive answers need an expiration date.'},status_code=400)
    if expiry:
        from datetime import datetime,timezone
        try: expiry=datetime.fromisoformat(str(expiry).replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
        except ValueError: return JSONResponse({'error':'Invalid expiration date.'},status_code=400)
    page=pages.get(q['job_id'])
    if not page or page.is_closed() or page.url!=q['page_url']: return JSONResponse({'error':'Open the same application page before answering.'},status_code=409)
    paused=await require_no_captcha(page,q['job_id'])
    if paused: return paused
    field={'frame':q['frame_index'],'index':q['field_index'],'label':label,'type':q['field_type'],'options':json.loads(q['options'])}
    try: await fill_field(page,field,answer)
    except Exception as exc:
        event('question_fill_failed',f'Question {qid}: {type(exc).__name__}: {str(exc)[:200]}')
        return JSONResponse({'error':'The field changed or cannot be filled. Check the application page.'},status_code=409)
    with db() as c:
        c.execute('INSERT INTO answers(question,answer,scope,job_id,role_type,expires_at) VALUES (?,?,?,?,?,?)',(label,answer,scope,q['job_id'] if scope=='job' else None,role if scope=='role' else None,expiry))
        c.execute("UPDATE questions SET status='answered' WHERE id=?",(qid,))
    event('question_answered',f'Question {qid} answered with {scope} scope')
    return JSONResponse({'ok':True})
app.router.routes.insert(-1,Route('/api/questions',pending_questions,methods=['GET']))
app.router.routes.insert(-1,Route('/api/questions/{question_id:int}/answer',resolve_question,methods=['POST']))

schedule_lock=asyncio.Lock()
async def run_discovery_schedule():
    from discovery import fetch_board
    from simplify import fetch_list
    from jobspy_discovery import search_site
    from datetime import datetime,timezone,timedelta
    setup=discovery_setup_error()
    if setup:return {'error':'Save your target job titles in Search rules before discovering jobs.'}
    if schedule_lock.locked(): return {'error':'A scheduled discovery run is already in progress.'}
    async with schedule_lock:
        with db() as c: row=c.execute('SELECT * FROM schedule WHERE id=1').fetchone()
        if not row: return {'error':'Configure a schedule first.'}
        with db() as c: rule=c.execute('SELECT data FROM rules WHERE id=1').fetchone()
        rules=json.loads(rule['data']) if rule else {}
        boards=json.loads(row['boards']); results=[]
        for board in boards:
            try:
                if board['provider']=='simplify':
                    from discovery_preferences import repository_allowed
                    if not repository_allowed(board['board'],rules):
                        results.append({'provider':'simplify','board':board['board'],'skipped':'Repository does not match your career stage.'})
                        continue
                    found=await asyncio.to_thread(fetch_list,board['board'])
                elif board['provider']=='jobspy':
                    query=next((s.strip() for s in rules.get('titles','').split(',') if s.strip()),'')
                    location=next((s.strip() for s in rules.get('locations','').split(',') if s.strip()),'')
                    if not query:raise ValueError('Set a job title in your rules first.')
                    hours=int(rules['max_age_days'])*24 if rules.get('max_age_days','').isdigit() and int(rules['max_age_days'])>0 else None
                    jobspy=await asyncio.wait_for(asyncio.to_thread(search_site,board['board'],query,location,20,hours,False),timeout=90)
                    found=jobspy['jobs']
                else: found=await asyncio.to_thread(fetch_board,board['provider'],board['board'])
                added=store_discovered(found)
                results.append({'provider':board['provider'],'board':board['board'],'found':len(found),'added':added,**({'error':jobspy['error']} if board['provider']=='jobspy' and jobspy['error'] else {})})
            except Exception: results.append({'provider':board['provider'],'board':board['board'],'error':'Board unavailable'})
        with db() as c: c.execute('UPDATE schedule SET last_run=?,last_result=? WHERE id=1',(datetime.now(timezone.utc).isoformat(),json.dumps(results)))
        event('scheduled_discovery',f'Checked {len(boards)} boards')
        return {'boards':results}

async def scheduler_loop():
    from datetime import datetime,timezone,timedelta
    while True:
        await asyncio.sleep(15)
        try:
            now=datetime.now(timezone.utc)
            with db() as c:
                row=c.execute('SELECT * FROM schedule WHERE id=1 AND enabled=1').fetchone()
                if not row or not row['next_run'] or datetime.fromisoformat(row['next_run'])>now: continue
                # Claim the next run before doing external work, including after a restart.
                claimed=c.execute('UPDATE schedule SET next_run=? WHERE id=1 AND enabled=1 AND next_run=?',((now+timedelta(minutes=row['interval_minutes'])).isoformat(),row['next_run'])).rowcount
                if not claimed: continue
            await run_discovery_schedule()
            with db() as c: schedule=c.execute('SELECT enabled,prepare_jobs FROM schedule WHERE id=1').fetchone()
            if schedule and schedule['enabled'] and schedule['prepare_jobs']: await start_preparation_run()
        except asyncio.CancelledError: raise
        except Exception: event('schedule_error','Scheduled discovery failed; check configuration')

async def schedule_settings(request):
    from datetime import datetime,timezone,timedelta
    from discovery import board_url
    from simplify import LISTS
    from jobspy_discovery import SITES
    if request.method=='GET':
        with db() as c: row=c.execute('SELECT * FROM schedule WHERE id=1').fetchone()
        if not row: return JSONResponse({'enabled':False,'interval_minutes':60,'boards':[],'next_run':None,'last_run':None,'last_result':None})
        return JSONResponse({**dict(row),'enabled':bool(row['enabled']),'boards':json.loads(row['boards']),'last_result':json.loads(row['last_result']) if row['last_result'] else None})
    data=await request.json(); boards=data.get('boards',[])
    try:
        interval=int(data.get('interval_minutes',60))
        if interval<1 or interval>10080 or not isinstance(boards,list) or len(boards)>25: raise ValueError()
        clean=[]
        for board in boards:
            provider=str(board['provider']); slug=str(board['board']).strip()
            if provider=='simplify':
                if slug not in LISTS: raise ValueError()
            elif provider=='jobspy':
                if slug not in SITES:raise ValueError()
            else: board_url(provider,slug)
            clean.append({'provider':provider,'board':slug})
        if data.get('enabled') is True and not clean: raise ValueError()
    except (ValueError,TypeError,KeyError): return JSONResponse({'error':'Enter valid boards and an interval between 1 and 10080 minutes.'},status_code=400)
    enabled=data.get('enabled') is True
    next_run=(datetime.now(timezone.utc)+timedelta(minutes=interval)).isoformat() if enabled else None
    with db() as c:
        c.execute('INSERT INTO schedule(id,enabled,interval_minutes,boards,next_run,prepare_jobs) VALUES(1,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled,interval_minutes=excluded.interval_minutes,boards=excluded.boards,next_run=excluded.next_run,prepare_jobs=excluded.prepare_jobs',(enabled,interval,json.dumps(clean),next_run,data.get('prepare_jobs') is True))
    event('schedule_updated','Discovery schedule updated')
    return JSONResponse({'enabled':enabled,'interval_minutes':interval,'boards':clean,'next_run':next_run,'prepare_jobs':data.get('prepare_jobs') is True})

async def schedule_run(request):
    result=await run_discovery_schedule()
    return JSONResponse(result,status_code=409 if 'error' in result else 200)
app.router.routes.insert(-1,Route('/api/schedule',schedule_settings,methods=['GET','POST']))
app.router.routes.insert(-1,Route('/api/schedule/run',schedule_run,methods=['POST']))

async def require_no_captcha(page,job_id):
    from form_engine import captcha_present
    if not await captcha_present(page): return None
    with db() as c: c.execute("UPDATE jobs SET status='waiting on user',updated_at=CURRENT_TIMESTAMP WHERE id=?",(job_id,))
    event('captcha_pause',f'Job {job_id}: user action required')
    return JSONResponse({'error':'CAPTCHA detected. Complete it in Chrome, then try again.','captcha':True},status_code=409)

async def next_application_page(request):
    from form_engine import inspect
    job_id=int(request.path_params['job_id'])
    async with lock:
        page=pages.get(job_id); session_id=page_sessions.get(job_id)
        if not page or page.is_closed() or not session_id: return JSONResponse({'error':'Open the application first.'},status_code=409)
        paused=await require_no_captcha(page,job_id)
        if paused: return paused
        fields=await inspect(page,{},False)
        if any(f.get('error') for f in fields): return JSONResponse({'error':'Cannot inspect all fields on this page.'},status_code=409)
        if any(not f.get('valid',True) or (f.get('required') and f.get('type')=='select-one' and not f.get('value')) for f in fields): return JSONResponse({'error':'Complete required fields before continuing.'},status_code=409)
        candidates=page.get_by_role('button',name=__import__('re').compile(r'^(next|continue|review application|review)$',__import__('re').I),exact=True)
        visible=[]
        for i in range(await candidates.count()):
            el=candidates.nth(i)
            if await el.is_visible() and await el.is_enabled(): visible.append(el)
        if len(visible)!=1: return JSONResponse({'error':'Could not identify one Next or Continue button. Continue manually in Chrome.'},status_code=409)
        history_id=secrets.token_hex(16); folder=DATA/'reviews'; folder.mkdir(exist_ok=True); shot=folder/(history_id+'.png')
        await page.screenshot(path=str(shot),full_page=True)
        with db() as c:notes=c.execute('SELECT frame_index,field_index,value,source FROM salary_notes WHERE job_id=? AND page_url=?',(job_id,page.url)).fetchall()
        salary_notes=[{'label':f['label'],'source':r['source']} for r in notes for f in fields if f.get('frame')==r['frame_index'] and f.get('index')==r['field_index'] and f.get('value')==r['value']]
        snapshot={'url':page.url,'fields':fields,'salary_notes':salary_notes}
        with db() as c: c.execute('INSERT INTO page_history(id,job_id,session_id,snapshot,screenshot) VALUES (?,?,?,?,?)',(history_id,job_id,session_id,json.dumps(snapshot,ensure_ascii=False),str(shot)))
        event('page_saved',f'Job {job_id}: application page saved before continuing')
        try:
            await visible[0].click(timeout=10000)
            await page.wait_for_timeout(700)
            if page.url==snapshot['url'] and await inspect(page,{},False)==fields:
                event('page_advance_uncertain',f'Job {job_id}: no visible page change')
                return JSONResponse({'error':'No page change was detected. Check Chrome before continuing.'},status_code=409)
        except Exception:
            event('page_advance_uncertain',f'Job {job_id}: verify the application page')
            return JSONResponse({'error':'Could not confirm navigation. Check Chrome before continuing.'},status_code=409)
        event('page_advanced',f'Job {job_id}: Next or Continue clicked')
        return JSONResponse({'ok':True,'url':page.url,'message':'Check the next page and fill remaining fields.'})

async def history_screenshot(request):
    history_id=request.path_params['history_id']
    with db() as c: row=c.execute('SELECT screenshot FROM page_history WHERE id=?',(history_id,)).fetchone()
    if not row: return JSONResponse({'error':'Page not found'},status_code=404)
    return FileResponse(row['screenshot'],media_type='image/png',headers={'Cache-Control':'no-store'})
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/next',next_application_page,methods=['POST']))
app.router.routes.insert(-1,Route('/api/history/{history_id:str}/screenshot',history_screenshot,methods=['GET']))

async def discover_simplify(request):
    from simplify import fetch_list,LISTS
    from discovery_preferences import repository_allowed
    setup=discovery_setup_error()
    if setup:return setup
    data=await request.json(); selected=data.get('list','new_grad')
    if selected not in LISTS:return JSONResponse({'error':'Unknown list.'},status_code=400)
    if not repository_allowed(selected,discovery_preferences()):return JSONResponse({'error':'Choose the matching career stage in Search rules before importing this repository.'},status_code=409)
    try: found=await asyncio.to_thread(fetch_list,selected)
    except Exception:return JSONResponse({'error':'Could not read the SimplifyJobs list.'},status_code=502)
    added=store_discovered(found);event('discovery',f'Simplify {selected}: {len(found)} found, {added} added')
    return JSONResponse({'found':len(found),'added':added})
app.router.routes.insert(-1,Route('/api/discover/simplify',discover_simplify,methods=['POST']))

async def cover_fields(page):
    found=[]
    for fi,frame in enumerate(page.frames):
        controls=frame.locator('input[type=file], textarea, input[type=text]')
        for ci in range(await controls.count()):
            control=controls.nth(ci)
            info=await control.evaluate("e => ({label:((e.labels && [...e.labels].map(x=>x.innerText).join(' ')) || e.getAttribute('aria-label') || e.placeholder || e.name || e.id || ''),identity:[e.id,e.name,e.getAttribute('aria-label'),e.closest('[role=group]')?.getAttribute('aria-labelledby')].filter(Boolean).join(' '), type:e.type})")
            if 'cover letter' in (info['label']+' '+info['identity']).lower().replace('_',' ').replace('-',' '):
                found.append({'frame':fi,'index':ci,'label':info['label'],'type':info['type'],'control':control})
    return found

async def make_cover_letter(request):
    import keyring
    from cover_letter import draft
    job_id=int(request.path_params['job_id']); data=await request.json()
    try: resume_id=int(data.get('resume_id'))
    except (TypeError,ValueError): return JSONResponse({'error':'Choose a resume.'},status_code=400)
    page=pages.get(job_id)
    if not page or page.is_closed(): return JSONResponse({'error':'Open the application first.'},status_code=409)
    paused=await require_no_captcha(page,job_id)
    if paused:return paused
    fields=await cover_fields(page)
    if len(fields)!=1:return JSONResponse({'error':'Could not identify one cover-letter field on this page.'},status_code=409)
    original_url=page.url
    original_field={k:v for k,v in fields[0].items() if k!='control'}
    with db() as c:
        job=c.execute('SELECT title,company,description FROM jobs WHERE id=?',(job_id,)).fetchone()
        resume=c.execute('SELECT extracted_text FROM resumes WHERE id=?',(resume_id,)).fetchone()
        try: cfg=c.execute("SELECT value FROM settings WHERE key='model'").fetchone()
        except sqlite3.OperationalError: cfg=None
    if not job or not resume: return JSONResponse({'error':'Job or resume not found.'},status_code=404)
    if not job['description'] or not cfg: return JSONResponse({'error':'A job description and configured model are required.'},status_code=409)
    settings=json.loads(cfg['value'])
    try:
        key=keyring.get_password('OfferLetter','model:'+settings['provider']) if settings['provider']!='local' else ''
        if settings['provider']!='local' and not key: raise ValueError('Missing key')
        result=await asyncio.to_thread(draft,settings,key,job['description'],resume['extracted_text'],job['company'],job['title'])
    except Exception:return JSONResponse({'error':'Could not generate a draft with verifiable resume excerpts. Check the model and try again.'},status_code=502)
    current=await cover_fields(page)
    if page.url!=original_url or len(current)!=1 or {k:v for k,v in current[0].items() if k!='control'}!=original_field: return JSONResponse({'error':'The page changed during drafting. Try again.'},status_code=409)
    cover_id=secrets.token_hex(16); field={k:v for k,v in fields[0].items() if k!='control'}
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS cover_letters (id TEXT PRIMARY KEY,job_id INTEGER NOT NULL REFERENCES jobs(id),resume_id INTEGER NOT NULL, page_url TEXT NOT NULL,field TEXT NOT NULL,text TEXT NOT NULL,quotes TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,attached INTEGER NOT NULL DEFAULT 0)')
        c.execute('INSERT INTO cover_letters(id,job_id,resume_id,page_url,field,text,quotes) VALUES(?,?,?,?,?,?,?)',(cover_id,job_id,resume_id,page.url,json.dumps(field),result['text'],json.dumps(result['quotes'])))
    event('cover_drafted',f'Job {job_id}: cover letter drafted from resume {resume_id}')
    return JSONResponse({'id':cover_id,**result,'notice':'Review the draft and the quoted resume evidence before attaching.'})

async def attach_cover_letter(request):
    import html
    job_id=int(request.path_params['job_id']); data=await request.json(); cover_id=data.get('cover_id')
    page=pages.get(job_id)
    if not page or page.is_closed():return JSONResponse({'error':'Open the application first.'},status_code=409)
    paused=await require_no_captcha(page,job_id)
    if paused:return paused
    with db() as c:
        try: cover=c.execute('SELECT * FROM cover_letters WHERE id=? AND job_id=?',(cover_id,job_id)).fetchone()
        except sqlite3.OperationalError: cover=None
    if not cover:return JSONResponse({'error':'Cover letter not found.'},status_code=404)
    fields=await cover_fields(page)
    if page.url!=cover['page_url'] or len(fields)!=1 or {k:v for k,v in fields[0].items() if k!='control'}!=json.loads(cover['field']): return JSONResponse({'error':'The cover-letter field changed. Create a new draft.'},status_code=409)
    field=fields[0]; control=field['control']
    try:
        if field['type']=='file':
            doc=await browser.new_page()
            try:
                text=html.escape(cover['text'])
                await doc.set_content('<!doctype html><meta charset="utf-8"><style>body{font:12pt/1.6 Arial,sans-serif;white-space:pre-wrap;margin:0}</style><body>'+text+'</body>')
                pdf=await doc.pdf(format='Letter',margin={'top':'0.8in','right':'0.8in','bottom':'0.8in','left':'0.8in'},print_background=True)
            finally: await doc.close()
            from io import BytesIO
            from pypdf import PdfReader
            rendered=' '.join(p.extract_text() or '' for p in PdfReader(BytesIO(pdf)).pages)
            if not all(quote in rendered for quote in json.loads(cover['quotes'])): raise ValueError('PDF did not preserve resume evidence')
            await control.set_input_files({'name':'cover-letter.pdf','mimeType':'application/pdf','buffer':pdf})
        elif field['type'] in ('textarea','text'):
            if not await control.is_visible(): raise ValueError('Field is hidden')
            await control.fill(cover['text'])
        else: raise ValueError('Unsupported cover letter field')
    except Exception:return JSONResponse({'error':'Could not attach the letter. Check the application page.'},status_code=409)
    with db() as c:c.execute('UPDATE cover_letters SET attached=1 WHERE id=?',(cover_id,))
    event('cover_attached',f'Job {job_id}: cover letter attached')
    return JSONResponse({'ok':True})
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/cover-letter',make_cover_letter,methods=['POST']))
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/cover-letter/attach',attach_cover_letter,methods=['POST']))

preparation_task=None
preparation_start_lock=asyncio.Lock()
class InternalRequest:
    def __init__(self,job_id,data=None,method='POST'):
        self.path_params={'job_id':job_id};self.data=data or {};self.method=method
    async def json(self):return self.data

def preparation_policy(fit,rules):
    if fit['result']=='fail':return 'skip'
    if any(check['result']=='flag' for check in fit['rule_checks']):return 'review fit'
    for key,label in (('salary_floor','Salary floor'),('max_age_days','Posting age'),('remote','Remote preference')):
        if str(rules.get(key,'')).strip() and not any(c.get('rule')==label and c.get('result')=='pass' for c in fit['rule_checks']):return 'review fit'
    if fit['result']=='borderline':
        return {'skip':'skip','flag':'review fit','apply':'prepare'}.get(rules.get('strictness','flag'),'review fit')
    return 'prepare'

def run_is_pausing(run_id):
    with db() as c: row=c.execute('SELECT status FROM runs WHERE id=?',(run_id,)).fetchone()
    return not row or row['status']!='running'

async def read_posting(url):
    """The posting's visible text, read in Chrome so pages built by scripts render. '' when it can't be read."""
    if browser is None:await open_browser(None)
    if browser is None:return ''
    page=None
    try:
        async with reading_slots:
            page=await browser.new_page()
            await page.goto(url,wait_until='domcontentloaded',timeout=30000)
            try:await page.wait_for_load_state('networkidle',timeout=10000)
            except Exception:pass
            text=re.sub(r'\s+',' ',await page.inner_text('body'))[:30000]
            return text if len(text)>=600 else ''
    except Exception:return ''
    finally:
        if page is not None:
            try:await page.close()
            except Exception:pass
reading_slots=asyncio.Semaphore(3)  # short-lived reading tabs, separate from application tabs

async def preparation_worker(run_id,summary=None,more=lambda:False):
    from matching import rank
    summary=summary if summary is not None else {}  # shared with screening when both run, so neither overwrites the other
    summary.update(phase='preparing',prepared=0,skipped=0,needs_attention=0,errors=0,reason='')
    def save(status='running'):
        with db() as c:
            if status=='running': c.execute("UPDATE runs SET summary=? WHERE id=? AND status='running'",(json.dumps(summary),run_id))
            else: c.execute('UPDATE runs SET status=?,summary=?,finished_at=CURRENT_TIMESTAMP WHERE id=?',(status,json.dumps(summary),run_id))
    try:
        with db() as c:
            resumes=[dict(r) for r in c.execute('SELECT id,name,titles,extracted_text FROM resumes')]
            rule=c.execute('SELECT data FROM rules WHERE id=1').fetchone()
            try: config=c.execute("SELECT value FROM settings WHERE key='model'").fetchone()
            except sqlite3.OperationalError:config=None
        rules=json.loads(rule['data']) if rule else {}
        if not resumes or not config:
            summary['reason']='Add a resume and configure a model before preparing jobs.';save('blocked');return
        seen=set();walled={}
        while True:
            # Take the next found job each time, so jobs the user approves during the run are included.
            with db() as c:
                # Jobs the user approved go first and skip the fit gate; each job is taken at most once per run.
                skip=(' AND id NOT IN (%s)'%','.join('?'*len(seen))) if seen else ''
                row=c.execute("SELECT * FROM jobs WHERE status IN ('found','approved')"+skip+" ORDER BY status='approved' DESC,id LIMIT 1",tuple(seen)).fetchone()
            if not row:
                if not more():break
                # Screening is still adding jobs: wait for the next clear one.
                if run_is_pausing(run_id):summary['reason']='Paused by user.';save('paused');return
                if summary.get('reason'):summary['reason']='';save()
                await asyncio.sleep(2);continue
            job=dict(row);seen.add(job['id'])
            from ats_navigation import on_job_board
            wall=on_job_board(job['url']) if not job['apply_url'] else ''
            if wall in walled and job['status']!='approved':
                # This board already showed a sign-in wall in this run: hand it over without a model call or a tab.
                with db() as c:c.execute("UPDATE jobs SET status='waiting on user',match_note=? WHERE id=? AND status='found'",(walled[wall],job['id']))
                summary['needs_attention']+=1;save();continue
            with db() as c: state=c.execute('SELECT status FROM runs WHERE id=?',(run_id,)).fetchone()
            if not state or state['status']=='pausing':summary['reason']='Paused by user.';save('paused');return
            # Respect the tab limit: wait for the user to finish or close a tab, then continue.
            while True:
                with db() as c: rule=c.execute('SELECT data FROM rules WHERE id=1').fetchone()
                try:limit=max(1,int((json.loads(rule['data']) if rule else {}).get('tab_limit') or 3))
                except (TypeError,ValueError):limit=3
                for stale in [key for key,value in pages.items() if value.is_closed()]: pages.pop(stale,None);page_sessions.pop(stale,None)
                if len(pages)<limit:break
                if run_is_pausing(run_id):summary['reason']='Paused by user.';save('paused');return
                summary['reason']=f'Waiting for a free tab: {len(pages)} of {limit} open. Finish or close one to continue.';save()
                await asyncio.sleep(3)
            summary['reason']=f'Preparing {job["title"] or "a job"}';save()
            if not job['description']:
                # Read the posting in Chrome, in the tab the application would use anyway, so pages built by scripts render.
                text=''
                if browser is None:await open_browser(None)
                if browser is not None and (await open_job(InternalRequest(job['id']))).status_code==200 and job['id'] in pages:
                    try:
                        await pages[job['id']].wait_for_load_state('networkidle',timeout=15000)
                    except Exception:pass
                    try:text=re.sub(r'\s+',' ',await pages[job['id']].inner_text('body'))[:30000]
                    except Exception:text=''
                    if len(text)<600:text=''
                if text:
                    with db() as c:c.execute('UPDATE jobs SET description=? WHERE id=?',(text,job['id']))
                    job['description']=text
            if not job['description']:
                with db() as c:c.execute("UPDATE jobs SET status='waiting on user',match_note=? WHERE id=? AND status IN ('found','approved')",('Could not read the job description, so the fit was not checked. Open it to decide.',job['id']))
                if job['id'] in pages:
                    try:await pages[job['id']].close()
                    except Exception:pass
                    pages.pop(job['id'],None);page_sessions.pop(job['id'],None)
                summary['needs_attention']+=1;save();continue
            selected=rank(job,resumes)[0]['id']
            if job['status']=='approved':policy='prepare'  # the user already decided; no second fit check
            else:
                fit_response=await fit_check(InternalRequest(job['id'],{'resume_id':selected}))
                if run_is_pausing(run_id):summary['reason']='Paused by user.';save('paused');return
                if fit_response.status_code!=200:
                    summary['reason']='Model check failed; check model settings.';summary['errors']+=1;save('waiting');return
                fit=json.loads(fit_response.body);policy=preparation_policy(fit,rules)
            if policy!='prepare':
                new_status='skipped' if policy=='skip' else 'review fit'
                unmet=[r['requirement'] for r in fit.get('requirements',[]) if r.get('assessment')=='not_met'][:2]
                unclear=[r['requirement'] for r in sorted(fit.get('requirements',[]),key=lambda r:r.get('kind')!='required') if r.get('assessment')=='unclear'][:2]
                flagged=[check.get('rule') or check.get('name') for check in fit.get('rule_checks',[]) if check.get('result')!='pass'][:2]
                note=('Not a fit: '+'; '.join(unmet) if unmet else 'Fit unclear: '+'; '.join(unclear or flagged or ['check the requirements']))[:300]
                with db() as c:c.execute('UPDATE jobs SET status=?,match_note=? WHERE id=? AND status=\'found\'',(new_status,note,job['id']))
                if job['id'] in pages:  # opened only to read the posting: free the tab
                    try:await pages[job['id']].close()
                    except Exception:pass
                    pages.pop(job['id'],None);page_sessions.pop(job['id'],None)
                summary['skipped' if policy=='skip' else 'needs_attention']+=1;save();continue
            if browser is None:
                response=await open_browser(None)
                if response.status_code!=200:summary['reason']='Could not open Chrome.';summary['errors']+=1;save('waiting');return
            response=await open_job(InternalRequest(job['id']))
            if response.status_code!=200:
                summary['reason']='Could not open an application; check Chrome and the tab limit.';summary['errors']+=1;save('waiting');return
            if run_is_pausing(run_id):summary['reason']='Paused by user.';save('paused');return
            # Application pages often keep loading after they open; let them settle and retry before handing the job to the user.
            for attempt in range(3):
                if job['id'] in pages:
                    try:await pages[job['id']].wait_for_load_state('networkidle',timeout=10000)
                    except Exception:pass
                response=await inspect_job(InternalRequest(job['id']))
                if response.status_code==200:break
                await asyncio.sleep(2)
            if response.status_code!=200:
                with db() as c:c.execute("UPDATE jobs SET status='waiting on user',match_note=? WHERE id=? AND status IN ('found','approved')",('Opened in Chrome, but the form could not be read. Fill it there.',job['id']))
                summary['needs_attention']+=1;save();continue
            fields=json.loads(response.body)['fields']
            if run_is_pausing(run_id):summary['reason']='Paused by user.';save('paused');return
            from ats_navigation import on_job_board
            board=on_job_board(pages[job['id']].url) if job['id'] in pages else ''
            real=[f for f in fields if f.get('type') not in ('hidden','search','submit','button')]
            if board or len(real)<2:
                # A listing page or a page with no form is not a filled application: hand it over with the reason, tab left open.
                # The tab is closed so these don't use up the tab limit; Open on the Jobs page brings it back.
                note=(f'{board} asks you to sign in or apply on {board}. Sign in once in OfferLetter’s Chrome window, then open it from Jobs' if board
                      else 'Workday asks you to sign in or create an account on this employer’s site before the form appears. Open it from Jobs to apply' if 'myworkdayjobs.com' in (urlparse(pages[job['id']].url).hostname or '')
                      else 'Opened the posting, but found no application form on the page. Open it from Jobs to apply')
                with db() as c:
                    c.execute("UPDATE jobs SET status='waiting on user',match_note=? WHERE id=? AND status IN ('found','approved','waiting on user')",(note,job['id']))
                    c.execute("DELETE FROM questions WHERE job_id=? AND status='pending'",(job['id'],))  # a sign-in or listing page's boxes are not questions
                if board:walled[board]=note
                try:await pages[job['id']].close()
                except Exception:pass
                pages.pop(job['id'],None);page_sessions.pop(job['id'],None)
                summary['needs_attention']+=1;save();continue
            if any(f.get('type')=='file' and ('resume' in f.get('label','').lower() or 'cv' in f.get('label','').lower()) for f in fields):
                attached=await attach_resume(InternalRequest(job['id'],{'resume_id':selected}))
                if attached.status_code!=200:summary['needs_attention']+=1;save();continue
            # Automation ends at the current page; user answers, navigates and reviews.
            with db() as c:c.execute("UPDATE jobs SET status='waiting on user',match_note='' WHERE id=? AND status IN ('found','approved','waiting on user')",(job['id'],))
            summary['prepared']+=1;save()
        summary['reason']='All eligible found jobs were considered.';save('complete')
    except asyncio.CancelledError:
        summary['reason']='Run interrupted by shutdown.';save('interrupted');raise
    except Exception:
        summary['errors']+=1;summary['reason']='Unexpected error; check the event log.';event('run_error',f'Preparation run {run_id} failed');save('failed')

async def start_preparation_run():
    global preparation_task
    async with preparation_start_lock:
        if preparation_task and not preparation_task.done():return {'error':'A preparation run is already active.'}
        with db() as c:cur=c.execute("INSERT INTO runs(status) VALUES ('running')"); run_id=cur.lastrowid
        preparation_task=asyncio.create_task(preparation_worker(run_id))
        event('run_started',f'Preparation run {run_id} started')
        return {'id':run_id,'status':'running'}

async def preparation_endpoint(request):
    if request.method=='GET':
        with db() as c:row=c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()
        return JSONResponse({**dict(row),'summary':json.loads(row['summary'])} if row else {'status':'not started'})
    result=await start_preparation_run();return JSONResponse(result,status_code=409 if 'error' in result else 202)

async def pause_preparation(request):
    with db() as c:changed=c.execute("UPDATE runs SET status='pausing' WHERE status='running'").rowcount
    return JSONResponse({'status':'pausing'} if changed else {'error':'No run is active.'},status_code=200 if changed else 409)
app.router.routes.insert(-1,Route('/api/runs',preparation_endpoint,methods=['GET','POST']))
app.router.routes.insert(-1,Route('/api/runs/pause',pause_preparation,methods=['POST']))

gmail_pending={}
async def gmail_settings(request):
    import keyring
    from gmail_connector import KEY_SERVICE,KEY_NAME
    with db() as c:c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    if request.method=='GET':
        with db() as c:row=c.execute("SELECT value FROM settings WHERE key='gmail'").fetchone()
        try:connected=bool(keyring.get_password(KEY_SERVICE,KEY_NAME))
        except Exception:connected=False
        return JSONResponse({'connected':connected,**(json.loads(row['value']) if row else {'codes':False,'links':False,'status_updates':False})})
    data=await request.json();flags={k:data.get(k) is True for k in ('codes','links','status_updates')}
    with db() as c:c.execute("INSERT INTO settings(key,value) VALUES ('gmail',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(flags),))
    event('gmail_settings','Gmail uses updated');return JSONResponse(flags)

async def gmail_begin(request):
    from gmail_connector import parse_client,begin_auth
    data=await request.json();raw=data.get('client_json','')
    if not isinstance(raw,str) or len(raw)>20000:return JSONResponse({'error':'Provide a Google desktop OAuth client JSON.'},status_code=400)
    try: pending=begin_auth(parse_client(raw),request.url.port or 80)
    except Exception:return JSONResponse({'error':'Invalid Google desktop OAuth client JSON.'},status_code=400)
    now=time.time()
    for state in list(gmail_pending):
        if now-gmail_pending[state]['created']>600:gmail_pending.pop(state,None)
    if len(gmail_pending)>=5:return JSONResponse({'error':'Too many pending sign-in attempts.'},status_code=429)
    gmail_pending[pending['state']]=pending
    return JSONResponse({'authorization_url':pending['url']})

async def gmail_callback(request):
    import keyring
    from gmail_connector import exchange,KEY_SERVICE,KEY_NAME
    from starlette.responses import HTMLResponse
    state=request.query_params.get('state','');pending=gmail_pending.pop(state,None)
    if not pending or time.time()-pending['created']>600:return HTMLResponse('Sign-in expired or was not initiated here. Return to OfferLetter and try again.',status_code=400)
    code=request.query_params.get('code','')
    if not code or len(code)>4096:return HTMLResponse('Sign-in was not completed. You can close this window.',status_code=400)
    try:
        credentials=await asyncio.to_thread(exchange,pending,code)
        keyring.set_password(KEY_SERVICE,KEY_NAME,json.dumps(credentials))
    except Exception:return HTMLResponse('Could not complete sign-in or save credentials. Return to OfferLetter and try again.',status_code=502)
    event('gmail_connected','Gmail authorized');return HTMLResponse('Gmail connected. You can close this window and return to OfferLetter.')

async def gmail_disconnect(request):
    import keyring
    from gmail_connector import KEY_SERVICE,KEY_NAME
    try:
        if keyring.get_password(KEY_SERVICE,KEY_NAME):keyring.delete_password(KEY_SERVICE,KEY_NAME)
    except Exception:return JSONResponse({'error':'Could not remove local Gmail credentials.'},status_code=503)
    with db() as c:c.execute("INSERT INTO settings(key,value) VALUES ('gmail',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps({'codes':False,'links':False,'status_updates':False}),))
    event('gmail_disconnected','Local Gmail credentials removed')
    return JSONResponse({'ok':True,'notice':'Local credentials removed. Revoke access in your Google account to remove the Google authorization.'})

async def gmail_verification(request):
    import keyring
    from gmail_connector import KEY_SERVICE,KEY_NAME,allowed_domains,access_token,search_verification
    job_id=int(request.path_params['job_id']);page=pages.get(job_id);opened=page_opened_at.get(job_id)
    if not page or page.is_closed() or not opened:return JSONResponse({'error':'Open the application in Chrome first.'},status_code=409)
    with db() as c:
        job=c.execute('SELECT url FROM jobs WHERE id=?',(job_id,)).fetchone()
        settings=c.execute("SELECT value FROM settings WHERE key='gmail'").fetchone()
    flags=json.loads(settings['value']) if settings else {}
    if not flags.get('codes') and not flags.get('links'):return JSONResponse({'error':'Enable codes or verification links in Gmail settings.'},status_code=403)
    domains=allowed_domains(job['url']) if job else []
    if not domains:return JSONResponse({'error':'Cannot identify a trusted sender for this application.'},status_code=409)
    try:
        raw=keyring.get_password(KEY_SERVICE,KEY_NAME)
        if not raw:return JSONResponse({'error':'Connect Gmail first.'},status_code=409)
        token,updated=await asyncio.to_thread(access_token,json.loads(raw))
        if json.loads(raw)!=updated:keyring.set_password(KEY_SERVICE,KEY_NAME,json.dumps(updated))
        after=max(opened-60,int(time.time())-900)
        matches=await asyncio.to_thread(search_verification,token,domains,after,bool(flags.get('codes')),bool(flags.get('links')))
    except Exception:return JSONResponse({'error':'Could not check Gmail. Reconnect or try again.'},status_code=502)
    event('email_read',f'Job {job_id}: checked recent verification messages; {len(matches)} matches')
    return JSONResponse({'messages':matches,'notice':'Verify the sender and destination before using a code or link. Links are never opened automatically.'},headers={'Cache-Control':'no-store'})

app.router.routes.insert(-1,Route('/api/gmail/settings',gmail_settings,methods=['GET','POST']))
app.router.routes.insert(-1,Route('/api/gmail/connect',gmail_begin,methods=['POST']))
app.router.routes.insert(-1,Route('/api/gmail/callback',gmail_callback,methods=['GET']))
app.router.routes.insert(-1,Route('/api/gmail/disconnect',gmail_disconnect,methods=['POST']))
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/gmail-verification',gmail_verification,methods=['POST']))

async def gmail_status_scan(request):
    import keyring
    from datetime import datetime,timezone
    from gmail_connector import KEY_SERVICE,KEY_NAME,allowed_domains,access_token,search_status
    job_id=int(request.path_params['job_id'])
    with db() as c:
        job=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        settings=c.execute("SELECT value FROM settings WHERE key='gmail'").fetchone()
        approval=c.execute('SELECT approved_at FROM approvals WHERE job_id=?',(job_id,)).fetchone()
    if not settings or not json.loads(settings['value']).get('status_updates'):return JSONResponse({'error':'Enable Gmail status updates first.'},status_code=403)
    if not job or not approval:return JSONResponse({'error':'Status checks require a recorded application submission attempt.'},status_code=409)
    domains=allowed_domains(job['url'])
    if not domains or not job['title']:return JSONResponse({'error':'A known application domain and job title are required.'},status_code=409)
    try:
        raw=keyring.get_password(KEY_SERVICE,KEY_NAME)
        if not raw:return JSONResponse({'error':'Connect Gmail first.'},status_code=409)
        token,updated=await asyncio.to_thread(access_token,json.loads(raw))
        if json.loads(raw)!=updated:keyring.set_password(KEY_SERVICE,KEY_NAME,json.dumps(updated))
        after=int(datetime.strptime(approval['approved_at'],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp())
        results=await asyncio.to_thread(search_status,token,domains,after,job['title'])
    except Exception:return JSONResponse({'error':'Could not check Gmail. Reconnect or try again.'},status_code=502)
    if results:
        latest=results[-1]
        with db() as c:
            c.execute('CREATE TABLE IF NOT EXISTS email_status (job_id INTEGER PRIMARY KEY REFERENCES jobs(id),message_id TEXT NOT NULL,received_ms INTEGER NOT NULL)')
            previous=c.execute('SELECT received_ms FROM email_status WHERE job_id=?',(job_id,)).fetchone()
            if not previous or latest['received_ms']>previous['received_ms']:
                c.execute('UPDATE jobs SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(latest['status'],job_id))
                c.execute('INSERT INTO email_status(job_id,message_id,received_ms) VALUES (?,?,?) ON CONFLICT(job_id) DO UPDATE SET message_id=excluded.message_id,received_ms=excluded.received_ms',(job_id,latest['id'],latest['received_ms']))
                c.execute('INSERT INTO events(kind,detail) VALUES (?,?)',('status_from_email',f'Job {job_id}: marked {latest["status"]} from matching email'))
    event('email_read',f'Job {job_id}: checked application status messages; {len(results)} matches')
    return JSONResponse({'matches':results,'notice':'Check Gmail to verify the inferred status.'},headers={'Cache-Control':'no-store'})
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/gmail-status',gmail_status_scan,methods=['POST']))

async def gmail_status_monitor():
    """Periodically check only opted-in, previously attempted applications."""
    while True:
        await asyncio.sleep(900)
        try:
            with db() as c:
                try: settings=c.execute("SELECT value FROM settings WHERE key='gmail'").fetchone()
                except sqlite3.OperationalError: settings=None
                if not settings or not json.loads(settings['value']).get('status_updates'):continue
                ids=[row['id'] for row in c.execute("SELECT j.id FROM jobs j JOIN approvals a ON a.job_id=j.id WHERE j.status IN ('submitted','submission uncertain','interview','rejected') ORDER BY j.id")]
            for job_id in ids:
                with db() as c: current=c.execute("SELECT value FROM settings WHERE key='gmail'").fetchone()
                if not current or not json.loads(current['value']).get('status_updates'):break
                response=await gmail_status_scan(InternalRequest(job_id))
                if response.status_code in (403,502):break
                await asyncio.sleep(1)
        except asyncio.CancelledError:raise
        except Exception:event('gmail_monitor_error','Gmail status monitor failed')

account_staged={}
async def account_prepare(request):
    import keyring,re
    from account_workflow import SERVICE,account_host,credential_ref,generate_password,registration_form
    job_id=int(request.path_params['job_id']);data=await request.json();email=str(data.get('email','')).strip()
    if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):return JSONResponse({'error':'Enter a valid account email address.'},status_code=400)
    async with lock:
        page=pages.get(job_id)
        if not page or page.is_closed():return JSONResponse({'error':'Open the account-creation page in Chrome first.'},status_code=409)
        paused=await require_no_captcha(page,job_id)
        if paused:return paused
        try:host=account_host(page.url);form=await registration_form(page)
        except Exception:return JSONResponse({'error':'Open an HTTPS page with one recognizable account-creation form.'},status_code=409)
        ref=credential_ref(host,email)
        with db() as c:existing=c.execute('SELECT id,status FROM accounts WHERE domain=? AND email=? COLLATE NOCASE',(host,email)).fetchone()
        if existing:return JSONResponse({'error':'An account record already exists for this domain and email. Use its saved credential.'},status_code=409)
        try:
            if keyring.get_password(SERVICE,ref):return JSONResponse({'error':'A saved credential already exists for this domain and email.'},status_code=409)
        except Exception:return JSONResponse({'error':'System credential store is unavailable.'},status_code=503)
        if (await form['email'].input_value()).strip() not in ('',email):return JSONResponse({'error':'The form contains a different email address.'},status_code=409)
        for field in form['passwords']:
            if await field.input_value():return JSONResponse({'error':'Clear the password fields before generating a new credential.'},status_code=409)
        password=generate_password()
        try:
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                cur=c.execute('INSERT INTO accounts(domain,email,key_ref) VALUES (?,?,?)',(host,email,ref));account_id=cur.lastrowid
                keyring.set_password(SERVICE,ref,password)
        except Exception:
            try:
                with db() as c: saved=c.execute('SELECT id FROM accounts WHERE key_ref=?',(ref,)).fetchone()
                if not saved and keyring.get_password(SERVICE,ref)==password:keyring.delete_password(SERVICE,ref)
            except Exception:pass
            return JSONResponse({'error':'Could not save the account credential securely.'},status_code=503)
        account_staged[job_id]={'account_id':account_id,'url':page.url,'domain':host,'email':email,'ref':ref}
        try:
            await form['email'].fill(email)
            for field in form['passwords']:
                if page.url!=account_staged[job_id]['url']:raise ValueError('Page changed')
                await field.fill(password)
        except Exception:
            event('account_fill_failed',f'Job {job_id}: account fields could not be filled')
            return JSONResponse({'error':'Credential saved, but the form changed. Check Chrome and use the saved password if needed.'},status_code=409)
        event('account_staged',f'Job {job_id}: credential stored for {host}')
        return JSONResponse({'account_id':account_id,'domain':host,'notice':'Credential saved. Complete other required fields in Chrome, then choose Create account.'})

async def account_register(request):
    import keyring
    from account_workflow import SERVICE,account_host,registration_form
    job_id=int(request.path_params['job_id'])
    async with lock:
        page=pages.get(job_id);staged=account_staged.get(job_id)
        if not page or page.is_closed() or not staged or page.url!=staged['url']:return JSONResponse({'error':'Stage this account on the current page first.'},status_code=409)
        paused=await require_no_captcha(page,job_id)
        if paused:return paused
        try:
            if account_host(page.url)!=staged['domain']:raise ValueError()
            form=await registration_form(page)
            password=keyring.get_password(SERVICE,staged['ref'])
            if not password or (await form['email'].input_value()).strip()!=staged['email']:raise ValueError()
            for field in form['passwords']:
                if await field.input_value()!=password:raise ValueError()
            if not await form['form'].evaluate('e => e.checkValidity()'):return JSONResponse({'error':'Complete all required registration fields in Chrome.'},status_code=409)
        except Exception:return JSONResponse({'error':'Account form changed. Check Chrome before continuing.'},status_code=409)
        with db() as c:
            claimed=c.execute("UPDATE accounts SET status='attempted',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='staged'",(staged['account_id'],)).rowcount
            if not claimed:return JSONResponse({'error':'Account creation was already attempted.'},status_code=409)
            c.execute('INSERT INTO events(kind,detail) VALUES (?,?)',('account_creation_attempted',f'Job {job_id}: account creation attempted on {staged["domain"]}'))
        try:
            before=(await page.locator('body').inner_text(timeout=5000)).lower()
            await form['button'].click(timeout=10000);await page.wait_for_timeout(1000)
            body=(await page.locator('body').inner_text(timeout=5000)).lower()
            created=any(t in body and t not in before for t in ('account created successfully','your account has been created'))
            verify='check your email to verify your account' in body and 'check your email to verify your account' not in before
            status='verification pending' if verify else ('created' if created else 'uncertain')
        except Exception:status='uncertain'
        with db() as c:c.execute('UPDATE accounts SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,staged['account_id']))
        event('account_creation_result',f'Job {job_id}: account creation {status}')
        return JSONResponse({'status':status,'notice':'Check Chrome and complete any email verification. OfferLetter will not retry automatically.'})

async def accounts_list(request):
    with db() as c:rows=c.execute('SELECT id,domain,email,status,created_at FROM accounts ORDER BY id DESC').fetchall()
    return JSONResponse([dict(row) for row in rows],headers={'Cache-Control':'no-store'})

async def account_reveal(request):
    import keyring
    from account_workflow import SERVICE
    account_id=int(request.path_params['account_id'])
    with db() as c:account=c.execute('SELECT key_ref FROM accounts WHERE id=?',(account_id,)).fetchone()
    if not account:return JSONResponse({'error':'Account not found.'},status_code=404)
    try:password=keyring.get_password(SERVICE,account['key_ref'])
    except Exception:return JSONResponse({'error':'System credential store is unavailable.'},status_code=503)
    if not password:return JSONResponse({'error':'Credential not found.'},status_code=404)
    event('account_credential_viewed',f'Account {account_id}: credential viewed')
    return JSONResponse({'password':password},headers={'Cache-Control':'no-store'})
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/account/prepare',account_prepare,methods=['POST']))
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/account/register',account_register,methods=['POST']))
app.router.routes.insert(-1,Route('/api/accounts',accounts_list,methods=['GET']))
app.router.routes.insert(-1,Route('/api/accounts/{account_id:int}/reveal',account_reveal,methods=['POST']))

async def account_sign_in(request):
    import keyring
    from account_workflow import SERVICE,account_host,login_form
    job_id=int(request.path_params['job_id']);data=await request.json()
    try:account_id=int(data.get('account_id'))
    except (ValueError,TypeError):return JSONResponse({'error':'Choose a saved account.'},status_code=400)
    async with lock:
        page=pages.get(job_id)
        if not page or page.is_closed():return JSONResponse({'error':'Open the sign-in page in Chrome first.'},status_code=409)
        paused=await require_no_captcha(page,job_id)
        if paused:return paused
        with db() as c:account=c.execute('SELECT * FROM accounts WHERE id=?',(account_id,)).fetchone()
        if not account:return JSONResponse({'error':'Account not found.'},status_code=404)
        try:
            if account_host(page.url)!=account['domain']:return JSONResponse({'error':'The sign-in domain does not match the saved account.'},status_code=409)
            form=await login_form(page);password=keyring.get_password(SERVICE,account['key_ref'])
            if not password:return JSONResponse({'error':'Saved credential is unavailable.'},status_code=409)
            existing=(await form['email'].input_value()).strip()
            if existing and existing.casefold()!=account['email'].casefold():return JSONResponse({'error':'The form contains a different email address.'},status_code=409)
            if await form['password'].input_value():return JSONResponse({'error':'Clear the password field before using the saved credential.'},status_code=409)
            sign_in_url=page.url
            await form['email'].fill(account['email'])
            if page.url!=sign_in_url:raise ValueError('Page changed')
            await form['password'].fill(password)
            if not await form['form'].evaluate('e => e.checkValidity()'):return JSONResponse({'error':'Complete the remaining sign-in fields in Chrome.'},status_code=409)
            event('account_signin_attempted',f'Job {job_id}: sign-in attempted on {account["domain"]}')
            await form['button'].click(timeout=10000)
        except Exception:return JSONResponse({'error':'Sign-in could not be completed. Check Chrome; it will not be retried automatically.'},status_code=409)
        return JSONResponse({'status':'attempted','notice':'Check Chrome and complete any verification or CAPTCHA.'})
app.router.routes.insert(-1,Route('/api/jobs/{job_id:int}/account/sign-in',account_sign_in,methods=['POST']))

async def embedding_settings(request):
    from semantic_memory import endpoint
    if request.method=='GET':
        with db() as c:row=c.execute("SELECT value FROM settings WHERE key='embeddings'").fetchone()
        return JSONResponse(json.loads(row['value']) if row else {'enabled':False,'base_url':'http://127.0.0.1:11434/v1','model':'nomic-embed-text'})
    data=await request.json();model=str(data.get('model','')).strip();base=str(data.get('base_url','')).strip();enabled=data.get('enabled') is True
    if enabled and (not model or len(model)>200):return JSONResponse({'error':'Enter a local embedding model name.'},status_code=400)
    try:endpoint(base)
    except ValueError as exc:return JSONResponse({'error':str(exc)},status_code=400)
    settings={'enabled':enabled,'model':model,'base_url':base}
    with db() as c:c.execute("INSERT INTO settings(key,value) VALUES('embeddings',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(settings),))
    event('embedding_settings','Local answer matching settings updated')
    return JSONResponse(settings)
app.router.routes.insert(-1,Route('/api/settings/embeddings',embedding_settings,methods=['GET','POST']))

# --- Metrics and read-only chat (FRD success metrics, bonus FR12) ---
async def metrics_endpoint(request):
    import metrics
    with db() as c: return JSONResponse(metrics.compute(c))
async def chat_endpoint(request):
    import chat
    payload=await request.json(); message=payload.get('message')
    if not isinstance(message,str) or not message.strip() or len(message)>500: return JSONResponse({'error':'Enter a short question.'},status_code=400)
    with db() as c: result=chat.answer(c,message)
    if result['action']=='pause':
        with db() as c:
            if not c.execute("UPDATE runs SET status='pausing' WHERE status='running'").rowcount: result['reply']='No run is active.'
        event('chat_pause','Run pause requested from chat')
    return JSONResponse({'reply':result['reply']})
app.router.routes.insert(-1,Route('/api/metrics',metrics_endpoint,methods=['GET']))
app.router.routes.insert(-1,Route('/api/chat',chat_endpoint,methods=['POST']))

# --- Tracker table (FRD FR8) ---
async def tracker_endpoint(request):
    import tracker
    with db() as c: return JSONResponse(tracker.rows(c))
app.router.routes.insert(-1,Route('/api/tracker',tracker_endpoint,methods=['GET']))

async def discover_jobspy(request):
    from jobspy_discovery import SITES,search_site
    setup=discovery_setup_error()
    if setup:return setup
    data=await request.json();query=str(data.get('query','')).strip();location=str(data.get('location','')).strip();sites=data.get('sites',list(SITES))
    from discovery_preferences import contains,terms
    preferences=discovery_preferences()
    if query and not any(contains(query,title) for title in terms(preferences.get('titles'))):
        return JSONResponse({'error':'Search for one of your saved target job titles, or update Search rules first.'},status_code=400)
    try:
        limit=int(data.get('limit',20));hours=int(data['hours_old']) if data.get('hours_old') not in (None,'') else None
        if not query or len(query)>200 or len(location)>200 or not 1<=limit<=100 or (hours is not None and not 1<=hours<=87600):raise ValueError()
        if not isinstance(sites,list) or not sites or any(site not in SITES for site in sites):raise ValueError()
    except (TypeError,ValueError):return JSONResponse({'error':'Enter a search, valid sources, and a result limit from 1 to 100.'},status_code=400)
    sites=list(dict.fromkeys(sites));fetch_description=data.get('fetch_description') is True
    async def one(site):
        try:
            response=await asyncio.wait_for(asyncio.to_thread(search_site,site,query,location,limit,hours,fetch_description),timeout=90)
            added=store_discovered(response['jobs'])
            return {'source':site,'found':len(response['jobs']),'added':added,'error':response['error'],'warnings':response['warnings']}
        except asyncio.TimeoutError:return {'source':site,'found':0,'added':0,'error':'Source timed out; try again later.'}
        except Exception:return {'source':site,'found':0,'added':0,'error':'Source unavailable; try again later.'}
    results=await asyncio.gather(*(one(site) for site in sites))
    event('jobspy_discovery','JobSpy search completed across '+str(len(results))+' sources')
    return JSONResponse({'sources':results})
app.router.routes.insert(-1,Route('/api/discover/jobspy',discover_jobspy,methods=['POST']))


async def onboarding_endpoint(request):
    """First-run setup state. Existing installs with a profile email and a resume count as set up."""
    if request.method=='POST':
        done=(await request.json()).get('done') is True
        with db() as c:
            c.execute("INSERT INTO settings(key,value) VALUES ('onboarded',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(done),))
        event('onboarding_updated','Setup completed' if done else 'Setup restarted')
        return JSONResponse({'done':done})
    with db() as c:
        row=c.execute("SELECT value FROM settings WHERE key='onboarded'").fetchone()
        if row: return JSONResponse({'done':json.loads(row['value']) is True})
        profile=c.execute('SELECT data FROM profile WHERE id=1').fetchone()
        has_resume=c.execute('SELECT 1 FROM resumes LIMIT 1').fetchone() is not None
    email=(json.loads(profile['data']).get('email','') if profile else '').strip()
    return JSONResponse({'done':bool(email and has_resume)})
app.router.routes.insert(-1,Route('/api/onboarding',onboarding_endpoint,methods=['GET','POST']))

# --- One button: search every working source, sort against the user's preferences, then prepare the clear matches ---
SEARCH_SITES=('linkedin','indeed')  # Google, Glassdoor and ZipRecruiter currently return nothing or block JobSpy requests.
async def search_all_sources(rules,progress,started=lambda n:None):
    from jobspy_discovery import search_site
    from discovery import fetch_board
    from simplify import fetch_list
    from discovery_preferences import terms,location_terms,repository_allowed
    titles=terms(rules.get('titles'))[:3]
    place=next(iter(location_terms(rules.get('locations'))),('',''))
    location=', '.join(x for x in (place[0],place[1].upper()) if x)
    try:hours=int(rules.get('max_age_days') or 0)*24 or None
    except (TypeError,ValueError):hours=None
    jobs=[]
    for title in titles:
        for site in SEARCH_SITES:
            # LinkedIn leaves descriptions out unless asked; a fit check needs them.
            jobs.append((site.capitalize()+': '+title,lambda site=site,title=title:search_site(site,title,location,25,hours,site=='linkedin'),240 if site=='linkedin' else 120))
    stage={'internship':'internships','new_grad':'new_grad'}.get(rules.get('career_stage'))
    if stage and repository_allowed(stage,rules):jobs.append(('Simplify '+stage.replace('_',' ')+' list',lambda stage=stage:{'jobs':fetch_list(stage),'error':None},120))
    with db() as c:row=c.execute('SELECT boards FROM schedule WHERE id=1').fetchone()
    for board in (json.loads(row['boards']) if row else []):
        if board.get('provider') in ('greenhouse','lever','ashby'):
            jobs.append((board['provider'].capitalize()+': '+board['board'],lambda b=board:{'jobs':fetch_board(b['provider'],b['board']),'error':None},90))
    async def one(name,call,timeout):
        try:
            result=await asyncio.wait_for(asyncio.to_thread(call),timeout=timeout)
            counts={};added=store_discovered(result['jobs'],counts,screen=True)
            return {'source':name,'found':len(result['jobs']),'added':added,'clear':counts.get('clear',0),'gray':counts.get('gray',0),'error':result.get('error')}
        except asyncio.TimeoutError:return {'source':name,'found':0,'added':0,'error':'Timed out'}
        except Exception:return {'source':name,'found':0,'added':0,'error':'Unavailable right now'}
        finally:progress()
    started(len(jobs))
    return await asyncio.gather(*(one(*j) for j in jobs)),len(jobs)

def screen_parallel(rules,config):
    try:n=int(rules.get('screen_parallel') or 0)
    except (TypeError,ValueError):n=0
    return min(16,max(1,n or (2 if config.get('provider')=='local' else 6)))

async def screening_worker(run_id,summary,save):
    """One model call per remotely related job: read the description (in Chrome when missing), then apply, close match or skip."""
    import keyring
    from model_client import screen
    from matching import rank
    with db() as c:
        resumes=[dict(r) for r in c.execute('SELECT id,name,titles,extracted_text FROM resumes')]
        try:config=c.execute("SELECT value FROM settings WHERE key='model'").fetchone()
        except sqlite3.OperationalError:config=None
    rules=discovery_preferences()
    if not config or not resumes:return 'Add a resume and configure a model first.'
    cfg=json.loads(config['value'])
    key=keyring.get_password('OfferLetter','model:'+cfg['provider']) if cfg['provider']!='local' else ''
    from ats_navigation import on_job_board
    with db() as c:todo=[dict(r) for r in c.execute("SELECT * FROM jobs WHERE status='screening' ORDER BY id")]
    todo.sort(key=lambda j:bool(on_job_board(j['url']) and not j['apply_url']))  # employer links first: those can actually be filled
    summary.update(screen_total=len(todo),screened=0,screen_apply=0,screen_close=0,screen_skip=0)
    failures={'n':0};slots=asyncio.Semaphore(screen_parallel(rules,cfg))
    async def one(job):
        async with slots:
            if run_is_pausing(run_id) or failures['n']>=5:return
            if not job['description']:
                text=await read_posting(job['url'])
                if text:
                    job['description']=text
                    with db() as c:c.execute('UPDATE jobs SET description=? WHERE id=?',(text,job['id']))
            resume=rank(job,resumes)[0] if job['description'] else resumes[0]
            seeker={'titles':rules.get('titles',''),'career_stage':rules.get('career_stage',''),'resume':resume.get('extracted_text') or ''}
            try:
                verdict=await asyncio.wait_for(asyncio.to_thread(screen,cfg,key,job,seeker),timeout=180)
                failures['n']=0
            except Exception:
                failures['n']+=1
                verdict={'decision':'close','reason':'The model could not screen this one'}
            where=job['match_note']  # a location note from the rules, such as a nearby city
            reason=verdict['reason'] or ''
            if not job['description'] and verdict['decision']=='apply':verdict['decision']='close';reason=(reason+'; ' if reason else '')+'judged from the title only'
            if verdict['decision']=='apply' and not where:status,note='found',''
            elif verdict['decision']=='skip':status,note='skipped','Not a match: '+reason if reason else 'Not a match'
            else:status,note='check match','; '.join(x for x in (where,reason) if x)
            with db() as c:c.execute("UPDATE jobs SET status=?,match_note=? WHERE id=? AND status='screening'",(status,note[:300],job['id']))
            summary['screened']+=1;summary['screen_'+{'found':'apply','check match':'close','skipped':'skip'}[status]]+=1
            save()
    await asyncio.gather(*(one(j) for j in todo))
    if failures['n']>=5:return 'The model stopped answering; check model settings.'
    return ''

async def find_and_apply_worker(run_id):
    summary={'phase':'searching','sources_done':0,'sources_total':0,'found':0,'clear':0,'gray':0,'reason':'Searching job sites'}
    def save():
        with db() as c:c.execute("UPDATE runs SET summary=? WHERE id=? AND status IN ('running','pausing')",(json.dumps(summary),run_id))
    def progress():summary['sources_done']+=1;save()
    def started(n):summary['sources_total']=n;save()
    try:
        rules=discovery_preferences()
        # Jobs found by earlier runs but never filled get the same screening; jobs added by hand or approved by the user keep their place.
        with db() as c:c.execute("UPDATE jobs SET status='screening' WHERE status='found' AND source NOT IN ('direct','')")
        results,total=await search_all_sources(rules,progress,started)
        summary.update(sources_total=total,found=sum(r['found'] for r in results),clear=sum(r.get('clear',0) for r in results),gray=sum(r.get('gray',0) for r in results),
                       sources=[{k:r[k] for k in ('source','found','added','error')} for r in results])
        event('find_and_apply',f"Search found {summary['found']}: {summary['clear']} clear, {summary['gray']} to check")
        if run_is_pausing(run_id):
            summary['reason']='Paused by user.'
            with db() as c:c.execute("UPDATE runs SET status='paused',summary=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",(json.dumps(summary),run_id))
            return
        # Screen and fill at the same time: clear jobs start filling while the rest are still being judged.
        screening=asyncio.create_task(screening_worker(run_id,summary,save))
        await preparation_worker(run_id,summary,more=lambda:not screening.done())
        problem=await screening
        if problem:
            with db() as c:
                row=c.execute('SELECT summary FROM runs WHERE id=?',(run_id,)).fetchone()
                final={**json.loads(row['summary'] or '{}'),'reason':problem}
                c.execute("UPDATE runs SET status='waiting',summary=? WHERE id=? AND status IN ('completed','running')",(json.dumps(final),run_id))
    except asyncio.CancelledError:raise
    except Exception:
        event('run_error',f'Find and apply run {run_id} failed')
        with db() as c:c.execute("UPDATE runs SET status='failed',summary=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",(json.dumps({**summary,'reason':'Unexpected error; check Activity in Settings.'}),run_id))

async def find_and_apply(request):
    global preparation_task
    setup=discovery_setup_error()
    if setup:return setup
    async with preparation_start_lock:
        if preparation_task and not preparation_task.done():return JSONResponse({'error':'OfferLetter is already working. Pause it first.'},status_code=409)
        with db() as c:run_id=c.execute("INSERT INTO runs(status,summary) VALUES ('running',?)",(json.dumps({'phase':'searching','reason':'Searching job sites'}),)).lastrowid
        preparation_task=asyncio.create_task(find_and_apply_worker(run_id))
    event('run_started',f'Find and apply run {run_id} started')
    return JSONResponse({'id':run_id,'status':'running'},status_code=202)
app.router.routes.insert(-1,Route('/api/find-and-apply',find_and_apply,methods=['POST']))

# --- Home assistant chat ---
async def assistant_endpoint(request):
    import keyring, assistant, chat
    from model_client import converse
    with db() as c:c.execute('CREATE TABLE IF NOT EXISTS assistant_messages (id INTEGER PRIMARY KEY, role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    if request.method=='DELETE':
        with db() as c:c.execute('DELETE FROM assistant_messages')
        return JSONResponse({'ok':True})
    if request.method=='GET':
        with db() as c:rows=[dict(r) for r in c.execute('SELECT role,text,created_at FROM (SELECT * FROM assistant_messages ORDER BY id DESC LIMIT 60) ORDER BY id')]
        return JSONResponse(rows)
    message=(await request.json()).get('message')
    if not isinstance(message,str) or not message.strip() or len(message)>2000:return JSONResponse({'error':'Type a question (up to 2000 characters).'},status_code=400)
    message=message.strip();source='model'
    with db() as c:history=[dict(r) for r in c.execute('SELECT role,text FROM (SELECT * FROM assistant_messages ORDER BY id DESC LIMIT 8) ORDER BY id')]
    while history and history[0]['role']!='user':history.pop(0)
    if assistant.wants_pause(message):
        with db() as c:paused=c.execute("UPDATE runs SET status='pausing' WHERE status='running'").rowcount
        reply='Pausing after the current step.' if paused else 'Nothing is running right now.';source='action'
        if paused:event('chat_pause','Run pause requested from the assistant')
    else:
        with db() as c:
            try:config=c.execute("SELECT value FROM settings WHERE key='model'").fetchone()
            except sqlite3.OperationalError:config=None
            open_tabs=sum(1 for p in pages.values() if not p.is_closed())
            state=assistant.snapshot(c,open_tabs)
        reply=None
        if config:
            cfg=json.loads(config['value'])
            try:
                key=keyring.get_password('OfferLetter','model:'+cfg['provider']) if cfg['provider']!='local' else ''
                if cfg['provider']=='local' or key:reply=await asyncio.to_thread(converse,cfg,key,assistant.SYSTEM,assistant.build_messages(history,state,message))
            except Exception:reply=None
        if not reply:
            with db() as c:reply=chat.answer(c,message)['reply']
            reply=('The AI model is not reachable, so here is a basic answer. '+reply) if config else ('Set up an AI model in Settings for full answers. '+reply)
            source='basic'
    with db() as c:
        c.execute('INSERT INTO assistant_messages(role,text) VALUES (?,?)',('user',message))
        c.execute('INSERT INTO assistant_messages(role,text) VALUES (?,?)',('assistant',reply[:8000]))
    return JSONResponse({'reply':reply[:8000],'source':source})
app.router.routes.insert(-1,Route('/api/assistant',assistant_endpoint,methods=['GET','POST','DELETE']))
