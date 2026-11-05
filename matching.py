"""Explainable preliminary resume ranking, not a qualification decision."""
import re
from collections import Counter
STOP=set('the and for with from that this have will your are you our job work experience role years skills requirements preferred required ability including their about using into'.split())
def words(text): return [w for w in re.findall(r'[a-z][a-z0-9+#.-]{2,}',text.lower()) if w not in STOP]
def rank(job,resumes):
    job_words=Counter(words(job.get('title','')+' '+job.get('description','')))
    results=[]
    for resume in resumes:
        resume_words=set(words(resume['extracted_text']+' '+resume['titles']))
        overlap=sorted((w for w in job_words if w in resume_words),key=lambda w:(-job_words[w],w))
        score=sum(min(job_words[w],3) for w in overlap)
        results.append({'id':resume['id'],'name':resume['name'],'score':score,'matching_terms':overlap[:15]})
    return sorted(results,key=lambda x:(-x['score'],x['id']))
