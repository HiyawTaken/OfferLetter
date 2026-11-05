"""Navigation helpers for known public ATS job pages."""
import re
from urllib.parse import urlparse,urljoin


def application_target(current,href):
 p=urlparse(current)
 if p.scheme!='https' or p.username or p.password or p.port not in (None,443):return None
 suffix={'jobs.lever.co':'apply','jobs.ashbyhq.com':'application'}.get((p.hostname or '').lower())
 if not suffix:return None
 path=p.path.rstrip('/')
 if not path or path.endswith('/'+suffix):return None
 target=urlparse(urljoin(current,href or ''))
 if target.scheme!='https' or target.hostname!=p.hostname or target.port not in (None,443) or target.username or target.password:return None
 if target.path.rstrip('/')!=path+'/'+suffix:return None
 return target.geturl()


async def follow_application_link(page):
 candidates=page.locator('a[href]');targets=set()
 for i in range(await candidates.count()):
  href=await candidates.nth(i).get_attribute('href');target=application_target(page.url,href)
  if target:targets.add(target)
 if len(targets)!=1:return False
 await page.goto(next(iter(targets)),wait_until='domcontentloaded',timeout=30000)
 return True




BOARDS={'indeed.com':'Indeed','linkedin.com':'LinkedIn','glassdoor.com':'Glassdoor','ziprecruiter.com':'ZipRecruiter'}
def on_job_board(url):
 """'Indeed', 'LinkedIn', ... when the page is a job board's own listing or apply flow, else ''."""
 host=(urlparse(url).hostname or '').lower()
 return next((name for domain,name in BOARDS.items() if host==domain or host.endswith('.'+domain)),'')

APPLY_ELSEWHERE=re.compile(r"^\s*apply\s+(?:now\s+)?on\s+(?:the\s+)?(?:company|employer)(?:['’]s)?\s+(?:site|website)\s*$|^\s*apply\s*$",re.I)
async def follow_board_apply(page):
 """On a board listing, follow its link to the employer's own application. Easy Apply / Indeed Apply buttons have no link and stay put."""
 links=page.locator('a[href]');targets=set()
 for i in range(min(await links.count(),400)):
  link=links.nth(i)
  try:
   text=(await link.inner_text(timeout=500)).strip()
   if not APPLY_ELSEWHERE.match(text) or not await link.is_visible():continue
   target=urljoin(page.url,await link.get_attribute('href') or '')
  except Exception:continue
  if urlparse(target).scheme=='https' and target.split('#')[0]!=page.url.split('#')[0]:targets.add(target)
 if len(targets)!=1:return False
 await page.goto(next(iter(targets)),wait_until='domcontentloaded',timeout=30000)
 try:await page.wait_for_load_state('networkidle',timeout=10000)
 except Exception:pass
 return True
