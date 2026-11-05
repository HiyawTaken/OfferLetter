import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import model_client

RESUME = 'Built APIs in Python. B.S. Computer Science.'


def reply(*rows, claimed='pass'):
    return json.dumps({'result': claimed, 'requirements': [
        {'requirement': f'r{i}', 'kind': k, 'assessment': a, 'evidence': e, 'reason': 'x'} for i, (k, a, e) in enumerate(rows)]})


class VerdictTests(unittest.TestCase):
    def verdict(self, *rows, claimed='pass'):
        return model_client.validate_response(reply(*rows, claimed=claimed), RESUME)['result']

    def test_all_required_met_passes_even_if_preferred_missing(self):
        self.assertEqual(self.verdict(('required', 'met', 'Python'), ('preferred', 'not_met', ''), claimed='fail'), 'pass')

    def test_unmet_required_fails_even_if_model_says_pass(self):
        self.assertEqual(self.verdict(('required', 'met', 'Python'), ('required', 'not_met', '')), 'fail')

    def test_unclear_required_is_borderline(self):
        self.assertEqual(self.verdict(('required', 'met', 'Python'), ('required', 'unclear', ''), claimed='pass'), 'borderline')

    def test_unverifiable_quote_downgrades_met_to_unclear(self):
        self.assertEqual(self.verdict(('required', 'met', 'invented text')), 'borderline')

    def test_ellipsis_quote_with_real_fragments_is_accepted(self):
        self.assertEqual(self.verdict(('required', 'met', 'Built APIs ... Computer Science')), 'pass')

    def test_one_fabricated_fragment_rejects_the_quote(self):
        self.assertEqual(self.verdict(('required', 'met', 'Built APIs ... Kubernetes')), 'borderline')

    def test_think_blocks_and_fences_are_stripped(self):
        self.assertEqual(json.loads(model_client.extract_json('<think>hmm</think>\n```json\n{"a": 1}\n```')), {'a': 1})


if __name__ == '__main__':
    unittest.main()
