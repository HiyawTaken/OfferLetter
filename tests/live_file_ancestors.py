import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='chrome',headless=True);page=await b.new_page();await page.goto('https://job-boards.greenhouse.io/figma/jobs/5426468004',wait_until='domcontentloaded',timeout=30000);await page.wait_for_timeout(1200)
  e=page.locator('input[type=file]').first
  print(await e.evaluate("e=>{let a=e;return Array.from({length:6},(_,i)=>{let x=a;a=a?.parentElement;return {i,tag:x?.tagName,cls:x?.className,text:x?.innerText?.slice(0,350)}})}"))
  await b.close()
asyncio.run(main())
