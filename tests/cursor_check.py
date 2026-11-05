import asyncio, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for d in ('.deps',):
    p = Path(__file__).resolve().parent.parent / d
    if p.is_dir(): sys.path.insert(0, str(p))
from playwright.async_api import async_playwright
from form_engine import install_cursor, inspect

async def main():
    async with async_playwright() as pw:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = await pw.chromium.launch_persistent_context(tmp, channel='chrome', headless=False)
            try:
                await install_cursor(ctx)
                page = await ctx.new_page()
                await page.goto('data:text/html,<form><label>First name<input name=f></label><label>Email<input name=e type=email></label></form>')
                fields = await inspect(page, {'first_name': 'Ada', 'email': 'ada@example.com'}, True)
                assert all(f.get('filled') for f in fields), fields
                pos = await page.evaluate("(()=>{const d=document.getElementById('__ol_cursor');return d?[parseFloat(d.style.left),parseFloat(d.style.top)]:null})()")
                assert pos and pos[0] > 0 and pos[1] > 0, pos
                print('Visible cursor present and moved to', pos)
            finally:
                await ctx.close()
asyncio.run(main())
