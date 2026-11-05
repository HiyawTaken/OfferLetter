import json, os, unittest
os.environ['OFFERLETTER_DATA'] = str(__import__('pathlib').Path('test-data').resolve())
import app, tracker


class TrackerTests(unittest.TestCase):
    def setUp(self):
        app.initialize()
        with app.db() as c:
            c.execute('DROP TABLE IF EXISTS fit_checks')
            for t in ('approvals', 'questions', 'jobs', 'resumes'):
                c.execute(f'DELETE FROM {t}')

    def test_row_without_fit_check(self):
        with app.db() as c:
            c.execute("INSERT INTO jobs(url,company,title) VALUES ('https://a.example/1','Acme','Engineer')")
            row = tracker.rows(c)[0]
        self.assertEqual((row['source'], row['fit'], row['resume'], row['status']), ('pasted link', '', '', 'found'))

    def test_latest_fit_and_resume_are_shown(self):
        with app.db() as c:
            c.execute("INSERT INTO jobs(url,company,title,source) VALUES ('https://a.example/2','Acme','Engineer','greenhouse')")
            job = c.execute('SELECT id FROM jobs').fetchone()['id']
            c.execute("INSERT INTO resumes(id,name,path,titles,extracted_text) VALUES (1,'SWE resume','p','[]','t')")
            c.execute('CREATE TABLE IF NOT EXISTS fit_checks (id INTEGER PRIMARY KEY,job_id INTEGER NOT NULL,resume_id INTEGER NOT NULL,result TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
            c.execute('INSERT INTO fit_checks(job_id,resume_id,result) VALUES (?,?,?)', (job, 1, json.dumps({'result': 'fail'})))
            c.execute('INSERT INTO fit_checks(job_id,resume_id,result) VALUES (?,?,?)', (job, 1, json.dumps({'result': 'pass'})))
            row = tracker.rows(c)[0]
        self.assertEqual((row['fit'], row['resume'], row['source']), ('pass', 'SWE resume', 'greenhouse'))


if __name__ == '__main__':
    unittest.main()
