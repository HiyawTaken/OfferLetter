import asyncio
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from discovery import fetch_board
from form_engine import inspect,captcha_present
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True)
  for source,slug in [('lever','levelai'),('ashby','notion')]:
   jobs=await asyncio.to_thread(fetch_board,source,slug);page=await browser.new_page()
   try:
    await page.goto(jobs[0]['url'],wait_until='domcontentloaded',timeout=30000);await page.wait_for_timeout(1000)
    links=page.get_by_role('link',name='Apply',exact=False);href=await links.first.get_attribute('href') if await links.count() else ''
    print(source,'apply href:',href)
    if href and (href.startswith('/') or href.startswith('https://jobs.'+source+'hq.com/') or href.startswith('https://jobs.lever.co/')):
     await page.goto(urljoin(page.url,href),wait_until='domcontentloaded',timeout=30000);await page.wait_for_timeout(1500)
     fields=await inspect(page,{},False);print(source,'application page',page.url,'fields',len(fields),'captcha',await captcha_present(page))
     for f in fields[:15]:print(' ',f.get('type'),repr(f.get('label')),'required',f.get('required'))
   except Exception as e:print(source,'error:',type(e).__name__)
   await page.close()
  await browser.close()
asyncio.run(main())

