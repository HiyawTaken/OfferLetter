import asyncio, json, unittest, uuid
from pathlib import Path
from unittest.mock import patch
import app
from discovery_preferences import related, classify


class RelatedTitleTests(unittest.TestCase):
    targets = ['Data Engineer', 'Tech Sales']

    def test_remotely_related_titles_are_kept(self):
        for title in ['Analytics Engineer', 'Senior Data Engineer', 'BI Developer', 'Data Analyst', 'Account Executive', 'Business Development Representative', 'Mechanical Engineer']:
            self.assertTrue(related(title, self.targets), title)

    def test_unrelated_titles_are_dropped(self):
        for title in ['Registered Nurse', 'Barista', 'Warehouse Associate', 'Senior Associate']:
            self.assertFalse(related(title, self.targets), title)

    def test_loose_mode_still_applies_certain_rules(self):
        rules = {'titles': 'Data Engineer', 'locations': 'Austin, TX', 'excluded_companies': 'Acme'}
        self.assertEqual(classify({'title': 'Analytics Engineer', 'location': 'Austin, TX'}, rules, loose=True)[0], 'clear')
        self.assertEqual(classify({'title': 'Analytics Engineer', 'location': 'Austin, TX'}, rules)[0], 'miss')  # strict titles would drop it
        self.assertEqual(classify({'title': 'Data Engineer', 'location': 'Austin, TX', 'company': 'Acme'}, rules, loose=True)[0], 'miss')
        self.assertEqual(classify({'title': 'Data Engineer', 'location': 'Boise, ID'}, rules, loose=True)[0], 'miss')


class ScreeningWorkerTests(unittest.TestCase):
    def test_decisions_become_statuses(self):
        async def run():
            isolated = Path('test-data') / ('screen-' + uuid.uuid4().hex + '.db')
            with patch.object(app, 'DB', isolated):
                app.initialize()
                with app.db() as c:
                    c.execute("INSERT INTO runs(id,status,summary) VALUES(1,'running','{}')")
                    c.execute("INSERT INTO resumes(name,path,titles,extracted_text) VALUES('r','none','data engineer','python sql')")
                    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                    c.execute("INSERT INTO settings(key,value) VALUES('model',?)", (json.dumps({'provider': 'local', 'model': 'x'}),))
                    c.execute("INSERT INTO rules(id,data) VALUES(1,?)", (json.dumps({'titles': 'Data Engineer', 'screen_parallel': 3}),))
                    for i, (title, desc, note) in enumerate([('Data Engineer', 'Build pipelines', ''), ('Data Engineer', 'Build pipelines', 'In Oakland, near San Francisco'),
                                                             ('Analytics Engineer', 'dbt models', ''), ('Mechanical Engineer', 'CAD', ''), ('Data Engineer', '', '')]):
                        c.execute("INSERT INTO jobs(url,title,description,status,match_note) VALUES(?,?,?,'screening',?)", (f'https://s.example/{i}', title, desc, note))
                calls, reads = [], []
                def fake_screen(cfg, key, job, seeker):
                    calls.append(job['title'])
                    return {'apply': {'decision': 'apply', 'reason': 'Same work'}, 'close': {'decision': 'close', 'reason': 'Adjacent role'}, 'skip': {'decision': 'skip', 'reason': 'Mechanical design work'}}[
                        'skip' if 'Mechanical' in job['title'] else 'close' if 'Analytics' in job['title'] else 'apply']
                async def fake_read(url):
                    reads.append(url); return ''
                summary = {}
                with patch('model_client.screen', fake_screen), patch.object(app, 'read_posting', fake_read):
                    problem = await app.screening_worker(1, summary, lambda: None)
                self.assertEqual(problem, '')
                with app.db() as c:
                    rows = {r['url'][-1]: (r['status'], r['match_note']) for r in c.execute('SELECT url,status,match_note FROM jobs')}
                self.assertEqual(rows['0'], ('found', ''))
                self.assertEqual(rows['1'][0], 'check match')  # nearby city still needs the user
                self.assertIn('Oakland', rows['1'][1])
                self.assertEqual(rows['2'], ('check match', 'Adjacent role'))
                self.assertEqual(rows['3'], ('skipped', 'Not a match: Mechanical design work'))
                self.assertEqual(rows['4'][0], 'check match')  # no description could be read: never auto-applied
                self.assertEqual(reads, ['https://s.example/4'])  # only the job without a description is opened
                self.assertEqual(summary['screened'], 5)
                self.assertEqual((summary['screen_apply'], summary['screen_close'], summary['screen_skip']), (1, 3, 1))
        asyncio.run(run())

    def test_model_down_stops_screening(self):
        async def run():
            isolated = Path('test-data') / ('screen-' + uuid.uuid4().hex + '.db')
            with patch.object(app, 'DB', isolated):
                app.initialize()
                with app.db() as c:
                    c.execute("INSERT INTO runs(id,status,summary) VALUES(1,'running','{}')")
                    c.execute("INSERT INTO resumes(name,path,titles,extracted_text) VALUES('r','none','x','y')")
                    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                    c.execute("INSERT INTO settings(key,value) VALUES('model',?)", (json.dumps({'provider': 'local', 'model': 'x'}),))
                    c.execute("INSERT INTO rules(id,data) VALUES(1,?)", (json.dumps({'titles': 'Data Engineer', 'screen_parallel': 1}),))
                    for i in range(12):
                        c.execute("INSERT INTO jobs(url,title,description,status) VALUES(?,?,?,'screening')", (f'https://d.example/{i}', 'Data Engineer', 'text'))
                def broken(*a): raise ConnectionError('down')
                with patch('model_client.screen', broken):
                    problem = await app.screening_worker(1, {}, lambda: None)
                self.assertIn('model', problem)
                with app.db() as c:
                    left = c.execute("SELECT COUNT(*) n FROM jobs WHERE status='screening'").fetchone()['n']
                self.assertEqual(left, 7)  # stopped after 5 failures; the rest wait for the next run
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()


class BoardPageTests(unittest.TestCase):
    def test_board_pages_are_recognized(self):
        from ats_navigation import on_job_board, APPLY_ELSEWHERE
        self.assertEqual(on_job_board('https://www.indeed.com/viewjob?jk=1'), 'Indeed')
        self.assertEqual(on_job_board('https://www.linkedin.com/jobs/view/1'), 'LinkedIn')
        self.assertEqual(on_job_board('https://job-boards.greenhouse.io/acme/jobs/1'), '')
        self.assertEqual(on_job_board('https://notindeed.com.evil.example/'), '')
        for text in ['Apply on company site', 'Apply', 'Apply on employer’s website']:
            self.assertTrue(APPLY_ELSEWHERE.match(text), text)
        for text in ['Easy Apply', 'Apply with Indeed', 'Save']:
            self.assertFalse(APPLY_ELSEWHERE.match(text), text)

    def test_jobspy_keeps_the_employer_link(self):
        from jobspy_discovery import normalize_records
        row = {'job_url': 'https://www.indeed.com/viewjob?jk=1', 'title': 'Data Engineer', 'job_url_direct': 'https://acme.wd1.myworkdayjobs.com/x/job/1'}
        self.assertEqual(normalize_records([row], 'indeed')[0]['apply_url'], 'https://acme.wd1.myworkdayjobs.com/x/job/1')
        self.assertEqual(normalize_records([{**row, 'job_url_direct': 'javascript:alert(1)'}], 'indeed')[0]['apply_url'], '')
