import asyncio,json,uuid
from pathlib import Path
from unittest.mock import patch
from playwright.async_api import async_playwright
import app
from form_engine import inspect
class RevealRequest:
 def __init__(self,aid):self.path_params={'account_id':aid}
async def main():
 isolated=Path('test-data')/('accounts-'+uuid.uuid4().hex+'.db');secrets={}
 def get(service,key):return secrets.get((service,key))
 def set_password(service,key,password):secrets[(service,key)]=password
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox']);page=await browser.new_page()
  html='''<form onsubmit="event.preventDefault(); document.body.textContent='Account created successfully';"><label>Email<input type="email" required></label><label>Password<input type="password" required></label><label>Confirm password<input type="password" required></label><label>Accept terms<input id="terms" type="checkbox" required></label><button type="submit">Create account</button></form>'''
  await page.route('https://accounts.example.test/**',lambda route:route.fulfill(status=200,body=html,content_type='text/html'))
  await page.goto('https://accounts.example.test/register')
  with patch.object(app,'DB',isolated),patch.dict(app.pages,{1:page}),patch('keyring.get_password',side_effect=get),patch('keyring.set_password',side_effect=set_password):
   app.initialize()
   with app.db() as c:c.execute("INSERT INTO jobs(id,url,title) VALUES (1,'https://accounts.example.test/job','Test')")
   staged=await app.account_prepare(app.InternalRequest(1,{'email':'ada@example.test'}));assert staged.status_code==200,staged.body
   aid=json.loads(staged.body)['account_id'];password=next(iter(secrets.values()));assert len(password)>=20
   assert await page.locator('input[type=password]').first.input_value()==password
   fields=await inspect(page,{},False);assert password not in str(fields)
   denied=await app.account_register(app.InternalRequest(1));assert denied.status_code==409,denied.body
   await page.locator('#terms').check()
   created=await app.account_register(app.InternalRequest(1));assert created.status_code==200,created.body
   assert json.loads(created.body)['status']=='created',created.body
   repeat=await app.account_register(app.InternalRequest(1));assert repeat.status_code==409
   reveal=await app.account_reveal(RevealRequest(aid));assert json.loads(reveal.body)['password']==password
   await page.set_content('''<form onsubmit="event.preventDefault();document.body.textContent='Signed in';"><input type="email" required><input type="password" required><button type="submit">Sign in</button></form>''')
   signin=await app.account_sign_in(app.InternalRequest(1,{'account_id':aid}));assert signin.status_code==200,signin.body
   assert await page.locator('body').inner_text()=='Signed in'
   await page.route('https://other.example.test/**',lambda route:route.fulfill(status=200,body='<form><input type="email"><input type="password"><button>Sign in</button></form>',content_type='text/html'))
   await page.goto('https://other.example.test/login')
   mismatch=await app.account_sign_in(app.InternalRequest(1,{'account_id':aid}));assert mismatch.status_code==409
   with app.db() as c:dump='\n'.join(c.iterdump())
   assert password not in dump
  await browser.close()
 print('Account staging, required-field gate, sign-in domain check and credential privacy passed')
asyncio.run(main())
