import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='chrome',headless=True);pg=await b.new_page();await pg.goto('https://jobs.ashbyhq.com/notion/1fc309c8-da20-4ff2-84c7-8b863ece2b0a/application',wait_until='domcontentloaded');await pg.wait_for_timeout(1000)
  e=pg.locator('input[type=radio]').first
  print(await e.evaluate("e=>{let a=e;return Array.from({length:6},(_,i)=>{let x=a;a=a?.parentElement;return {i,tag:x?.tagName,cls:x?.className,role:x?.getAttribute('role'),text:x?.innerText?.slice(0,250)}})}"));await b.close()
asyncio.run(main())
