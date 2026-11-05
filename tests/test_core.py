import os, tempfile, unittest
os.environ['OFFERLETTER_DATA']=str(__import__('pathlib').Path('test-data').resolve())
import app
class CoreTests(unittest.TestCase):
 def setUp(self): app.initialize()
 def test_url(self):
  self.assertTrue(app.valid_url('https://example.com/job'))
  self.assertFalse(app.valid_url('javascript:alert(1)'))
  self.assertFalse(app.valid_url('https://user:pass@example.com'))
 def test_database_and_duplicates(self):
  import sqlite3
  with app.db() as c:
   c.execute('DELETE FROM jobs')
   c.execute('INSERT INTO jobs(url) VALUES (?)',('https://example.com/job',))
   with self.assertRaises(sqlite3.IntegrityError): c.execute('INSERT INTO jobs(url) VALUES (?)',('https://example.com/job',))
 def test_profile(self):
  with app.db() as c:
   c.execute("INSERT OR REPLACE INTO profile(id,data) VALUES(1,?)",('{"first_name":"Test"}',))
   self.assertIn('Test', c.execute('SELECT data FROM profile').fetchone()['data'])
if __name__=='__main__': unittest.main()

