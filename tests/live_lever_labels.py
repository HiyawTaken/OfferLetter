import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(channel='chrome',headless=True);pg=await b.new_page();await pg.goto('https://jobs.lever.co/levelai/c55479cf-bc3e-471b-9ed7-ac213b0ee8b5/apply',wait_until='domcontentloaded');await pg.wait_for_timeout(1000)
  for el in await pg.locator('input[type=text],input[type=email],input[type=tel]').all():
   print(await el.evaluate("e=>({id:e.id,name:e.name,placeholder:e.placeholder,outer:e.outerHTML.slice(0,550),label:e.labels?.[0]?.outerHTML.slice(0,1000)})"))
  await b.close()
asyncio.run(main())
