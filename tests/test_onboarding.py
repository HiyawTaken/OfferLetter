import json, os, unittest
os.environ['OFFERLETTER_DATA'] = str(__import__('pathlib').Path('test-data').resolve())
import app
from starlette.testclient import TestClient


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        app.initialize()
        with app.db() as c:
            c.execute("DELETE FROM settings WHERE key='onboarded'")
            c.execute('DELETE FROM profile'); c.execute('DELETE FROM resumes')
        self.client = TestClient(app.app, base_url='http://127.0.0.1')
        self.h = {'x-offerletter-token': app.TOKEN}

    def test_new_install_needs_setup_then_finishes(self):
        self.assertFalse(self.client.get('/api/onboarding').json()['done'])
        self.assertTrue(self.client.post('/api/onboarding', headers=self.h, json={'done': True}).json()['done'])
        self.assertTrue(self.client.get('/api/onboarding').json()['done'])

    def test_existing_install_with_profile_and_resume_skips_setup(self):
        with app.db() as c:
            c.execute('INSERT INTO profile(id,data) VALUES (1,?)', (json.dumps({'email': 'a@example.test'}),))
            c.execute("INSERT INTO resumes(id,name,path,titles,extracted_text) VALUES (1,'r','p','[]','t')")
        self.assertTrue(self.client.get('/api/onboarding').json()['done'])

    def test_restart_setup_requires_token(self):
        self.assertEqual(self.client.post('/api/onboarding', json={'done': False}).status_code, 403)

    def test_work_history_round_trip_and_invalid_dates(self):
        entry={'employer':'Example Company','title':'Data Intern','start_date':'2025-01','end_date':'2025-06','description':'Built pipelines','currently_working':False}
        saved=self.client.post('/api/profile',headers=self.h,json={'first_name':'Ada','experience':[entry]})
        self.assertEqual(saved.status_code,200)
        profile=self.client.get('/api/profile').json()
        self.assertEqual(profile['experience'][0]['description'],'Built pipelines')
        self.assertEqual(profile['current_company'],'Example Company')
        bad={**entry,'end_date':'2024-06'}
        self.assertEqual(self.client.post('/api/profile',headers=self.h,json={'experience':[bad]}).status_code,400)
        self.assertEqual(self.client.get('/api/profile').json()['experience'],profile['experience'])
        self.client.post('/api/profile',headers=self.h,json={'first_name':'Ada'})
        self.assertEqual(len(self.client.get('/api/profile').json()['experience']),1)


if __name__ == '__main__':
    unittest.main()
