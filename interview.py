"""Interview question generation and answer evaluation."""

import re
from utils import DEEPSEEK_KEY, call_deepseek


def generate_questions_ai(job):
    prompt = f"""Job: {job['title']} at {job['company']}
Description: {job.get('description','')[:2000]}
Requirements: {job.get('requirements','')[:1000]}

Generate 8 interview questions. Prioritize behavioral and situational (5-6), with only 2-3 technical. Make them specific to this role and company. Return as numbered list. Do NOT repeat the question number in the question text."""
    result = call_deepseek(prompt, "You are a senior hiring manager focused on behavioral and culture-fit assessment. Be specific and challenging.")
    if result:
        qs = []
        for line in result.split('\n'):
            line = line.strip()
            if not line:
                continue
            cleaned = re.sub(r'^\d+[\.\)\-]+\s*', '', line)
            if cleaned and len(cleaned) > 10:
                qs.append(cleaned)
        return qs[:10]
    return None


def generate_questions_simple(job):
    desc = (job.get('description', '') + ' ' + job.get('requirements', '')).lower()
    title = job.get('title', '').lower()
    qs = []
    tech_map = {
        'python': "Walk me through how you'd debug a performance issue in a Python service.",
        'javascript': "Describe a time you had to optimize a slow web application.",
        'java': "Tell me about a complex system you built in Java and the trade-offs you made.",
        'sql': "Describe how you'd investigate a slow database query in production.",
        'aws': "Tell me about a time you designed or migrated a cloud architecture.",
        'docker': "Walk me through how you set up CI/CD for a containerized app.",
        'react': "Describe a challenging UI problem you solved and your approach.",
        'data': "Tell me about a time your data analysis changed a business decision.",
        'api': "Describe how you designed an API and handled versioning or breaking changes.",
        'cloud': "Tell me about a system you scaled and the bottlenecks you hit.",
    }
    for kw, q in tech_map.items():
        if kw in desc and len(qs) < 2:
            qs.append(q)
    behavioral = [
        "Tell me about yourself and your background — focus on what brought you to this field.",
        "Why are you interested in this role and this company specifically?",
        "Describe the most challenging project you worked on. What made it hard and how did you overcome it?",
        "Tell me about a time you disagreed with a coworker or manager. How did you handle it?",
        "Describe a situation where you had to learn something completely new on the job.",
        "Tell me about a time you failed or made a mistake. What happened and what did you learn?",
        "How do you prioritize when you have multiple competing deadlines?",
        "Describe a time you had to influence a team or stakeholder without formal authority.",
    ]
    qs.extend(behavioral)
    if 'senior' in title or 'lead' in title:
        qs.extend([
            "Tell me about a time you had to manage an underperforming team member.",
            "How do you balance hands-on technical work with leadership responsibilities?",
        ])
    if 'manager' in title or 'lead' in title:
        qs.append("Describe your approach to building and scaling a high-performing team.")
    return qs[:10]


def generate_suggested_answer(question, job_title, company, jd_text=""):
    """Generate a model/suggested answer for an interview question."""
    from utils import DEEPSEEK_KEY, call_deepseek
    if not DEEPSEEK_KEY:
        return None
    prompt = f"""Job: {job_title} at {company}
Job Description: {jd_text[:1000]}
Interview Question: {question}

Write a strong, concise model answer (2-3 short paragraphs) using the STAR method where applicable.
Tailor it to the specific role and company. Keep it professional but conversational — like a real person answering, not a textbook."""
    return call_deepseek(prompt, "You are an experienced interview coach. Write realistic, concise model answers.", max_tokens=350)


def evaluate_answer(question, answer):
    if not DEEPSEEK_KEY or len(answer.split()) < 5:
        return None
    prompt = f"""Question: {question}
Candidate's answer: {answer}
Brief feedback (2-3 sentences): what was strong, what to improve, score 1-10."""
    return call_deepseek(prompt, "You are an interview coach. Be constructive and brief.")
