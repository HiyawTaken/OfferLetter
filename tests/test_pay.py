import unittest
from salary import pay_label, pay_from_text, pay_text


class PayTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(pay_label('105000.0', '135000.0', 'year'), '$105k–$135k/yr')
        self.assertEqual(pay_label(25, 35, 'hourly'), '$25–$35/hr')
        self.assertEqual(pay_label(30, 40, 'per-hour-wage'), '$30–$40/hr')  # Lever
        self.assertEqual(pay_label(76600, 106450, 'year'), '$76.6k–$106k/yr')
        self.assertEqual(pay_label(50, 40, 'hour'), '')
        self.assertEqual(pay_label(30, 40, 'hour', 'EUR'), '')
        self.assertEqual(pay_label(30, 40, ''), '')

    def test_posting_text(self):
        self.assertEqual(pay_from_text('The rate is $40 - $55 per hour.'), '$40–$55/hr')
        self.assertEqual(pay_from_text('Base pay range $120,000 - $150,000'), '$120k–$150k/yr')
        self.assertEqual(pay_from_text('$30 to $36 hourly'), '$30–$36/hr')
        self.assertEqual(pay_from_text('Salary: $95K-$120K a year'), '$95k–$120k/yr')
        for text in ['We raised $50,000,000', '$1,000 signing bonus', 'Up to $2,000 for your home office', '']:
            self.assertEqual(pay_from_text(text), '', text)

    def test_order(self):
        self.assertEqual(pay_text({'pay': '$20/hr', 'salary_min': '90000'}), '$20/hr')
        self.assertEqual(pay_text({'salary_min': '90000', 'salary_max': '120000', 'salary_period': 'year', 'description': '$40/hr'}), '$90k–$120k/yr')
        self.assertEqual(pay_text({'description': 'Pay: $40/hr'}), '$40/hr')


if __name__ == '__main__':
    unittest.main()
