
from dataclasses import asdict
import csv
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from smtp_email import send_report_email
from assessment_questions import QUESTIONS
from tracker_security import TrackerStore
from program_catalog import APP_TITLE, INSTITUTE_NAME, PROGRAM_DESCRIPTIONS, PROGRAM_GENAI, PROGRAM_FDE
from career_assessment_engine import CandidateProfile, CareerAssessmentEngine, generate_ai_summary

load_dotenv(Path(__file__).with_name(".env"))

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
CALL_RECORDS_FILE = DATA_DIR / "call_records.csv"

CALL_RECORD_FIELDS = [
    "created_at", "candidate_name", "student_email", "student_mobile",
    "advisor_name", "current_role", "experience_years",
    "current_ctc_lpa", "target_ctc_lpa", "job_switch_timeline_months",
    "initial_program_preference", "recommended_path", "objective_score",
    "objective_production", "lead_status", "payment_status",
    "follow_up_frequency", "next_follow_up_date", "call_conclusion",
    "sales_notes", "email_status", "report_json",
]

st.set_page_config(page_title=f"{APP_TITLE} | {INSTITUTE_NAME}", page_icon="C", layout="wide")

st.markdown(
    "<style>" + Path(__file__).with_name("brand_styles.css").read_text(encoding="utf-8") + "</style>",
    unsafe_allow_html=True,
)

PROGRAMS = list(PROGRAM_DESCRIPTIONS)

INTERVIEW_STAGES = [
    "Not getting interview calls",
    "Getting calls but rejected in screening/L1",
    "Getting rejected in L2/L3 technical rounds",
    "Reaching final/managerial round but not converting",
    "Offer stage but struggling with HR/salary negotiation",
    "Not actively interviewing yet",
]

def init_state():
    defaults = {
        "step": 1,
        "profile_data": None,
        "assessment_result": None,
        "candidate_obj": None,
        "ai_summary": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def reset_assessment():
    keys = list(st.session_state.keys())
    for k in keys:
        if k.startswith("q_") or k in {"profile_data","assessment_result","candidate_obj","ai_summary","record_id","candidate_referral"}:
            del st.session_state[k]
    st.session_state.step = 1

def score_slider(label, default=5, help_text=None):
    return st.slider(label, 0, 10, default, help=help_text)

def load_call_records():
    return store.records(st.session_state.get("staff_token"))


def append_call_record(profile, result, advisor):
    row = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_name": profile.candidate_name,
        "student_email": profile.student_email,
        "student_mobile": profile.student_mobile,
        "advisor_name": advisor["advisor_name"],
        "current_role": profile.current_role,
        "experience_years": profile.experience_years,
        "current_ctc_lpa": profile.current_ctc_lpa,
        "target_ctc_lpa": profile.target_ctc_lpa,
        "job_switch_timeline_months": profile.job_switch_timeline_months,
        "initial_program_preference": profile.initial_program_preference,
        "recommended_path": result["recommended_path"],
        "objective_score": result["scores"]["objective_overall"],
        "objective_production": result["scores"]["objective_production"],
        "lead_status": advisor["lead_status"],
        "payment_status": advisor["payment_status"],
        "follow_up_frequency": advisor["follow_up_frequency"],
        "next_follow_up_date": advisor["next_follow_up_date"].isoformat(),
        "call_conclusion": advisor["call_conclusion"],
        "sales_notes": advisor["sales_notes"],
        "email_status": advisor["email_status"],
        "report_json": json.dumps(result, ensure_ascii=False),
    }
    row["summary"] = st.session_state.ai_summary
    row["profile_json"] = json.dumps(st.session_state.profile_data, ensure_ascii=False)
    return store.submit(row, st.session_state.get("staff_token"), st.session_state.get("candidate_referral"))


def score_text(value):
    return "Not assessed" if value is None else f"{value}%"


