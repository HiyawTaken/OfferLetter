import sqlite3
import unittest
from discovery_preferences import classify, location_terms, matches
import assistant

RULES = {'titles': 'Software Engineer Intern, Backend Engineer', 'locations': 'San Francisco, CA'}


def tier(title, location='San Francisco, CA', rules=RULES):
    return classify({'title': title, 'location': location}, rules)[0]


class ClassifyTests(unittest.TestCase):
    def test_word_forms_and_order_are_clear(self):
        # Real LinkedIn and Indeed titles the old exact-phrase filter dropped.
        for title in ('Software Engineering Intern', 'Software Engineering Internship - San Francisco', '2027 Intern - Software Engineer', 'Software Engineer, Intern (Summer 2027) - US'):
            self.assertEqual(tier(title), 'clear', title)

    def test_close_titles_are_gray(self):
        self.assertEqual(tier('Software Developer Intern'), 'gray')
        self.assertEqual(tier('Systems Engineer Intern'), 'miss')  # shares only generic words
        self.assertEqual(tier('Hardware Engineer Intern'), 'miss')
        self.assertEqual(tier('Engineering Manager, Backend'), 'gray')  # a role-changing word: a person decides
        self.assertFalse(matches({'title': 'Engineering Manager'}, {'titles': 'Engineer'}))

    def test_unrelated_titles_are_dropped(self):
        self.assertEqual(tier('Intern, Technology'), 'miss')
        self.assertEqual(tier('Contract Student Worker - Fleet Maps Validation'), 'miss')

    def test_locations(self):
        self.assertEqual(location_terms('San Francisco, CA, New York, NY, Texas'), [('San Francisco', 'ca'), ('New York', 'ny'), ('', 'tx')])
        self.assertEqual(location_terms('New York'), [('New York', '')])
        self.assertEqual(tier('Software Engineer Intern', 'South San Francisco, CA'), 'clear')
        self.assertEqual(tier('Software Engineer Intern', 'Foster City, CA'), 'gray')   # same state: nearby, ask
        self.assertEqual(tier('Software Engineer Intern', 'Seattle, WA'), 'miss')
        self.assertEqual(tier('Software Engineer Intern', 'San Francisco, TX'), 'miss')  # a city name in another state
        self.assertEqual(tier('Software Engineer Intern', ''), 'gray')
        self.assertEqual(tier('Software Engineer Intern', 'Remote'), 'gray')
        self.assertEqual(tier('Software Engineer', 'Austin, TX', {'titles': 'Software Engineer', 'locations': 'Texas'}), 'clear')
        remote_only = {'titles': 'Software Engineer', 'remote': 'remote only'}
        self.assertEqual(tier('Software Engineer', 'Remote - US', remote_only), 'clear')
        self.assertEqual(tier('Software Engineer', 'Austin, TX', remote_only), 'miss')

    def test_nearby_means_same_metro_not_same_state(self):
        self.assertEqual(tier('Software Engineer Intern', 'San Jose, CA'), 'gray')
        self.assertEqual(tier('Software Engineer Intern', 'San Diego, CA'), 'miss')
        self.assertEqual(tier('Software Engineer Intern', 'Redondo Beach, CA'), 'miss')
        self.assertEqual(tier('Software Engineer Intern', 'Jersey City, NJ', {'titles': 'Software Engineer Intern', 'locations': 'New York, NY'}), 'gray')

    def test_shorthand_and_multi_city_lists(self):
        self.assertEqual(tier('Software Engineer Intern', '5 locationsSeattle, WA SF LA NYC Sunnyvale, CA'), 'clear')
        self.assertEqual(tier('Software Engineer Intern', '9 locationsBoston, MA Seattle, WA Austin, TX'), 'miss')

    def test_two_uncertain_things_are_not_a_match(self):
        self.assertEqual(tier('Software Developer Intern', 'San Jose, CA'), 'miss')
        self.assertEqual(tier('Gameplay Engineer Intern', 'Irvine, CA'), 'miss')

    def test_excluded_company_is_dropped(self):
        self.assertEqual(classify({'title': 'Software Engineer Intern', 'location': 'San Francisco, CA', 'company': 'Acme'}, {**RULES, 'excluded_companies': 'Acme'})[0], 'miss')


class AssistantSnapshotTests(unittest.TestCase):
    def test_snapshot_leaves_out_private_profile_and_answers(self):
        c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
        c.executescript('''CREATE TABLE rules (id INTEGER PRIMARY KEY, data TEXT);
            CREATE TABLE profile (id INTEGER PRIMARY KEY, data TEXT);
            CREATE TABLE answers (id INTEGER PRIMARY KEY, question TEXT, answer TEXT);
            CREATE TABLE jobs (id INTEGER PRIMARY KEY, url TEXT, company TEXT, title TEXT, status TEXT, created_at TEXT, location TEXT DEFAULT '', description TEXT DEFAULT '', source TEXT DEFAULT '', posted_date TEXT DEFAULT '', match_note TEXT DEFAULT '');
            CREATE TABLE questions (id INTEGER PRIMARY KEY, job_id INTEGER, label TEXT, status TEXT);
            CREATE TABLE runs (id INTEGER PRIMARY KEY, status TEXT, summary TEXT, started_at TEXT, finished_at TEXT);
            CREATE TABLE resumes (id INTEGER PRIMARY KEY, name TEXT, titles TEXT);
            CREATE TABLE events (id INTEGER PRIMARY KEY, created_at TEXT, detail TEXT);''')
        c.execute("INSERT INTO rules VALUES (1, '{\"titles\": \"Software Engineer Intern\", \"tab_limit\": 2}')")
        c.execute("INSERT INTO profile VALUES (1, '{\"email\": \"maya@example.com\", \"eeo_race\": \"Asian\"}')")
        c.execute("INSERT INTO answers VALUES (1, 'Salary?', '123456')")
        c.execute("INSERT INTO jobs(url, company, title, status, match_note) VALUES ('https://x.example/1', 'Acme', 'Systems Engineer Intern', 'check match', 'Title is close')")
        c.execute("INSERT INTO questions VALUES (1, 1, 'Why Acme?', 'pending')")
        text = str(assistant.snapshot(c, open_tabs=1))
        for private in ('maya@example.com', 'Asian', '123456'):
            self.assertNotIn(private, text)
        self.assertIn('Systems Engineer Intern', text)
        self.assertIn('close match', text)
        self.assertIn('Why Acme?', text)

    def test_pause_intent_is_short_commands_only(self):
        self.assertTrue(assistant.wants_pause('pause'))
        self.assertTrue(assistant.wants_pause('Stop the run please'))
        self.assertFalse(assistant.wants_pause('Why did the last run stop before finishing all the jobs I queued up?'))


if __name__ == '__main__':
    unittest.main()
