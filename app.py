#!/usr/bin/env python3
"""Job Scraper UI — Streamlit. Usage: streamlit run app.py"""

import re, json, html as _html
import streamlit as st

from utils import (DEEPSEEK_KEY, detect_mode, extract_requirements,
                   extract_salary_from_jd, clean_html)
from scraper import (scrape_linkedin, get_job_details, scrape_similar_jobs,
                     extract_title, extract_company)
from glassdoor import lookup_glassdoor, guess_company_info
from resume import (parse_resume, tailor_resume_simple, tailor_resume_ai,
                    generate_tailored_resume, build_docx, build_tailored_docx)
from interview import (generate_questions_ai, generate_questions_simple,
                       evaluate_answer, improve_answer)

st.set_page_config(page_title="Job Scraper", page_icon="🎯", layout="wide")

# Hide Streamlit branding
st.markdown("""
<style>
/* Hide Streamlit toolbar, footer, branding */
[data-testid="stToolbar"], footer, [data-testid="stFooter"],
.viewerBadge_container__1QSob,
a[href*="/creators/"], a[href*="github"],
iframe[src*="github"], div:has(> a[href*="github"])
{display:none !important;}

/* Subtle header — keep rendered so collapsedControl (< arrow) stays alive */
header { min-height: 0 !important; background: transparent !important; }
header [data-testid="collapsedControl"] { position: fixed; top: 12px; left: 10px; z-index: 99998; }

/* ── Dark Mode ── */
body.dark { --bg: #0e1117; --fg: #fafafa; --card: #1a1c24; --border: #333; }
body.dark [data-testid="stAppViewContainer"] { background: var(--bg) !important; }
body.dark .stMarkdown, body.dark h1, body.dark h2, body.dark h3,
body.dark h4, body.dark h5, body.dark h6, body.dark p, body.dark li,
body.dark span, body.dark label, body.dark div:not([data-testid]) {
    color: var(--fg) !important; }
body.dark [data-testid="stExpander"] { background: var(--card) !important; border-color: var(--border) !important; }
body.dark [data-testid="stExpander"] summary { color: var(--fg) !important; }
body.dark .stTextInput input, body.dark .stTextArea textarea,
body.dark [data-testid="stSelectbox"] div {
    background: var(--card) !important; color: var(--fg) !important; border-color: var(--border) !important; }
body.dark button[kind="secondary"] { background: #2d3143 !important; color: var(--fg) !important; border-color: #444 !important; }
body.dark [data-testid="stMetricValue"] { color: var(--fg) !important; }
body.dark [data-testid="stMetricLabel"], body.dark .stCaption { color: #aaa !important; }
body.dark [data-testid="stProgress"] > div { background: #333 !important; }
body.dark hr { border-color: #333 !important; }
body.dark .stAlert { background: var(--card) !important; }
body.dark [data-testid="stSidebar"] { background: #0a0b10 !important; }
body.dark [data-testid="stSidebar"] * { color: var(--fg) !important; }

/* Theme button */
#_dm_btn { position: fixed; top: 10px; right: 16px; z-index: 99999;
    background: #f0f0f0; border: 1px solid #ccc; border-radius: 20px;
    padding: 5px 12px; cursor: pointer; font-size: 15px; }
body.dark #_dm_btn { background: #333; color: #fff; border-color: #555; }
</style>

<div id="_dm_btn" title="Theme">🌙</div>

<script>
var _mq = window.matchMedia('(prefers-color-scheme:dark)');
function _udm(m){
    var btn = document.getElementById('_dm_btn'); if (!btn) return;
    btn.textContent = {dark:'🌙',light:'☀️',system:'💻'}[m]||'🌙';
}
function _applyDm(){
    var m = localStorage.getItem('_dm')||'system';
    document.body.classList.toggle('dark', m==='dark'||(m==='system'&&_mq.matches));
    _udm(m);
}
_mq.addEventListener('change', function(){
    if ((localStorage.getItem('_dm')||'system')==='system') _applyDm();
});
_applyDm();

// Event delegation (inline onclick gets stripped by React — this survives)
document.addEventListener('click', function(e){
    var d = e.target.closest('#_dm_btn');
    if (!d) return;
    var b = document.body, m = localStorage.getItem('_dm')||'system';
    if (m === 'dark')       { m = 'light'; }
    else if (m === 'light') { m = 'system'; }
    else                    { m = 'dark'; }
    localStorage.setItem('_dm', m);
    _applyDm();
});
</script>
<div id="_x_hide_branding" style="display:none;"></div>
""", unsafe_allow_html=True)


