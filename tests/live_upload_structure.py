import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='chrome',headless=True);page=await b.new_page();await page.goto('https://job-boards.greenhouse.io/figma/jobs/5426468004',wait_until='domcontentloaded',timeout=30000);await page.wait_for_timeout(1500)
  for i in range(await page.locator('input[type=file]').count()):
   e=page.locator('input[type=file]').nth(i);print('FILE',await e.evaluate("e=>e.closest('fieldset, .file-upload, [class*=upload], [class*=field]')?.outerHTML.slice(0,3500) || e.parentElement.parentElement.outerHTML.slice(0,3500)"))
  print('SUBMIT',await page.locator('button[type=submit],input[type=submit]').evaluate_all('es=>es.map(e=>e.outerHTML)'))
  await b.close()
asyncio.run(main())
