import unittest
from pathlib import Path
from dataclasses import fields
from streamlit.testing.v1 import AppTest
from career_assessment_engine import CandidateProfile, CareerAssessmentEngine
from program_catalog import PROGRAM_1M, PROGRAM_2M, PROGRAM_GENAI, PROGRAM_FDE


def profile(**changes):
    values = {f.name: 5 for f in fields(CandidateProfile) if f.name.endswith('_score')}
    values.update(candidate_name='Test Candidate', student_email='test@example.com', student_mobile='1234567890', experience_years=3, current_role='Engineer', current_ctc_lpa=8, target_ctc_lpa=16, job_switch_timeline_months=1, interview_stage='Not actively interviewing yet', career_goal='GenAI Engineer', initial_program_preference=PROGRAM_1M, has_deployed_ai=False, has_client_facing_experience=False, has_interview_calls=False, growth_preference='Aggressive growth', weekly_commitment='10+ hours/week', challenge_readiness='Yes, I want to push myself', current_challenges=[])
    values.update(changes)
    return CandidateProfile(**values)


def mcq(overall=70, foundation=60, genai=60, production=60, categories=None):
    return dict(mcq_overall=overall, mcq_foundation=foundation, mcq_genai=genai, mcq_production=production, category_scores=categories or {'ML Fundamentals':70}, question_review=[], correct_total=21)


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from unittest.mock import patch
        from tracker_security import TrackerStore
        self.folder = tempfile.TemporaryDirectory()
        original = TrackerStore.__init__
        test_db = Path(self.folder.name) / 'tracker.sqlite3'
        self.patches = [patch.object(TrackerStore, '__init__', lambda obj: original(obj, test_db)), patch.object(TrackerStore, 'bootstrap'), patch.object(TrackerStore, 'import_legacy')]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.folder.cleanup()

    def test_score_band_boundaries_with_required_criteria(self):
        engine = CareerAssessmentEngine()
        intensive = profile(has_relevant_project=True, growth_preference='Aggressive growth', weekly_commitment='10+ hours/week', challenge_readiness='Yes, I want to push myself')
        consistent = profile(has_relevant_project=True, growth_preference='Normal growth', weekly_commitment='4-6 hours/week', challenge_readiness='Yes, with support')
        self.assertEqual(engine.recommend(intensive, mcq(overall=80))['recommended_path'], PROGRAM_1M)
        self.assertEqual(engine.recommend(intensive, mcq(overall=79.9))['recommended_path'], PROGRAM_2M)
        self.assertEqual(engine.recommend(consistent, mcq(overall=70))['recommended_path'], PROGRAM_2M)
        self.assertEqual(engine.recommend(consistent, mcq(overall=69.9))['recommended_path'], PROGRAM_FDE)
        self.assertEqual(engine.recommend(consistent, mcq(overall=50))['recommended_path'], PROGRAM_FDE)
        self.assertEqual(engine.recommend(consistent, mcq(overall=49.9))['recommended_path'], PROGRAM_GENAI)

    def test_score_alone_cannot_unlock_short_programs(self):
        engine = CareerAssessmentEngine()
        no_project = profile(has_relevant_project=False, has_deployed_ai=False)
        low_commitment = profile(has_relevant_project=True, weekly_commitment='2-3 hours/week')
        low_agility = profile(has_relevant_project=True, growth_preference='Learn and implement steadily')
        low_intensity = profile(has_relevant_project=True, challenge_readiness='Normal pace')
        for candidate in (no_project, low_commitment, low_agility, low_intensity):
            self.assertEqual(engine.recommend(candidate, mcq(overall=90))['recommended_path'], PROGRAM_FDE)

    def test_eighty_plus_can_fall_back_to_two_months(self):
        engine = CareerAssessmentEngine()
        candidate = profile(has_relevant_project=True, growth_preference='Normal growth', weekly_commitment='4-6 hours/week', challenge_readiness='Yes, with support')
        result = engine.recommend(candidate, mcq(overall=85))
        self.assertEqual(result['recommended_path'], PROGRAM_2M)
        self.assertTrue(result['short_program_criteria']['two_month_ready'])
        self.assertFalse(result['short_program_criteria']['one_month_ready'])

    def test_direct_enrollment_is_only_four_months(self):
        engine = CareerAssessmentEngine()
        for program in (PROGRAM_GENAI, PROGRAM_FDE):
            result = engine.direct_enrollment(profile(initial_program_preference=program))
            self.assertEqual(result['recommended_path'], program)
            self.assertIsNone(result['scores']['objective_overall'])
            self.assertIsNone(result['correct_total'])
        for program in (PROGRAM_1M, PROGRAM_2M):
            with self.assertRaises(ValueError): engine.direct_enrollment(profile(initial_program_preference=program))

    def test_direct_ui_skips_test_and_renders_report(self):
        app = AppTest.from_file('streamlit_app.py').run(timeout=30)
        app.radio(key='entry_route').set_value('Choose a 4-month program without a test').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio[1].options, [PROGRAM_GENAI, PROGRAM_FDE])
        self.assertEqual(len(app.slider), 0)
        for field, value in [('Candidate name *','Test Candidate'),('Email ID *','test@example.com'),('Mobile number *','1234567890')]:
            next(w for w in app.text_input if w.label == field).set_value(value)
        app.radio[1].set_value(PROGRAM_FDE)
        app.checkbox[0].check()
        next(b for b in app.button if b.label == 'Continue with Selected 4-Month Program').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.session_state['step'], 4)
        result = app.session_state['assessment_result']
        self.assertEqual(result['recommended_path'], PROGRAM_FDE)
        self.assertIsNone(result['scores']['objective_overall'])
        self.assertFalse(any(x.label == 'Objective Score' for x in app.metric))
        self.assertFalse(any(e.label == "Complete Assessment Answer Review" for e in app.expander))
        # Exercise the report and CSV helpers without running the Streamlit page again.
        import ast, csv, json, tempfile
        from datetime import datetime
        source = ast.parse(Path('streamlit_app.py').read_text(encoding='utf-8'))
        names = {'score_text', 'result_text', 'append_call_record'}
        helpers = ast.Module(body=[node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
        from program_catalog import INSTITUTE_NAME, PROGRAM_DESCRIPTIONS
        from dataclasses import asdict
        from assessment_questions import QUESTIONS
        scope = dict(INSTITUTE_NAME=INSTITUTE_NAME, PROGRAM_DESCRIPTIONS=PROGRAM_DESCRIPTIONS, csv=csv, json=json, datetime=datetime, asdict=asdict, QUESTIONS=QUESTIONS)
        exec(compile(helpers, 'streamlit_app.py', 'exec'), scope)
        candidate = app.session_state['candidate_obj']
        text = scope['result_text'](candidate, result, result['ai_summary_fallback'])
        self.assertIn('Not assessed', text)
        self.assertNotIn('None%', text)
        self.assertIn('direct enrollment', text)
        from types import SimpleNamespace
        from unittest.mock import Mock
        capture = Mock()
        scope['store'] = capture
        class Session(dict):
            def __getattr__(self, name): return self[name]
        scope['st'] = SimpleNamespace(session_state=Session(ai_summary=result['ai_summary_fallback'],profile_data=app.session_state['profile_data']))
        advisor = dict(advisor_name='',lead_status='Interested',payment_status='Not discussed',follow_up_frequency='After 1 week',next_follow_up_date=datetime.now().date(),call_conclusion='Selected directly',sales_notes='',email_status='Not requested')
        scope['append_call_record'](candidate, result, advisor)
        payload = capture.submit.call_args.args[0]
        self.assertIsNone(payload['objective_score'])
        self.assertEqual(json.loads(payload['report_json'])['assessment_status'], 'Not taken - direct enrollment')

    def test_assessment_ui_collects_evidence_and_requires_test(self):
        app = AppTest.from_file('streamlit_app.py').run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any('chatbot' in c.label for c in app.checkbox))
        for field, value in [('Candidate name *','Test Candidate'),('Email ID *','test@example.com'),('Mobile number *','1234567890')]:
            next(w for w in app.text_input if w.label == field).set_value(value)
        next(c for c in app.checkbox if c.label.startswith('I understand short-program')).check()
        next(b for b in app.button if b.label == 'Continue to Technical Assessment').click().run()
        self.assertEqual(app.session_state['step'], 3)
        self.assertEqual(len(app.radio), 30)
        next(b for b in app.button if b.label == 'Generate Diagnostic Report').click().run()
        self.assertEqual(app.session_state['step'], 3)
        self.assertTrue(app.error)
        for question in app.radio: question.set_value(question.options[0])
        next(b for b in app.button if b.label == 'Generate Diagnostic Report').click().run(timeout=30)
        self.assertEqual(app.session_state['step'], 4)
        self.assertFalse(app.exception, [e.message for e in app.exception])


if __name__ == '__main__': unittest.main()