def result_text(profile, result, summary):
    lines = [
        f"{INSTITUTE_NAME} | AI Career Report - {profile.candidate_name}",
        "",
        f"Initial preference: {profile.initial_program_preference}",
        f"Recommended path: {result['recommended_path']}",
        f"Program includes: {result.get('program_description', PROGRAM_DESCRIPTIONS.get(result['recommended_path'], ''))}",
        f"Current level: {result['current_level']}",
        f"Estimated duration: {result['estimated_duration']}",
        f"Assessment status: {result.get('assessment_status', 'Completed')}",
        f"Objective score: {score_text(result['scores']['objective_overall'])}",
        f"Production readiness: {score_text(result['scores']['objective_production'])}",
        "",
        "Personalized summary:",
        summary,
        "",
        f"Relevant project experience: {profile.project_experience or 'Not provided'}",
        "",
        "Strong areas (assessment only):",
        *[f"- {x}" for x in result["strong_categories"]],
        "",
        "Priority gaps (assessment only):",
        *[f"- {x}" for x in result["weak_categories"]],
        "",
        "Suggested learning plan:",
        *[f"- {x}" for x in result["suggested_learning_plan"]],
    ]
    lines.extend(["", "Your submitted profile and self-ratings:"])
    for key, value in asdict(profile).items():
        if result.get('assessment_status', 'Completed') != 'Completed' and key.endswith('_score'):
            continue
        label = key.replace('_score', ' (0-10)').replace('_', ' ').capitalize()
        lines.append(f"{label}: {value}")
    if result.get('assessment_status', 'Completed') == 'Completed':
        lines.extend(["", "Complete assessment answer review:"])
        for answer in result['question_review']:
            question = answer.get('question', QUESTIONS[answer['question_no'] - 1]['question'])
            lines.extend(["", f"Q{answer['question_no']}. {question}", f"Category: {answer['category']}"])
            options = answer.get('options', QUESTIONS[answer['question_no'] - 1]['options'])
            lines.extend(f"  {i+1}. {option}" for i, option in enumerate(options))
            lines.extend([f"Your answer: {answer['selected']}", f"Correct answer: {answer['best_answer']}", f"Result: {'Correct' if answer['correct'] else 'Incorrect'}"])
    return "\n".join(lines)

init_state()

st.markdown(
    f'<div class="ck-brand"><span class="ck-brand-mark"></span><span class="ck-brand-name">{INSTITUTE_NAME}</span></div>',
    unsafe_allow_html=True,
)
st.title(APP_TITLE)
st.caption("Career assessment and personalized learning paths")
st.markdown('<div class="ck-brand-rule"></div>', unsafe_allow_html=True)

store = TrackerStore()
store.bootstrap()
store.import_legacy(CALL_RECORDS_FILE)
staff = store.identity(st.session_state.get("staff_token"))
with st.sidebar:
    st.subheader("Staff Access")
    if staff:
        st.write(f"{staff['name']} | {staff['role'].title()}")
        if st.button("Sign out"):
            store.logout(st.session_state.staff_token)
            st.session_state.clear()
            st.rerun()
        with st.expander("Change my password"):
            with st.form("change_password"):
                new_password = st.text_input("New password (12+ characters)", type="password")
                change = st.form_submit_button("Change password")
            if change:
                try:
                    store.change_password(st.session_state.staff_token, new_password)
                    st.session_state.clear()
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        if staff['role'] == 'sales':
            st.caption("Candidate link: append this to the app URL. Candidates do not need your password.")
            st.code("?ref=" + store.referral(st.session_state.staff_token), language=None)
    else:
        with st.expander("Staff sign in"):
            with st.form("staff_login"):
                login_id = st.text_input("Sales ID / Admin ID")
                login_password = st.text_input("Password", type="password")
                login = st.form_submit_button("Sign in")
            if login:
                token = store.login(login_id, login_password)
                if token:
                    st.session_state.clear()
                    st.session_state.staff_token = token
                    st.rerun()
                st.error("Sign-in failed. Check your credentials or try again later.")

if staff:
    pages = ["Candidate Assessment", "Sales Tracker"]
    if staff['role'] == 'admin': pages.append("Account Management")
    page = st.radio("Workspace", pages, horizontal=True, key="workspace")
else:
    page = "Candidate Assessment"

