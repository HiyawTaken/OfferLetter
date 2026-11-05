import os, unittest
os.environ['OFFERLETTER_DATA'] = str(__import__('pathlib').Path('test-data').resolve())
import app


def fit(result, checks=()):
    return {'result': result, 'rule_checks': list(checks)}


class PolicyTests(unittest.TestCase):
    def test_fail_is_skipped(self):
        self.assertEqual(app.preparation_policy(fit('fail'), {}), 'skip')

    def test_pass_is_prepared(self):
        self.assertEqual(app.preparation_policy(fit('pass'), {}), 'prepare')

    def test_borderline_follows_strictness(self):
        self.assertEqual(app.preparation_policy(fit('borderline'), {'strictness': 'flag'}), 'review fit')
        self.assertEqual(app.preparation_policy(fit('borderline'), {'strictness': 'skip'}), 'skip')
        self.assertEqual(app.preparation_policy(fit('borderline'), {'strictness': 'apply'}), 'prepare')

    def test_flagged_rule_asks_user_even_when_fit_passes(self):
        self.assertEqual(app.preparation_policy(fit('pass', [{'rule': 'Locations', 'result': 'flag'}]), {}), 'review fit')

    def test_unverifiable_salary_floor_asks_user(self):
        self.assertEqual(app.preparation_policy(fit('pass'), {'salary_floor': '90000'}), 'review fit')


if __name__ == '__main__':
    unittest.main()
