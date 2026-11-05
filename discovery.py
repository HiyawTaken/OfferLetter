"""Public ATS board discovery; descriptions are untrusted external content."""
import html, json, re, urllib.request
from urllib.parse import quote

def board_url(provider, slug):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', slug): raise ValueError('Invalid board identifier')
    slug=quote(slug,safe='')
    urls={'greenhouse':f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true',
          'lever':f'https://api.lever.co/v0/postings/{slug}?mode=json',
          'ashby':f'https://api.ashbyhq.com/posting-api/job-board/{slug}'}
    if provider not in urls: raise ValueError('Unsupported board')
    return urls[provider]

def parse_jobs(provider, data, company):
    from datetime import datetime,timezone
    from salary import amount
    items=data if provider=='lever' else data.get('jobs',[])
    out=[]
    for item in items:
        if provider=='greenhouse':
            url=item.get('absolute_url'); title=item.get('title'); location=(item.get('location') or {}).get('name',''); description=item.get('content','')
        elif provider=='lever':
            url=item.get('hostedUrl'); title=item.get('text'); location=(item.get('categories') or {}).get('location',''); description=item.get('descriptionPlain','')
        else:
            url=item.get('jobUrl'); title=item.get('title'); location=item.get('location',''); description=item.get('descriptionPlain','')
        if not url or not title: continue
        published=item.get('first_published') if provider=='greenhouse' else item.get('createdAt') if provider=='lever' else item.get('publishedAt')
        try:
            posted=(datetime.fromtimestamp(published/1000,timezone.utc).date().isoformat() if isinstance(published,(int,float)) else datetime.fromisoformat(published.replace('Z','+00:00')).date().isoformat()) if published else ''
        except (ValueError,TypeError,OverflowError,OSError):posted=''
        pay=item.get('salaryRange') or {} if provider=='lever' else {}
        if not isinstance(pay,dict):pay={}
        low,high=amount(pay.get('min')),amount(pay.get('max'))
        from salary import pay_label
        pay_shown=pay_label(pay.get('min'),pay.get('max'),pay.get('interval'),pay.get('currency') or 'USD')
        currency=str(pay.get('currency') or '').upper();interval=str(pay.get('interval') or '').lower()
        if currency!='USD' or interval not in ('year','yearly','annual') or (low and high and low>high):low=high=None
        out.append({'url':url,'company':company,'title':title,'location':location,'description':html.unescape(re.sub('<[^>]+>',' ',description or ''))[:30000],'source':provider,'posted_date':posted,'salary_min':str(low or ''),'salary_max':str(high or ''),'salary_currency':'USD' if low or high else '','salary_period':'year' if low or high else '','pay':pay_shown})
    return out

def fetch_board(provider,slug):
    url=board_url(provider,slug)
    def fetch(target):
        req=urllib.request.Request(target,headers={'User-Agent':'OfferLetter/0.1'})
        with urllib.request.urlopen(req,timeout=20) as response:
            if int(response.headers.get('Content-Length','0'))>5000000: raise ValueError('Board response is too large')
            data=response.read(5000001)
            if len(data)>5000000: raise ValueError('Board response is too large')
            return json.loads(data)
    try: data=fetch(url)
    except ValueError as exc:
        if provider!='greenhouse' or str(exc)!='Board response is too large': raise
        # Large boards can omit descriptions and remain discoverable.
        data=fetch(url.split('?')[0])
    return parse_jobs(provider,data,slug)

class _Text(__import__('html.parser').parser.HTMLParser):
    """Visible text of a page, without scripts, styles or navigation chrome."""
    SKIP={'script','style','noscript','svg','nav','header','footer','form','button'}
    def __init__(self):super().__init__();self.parts=[];self.depth=0
    def handle_starttag(self,tag,attrs):
        if tag in self.SKIP:self.depth+=1
    def handle_endtag(self,tag):
        if tag in self.SKIP and self.depth:self.depth-=1
    def handle_data(self,data):
        if not self.depth and data.strip():self.parts.append(data.strip())

def fetch_posting_text(url,limit=30000):
    """Text of a public job posting, for a fit check when a list gave no description. '' when the page has none (pages built by scripts)."""
    if not re.match(r'^https?://',url or ''):return ''
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36','Accept':'text/html'})
    with urllib.request.urlopen(req,timeout=20) as response:
        if 'html' not in (response.headers.get('Content-Type') or ''):return ''
        raw=response.read(3000001)
    parser=_Text();parser.feed(raw[:3000000].decode('utf-8','replace'))
    text=re.sub(r'\s+',' ',' '.join(parser.parts)).strip()
    return text[:limit] if len(text)>=600 else ''
