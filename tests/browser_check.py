import asyncio
from playwright.async_api import async_playwright
from form_engine import inspect, captcha_present,final_submit_controls
from answer_memory import fill_field
from ats_navigation import follow_application_link
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox'])
  page=await browser.new_page()
  await page.set_content('''<form><label>First name <input name="first" required></label><label>Email <input type="email"></label><label>Are you authorized to work? <input name="authorization"></label><button type="submit">Submit</button></form>''')
  result=await inspect(page,{'first_name':'Ada','email':'ada@example.test','work_authorization':'Yes'},True)
  assert await page.locator('[name=first]').input_value()=='Ada'
  assert await page.locator('[type=email]').input_value()=='ada@example.test'
  assert await page.locator('[name=authorization]').input_value()==''
  assert len(result)==3
  await page.set_content('''<label>Are you legally authorized to work in the United States?<select id="auth" required><option value="" disabled selected>Choose one</option><option value="Y">Yes</option><option value="N">No</option></select></label><label>Will you now or in the future require sponsorship for employment visa status?<select id="sponsor"><option value="">Select</option><option value="1">Yes</option><option value="0">No</option></select></label><label>Are you authorized to work in Canada?<select id="canada"><option value="">Select</option><option>Yes</option><option>No</option></select></label>''')
  fields=await inspect(page,{'work_authorization':'Yes','sponsorship':'No'},True)
  assert await page.locator('#auth').input_value()=='Y',fields
  assert await page.locator('#sponsor').input_value()=='0',fields
  assert await page.locator('#canada').input_value()=='',fields
  assert fields[0]['value']=='Yes' and fields[0]['high_stakes'],fields
  # Self-identification worded differently from the profile: same meaning fills, ambiguous asks.
  await page.set_content('''<label>Gender<select id="g"><option value="">Select...</option><option>Male</option><option>Female</option><option>Decline To Self Identify</option></select></label><label>Race<select id="r"><option value="">Select...</option><option>Asian</option><option>White</option><option>Decline To Self Identify</option></select></label><label>Veteran status<select id="v"><option value="">Select...</option><option>I am not a veteran</option><option>I am a veteran, but not a protected veteran</option></select></label>''')
  selfid=await inspect(page,{'eeo_gender':'I do not wish to self-identify','eeo_race':'Asian (Not Hispanic or Latino)','eeo_veteran':'I am not a protected veteran'},True)
  assert await page.locator('#g').input_value()=='Decline To Self Identify',selfid
  assert await page.locator('#r').input_value()=='Asian',selfid
  assert await page.locator('#v').input_value()=='',selfid
  assert selfid[0]['value']=='Decline To Self Identify' and selfid[0]['high_stakes'],selfid
  await page.set_content('''<div class="select__container"><label id="gender-label" for="gender">Gender</label><div class="select__single-value"></div><input id="gender" role="combobox" aria-labelledby="gender-label" onclick="document.getElementById('gchoices').hidden=false"></div><div id="gchoices" role="listbox" hidden><div role="option" onclick="document.querySelector('.select__single-value').textContent='Male';this.parentNode.hidden=true">Male</div><div role="option" onclick="document.querySelector('.select__single-value').textContent='Female';this.parentNode.hidden=true">Female</div><div role="option" onclick="document.querySelector('.select__single-value').textContent='Decline To Self Identify';this.parentNode.hidden=true">Decline To Self Identify</div></div>''')
  picker=(await inspect(page,{},False))[0]
  assert await fill_field(page,picker,'I do not wish to self-identify')=='Decline To Self Identify'
  assert (await inspect(page,{},False))[0]['value']=='Decline To Self Identify'
  await page.set_content('''<div class="select__container"><label id="country-label" for="country">Country<span aria-hidden="true">*</span></label><div class="select__single-value"></div><input id="country" role="combobox" aria-labelledby="country-label" aria-required="true" onclick="document.getElementById('choices').hidden=false"><input aria-hidden="true" required tabindex="-1"></div><div id="choices" role="listbox" hidden><div role="option" onclick="document.querySelector('.select__single-value').textContent='United States';this.parentNode.hidden=true">United States</div></div><div role="group" aria-labelledby="upload-label-resume" aria-required="true"><div id="upload-label-resume">Resume/CV*</div><label for="resume">Attach</label><input id="resume" type="file" style="display:none"></div>''')
  custom=await inspect(page,{},False)
  assert len(custom)==2,custom
  assert custom[0]['type']=='combobox' and custom[0]['required'] and not custom[0]['valid'],custom
  assert custom[1]['type']=='file' and 'Resume' in custom[1]['label'] and custom[1]['required'],custom
  await fill_field(page,custom[0],'United States')
  selected=await inspect(page,{},False)
  assert selected[0]['value']=='United States' and selected[0]['valid'],selected
  await page.set_content('''<label><div class="application-label">Full name<span class="required">✱</span></div><div class="application-field"><input name="name" required></div></label><label><div class="application-label">Current location<span class="required">✱</span></div><div><input data-qa="location-input" name="location" required><input type="hidden" name="selectedLocation"></div></label><button type="button">Submit application</button><button type="submit" style="display:none"></button>''')
  lever=await inspect(page,{'first_name':'Ada','last_name':'Lovelace','location':'London'},True)
  assert lever[0]['value']=='Ada Lovelace' and lever[0]['valid'],lever
  assert lever[1]['type']=='location-autocomplete' and not lever[1]['valid'],lever
  await page.locator('[data-qa="location-input"]').fill('London')
  await page.locator('[name="selectedLocation"]').evaluate('(e) => e.value = JSON.stringify({name:""})')
  assert not (await inspect(page,{},False))[1]['valid']
  await page.locator('[name="selectedLocation"]').evaluate('(e) => e.value = JSON.stringify({name:"London"})')
  assert (await inspect(page,{},False))[1]['valid']
  assert len(await final_submit_controls(page))==1
  await page.route('https://jobs.lever.co/**',lambda route:route.fulfill(status=200,body='<a href="/company/123/apply">Apply</a>',content_type='text/html'))
  await page.goto('https://jobs.lever.co/company/123');assert await follow_application_link(page)
  assert page.url=='https://jobs.lever.co/company/123/apply'
  await page.set_content('<label>Password<input type="password" value="super-secret"></label>')
  password=await inspect(page,{},False)
  assert password[0]['value']=='[redacted]' and 'super-secret' not in str(password)
  await page.set_content('<div data-captcha-challenge style="height:20px">Challenge</div>')
  assert await captcha_present(page)
  await page.locator('[data-captcha-challenge]').evaluate('(e)=>e.remove()')
  assert not await captcha_present(page)
  await page.set_content('<iframe src="https://www.recaptcha.net/recaptcha/enterprise/anchor?size=invisible" style="width:10px;height:10px"></iframe>')
  assert not await captcha_present(page)
  print('Browser form inspection and filling passed; submission was not triggered')
  await browser.close()
asyncio.run(main())