def main():
    st.title("🎯 SG Job Hunting Tool")
    st.caption("Scrape. Research. Tailor. Interview.")

    # Init session state
    defaults = {
        "jobs": [], "selected_job": None, "research": None, "salary_data": None,
        "similar_jobs": [], "tailored_resume": None, "resume_text": "",
        "interview_questions": [], "interview_answers": {},
        "interview_feedback": {}, "interview_scores": {},
        "research_query": "", "salary_query": "",
        "resume_mode": "ai",
        "current_tab": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ── Sidebar ──
    with st.sidebar:
        st.header("🔍 Search")
        keywords = st.text_input("Job title / keywords", placeholder="e.g. Software Engineer Intern")
        country = st.selectbox("Country", ["Singapore", "Malaysia", "Indonesia", "Thailand", "Vietnam", "Philippines", "India", "United States", "United Kingdom", "Australia", "Canada"])
        remote = st.checkbox("Remote only", value=False)

        if st.button("🔍 Search Jobs", type="primary", use_container_width=True):
            with st.spinner("Scraping LinkedIn..."):
                query = keywords.strip()
                if remote:
                    query += " remote"
                if country != "Singapore":
                    query += f" {country}"
                st.session_state.jobs = scrape_linkedin(query)
                st.session_state.selected_job = None
                st.session_state.research = None
                st.session_state.salary_data = None
                st.session_state.similar_jobs = []
            if st.session_state.jobs:
                st.success(f"Found {len(st.session_state.jobs)} jobs")
            else:
                st.warning("No jobs found. Try different keywords.")

        st.divider()

        # ── Resume Upload ──
        st.header("📄 Resume")
        uploaded_file = st.file_uploader("Upload resume", type=["pdf", "docx", "doc", "txt"])
        if uploaded_file:
            resume_bytes = uploaded_file.read()
            st.session_state.resume_text = parse_resume(resume_bytes, uploaded_file.name)
            if st.session_state.resume_text:
                st.success(f"Parsed: {len(st.session_state.resume_text):,} chars")
                with st.expander("Preview"):
                    st.text(st.session_state.resume_text[:500])
            else:
                st.error("Could not parse resume.")

        st.divider()

        # ── Keyboard shortcuts ──
        st.caption("⌨️ Left/Right arrow keys to switch tabs")

    # ── Keyboard navigation ──
    st.markdown("""
    <script>
    document.addEventListener('keydown', function(e){
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight'){
            var tabs = window.parent.document.querySelectorAll('[data-testid="stTab"]');
            if (!tabs.length) tabs = document.querySelectorAll('[data-testid="stTab"]');
            if (!tabs.length) return;
            var current = -1;
            for (var i = 0; i < tabs.length; i++){
                if (tabs[i].getAttribute('aria-selected') === 'true'){ current = i; break; }
            }
            if (current === -1){ tabs[0].click(); return; }
            var next = e.key === 'ArrowLeft'
                ? (current - 1 + tabs.length) % tabs.length
                : (current + 1) % tabs.length;
            tabs[next].click();
        }
    });
    </script>
    """, unsafe_allow_html=True)

    # ── Job detail area ──
    if st.session_state.jobs:
        jobs = st.session_state.jobs
        cols = st.columns([1, 3])

        # Job list
        with cols[0]:
            st.subheader(f"Jobs ({len(jobs)})")
            for i, job in enumerate(jobs):
                title = job.get("title", "Untitled")
                company = job.get("company", "Unknown")
                mode = job.get("mode", "")
                mode_badge = {"Remote": "🟢", "Hybrid": "🟡", "On-site": "🔴"}.get(mode, "")
                snippet = (job.get("description") or "")[:80].strip()
                with st.container():
                    c = st.columns([1, 9])
                    if c[0].button("▶", key=f"sel_{i}", help="Select job"):
                        st.session_state.selected_job = job
                        st.session_state.research = None
                        st.session_state.salary_data = None
                        st.session_state.similar_jobs = []
                        st.session_state.interview_questions = []
                        st.session_state.interview_answers = {}
                        st.session_state.interview_feedback = {}
                        st.session_state.interview_scores = {}
                    c[1].markdown(f"**{title}**  \n{company} {mode_badge}  \n_{snippet}_")
                st.divider()

        # Job detail + tabs
        with cols[1]:
            job = st.session_state.selected_job
            if not job:
                st.info("👈 Select a job from the list")
            else:
                st.subheader(job.get("title", "Untitled"))
                st.caption(f"{job.get('company', 'Unknown')} — {job.get('location', 'N/A')} — {job.get('date_posted', '')}")

                # Logo
                logo = job.get("logo", "")
                if logo:
                    st.image(logo, width=80)

                tab_labels = ["📋 Details", "🔎 Research", "💰 Salary", "📝 Resume", "🎤 Interview"]
                tabs = st.tabs(tab_labels)

                # ── Tab 0: Details ──
                with tabs[0]:
                    desc = job.get("description", "")
                    cleaned = clean_html(desc) if desc else ""
                    if cleaned:
                        with st.expander("Description", expanded=True):
                            st.markdown(cleaned)
                    reqs = job.get("requirements", "")
                    if reqs:
                        with st.expander("Requirements"):
                            st.markdown(reqs)
                    url = job.get("url", "")
                    if url:
                        st.link_button("Open on LinkedIn", url)

                    # Similar jobs
                    st.divider()
                    if st.button("Find Similar Jobs"):
                        with st.spinner("Finding similar jobs..."):
                            st.session_state.similar_jobs = scrape_similar_jobs(job)
                    if st.session_state.similar_jobs:
                        st.subheader("Similar Jobs")
                        for sj in st.session_state.similar_jobs:
                            st.markdown(f"- **{sj.get('title','')}** — {sj.get('company','')}")

                # ── Tab 1: Research ──
                with tabs[1]:
                    company = job.get("company", "")
                    st.subheader(f"Company Research: {company}")
                    if st.button("Research Company"):
                        with st.spinner("Researching..."):
                            st.session_state.research = lookup_glassdoor(company)
                    if st.session_state.research:
                        st.markdown(st.session_state.research)
                    else:
                        st.info("Click the button to research this company.")

                # ── Tab 2: Salary ──
                with tabs[2]:
                    st.subheader("Salary Estimate")
                    if st.button("Estimate Salary"):
                        with st.spinner("Estimating..."):
                            st.session_state.salary_data = guess_company_info(job)
                    sd = st.session_state.salary_data
                    if sd:
                        if isinstance(sd, dict):
                            for k, v in sd.items():
                                st.markdown(f"**{k}**: {v}")
                        else:
                            st.markdown(str(sd))
                    else:
                        st.info("Click the button to estimate salary.")

                # ── Tab 3: Resume ──
                with tabs[3]:
                    st.subheader("Tailor Resume")
                    if not st.session_state.resume_text:
                        st.warning("Upload a resume in the sidebar first.")
                    else:
                        mode = st.radio("Mode", ["ai", "simple"], horizontal=True,
                                        index=0 if st.session_state.resume_mode == "ai" else 1,
                                        key="resume_mode_radio")
                        st.session_state.resume_mode = mode

                        if st.button("Generate Tailored Resume", type="primary"):
                            with st.spinner("Tailoring resume..."):
                                if mode == "ai":
                                    tailored = tailor_resume_ai(
                                        st.session_state.resume_text,
                                        job.get("title", ""),
                                        job.get("company", ""),
                                        job.get("description", ""),
                                        job.get("requirements", "")
                                    )
                                else:
                                    tailored = tailor_resume_simple(
                                        st.session_state.resume_text,
                                        job.get("description", "")
                                    )
                                st.session_state.tailored_resume = tailored

                        if st.session_state.tailored_resume:
                            with st.expander("Tailored Resume", expanded=True):
                                st.markdown(st.session_state.tailored_resume)
                            if uploaded_file and uploaded_file.name.endswith(".docx"):
                                docx_bytes = build_tailored_docx(
                                    uploaded_file.getvalue(),
                                    st.session_state.tailored_resume
                                )
                            else:
                                docx_bytes = build_docx(st.session_state.tailored_resume)
                            st.download_button(
                                "Download DOCX", docx_bytes,
                                file_name="tailored_resume.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            )

                # ── Tab 4: Interview ──
                with tabs[4]:
                    st.subheader("Interview Prep")
                    if st.button("Generate Questions"):
                        with st.spinner("Generating..."):
                            st.session_state.interview_questions = generate_questions_ai(
                                job.get("title", ""),
                                job.get("description", "")
                            )
                            st.session_state.interview_answers = {}
                            st.session_state.interview_feedback = {}
                            st.session_state.interview_scores = {}

                    questions = st.session_state.interview_questions
                    if questions:
                        for i, q in enumerate(questions):
                            qtext = q if isinstance(q, str) else q.get("question", str(q))
                            with st.expander(f"Q{i+1}: {qtext}", expanded=i == 0):
                                answer = st.text_area("Your answer", key=f"ans_{i}", height=100)
                                c1, c2 = st.columns(2)
                                if c1.button("Evaluate", key=f"eval_{i}"):
                                    if answer.strip():
                                        with st.spinner("Evaluating..."):
                                            feedback = evaluate_answer(qtext, answer)
                                            st.session_state.interview_feedback[i] = feedback
                                            score_match = re.search(r'(\d+)/10', feedback)
                                            if score_match:
                                                st.session_state.interview_scores[i] = int(score_match.group(1))
                                if c2.button("Improve", key=f"imp_{i}"):
                                    if answer.strip():
                                        with st.spinner("Improving..."):
                                            improved = improve_answer(qtext, answer)
                                            st.session_state.interview_answers[i] = improved

                                if i in st.session_state.interview_feedback:
                                    st.markdown("**Feedback:**")
                                    st.markdown(st.session_state.interview_feedback[i])
                                if i in st.session_state.interview_answers:
                                    st.markdown("**Suggested Answer:**")
                                    st.markdown(st.session_state.interview_answers[i])

                        # Score summary
                        scores = st.session_state.interview_scores
                        if scores:
                            avg = sum(scores.values()) / len(scores)
                            st.divider()
                            st.metric("Average Score", f"{avg:.1f}/10")
                            for i, s in sorted(scores.items()):
                                st.progress(s / 10, f"Q{i+1}: {s}/10")

    else:
        # Landing page
        st.info("Enter keywords and click Search in the sidebar to start.")
        st.markdown("### Features")
        features = [
            ("Scrape", "Find jobs from LinkedIn with one click. Filter by country, remote, and date range."),
            ("Research", "Look up company reviews and ratings from multiple sources."),
            ("Salary", "Get salary estimates for any role and company."),
            ("Resume", "Upload your resume and tailor it for specific job descriptions with AI."),
            ("Interview", "Generate interview questions and get AI feedback on your answers."),
        ]
        emojis = ["🔍", "🔎", "💰", "📝", "🎤"]
        cols = st.columns(len(features))
        for i, ((title, desc), emoji) in enumerate(zip(features, emojis)):
            with cols[i]:
                st.markdown(f"### {emoji} {title}")
                st.caption(desc)


if __name__ == "__main__":
    main()
