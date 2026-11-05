import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='chrome',headless=True);page=await b.new_page();await page.goto('https://job-boards.greenhouse.io/figma/jobs/5426468004',wait_until='domcontentloaded',timeout=30000);await page.wait_for_timeout(1800)
  controls=page.locator('input,textarea,select')
  for i in range(await controls.count()):
   el=controls.nth(i)
   if not await el.is_visible():continue
   info=await el.evaluate('''e=>({tag:e.tagName,type:e.type,id:e.id,name:e.name,role:e.getAttribute('role'),aria:e.getAttribute('aria-label'),required:e.required,ariaRequired:e.getAttribute('aria-required'),outer:e.outerHTML.slice(0,550),parent:e.parentElement?.parentElement?.outerHTML.slice(0,1100)})''')
   print(str(info)[:1450])
  await b.close()
asyncio.run(main())
