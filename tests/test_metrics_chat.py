import os, unittest
os.environ['OFFERLETTER_DATA'] = str(__import__('pathlib').Path('test-data').resolve())
import app, metrics, chat


class MetricsChatTests(unittest.TestCase):
    def setUp(self):
        app.initialize()
        with app.db() as c:
            for t in ('events', 'approvals', 'questions', 'jobs', 'runs'):
                c.execute(f'DELETE FROM {t}')

    def test_unapproved_submit_flagged(self):
        with app.db() as c:
            c.execute("INSERT INTO jobs(url,status) VALUES ('https://a.example/1','submitted')")
            m = metrics.compute(c)
            self.assertEqual(len(m['submits_without_approval']), 1)
            self.assertFalse(m['audit_ok'])

    def test_clean_state_is_ok(self):
        with app.db() as c:
            c.execute("INSERT INTO jobs(url,status) VALUES ('https://a.example/1','found')")
            m = metrics.compute(c)
            self.assertTrue(m['audit_ok'])
            self.assertEqual(m['applications'], 1)

    def test_chat(self):
        with app.db() as c:
            c.execute("INSERT INTO jobs(url,company,title,status) VALUES ('https://a.example/2','Acme','Engineer','ready for review')")
            self.assertIn('Acme', chat.answer(c, "what's waiting on me?")['reply'])
            self.assertEqual(chat.answer(c, 'pause the run')['action'], 'pause')


if __name__ == '__main__':
    unittest.main()
