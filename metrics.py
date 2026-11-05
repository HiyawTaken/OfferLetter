"""Success metrics (FRD 'Demo plan and success metrics') computed from local tracker data."""


def _has(c, table):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def compute(c):
    jobs = c.execute('SELECT id,status FROM jobs ORDER BY id').fetchall()
    per_job = {r['job_id']: r['n'] for r in c.execute('SELECT job_id, COUNT(*) n FROM questions GROUP BY job_id')}
    # Questions asked per application, in the order applications were started (the learning curve).
    started = [j['id'] for j in jobs if j['id'] in per_job or j['status'] not in ('found', 'skipped')]
    curve = [{'job_id': i, 'questions': per_job.get(i, 0)} for i in started][:10]
    submitted = [j['id'] for j in jobs if j['status'] in ('submitted', 'interview', 'rejected')]
    approved = {r['job_id'] for r in c.execute('SELECT job_id FROM approvals')}
    without_approval = [i for i in submitted if i not in approved]
    count = lambda kind: c.execute('SELECT COUNT(*) n FROM events WHERE kind=?', (kind,)).fetchone()['n']
    clicks, approvals_logged, attempts = count('submit_clicked'), count('approval_given'), count('submit_attempt_started')
    statuses = {}
    for j in jobs:
        statuses[j['status']] = statuses.get(j['status'], 0) + 1
    fit = c.execute('SELECT COUNT(*) n FROM fit_checks').fetchone()['n'] if _has(c, 'fit_checks') else 0
    return {
        'applications': len(jobs),
        'status_counts': statuses,
        'questions_per_application': curve,
        'submits_without_approval': without_approval,
        'submit_clicks_logged': clicks,
        'approvals_logged': approvals_logged,
        'audit_ok': not without_approval and clicks <= approvals_logged and attempts <= approvals_logged,
        'fit_checks_run': fit,
        'form_coverage': {
            'attempted': statuses.get('submitted', 0) + statuses.get('submission uncertain', 0) + statuses.get('failed', 0),
            'succeeded': statuses.get('submitted', 0),
        },
    }
