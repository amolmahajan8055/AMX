
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from program_catalog import INSTITUTE_NAME, PROGRAM_1M, PROGRAM_2M, PROGRAM_GENAI, PROGRAM_FDE, PROGRAM_DESCRIPTIONS


@dataclass
class CandidateProfile:
    candidate_name: str
    student_email: str
    student_mobile: str
    experience_years: float
    current_role: str
    current_ctc_lpa: float
    target_ctc_lpa: float
    job_switch_timeline_months: int
    interview_stage: str
    career_goal: str
    initial_program_preference: str

    python_score: int
    ml_score: int
    genai_score: int
    rag_score: int
    agents_score: int
    cloud_score: int
    backend_score: int
    communication_score: int
    client_exposure_score: int
    deployment_score: int
    monitoring_score: int

    has_deployed_ai: bool
    has_client_facing_experience: bool
    has_interview_calls: bool

    growth_preference: str
    weekly_commitment: str
    challenge_readiness: str
    current_challenges: List[str]
    has_relevant_project: bool = False
    project_experience: str = ""
    security_score: int = 0
    development_score: int = 0
    evaluation_score: int = 0
    neural_networks_score: int = 0
    agentic_score: int = 0
    project_delivery_score: int = 0
    presales_score: int = 0
    team_leadership_score: int = 0