@st.fragment(run_every="60s")
def show_follow_up_reminders():
    token = st.session_state.get('staff_token')
    if not store.identity(token):
        return
    reminders = store.reminders(token)
    if not reminders:
        st.caption("No calls due today or tomorrow.")
        return
    today = datetime.now().date().isoformat()
    signature = today + json.dumps([(r['record_id'],r['next_follow_up_date']) for r in reminders])
    if st.session_state.get('reminder_signature') != signature:
        for row in reminders[:5]:
            st.toast(f"{row['reminder_status']}: Call {row['candidate_name']} - {row['next_follow_up_date']}")
        st.session_state.reminder_signature = signature
    st.warning(f"{len(reminders)} follow-up call(s) need attention. Open Sales Tracker to record the call and next update.")
    with st.expander("Calls due today, tomorrow or overdue", expanded=True):
        st.dataframe(pd.DataFrame([{key:row.get(key,'') for key in ['reminder_status','candidate_name','student_mobile','next_follow_up_date','sales_id','call_status','sales_notes']} for row in reminders]), hide_index=True)

if staff:
    show_follow_up_reminders()

if page == "Candidate Assessment":
    # ---------- STEP INDICATOR ----------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("1", "Profile & Goal")
    c2.metric("2", "Self-Assessment")
    c3.metric("3", "Test / Direct Selection")
    c4.metric("4", "Report & Advisor" if staff else "Your Results")

    # ---------- STEP 1 + 2 ----------
    if st.session_state.step == 1:
        st.subheader("Step 1 — Candidate Profile, Career Goal & Self-Assessment")
        entry_route = st.radio(
            "How would you like to proceed?",
            ["Check eligibility for a 1- or 2-month accelerator", "Choose a 4-month program without a test"],
            key="entry_route",
        )
        direct = entry_route == "Choose a 4-month program without a test"
        if direct:
            st.info("Choose a complete four-month program and submit your details. The technical test and self-ratings are optional and skipped on this path.")
        else:
            st.info("Complete the assessment to find the learning path that fits your current skills and project experience.")

        with st.form("candidate_profile_form"):
            st.markdown("### A. Basic Details")
            a, b = st.columns(2)
            with a:
                candidate_name = st.text_input("Candidate name *")
                student_email = st.text_input("Email ID *")
                student_mobile = st.text_input("Mobile number *")
                experience_years = st.number_input("Total experience (years)", 0.0, 40.0, 3.0, 0.5)
                current_role = st.text_input("Current role")
            with b:
                current_ctc_lpa = st.number_input("Current CTC (LPA)", 0.0, 200.0, 8.0, 0.5)
                target_ctc_lpa = st.number_input("Target CTC (LPA)", 0.0, 300.0, 16.0, 0.5)
                job_switch_timeline_months = st.number_input("Desired job-switch timeline (months)", 0, 36, 3, 1)
                interview_stage = st.selectbox("Current job-search/interview stage", INTERVIEW_STAGES)
                career_goal = st.text_area("Career goal / target role", placeholder="Example: GenAI Engineer, FDE, AI Architect, Senior Data Scientist...")

            st.markdown("### B. Initial Program Preference")
            st.markdown("#### Available Learning Paths")
            available_programs = [PROGRAM_GENAI, PROGRAM_FDE] if direct else PROGRAMS
            for program in available_programs:
                description = PROGRAM_DESCRIPTIONS[program]
                st.markdown(f"**{program}**")
                st.write(description)
            initial_program_preference = st.radio(
                "Before seeing your assessment score, which path do you currently feel suits you best?",
                available_programs,
                help="This is captured before the test. The final recommendation may be different."
            )

            has_relevant_project = False
            project_experience = ""
            if not direct:
                has_relevant_project = st.checkbox("I have worked on a chatbot, RAG application or AI agent project")
                project_experience = st.text_area("Describe your project and your own contribution (optional)", help="If you wish, explain the use case, what you built, tools used, and evaluation or deployment.")
                st.markdown("### C. Rate Your Current Skills (0 = no exposure, 10 = can explain/build independently)")
                cols = st.columns(3)
                with cols[0]:
                    ml_score = score_slider("Machine Learning", 5)
                    python_score = score_slider("Python", 6)
                    neural_networks_score = score_slider("Neural Networks", 4)
                    rag_score = score_slider("RAG", 4)
                    agents_score = score_slider("AI Agent Development", 3)
                    agentic_score = score_slider("Agentic AI / Multi-Agent Workflows", 3)
                    genai_score = score_slider("GenAI / LLMs", 5)
                with cols[1]:
                    cloud_score = score_slider("Cloud (AWS / Azure)", 4)
                    monitoring_score = score_slider("Model Monitoring / Observability", 3)
                    security_score = score_slider("Security Best Practices", 3)
                    development_score = score_slider("Development", 4)
                    backend_score = score_slider("Backend / APIs", 4)
                    evaluation_score = score_slider("Testing / Evaluation / Guardrails", 3)
                with cols[2]:
                    communication_score = score_slider("Communication /presentation/story line", 6)
                    project_delivery_score = score_slider("Project Delivery", 4)
                    presales_score = score_slider("PoCs / Demos / Presales Activities", 4)
                    client_exposure_score = score_slider("Client / Stakeholder Management", 5)
                    team_leadership_score = score_slider("Team Leading / Team Building", 4)
                    deployment_score = score_slider("Deployment", 3)

                st.markdown("### D. Experience & Readiness")
                r1, r2, r3 = st.columns(3)
                with r1:
                    has_deployed_ai = st.checkbox("I have deployed an AI/ML/GenAI solution")
                    has_client_facing_experience = st.checkbox("I have client-facing/stakeholder-facing experience")
                    has_interview_calls = st.checkbox("I am currently getting interview calls")
                with r2:
                    weekly_commitment = st.selectbox(
                        "Realistic weekly commitment",
                        ["2-3 hours/week", "4-6 hours/week", "7-10 hours/week", "10+ hours/week"],
                        index=1,
                    )
                    growth_preference = st.selectbox(
                        "Preferred growth approach",
                        ["Learn and implement steadily", "Normal growth", "Aggressive growth", "Career switch as fast as realistically possible"],
                        index=1,
                    )
                with r3:
                    challenge_readiness = st.selectbox(
                        "How hard are you willing to push yourself?",
                        ["Normal pace", "Yes, with support", "Yes, I want to push myself"],
                        index=1,
                    )

                current_challenges = st.multiselect(
                    "What are your current challenges?",
                    [
                        "Not getting enough interview calls",
                        "Getting rejected in L1/screening",
                        "Getting rejected in L2/L3 technical rounds",
                        "Weak project storytelling",
                        "Weak resume / LinkedIn / Naukri",
                        "Weak ML fundamentals",
                        "Weak GenAI / RAG knowledge",
                        "Weak AI Agent / Agentic AI knowledge",
                        "No strong end-to-end projects",
                        "Weak cloud / deployment exposure",
                        "Weak production monitoring / observability",
                        "Weak communication / client-facing confidence",
                        "HR / salary negotiation difficulty",
                    ]
                )

            else:
                python_score = ml_score = genai_score = rag_score = agents_score = 0
                cloud_score = backend_score = deployment_score = monitoring_score = communication_score = client_exposure_score = 0
                security_score = development_score = evaluation_score = neural_networks_score = agentic_score = project_delivery_score = 0
                presales_score = team_leadership_score = 0
                has_deployed_ai = has_client_facing_experience = has_interview_calls = False
                weekly_commitment = "4-6 hours/week"
                growth_preference = "Learn and implement steadily"
                challenge_readiness = "Normal pace"
                current_challenges = []

            consent = st.checkbox(
                "I confirm my selected four-month program and understand that technical readiness has not been assessed."
                if direct else "I understand short-program eligibility depends on my assessment and project experience, and the recommended program may differ from my preference."
            )
            go = st.form_submit_button("Continue with Selected 4-Month Program" if direct else "Continue to Technical Assessment", type="primary", use_container_width=True)

        if go:
            if not candidate_name.strip() or "@" not in student_email or not student_mobile.strip():
                st.error("Please enter candidate name, a valid email ID and mobile number.")
            elif not consent:
                st.error("Please confirm the assessment/recommendation acknowledgement.")
            else:
                st.session_state.candidate_referral = st.query_params.get("ref")
                st.session_state.profile_data = dict(
                    candidate_name=candidate_name.strip(),
                    student_email=student_email.strip(),
                    student_mobile=student_mobile.strip(),
                    experience_years=experience_years,
                    current_role=current_role.strip(),
                    current_ctc_lpa=current_ctc_lpa,
                    target_ctc_lpa=target_ctc_lpa,
                    job_switch_timeline_months=job_switch_timeline_months,
                    interview_stage=interview_stage,
                    career_goal=career_goal.strip(),
                    initial_program_preference=initial_program_preference,
                    python_score=python_score, ml_score=ml_score,
                    genai_score=genai_score, rag_score=rag_score, agents_score=agents_score,
                    cloud_score=cloud_score, backend_score=backend_score,
                    communication_score=communication_score, client_exposure_score=client_exposure_score,
                    deployment_score=deployment_score, monitoring_score=monitoring_score,
                    security_score=security_score, development_score=development_score,
                    evaluation_score=evaluation_score, neural_networks_score=neural_networks_score,
                    agentic_score=agentic_score, project_delivery_score=project_delivery_score,
                    presales_score=presales_score, team_leadership_score=team_leadership_score,
                    has_deployed_ai=has_deployed_ai,
                    has_client_facing_experience=has_client_facing_experience,
                    has_interview_calls=has_interview_calls,
                    growth_preference=growth_preference,
                    weekly_commitment=weekly_commitment,
                    challenge_readiness=challenge_readiness,
                    current_challenges=current_challenges,
                    has_relevant_project=has_relevant_project,
                    project_experience=project_experience.strip(),
                )
                if direct:
                    candidate = CandidateProfile(**st.session_state.profile_data)
                    result = CareerAssessmentEngine().direct_enrollment(candidate)
                    st.session_state.candidate_obj = candidate
                    st.session_state.assessment_result = result
                    st.session_state.ai_summary = result["ai_summary_fallback"]
                    st.session_state.step = 4
                else:
                    st.session_state.step = 3
                st.rerun()

    # ---------- STEP 3 ----------
    elif st.session_state.step == 3:
        p = st.session_state.profile_data
        st.subheader("Step 3 — 30-Question Technical Readiness Assessment")
        st.write(f"**Candidate:** {p['candidate_name']}  |  **Initial preference:** {p['initial_program_preference']}")
        st.caption("Choose one answer for each question. Your report will show your responses and the correct answers after completion.")

        with st.form("technical_assessment"):
            selected_indices = []
            for i, q in enumerate(QUESTIONS, start=1):
                with st.container(border=True):
                    st.markdown(f"**Q{i}. {q['question']}**")
                    value = st.radio(
                        "Select one",
                        q["options"],
                        index=None,
                        key=f"q_{i}",
                        label_visibility="collapsed",
                    )
                    selected_indices.append(q["options"].index(value) if value in q["options"] else None)

            submitted = st.form_submit_button("Generate Diagnostic Report", type="primary", use_container_width=True)

        if submitted:
            missing = [i + 1 for i, v in enumerate(selected_indices) if v is None]
            if missing:
                st.error(f"Please answer all 30 questions. Missing: {', '.join(map(str, missing))}")
            else:
                candidate = CandidateProfile(**p)
                engine = CareerAssessmentEngine()
                mcq = engine.score_mcq(QUESTIONS, selected_indices)
                result = engine.recommend(candidate, mcq)
                summary = generate_ai_summary(candidate, result)
                st.session_state.candidate_obj = candidate
                st.session_state.assessment_result = result
                st.session_state.ai_summary = summary
                st.session_state.step = 4
                st.rerun()

        if st.button("← Back to Profile"):
            st.session_state.step = 1
            st.rerun()

    # ---------- STEP 4 ----------
    elif st.session_state.step == 4:
        profile = st.session_state.candidate_obj
        result = st.session_state.assessment_result
        summary = st.session_state.ai_summary
        scores = result["scores"]
        if not st.session_state.get("record_id"):
            initial_advisor = dict(advisor_name=staff['name'] if staff else "", lead_status="Assessment completed", payment_status="Not discussed", follow_up_frequency="", next_follow_up_date=date.today(), call_conclusion="", sales_notes="", email_status="Not requested")
            st.session_state.record_id = append_call_record(profile, result, initial_advisor)


        assessed = result.get("assessment_status", "Completed") == "Completed"
        if assessed and summary == result.get('ai_summary_fallback') and '\n' not in summary:
            summary = CareerAssessmentEngine()._fallback_summary(
                profile, result['recommended_path'], result['why_this_recommendation'],
                result['strong_categories'], result['weak_categories'],
                scores['objective_overall'], scores['objective_production'],
            )
            st.session_state.ai_summary = summary
            result['ai_summary_fallback'] = summary

        if not assessed:
            st.subheader("Selected Program - Direct Enrollment")
            st.info("You selected this program without taking the assessment. Your technical readiness has not been assessed.")
            with st.container(border=True):
                st.markdown(summary)
        else:
            st.subheader("Step 4 — Personalized Career Readiness Report")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Objective Score", score_text(scores["objective_overall"]))
            m2.metric("GenAI Readiness", score_text(scores["objective_genai"]))
            m3.metric("Production Readiness", score_text(scores["objective_production"]))
            m4.metric("Correct Answers", "Not taken" if result["correct_total"] is None else f"{result['correct_total']}/30")

            st.markdown("### Your Career Summary")
            with st.container(border=True):
                st.markdown(summary)

            st.markdown("### Preference vs Diagnostic Recommendation")
            compare = pd.DataFrame({
                "": ["Candidate's Initial Preference", "Diagnostic Recommendation"],
                "Program": [profile.initial_program_preference, result["recommended_path"]],
            })
            st.dataframe(compare, hide_index=True, use_container_width=True)
            if result["preference_match"]:
                st.success("The candidate's initial preference is aligned with the diagnostic recommendation.")
            else:
                st.info("Your suggested path differs from your initial preference. Your results below explain which skills to strengthen.")

        st.markdown("### Why This Path")
        st.success(f"**{result['recommended_path']}** — {result['estimated_duration']}")
        st.write(result.get("program_description", PROGRAM_DESCRIPTIONS.get(result["recommended_path"], "")))
        st.write(result["why_this_recommendation"])

        if assessed:
            st.markdown("### Objective Competency Breakdown")
            cat_df = pd.DataFrame(
                [{"Competency": k, "Score %": v, "Status": "Strong" if v >= 75 else "Developing" if v >= 60 else "Needs Improvement"}
                 for k, v in result["category_scores"].items()]
            ).sort_values("Score %")
            st.dataframe(cat_df, hide_index=True, use_container_width=True)
            st.bar_chart(cat_df.set_index("Competency")["Score %"], horizontal=True)

            st.markdown("### Self-Rating vs Objective Test")
            gap_df = pd.DataFrame([
                {"Area": "Foundations", "Self-rating %": scores["self_foundation"], "Objective %": scores["objective_foundation"]},
                {"Area": "GenAI", "Self-rating %": scores["self_genai"], "Objective %": scores["objective_genai"]},
                {"Area": "Production", "Self-rating %": scores["self_production"], "Objective %": scores["objective_production"]},
            ])
            st.dataframe(gap_df, hide_index=True, use_container_width=True)
            st.caption("This comparison helps identify where confidence and demonstrated knowledge differ.")

            a, b = st.columns(2)
            with a:
                st.markdown("#### Strong Areas")
                if result["strong_categories"]:
                    for x in result["strong_categories"]:
                        st.success(x)
                else:
                    st.info("No competency crossed the strong threshold yet.")
            with b:
                st.markdown("#### Priority Gaps")
                if result["weak_categories"]:
                    for x in result["weak_categories"]:
                        st.warning(x)
                else:
                    st.success("No major competency gap detected.")

        st.markdown("### Suggested Learning Path")
        for x in result["suggested_learning_plan"]:
            st.write(f"- {x}")

        with st.expander("Your submitted profile and self-ratings"):
            submitted = asdict(profile)
            if not assessed:
                submitted = {k:v for k,v in submitted.items() if not k.endswith('_score')}
            st.dataframe(pd.DataFrame([{"Field":k.replace('_score',' (0-10)').replace('_',' ').capitalize(), "Your response":str(v)} for k,v in submitted.items()]), hide_index=True)
        if assessed:
            with st.expander("Complete Assessment Answer Review", expanded=True):
                for answer in result['question_review']:
                    question = answer.get('question', QUESTIONS[answer['question_no']-1]['question'])
                    st.markdown(f"**Q{answer['question_no']}. {question}**")
                    for option in answer.get('options', QUESTIONS[answer['question_no']-1]['options']):
                        st.write(f"- {option}")
                    (st.success if answer['correct'] else st.error)("Correct" if answer['correct'] else "Incorrect")
                    st.write("Your answer:", answer['selected'])
                    st.write("Correct answer:", answer['best_answer'])
                    st.divider()

        if staff:
            st.divider()
            st.subheader("Advisor / Sales Call Closure")
            st.caption("These fields are for the internal team and are saved to the Sales Tracker.")

            with st.form("advisor_closure"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    advisor_name = staff["name"]
                    st.text_input("Call advisor", value=advisor_name, disabled=True)
                    lead_status = st.selectbox(
                        "Call outcome / lead status",
                        ["Interested", "Highly interested", "Follow-up needed", "Not interested", "Converted / Enrolled", "Paid"],
                    )
                    payment_status = st.selectbox(
                        "Payment status",
                        ["Not discussed", "Fee shared", "Payment pending", "Partial payment", "Paid in full", "Not applicable"],
                    )
                with c2:
                    follow_up_frequency = st.selectbox(
                        "Follow-up plan",
                        ["Within 2 days", "After 1 week", "After 1 month", "Next quarter", "No follow-up"],
                        index=1,
                    )
                    default_days = {"Within 2 days": 2, "After 1 week": 7, "After 1 month": 30, "Next quarter": 90, "No follow-up": 0}
                    use_custom_closure_date = st.checkbox("Use custom follow-up date")
                    next_follow_up_date = st.date_input(
                        "Expected next follow-up date",
                        value=date.today() + timedelta(days=default_days[follow_up_frequency]),
                    )
                with c3:
                    send_email = st.checkbox("Email report to student", value=False)
                    call_conclusion = st.text_area(
                        "One-line call conclusion",
                        value=(f"Recommended {result['recommended_path']} based on assessment and project experience." if assessed else f"Candidate selected {result['recommended_path']} directly; assessment not taken."),
                        height=90,
                    )

                sales_notes = st.text_area("Internal sales/advisor notes", height=90)
                save = st.form_submit_button("Save Call Record", type="primary", use_container_width=True)

            if save:
                if not advisor_name.strip():
                    st.error("Please enter the call advisor name.")
                else:
                    email_status = "Not requested"
                    if send_email:
                        ok, email_status = send_report_email(
                            profile.student_email,
                            f"{INSTITUTE_NAME} | Complete Assessment Report - {profile.candidate_name}",
                            result_text(profile, result, summary),
                        )
                        (st.success if ok else st.warning)(email_status)
                    next_follow_up_date = '' if follow_up_frequency == 'No follow-up' else next_follow_up_date if use_custom_closure_date else date.today() + timedelta(days=default_days[follow_up_frequency])
                    advisor = {
                        "advisor_name": advisor_name.strip(),
                        "lead_status": lead_status,
                        "payment_status": payment_status,
                        "follow_up_frequency": follow_up_frequency,
                        "next_follow_up_date": next_follow_up_date,
                        "call_conclusion": call_conclusion.strip(),
                        "sales_notes": sales_notes.strip(),
                        "email_status": email_status,
                    }
                    store.update(st.session_state.staff_token, st.session_state.record_id, advisor)
                    st.success("Call record saved to your private tracker.")

        report_txt = result_text(profile, result, summary)
        st.download_button(
            "Download Full Report ? Inputs, 30 Answers & Summary (TXT)",
            report_txt.encode("utf-8"),
            file_name=f"{profile.candidate_name.replace(' ', '_')}_career_readiness_report.txt",
            mime="text/plain",
            use_container_width=True,
        )

        if st.button("Start New Candidate Assessment" if staff else "Start a New Assessment", use_container_width=True):
            reset_assessment()
            st.rerun()

if page == "Sales Tracker" and staff:
    st.subheader("Sales Follow-up Tracker")
    records = load_call_records()
    if not records:
        st.info("No call records saved yet.")
    else:
        df = pd.DataFrame(records)
        st.dataframe(df, hide_index=True, use_container_width=True)

        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Download Accessible Call Records CSV",
            csv_bytes,
            file_name=f"call_records_{date.today().isoformat()}.csv",
            mime="text/csv",
        )

        st.markdown("### Quick Follow-up View")
        if "next_follow_up_date" in df.columns:
            follow = df.copy()
            follow["next_follow_up_date"] = pd.to_datetime(follow["next_follow_up_date"], errors="coerce")
            follow = follow.sort_values("next_follow_up_date")
            show_cols = [c for c in [
                "candidate_name", "student_mobile", "recommended_path", "lead_status",
                "payment_status", "advisor_name", "next_follow_up_date", "call_conclusion"
            ] if c in follow.columns]
            st.dataframe(follow[show_cols], hide_index=True, use_container_width=True)

    if staff['role'] == 'admin' and records:
        with st.expander("Assign candidate to sales executive"):
            sales_accounts = [a for a in store.accounts(st.session_state.staff_token) if a['role'] == 'sales']
            with st.form("assign_candidate"):
                record_id = st.selectbox("Candidate record", [r['record_id'] for r in records], format_func=lambda rid: next(f"{r['candidate_name']} ({rid[:8]})" for r in records if r['record_id']==rid))
                owner = st.selectbox("Sales executive", [a['id'] for a in sales_accounts], format_func=lambda uid: next(f"{a['name']} ({uid})" for a in sales_accounts if a['id']==uid))
                assign = st.form_submit_button("Assign record")
            if assign:
                store.assign(st.session_state.staff_token, record_id, owner)
                st.rerun()
    if records:
        with st.expander("View saved candidate report / update follow-up"):
            selected = st.selectbox("Saved candidate", [r['record_id'] for r in records], format_func=lambda rid: next(f"{r['candidate_name']} ({rid[:8]})" for r in records if r['record_id']==rid))
            record = next(r for r in store.records(st.session_state.staff_token) if r['record_id']==selected)
            st.write(record.get('summary', ''))
            if record.get('report_json'):
                saved = json.loads(record['report_json'])
                st.write(saved.get('program_description', ''))
            if record.get('call_history'):
                st.markdown("#### Call and Follow-up History")
                st.dataframe(pd.DataFrame(record['call_history']), hide_index=True)
            with st.form("saved_follow_up"):
                call_status = st.selectbox("Call activity", ['Schedule only', 'Call completed', 'No answer', 'Rescheduled'])
                notes = st.text_area("New call update / outcome", help="Required when recording a completed call, no answer or reschedule.")
                outcomes = ['Interested','Highly interested','Follow-up needed','Not interested','Converted / Enrolled','Paid']
                outcome = st.selectbox("Lead status", outcomes, index=outcomes.index(record['lead_status']) if record.get('lead_status') in outcomes else 0)
                follow_plan = st.selectbox("Next follow-up plan", ['After 1 week', 'After 1 month', 'Within 2 days', 'Next quarter', 'No follow-up'])
                manual_date = st.checkbox("Use a custom follow-up date")
                follow_date = st.date_input("Custom next follow-up", value=date.today())
                update = st.form_submit_button("Save call update and follow-up")
            if update:
                days = {'After 1 week':7, 'After 1 month':30, 'Within 2 days':2, 'Next quarter':90}
                next_date = '' if follow_plan == 'No follow-up' else follow_date if manual_date else date.today()+timedelta(days=days[follow_plan])
                try:
                    store.update(st.session_state.staff_token,selected,dict(sales_notes=notes,lead_status=outcome,next_follow_up_date=next_date,follow_up_frequency=follow_plan,call_status=call_status))
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

if page == "Account Management" and staff and staff['role'] == 'admin':
    st.subheader("Account Management")
    accounts = store.accounts(st.session_state.staff_token)
    st.dataframe(pd.DataFrame([{k:v for k,v in a.items() if k!='referral'} for a in accounts]), hide_index=True)
    st.caption("Generate a unique password for each of the ten sales IDs. Resetting a password signs that account out.")
    with st.form("reset_staff_password"):
        sales_id = st.selectbox("Sales account", [a['id'] for a in accounts if a['role']=='sales'])
        display_name = st.text_input("Executive name", value=next(a['name'] for a in accounts if a['id']==sales_id))
        generate = st.form_submit_button("Generate password")
    if generate:
        password = store.reset_password(st.session_state.staff_token,sales_id,display_name.strip() or sales_id)
        st.success(f"Password generated for {sales_id}. Copy it now; it is shown only once.")
        st.code(password, language=None)

st.caption("The recommendation engine is diagnostic guidance. It does not guarantee placement, interview calls, compensation or salary increase.")
