import unittest
from form_engine import match_profile, profile_key, select_label, HIGH_STAKES


class SelfIdTests(unittest.TestCase):
    profile = {'eeo_hispanic': 'No', 'eeo_race': 'Asian (Not Hispanic or Latino)', 'eeo_gender': 'Not set'}

    def test_hispanic_question_is_recognized_and_high_stakes(self):
        self.assertEqual(profile_key('Are you Hispanic or Latino?'), 'eeo_hispanic')
        self.assertEqual(match_profile('Are you Hispanic/Latino?', self.profile), 'No')  # Greenhouse's wording
        self.assertIsNone(match_profile('Do you identify as Hispanic or Latinx in any way?', self.profile))  # unknown wording: ask instead
        self.assertEqual(match_profile('Are you Hispanic or Latino? *', self.profile), 'No')
        self.assertIn('eeo_hispanic', HIGH_STAKES)

    def test_workday_ethnicity_label_uses_race_answer(self):
        self.assertEqual(match_profile('Ethnicity', self.profile), 'Asian (Not Hispanic or Latino)')
        options = ['Select One', 'Asian (Not Hispanic or Latino)', 'White (Not Hispanic or Latino)', 'I do not wish to self-identify']
        self.assertEqual(select_label('Asian (Not Hispanic or Latino)', options), 'Asian (Not Hispanic or Latino)')

    def test_not_set_is_never_filled(self):
        self.assertIsNone(match_profile('Gender', self.profile))


GREENHOUSE_GENDER = ['Male', 'Female', 'Decline To Self Identify']
GREENHOUSE_RACE = ['American Indian or Alaskan Native', 'Asian', 'Black or African American', 'Hispanic or Latino', 'White',
                   'Native Hawaiian or Other Pacific Islander', 'Two or More Races', 'Decline To Self Identify']
GREENHOUSE_VETERAN = ['I am not a protected veteran', 'I identify as one or more of the classifications of protected veteran', "I don't wish to answer"]
GREENHOUSE_DISABILITY = ['Yes, I have a disability, or have had one in the past', 'No, I do not have a disability and have not had one in the past', 'I do not want to answer']


class SameMeaningTests(unittest.TestCase):
    def pick(self, answer, options):
        from answer_memory import pick_option
        native = select_label(answer, options, self_id=True)
        self.assertEqual(native, pick_option(answer, options, self_id=True))  # native selects and pickers agree
        return native

    def test_decline_wordings_match(self):
        self.assertEqual(self.pick('I do not wish to self-identify', GREENHOUSE_GENDER), 'Decline To Self Identify')
        self.assertEqual(self.pick('I do not wish to self-identify', GREENHOUSE_VETERAN), "I don't wish to answer")
        self.assertEqual(self.pick('I do not wish to self-identify', ['Man', 'Woman', 'Prefer not to say']), 'Prefer not to say')

    def test_gender_and_race_wordings_match(self):
        self.assertEqual(self.pick('Female', ['Man', 'Woman', 'Non-binary']), 'Woman')
        self.assertEqual(self.pick('Asian (Not Hispanic or Latino)', GREENHOUSE_RACE), 'Asian')
        self.assertEqual(self.pick('American Indian or Alaska Native (Not Hispanic or Latino)', GREENHOUSE_RACE), 'American Indian or Alaskan Native')
        self.assertEqual(self.pick('White (Not Hispanic or Latino)', GREENHOUSE_RACE), 'White')
        self.assertEqual(self.pick('Hispanic or Latino', GREENHOUSE_RACE), 'Hispanic or Latino')

    def test_veteran_and_disability_exact_wording_still_wins(self):
        self.assertEqual(self.pick('I am not a protected veteran', GREENHOUSE_VETERAN), 'I am not a protected veteran')
        self.assertEqual(self.pick('No, I do not have a disability and have not had one in the past', ['Yes, I have a disability (or previously had a disability)', 'No, I don’t have a disability', 'I don’t wish to answer']),
                         'No, I don’t have a disability')

    def test_unsure_cases_ask_instead(self):
        # 'not a veteran' and 'veteran but not protected' are different facts, so they never stand in for each other.
        self.assertIsNone(self.pick('I am not a protected veteran', ['I am not a veteran', 'I am a veteran, but not a protected veteran', 'Decline']))
        # Two decline-style options: ambiguous.
        self.assertIsNone(self.pick('I do not wish to self-identify', ['Male', 'Female', 'Prefer not to say', 'Decline to answer']))
        # Caucasian must not read as Asian.
        self.assertIsNone(self.pick('Asian (Not Hispanic or Latino)', ['Caucasian', 'Black', 'Other']))
        # Free text typed under Other is only ever matched exactly.
        self.assertIsNone(self.pick('Genderqueer', GREENHOUSE_GENDER))

    def test_off_outside_self_identification(self):
        from answer_memory import pick_option
        self.assertIsNone(select_label('I do not wish to self-identify', GREENHOUSE_GENDER))
        self.assertIsNone(pick_option('I do not wish to self-identify', GREENHOUSE_GENDER))


if __name__ == '__main__':
    unittest.main()


class EducationProfileTests(unittest.TestCase):
    profile = {'location': 'Phoenix, Az', 'school': 'Example State University', 'degree': 'Bachelor’s Degree', 'discipline': 'Computer Science', 'grad_year': '2027', 'gpa': '3.6', 'sponsorship': 'No'}

    def test_greenhouse_education_labels(self):
        self.assertEqual(match_profile('School*', self.profile), 'Example State University')
        self.assertEqual(match_profile('Degree*', self.profile), 'Bachelor’s Degree')
        self.assertEqual(match_profile('Discipline', self.profile), 'Computer Science')
        self.assertEqual(match_profile('End date year', self.profile), '2027')
        self.assertEqual(match_profile('What is your cumulative GPA?*', self.profile), '3.6')
        self.assertEqual(match_profile('Country*', self.profile), 'United States')
        self.assertEqual(match_profile('Location (City)*', self.profile), 'Phoenix, Az')
        self.assertIsNone(match_profile('Country*', {'location': 'Toronto'}))  # no US state: ask instead

    def test_long_sponsorship_question(self):
        q = 'Do you now, or will you in the future, require sponsorship or support for employment visa status (e.g., H-1B visa status, F-1 STEM OPT training plan, etc.) to work legally in the United States?*'
        self.assertEqual(match_profile(q, self.profile), 'No')
        self.assertIsNone(match_profile('Will you require sponsorship to work in Canada?', self.profile))

    def test_choices(self):
        from answer_memory import pick_option, pick_place, pick_range
        self.assertEqual(pick_option('Bachelor’s Degree', ["Associate's Degree", "Bachelor's Degree", "Master's Degree"]), "Bachelor's Degree")
        self.assertEqual(pick_option('United States', ['United Kingdom +44', 'United States +1']), 'United States +1')
        self.assertEqual(pick_place('Phoenix, Az', ['Phoenix, Arizona, United States', 'Phoenix, Oregon, United States', 'Phoenixville, Pennsylvania, United States']), 'Phoenix, Arizona, United States')
        self.assertIsNone(pick_place('Springfield', ['Springfield, Illinois, United States', 'Springfield, Missouri, United States']))  # two states: ask
        self.assertEqual(pick_range('3.6', ['Below 3.0', '3.0 - 3.49', '3.5 - 3.74', '3.75 - 4.0']), '3.5 - 3.74')
        self.assertIsNone(pick_range('n/a', ['3.0 - 3.49']))
