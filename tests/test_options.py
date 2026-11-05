import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from answer_memory import pick_option

COUNTRIES = ['United States +1', 'United States Minor Outlying Islands +1', 'Canada +1', 'Dominican Republic +1']


class PickOptionTests(unittest.TestCase):
    def test_dial_code_is_ignored(self):
        self.assertEqual(pick_option('United States', COUNTRIES), 'United States +1')

    def test_exact_text_wins(self):
        self.assertEqual(pick_option('Yes', ['Yes', 'No']), 'Yes')

    def test_ambiguous_or_missing_is_never_guessed(self):
        self.assertIsNone(pick_option('United', COUNTRIES))
        self.assertIsNone(pick_option('Mexico', COUNTRIES))
        self.assertIsNone(pick_option('Yes', ['Yes, I am', 'No']))


if __name__ == '__main__':
    unittest.main()
