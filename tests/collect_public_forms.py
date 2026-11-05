import asyncio,json
from playwright.async_api import async_playwright
from discovery import fetch_board
from ats_navigation import follow_application_link
from form_engine import inspect
async def main():
 boards=[('greenhouse','figma',2),('lever','levelai',2),('ashby','notion',1)];forms=[]
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='chrome',headless=True)
  for source,slug,count in boards:
   jobs=await asyncio.to_thread(fetch_board,source,slug)
   for job in jobs[:count]:
    page=await b.new_page()
    try:
     await page.goto(job['url'],wait_until='domcontentloaded',timeout=30000);await page.wait_for_timeout(1000)
     if source in ('lever','ashby'):await follow_application_link(page);await page.wait_for_timeout(1000)
     fields=await inspect(page,{},False)
     clean=[{'label':f.get('label',''),'type':f.get('type',''),'required':f.get('required',False)} for f in fields if f.get('label')]
     forms.append({'source':source,'url':page.url,'fields':clean});print(source,len(clean))
    except Exception as e:print(source,'error',type(e).__name__)
    await page.close()
  await b.close()
 with open('tests/fixtures/public_forms.json','w',encoding='utf-8') as out:json.dump(forms,out,ensure_ascii=False,indent=2)
asyncio.run(main())
