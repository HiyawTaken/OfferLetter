import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='chrome',headless=True);page=await b.new_page()
  for url in ['https://jobs.lever.co/levelai/c55479cf-bc3e-471b-9ed7-ac213b0ee8b5/apply','https://jobs.ashbyhq.com/notion/1fc309c8-da20-4ff2-84c7-8b863ece2b0a/application']:
   await page.goto(url,wait_until='domcontentloaded');await page.wait_for_timeout(1200); print('PAGE',page.url)
   for i in range(await page.locator('input[type=file]').count()):
    e=page.locator('input[type=file]').nth(i); print(await e.evaluate("e=>({input:e.outerHTML,near:e.parentElement?.parentElement?.outerHTML.slice(0,1300)})"))
   print('submit',await page.locator('button[type=submit],input[type=submit]').evaluate_all('es=>es.map(x=>x.outerHTML.slice(0,500))'))
  await b.close()
asyncio.run(main())
