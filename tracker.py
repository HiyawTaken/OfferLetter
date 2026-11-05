"""Application tracker rows (FRD FR8): one row per job with source, fit result, resume used, status, dates and link."""
import json


def _table_exists(c, name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def rows(c):
    latest_fit = {}
    if _table_exists(c, 'fit_checks'):
        # Later rows overwrite earlier ones, leaving the latest fit check per job.
        for r in c.execute('SELECT f.job_id, f.resume_id, f.result, r.name AS resume_name '
                           'FROM fit_checks f LEFT JOIN resumes r ON r.id = f.resume_id ORDER BY f.id'):
            try:
                verdict = json.loads(r['result']).get('result', '')
            except (ValueError, AttributeError):
                verdict = ''
            latest_fit[r['job_id']] = {'fit': verdict, 'resume': r['resume_name'] or ''}
    out = []
    for j in c.execute('SELECT id, source, company, title, status, url, created_at, updated_at FROM jobs ORDER BY id DESC'):
        fit = latest_fit.get(j['id'], {'fit': '', 'resume': ''})
        out.append({
            'id': j['id'], 'source': j['source'] or 'pasted link', 'company': j['company'], 'title': j['title'],
            'fit': fit['fit'], 'resume': fit['resume'], 'status': j['status'],
            'found': j['created_at'], 'updated': j['updated_at'], 'url': j['url'],
        })
    return out
