import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='chrome',headless=True);pg=await b.new_page();await pg.goto('https://job-boards.greenhouse.io/figma/jobs/5426468004',wait_until='domcontentloaded');await pg.wait_for_timeout(1000)
  print((await pg.locator('input[type=file]').first.evaluate("e=>e.closest('.file-upload').outerHTML"))[:1800]);await b.close()
asyncio.run(main())
