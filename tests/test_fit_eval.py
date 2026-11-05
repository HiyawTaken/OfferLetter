import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fit_eval


class AgreementTests(unittest.TestCase):
    def test_rates(self):
        r = fit_eval.agreement([('pass', 'pass'), ('fail', 'borderline'), ('borderline', 'borderline'), ('pass', 'fail')])
        self.assertEqual(r['n'], 4)
        self.assertEqual(r['exact'], 0.5)
        self.assertEqual(r['binary'], 0.75)

    def test_empty(self):
        self.assertIsNone(fit_eval.agreement([])['exact'])


if __name__ == '__main__':
    unittest.main()
