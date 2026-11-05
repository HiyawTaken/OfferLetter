"""Conservative cross-source duplicate detection for known job identities."""
import re, unicodedata

def normalize(value):
    return ' '.join(re.findall(r'[\w]+',unicodedata.normalize('NFKC',value or '').casefold()))

def same_job(a,b):
    company_a,company_b=normalize(a.get('company','')),normalize(b.get('company',''))
    title_a,title_b=normalize(a.get('title','')),normalize(b.get('title',''))
    if not company_a or not company_b or not title_a or not title_b: return False
    if company_a!=company_b or title_a!=title_b: return False
    loc_a,loc_b=normalize(a.get('location','')),normalize(b.get('location',''))
    return not loc_a or not loc_b or loc_a==loc_b

def find_duplicate(job,rows,exclude_id=None):
    return next((dict(row) for row in rows if row['id']!=exclude_id and same_job(job,dict(row))),None)

def identity_key(job):
    company,title=normalize(job.get('company','')),normalize(job.get('title',''))
    return (company,title) if company and title else None

def build_index(rows):
    result={}
    for row in rows:
        job=dict(row);key=identity_key(job)
        if key: result.setdefault(key,[]).append(job)
    return result
