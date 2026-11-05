import asyncio
from playwright.async_api import async_playwright
from form_engine import inspect,captcha_present
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True)
  page=await browser.new_page();await page.goto('https://boards.greenhouse.io/figma/jobs/5426468004?gh_jid=5426468004',wait_until='domcontentloaded',timeout=30000)
  await page.wait_for_timeout(2500)
  fields=await inspect(page,{},False)
  print('URL:',page.url,'frames:',len(page.frames),'captcha:',await captcha_present(page),'visible fields:',len(fields))
  for f in fields[:35]:print(f.get('type'),repr(f.get('label')), 'required=',f.get('required'),'options=',len(f.get('options',[])))
  print('file_inputs=',await page.locator('input[type=file]').count(),'submit controls=',await page.locator('button[type=submit],input[type=submit]').count())
  await browser.close()
asyncio.run(main())
