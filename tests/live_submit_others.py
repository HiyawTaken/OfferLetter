import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='chrome',headless=True);page=await b.new_page()
  for url in ['https://jobs.lever.co/levelai/c55479cf-bc3e-471b-9ed7-ac213b0ee8b5/apply','https://jobs.ashbyhq.com/notion/1fc309c8-da20-4ff2-84c7-8b863ece2b0a/application']:
   await page.goto(url,wait_until='domcontentloaded');await page.wait_for_timeout(1500);print('PAGE',page.url)
   buttons=page.get_by_role('button')
   for i in range(await buttons.count()):
    e=buttons.nth(i)
    if await e.is_visible():
     t=(await e.inner_text()).strip()
     if any(k in t.lower() for k in ('submit','apply','send')):print(repr(t),(await e.evaluate('e=>e.outerHTML'))[:700])
  await b.close()
asyncio.run(main())