class CareerAssessmentEngine:
    PROGRAM_1M = PROGRAM_1M
    PROGRAM_2M = PROGRAM_2M
    PROGRAM_GENAI = PROGRAM_GENAI
    PROGRAM_FDE = PROGRAM_FDE

    def normalize10(self, v: int) -> float:
        return max(0, min(10, int(v))) * 10.0

    def _commitment_score(self, value: str) -> int:
        mapping = {
            "2-3 hours/week": 30,
            "4-6 hours/week": 55,
            "7-10 hours/week": 80,
            "10+ hours/week": 100,
        }
        return mapping.get(value, 55)

    def _challenge_score(self, value: str) -> int:
        mapping = {
            "normal pace": 35,
            "yes, with support": 70,
            "yes, i want to push myself": 100,
        }
        return mapping.get(value.lower().strip(), 70)

    def _growth_score(self, value: str) -> int:
        mapping = {
            "learn and implement steadily": 45,
            "normal growth": 55,
            "aggressive growth": 85,
            "career switch as fast as realistically possible": 100,
        }
        return mapping.get(value.lower().strip(), 55)

    def self_assessment_scores(self, p: CandidateProfile) -> Dict[str, int]:
        foundation = round(
            self.normalize10(p.python_score) * 0.30
            + self.normalize10(p.ml_score) * 0.35
            + self.normalize10(p.neural_networks_score) * 0.25
            + self.normalize10(p.development_score) * 0.10
        )
        genai = round(
            self.normalize10(p.genai_score) * 0.25
            + self.normalize10(p.rag_score) * 0.20
            + self.normalize10(p.agents_score) * 0.20
            + self.normalize10(p.agentic_score) * 0.20
            + self.normalize10(p.evaluation_score) * 0.15
        )
        production = round(
            self.normalize10(p.cloud_score) * 0.15
            + self.normalize10(p.backend_score) * 0.15
            + self.normalize10(p.development_score) * 0.10
            + self.normalize10(p.deployment_score) * 0.20
            + self.normalize10(p.monitoring_score) * 0.15
            + self.normalize10(p.security_score) * 0.15
            + self.normalize10(p.evaluation_score) * 0.10
        )
        interview = round(
            self.normalize10(p.communication_score) * 0.25
            + self.normalize10(p.client_exposure_score) * 0.20
            + self.normalize10(p.project_delivery_score) * 0.20
            + self.normalize10(p.presales_score) * 0.10
            + self.normalize10(p.team_leadership_score) * 0.05
            + (90 if p.has_interview_calls else 50) * 0.10
            + (90 if p.has_client_facing_experience else 45) * 0.10
        )
        return {
            "self_foundation": foundation,
            "self_genai": genai,
            "self_production": production,
            "self_interview": interview,
        }

    def score_mcq(self, questions: list, selected_indices: List[int]) -> Dict[str, Any]:
        rows = []
        category = {}
        correct_total = 0
        for i, q in enumerate(questions):
            selected = selected_indices[i]
            is_correct = selected == q["answer"]
            correct_total += int(is_correct)
            c = q["category"]
            if c not in category:
                category[c] = {"correct": 0, "total": 0}
            category[c]["correct"] += int(is_correct)
            category[c]["total"] += 1
            rows.append({
                "question_no": i + 1,
                "question": q["question"],
                "options": q["options"],
                "category": c,
                "correct": is_correct,
                "selected": q["options"][selected],
                "best_answer": q["options"][q["answer"]],
            })

        cat_scores = {}
        for c, v in category.items():
            cat_scores[c] = round(v["correct"] / v["total"] * 100)

        overall = round(correct_total / len(questions) * 100, 1)
        production_cats = {
            "Deployment & Performance",
            "Security & Governance",
            "Evaluation & Observability",
            "MLOps & Lifecycle",
            "Cloud & Architecture",
            "Production Readiness",
        }
        prod_correct = sum(1 for r in rows if r["category"] in production_cats and r["correct"])
        prod_total = sum(1 for r in rows if r["category"] in production_cats)
        production = round(prod_correct / prod_total * 100, 1) if prod_total else 0.0

        foundation_cats = {"ML Fundamentals", "NLP & Transformers"}
        base_correct = sum(1 for r in rows if r["category"] in foundation_cats and r["correct"])
        base_total = sum(1 for r in rows if r["category"] in foundation_cats)
        foundation = round(base_correct / base_total * 100, 1) if base_total else 0.0

        genai_cats = {"RAG & Retrieval", "Agents & MCP", "Evaluation & Observability", "Project Readiness"}
        gen_correct = sum(1 for r in rows if r["category"] in genai_cats and r["correct"])
        gen_total = sum(1 for r in rows if r["category"] in genai_cats)
        genai = round(gen_correct / gen_total * 100, 1) if gen_total else 0.0

        return {
            "mcq_overall": overall,
            "mcq_foundation": foundation,
            "mcq_genai": genai,
            "mcq_production": production,
            "category_scores": cat_scores,
            "question_review": rows,
            "correct_total": correct_total,
        }

    def _fde_intent(self, p: CandidateProfile) -> bool:
        text = f"{p.current_role} {p.career_goal}".lower()
        keywords = [
            "fde", "forward deployed", "solution architect", "architect",
            "consult", "client", "enterprise", "technical lead", "tech lead",
            "customer", "implementation", "pre-sales", "presales",
        ]
        return any(k in text for k in keywords)

    def recommend(self, p: CandidateProfile, mcq: Dict[str, Any]) -> Dict[str, Any]:
        s = self.self_assessment_scores(p)
        overall = mcq["mcq_overall"]
        foundation = mcq["mcq_foundation"]
        genai_obj = mcq["mcq_genai"]
        production = mcq["mcq_production"]
        cat = mcq["category_scores"]

        weak_categories = [k for k, v in cat.items() if v < 60]
        strong_categories = [k for k, v in cat.items() if v >= 75]

        commitment = self._commitment_score(p.weekly_commitment)
        challenge = self._challenge_score(p.challenge_readiness)
        growth = self._growth_score(p.growth_preference)
        practical_exposure = p.has_relevant_project or p.has_deployed_ai
        high_learning_agility = growth >= 85
        good_learning_agility = growth >= 55
        significant_effort = commitment >= 80 and challenge >= 100
        consistent_effort = commitment >= 55 and challenge >= 70
        one_month_ready = high_learning_agility and significant_effort and practical_exposure
        two_month_ready = good_learning_agility and consistent_effort and practical_exposure

        # Score establishes the readiness band; behavioral and practical evidence
        # determines whether a short, intensive program is suitable.
        if overall >= 80 and one_month_ready:
            recommendation = self.PROGRAM_1M
            reason = (
                "Your assessment shows strong technical understanding. Your learning approach, weekly commitment, "
                "readiness to work intensively and practical project exposure support a focused one-month interview accelerator."
            )
        elif overall >= 70 and two_month_ready:
            recommendation = self.PROGRAM_2M
            reason = (
                "Your assessment shows a good technical foundation. Your consistent weekly commitment, learning agility, "
                "effort readiness and practical project exposure support a two-month path combining project work and interview preparation."
            )
        elif overall >= 50:
            recommendation = self.PROGRAM_FDE
            if overall >= 70:
                missing = []
                if not practical_exposure: missing.append("practical or project exposure")
                if not good_learning_agility: missing.append("learning agility")
                if not consistent_effort: missing.append("consistent weekly commitment and intensive-work readiness")
                reason = (
                    "Your technical score is within a short-program range, but the short programs also require "
                    + ", ".join(missing) + ". The four-month FDE path provides deeper hands-on engineering, deployment and client-facing exposure."
                )
            else:
                reason = (
                    "Your assessment shows a moderate technical foundation. The four-month FDE path is best suited to deepen "
                    "hands-on engineering, deployment, production and client-facing capability."
                )
        else:
            recommendation = self.PROGRAM_GENAI
            reason = (
                "Your assessment indicates significant gaps in core fundamentals. The four-month Data Science / GenAI Foundation path "
                "provides structured learning from the basics before advanced engineering and interview preparation."
            )

        preference_match = p.initial_program_preference == recommendation
        pref_message = (
            f"Your initial preference ({p.initial_program_preference}) is aligned with the diagnostic recommendation."
            if preference_match
            else f"You initially preferred {p.initial_program_preference}, but the diagnostic currently recommends {recommendation}."
        )

        self_vs_test = {
            "foundation_gap": round(s["self_foundation"] - foundation, 1),
            "genai_gap": round(s["self_genai"] - genai_obj, 1),
            "production_gap": round(s["self_production"] - production, 1),
        }

        return {
            "candidate_name": p.candidate_name,
            "assessment_status": "Completed",
            "project_experience": p.project_experience,
            "has_relevant_project": p.has_relevant_project,
            "short_program_criteria": {
                "practical_exposure": practical_exposure,
                "learning_agility": "high" if high_learning_agility else "good" if good_learning_agility else "developing",
                "consistent_effort": consistent_effort,
                "significant_effort": significant_effort,
                "one_month_ready": one_month_ready,
                "two_month_ready": two_month_ready,
            },
            "recommended_path": recommendation,
            "program_description": PROGRAM_DESCRIPTIONS[recommendation],
            "why_this_recommendation": reason,
            "preference_alignment": pref_message,
            "preference_match": preference_match,
            "initial_program_preference": p.initial_program_preference,
            "scores": {
                **s,
                "objective_overall": overall,
                "objective_foundation": foundation,
                "objective_genai": genai_obj,
                "objective_production": production,
                "commitment_score": commitment,
                "growth_intent": growth,
                "challenge_readiness": challenge,
            },
            "category_scores": cat,
            "strong_categories": strong_categories,
            "weak_categories": weak_categories,
            "self_vs_test": self_vs_test,
            "estimated_duration": self._duration(recommendation),
            "current_level": self._level(overall, production),
            "suggested_learning_plan": self._learning_plan(recommendation),
            "mentor_note": self._mentor_note(p, recommendation, weak_categories),
            "sales_advisor_talking_points": self._sales_points(p, recommendation, preference_match),
            "question_review": mcq["question_review"],
            "correct_total": mcq["correct_total"],
            "ai_summary_fallback": self._fallback_summary(p, recommendation, reason, strong_categories, weak_categories, overall, production),
        }

    def direct_enrollment(self, p: CandidateProfile) -> Dict[str, Any]:
        program = p.initial_program_preference
        if program not in {self.PROGRAM_GENAI, self.PROGRAM_FDE}:
            raise ValueError("Direct enrollment is available only for four-month programs. Short programs require an assessment.")
        reason = "You selected the complete four-month learning path and chose to skip the assessment. No technical readiness or short-program eligibility has been assessed."
        return {
            "candidate_name": p.candidate_name,
            "assessment_status": "Not taken - direct enrollment",
            "recommended_path": program,
            "program_description": PROGRAM_DESCRIPTIONS[program],
            "why_this_recommendation": reason,
            "preference_alignment": "Selected directly by the candidate; no diagnostic recommendation was made.",
            "preference_match": True,
            "initial_program_preference": program,
            "scores": {key: None for key in ("objective_overall", "objective_foundation", "objective_genai", "objective_production", "self_foundation", "self_genai", "self_production", "self_interview")},
            "category_scores": {}, "strong_categories": [], "weak_categories": [], "self_vs_test": {},
            "estimated_duration": self._duration(program),
            "current_level": "Not assessed",
            "suggested_learning_plan": self._learning_plan(program),
            "mentor_note": reason,
            "sales_advisor_talking_points": ["Candidate selected a four-month program without taking the assessment."],
            "question_review": [], "correct_total": None,
            "ai_summary_fallback": f"{p.candidate_name}, you selected {program} at {INSTITUTE_NAME}. {reason} {PROGRAM_DESCRIPTIONS[program]}",
        }

    def _duration(self, recommendation: str) -> str:
        return {
            self.PROGRAM_1M: "1 month",
            self.PROGRAM_2M: "2 months",
            self.PROGRAM_GENAI: "4 months",
            self.PROGRAM_FDE: "4 months",
        }[recommendation]

    def _level(self, overall: float, production: float) -> str:
        if overall >= 80 and production >= 70:
            return "Interview-ready / Advanced"
        if overall >= 50:
            return "Intermediate / Builder"
        return "Foundation-building stage"

    def _learning_plan(self, recommendation: str) -> List[str]:
        if recommendation == self.PROGRAM_1M:
            return [
                "Week 1: Project selection, project storylines and impact articulation",
                "Week 2: Interview preparation, technical cross-questioning and architecture defense",
                "Week 3: Resume, LinkedIn and Naukri profile optimization",
                "Week 4: Mock interviews, feedback and gap closure",
            ]
        if recommendation == self.PROGRAM_2M:
            return [
                "Month 1: Strengthen core GenAI/RAG/agents/MCP concepts and build projects from scratch, including development, evaluation, deployment, monitoring, security and an introduction to fine-tuning",
                "Month 2: Build project storylines from scratch, practice technical defense and interview preparation, optimize resume, LinkedIn and Naukri profiles, and complete mock interviews with feedback",
                "Interview preparation, project storylines and technical defense, resume, LinkedIn and Naukri profile optimization, mock interviews and feedback.",
            ]
        if recommendation == self.PROGRAM_FDE:
            return [
                "Month 1: Complete technical foundations in Python, ML, GenAI, RAG and applied engineering for an FDE role",
                "Month 2: Build enterprise AI projects with APIs, backend development and cloud architecture",
                "Month 3: Deployment, monitoring, observability, security, client discovery and solution delivery ownership",
                "Month 4: Architecture decisions, client communication, project storylines, system design, profile optimization and mock interviews",
            ]
        return [
            "Month 1: Complete foundations in Python, data science, machine learning and neural networks, NLP and deep learning",
            "Month 2: GenAI concepts, Transformers, LLMs, prompt engineering, RAG and vector search",
            "Month 3: Hands-on project development, agents, MCP, evaluation, deployment, monitoring and security",
            "Month 4: End-to-end projects, project storylines, resume, LinkedIn and Naukri optimization and mock interviews",
        ]

    def _mentor_note(self, p: CandidateProfile, recommendation: str, weak_categories: List[str]) -> str:
        gaps = ", ".join(weak_categories[:4]) if weak_categories else "no major objective gaps"
        return (
            f"Candidate wants to switch in approximately {p.job_switch_timeline_months} month(s), "
            f"can commit {p.weekly_commitment}, and currently shows priority gaps in: {gaps}. "
            f"Recommended path: {recommendation}."
        )

    def _sales_points(self, p: CandidateProfile, recommendation: str, preference_match: bool) -> List[str]:
        points = [
            "Lead with the diagnostic result, not the fee or duration.",
            "Show the candidate their objective competency gaps and compare them with their self-ratings.",
            "Explain that the shortest suitable path is being recommended rather than automatically pushing the longest program.",
        ]
        if not preference_match:
            points.append(
                f"The candidate preferred {p.initial_program_preference}; explain specifically why the assessment points to {recommendation}."
            )
        else:
            points.append("The candidate's own preference and the assessment are aligned; use this as validation, not pressure.")
        return points

    def _fallback_summary(
        self,
        p: CandidateProfile,
        recommendation: str,
        reason: str,
        strengths: List[str],
        gaps: List[str],
        overall: float,
        production: float,
    ) -> str:
        if recommendation == self.PROGRAM_1M:
            explanation = "Your assessment and reported project experience suggest you can focus on interview preparation, project storylines and profile positioning."
        elif recommendation == self.PROGRAM_2M:
            explanation = "You have a working foundation. Building projects and strengthening production skills will help you prepare for technical interviews."
        else:
            explanation = "Your results suggest starting with the foundations, then building hands-on projects and production skills before interview preparation."
        sections = [
            f"**{p.candidate_name}, here is your assessment summary.**",
            f"**Your readiness**\n- Overall assessment: {overall}%\n- Production readiness: {production}%",
            f"**Suggested program**\n{recommendation}\n\n{explanation}",
            "**Strong areas**\n" + ("\n".join(f"- {area}" for area in strengths[:4]) if strengths else "No area reached the strong range yet. The learning path will help you build these skills."),
            "**Skills to strengthen first**\n" + ("\n".join(f"- {area}" for area in gaps[:5]) if gaps else "No major competency gaps were identified."),
        ]
        if p.initial_program_preference == recommendation:
            sections.append("**Your initial preference**\nYour preferred program aligns with the suggested path.")
        else:
            sections.append(f"**Your initial preference**\nYou selected {p.initial_program_preference}. Your assessment suggests {recommendation} to address the skills above.")
        return "\n\n".join(sections)

    def build_llm_prompt(self, p: CandidateProfile, result: Dict[str, Any]) -> str:
        safe_profile = asdict(p).copy()
        safe_profile.pop("student_mobile", None)
        safe_profile.pop("student_email", None)
        return f"""
You are a neutral AI Career & Program Advisor for {INSTITUTE_NAME}.

Write a concise, evidence-based assessment summary. The course recommendation has already been decided by a deterministic rules engine. DO NOT change it.

Rules:
- Be consultative and non-pushy.
- Explain why the recommended path fits the candidate.
- Compare initial preference vs recommended program.
- Mention 2-4 strengths and 2-4 priority gaps.
- Refer to objective test performance, self-rating, experience, switch timeline and weekly commitment.
- Do not promise a job, interview calls, salary hike, placement, or guaranteed outcome.
- Do not use fear-based sales language.
- Use short Markdown sections: Your readiness, Suggested program, Strong areas, Skills to strengthen first, Your initial preference. Use bullets for scores and skills, with blank lines between sections.
- Avoid internal enrollment rules and sales language.
- Maximum 250 words.

Candidate profile (contact details removed):
{json.dumps(safe_profile, indent=2)}

Diagnostic result:
{json.dumps({
    "recommended_path": result["recommended_path"],
    "program_description": PROGRAM_DESCRIPTIONS[result["recommended_path"]],
    "suggested_learning_plan": result["suggested_learning_plan"],
    "initial_program_preference": result["initial_program_preference"],
    "scores": result["scores"],
    "strong_categories": result["strong_categories"],
    "weak_categories": result["weak_categories"],
    "self_vs_test": result["self_vs_test"],
    "reason": result["why_this_recommendation"],
}, indent=2)}
"""


def generate_ai_summary(profile: CandidateProfile, result: Dict[str, Any]) -> str:
    """
    Optional live LLM summary.
    If OPENAI_API_KEY is unavailable or the API call fails, the deterministic
    summary is returned so the app always works locally.
    """
    import os
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return result["ai_summary_fallback"]

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
        response = client.responses.create(
            model=model,
            input=CareerAssessmentEngine().build_llm_prompt(profile, result),
        )
        text = getattr(response, "output_text", None)
        return text.strip() if text else result["ai_summary_fallback"]
    except Exception:
        return result["ai_summary_fallback"]
