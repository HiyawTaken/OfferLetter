"""Read public SimplifyJobs GitHub tables, without executing external content."""
from html.parser import HTMLParser
from urllib.parse import urlparse
import urllib.request

LISTS={'new_grad':'https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md', 'internships':'https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/README.md'}
class Rows(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.row=None;self.cell=None;self.last_company='';self.jobs=[]
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='tr': self.row=[]
  elif tag=='td' and self.row is not None: self.cell={'text':[],'links':[]}
  elif self.cell is not None and tag=='a': self.cell['links'].append(attrs.get('href',''))
  elif self.cell is not None and tag in ('br','summary'): self.cell['text'].append(' ')
  elif self.cell is not None and tag=='img' and attrs.get('alt'): self.cell['text'].append(' '+attrs['alt']+' ')
 def handle_data(self,data):
  if self.cell is not None:self.cell['text'].append(data)
 def handle_endtag(self,tag):
  if tag=='td' and self.cell is not None and self.row is not None:
   self.row.append(self.cell);self.cell=None
  elif tag=='tr' and self.row is not None:
   cells=self.row;self.row=None
   if len(cells)<4:return
   text=lambda c:' '.join(''.join(c['text']).split())
   company=text(cells[0]).replace('🔥','').strip()
   if company in ('↳','↪','↑',''):company=self.last_company
   else:self.last_company=company
   title=text(cells[1]);location=text(cells[2]);application=cells[3]
   if '🔒' in text(application):return
   links=[url for url in application['links'] if urlparse(url).scheme in ('http','https') and (urlparse(url).hostname or '').lower() not in ('simplify.jobs','www.simplify.jobs')]
   if not company or not title or not links:return
   self.jobs.append({'url':links[0],'company':company,'title':title,'location':location,'description':'','source':'simplify'})

def parse_list(markup):
 parser=Rows();parser.feed(markup);return parser.jobs

def fetch_list(name):
 if name not in LISTS: raise ValueError('Unknown list')
 req=urllib.request.Request(LISTS[name],headers={'User-Agent':'OfferLetter/0.1'})
 with urllib.request.urlopen(req,timeout=30) as response: data=response.read(8000001)
 if len(data)>8000000: raise ValueError('List is too large')
 return parse_list(data.decode('utf-8'))
