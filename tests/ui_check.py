import asyncio,os,pathlib,subprocess,sys,time,urllib.request
root=pathlib.Path(__file__).resolve().parents[1]
env=os.environ.copy();env['OFFERLETTER_DATA']=str(root/('test-ui-'+str(os.getpid())))
proc=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port','18772'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
try:
 for _ in range(50):
  try:urllib.request.urlopen('http://127.0.0.1:18772/api/session',timeout=1);break
  except Exception:time.sleep(.2)
 else:raise RuntimeError('Server did not start')
 from playwright.async_api import async_playwright
 async def run():
  async with async_playwright() as p:
   browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox']);page=await browser.new_page();errors=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto('http://127.0.0.1:18772/',wait_until='networkidle')
   await page.evaluate('''() => { const panel=renderReview({fields:[{label:'Will you need sponsorship?',value:'No',required:true,high_stakes:true},{label:'First name',value:'Ada',required:true}],previous_pages:[]});document.body.append(panel); }''')
   assert await page.locator('tr.high-stakes').count()==1
   assert 'No' in await page.locator('tr.high-stakes').inner_text()
   await page.evaluate('''() => { const editor=experienceEditor([]);document.body.append(editor);window.demoEditor=editor; }''')
   await page.get_by_role('button',name='Add work experience',exact=True).click()
   card=page.locator('.experience-entry').first
   await card.locator('[name=employer]').fill('Example Company')
   await card.locator('[name=title]').fill('Intern')
   await card.locator('[name=start_date]').fill('2025-01')
   await card.locator('[name=end_date]').fill('2025-06')
   await card.locator('[name=description]').fill('Built data pipelines')
   await card.locator('[name=currently_working]').check()
   assert await card.locator('[name=end_date]').is_disabled()
   assert (await page.evaluate('demoEditor.read()'))[0]['description']=='Built data pipelines'
   await page.get_by_role('button',name='Add work experience',exact=True).click()
   assert await page.locator('.experience-entry').count()==2
   await page.locator('.experience-entry').last.get_by_role('button',name='Remove this job').click()
   assert await page.locator('.experience-entry').count()==1
   await page.goto('http://127.0.0.1:18772/#/welcome/4',wait_until='networkidle')
   await page.reload(wait_until='networkidle')
   await page.get_by_role('heading',name='Work experience',exact=True).wait_for()
   assert await page.locator('[name=years_experience]').count()==0
   assert not errors,errors
   await browser.close();print('Review highlights high-stakes answers in the interface')
 asyncio.run(run())
finally:proc.terminate();proc.wait(timeout=10)
