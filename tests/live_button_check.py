import asyncio
from playwright.async_api import async_playwright
from form_engine import final_submit_controls
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True);page=await browser.new_page()
  urls=['https://job-boards.greenhouse.io/figma/jobs/5426468004','https://jobs.lever.co/levelai/c55479cf-bc3e-471b-9ed7-ac213b0ee8b5/apply','https://jobs.ashbyhq.com/notion/1fc309c8-da20-4ff2-84c7-8b863ece2b0a/application']
  for url in urls:
   await page.goto(url,wait_until='domcontentloaded',timeout=30000);await page.wait_for_timeout(1000)
   buttons=await final_submit_controls(page);print(page.url,'recognized',len(buttons),[x[1]['label'] for x in buttons])
  await browser.close()
asyncio.run(main())
