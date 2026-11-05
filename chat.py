"""Read-only chat over tracker state (FRD bonus FR12).

Answers are built from local data with no model call, so nothing leaves the machine.
The only action is pausing a preparation run, which the caller performs.
"""
import re


def answer(c, message):
    words = set(re.sub(r'[^a-z0-9 ]+', ' ', message.lower()).split())
    if 'pause' in words or 'stop' in words:
        return {'action': 'pause', 'reply': 'Pausing the current run after its current step.'}
    if 'resume' in words:
        return {'action': None, 'reply': 'Start a new preparation run with the Run button so you can watch the result.'}
    pending = c.execute("SELECT COUNT(*) n FROM questions WHERE status='pending'").fetchone()['n']
    review = c.execute("SELECT company,title FROM jobs WHERE status IN ('ready for review','waiting on user') ORDER BY id").fetchall()
    if words & {'waiting', 'pending', 'todo'} or ('on' in words and 'me' in words):
        lines = [f'{pending} unanswered question(s).']
        lines += [f"Awaiting you: {r['title'] or 'Untitled'} at {r['company'] or 'unknown company'}." for r in review[:10]]
        return {'action': None, 'reply': ' '.join(lines)}
    if words & {'submitted', 'applied'}:
        n = c.execute("SELECT COUNT(*) n FROM jobs WHERE status='submitted'").fetchone()['n']
        return {'action': None, 'reply': f'{n} application(s) submitted.'}
    run = c.execute('SELECT status FROM runs ORDER BY id DESC LIMIT 1').fetchone()
    counts = {r['status']: r['n'] for r in c.execute('SELECT status, COUNT(*) n FROM jobs GROUP BY status')}
    return {'action': None, 'reply': f"Latest run: {run['status'] if run else 'none'}. Jobs by status: {counts or 'none'}. {pending} unanswered question(s)."}
