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

st.set_page_config(page_title="Job Scraper", page_icon="🎯", layout="wide", initial_sidebar_state="expanded")

# Hide Streamlit branding
st.markdown("""
<style>
[data-testid="stToolbar"], footer, [data-testid="stFooter"],
.viewerBadge_container__1QSob,
a[href*="/creators/"], a[href*="github"],
iframe[src*="github"], div:has(> a[href*="github"])
{display:none !important;}
header { background: transparent !important; }
[data-testid="collapsedControl"] { position: fixed; top: 12px; left: 10px; z-index: 99998; }
</style>
<div id="_x_hide_branding" style="display:none;"></div>
""", unsafe_allow_html=True)

""", unsafe_allow_html=True)


def main():
    st.title("🎯 SG Job Hunting Tool")
    st.caption("🔍 Search jobs · 📄 Tailor resume · 🎤 Interview prep · 💰 Salary insights")

    # Keyboard nav
    st.markdown("""
    <script>
    (function() {
        function clickBtn(text) {
            var btns = window.parent.document.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                if (btns[i].innerText && btns[i].innerText.indexOf(text) !== -1) {
                    btns[i].click(); return true;
                }
            }
            return false;
        }
        document.addEventListener('keydown', function(e) {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            if (e.key === 'ArrowLeft') { clickBtn('◀'); e.preventDefault(); }
            if (e.key === 'ArrowRight') { clickBtn('▶'); e.preventDefault(); }
        });
    })();
    </script>
    """, unsafe_allow_html=True)

    # ── Sidebar ──
    with st.sidebar:
        st.header("⚙️ Settings")
        kw = st.text_input("Job title / keywords", placeholder="e.g. software engineer")
        company_filter = st.text_input("Company (optional)", placeholder="e.g. Google, Shopee")
        mode_filter = st.multiselect("Work mode filter", ["🏠 Remote", "🏢🏠 Hybrid", "🏢 In-office"], default=[])
        max_jobs = st.slider("Max jobs", 10, 50, 25)
        if st.button("🔍 Find Jobs", type="primary", use_container_width=True):
            st.session_state.job_idx = 0
            st.session_state.glassdoor_cache = {}
            st.session_state.custom_job = None
            search = kw
            if company_filter.strip():
                search = f"{kw} {company_filter.strip()}" if kw else company_filter.strip()
            with st.spinner(f"Searching for '{search}'..."):
                st.session_state.jobs = scrape_linkedin(search, max_jobs)
            st.rerun()
        st.divider()

        st.subheader("📋 Custom Job")
        with st.expander("Paste a job for analysis", expanded=False):
            custom_url = st.text_input("LinkedIn job URL", placeholder="https://www.linkedin.com/jobs/view/...", key="custom_url")
            custom_desc = st.text_area("Or paste job description", placeholder="Paste the full job posting here...", height=120, key="custom_desc")
            if st.button("🔍 Analyze This Job", use_container_width=True, key="custom_btn"):
                if custom_url:
                    with st.spinner("Fetching job..."):
                        desc, reqs = get_job_details(custom_url)
                        if desc:
                            st.session_state.custom_job = {
                                "title": extract_title(desc), "company": extract_company(desc),
                                "url": custom_url, "description": desc, "requirements": reqs,
                                "mode": detect_mode(desc), "date_posted": "", "source": "custom"
                            }
                            st.session_state.jobs = [st.session_state.custom_job]
                            st.session_state.job_idx = 0
                            st.session_state.glassdoor_cache = {}
                            st.rerun()
                        else:
                            st.error("Could not fetch job — site may block datacenter IPs.")
                elif custom_desc.strip():
                    st.session_state.custom_job = {
                        "title": extract_title(custom_desc), "company": extract_company(custom_desc),
                        "url": "", "description": custom_desc,
                        "requirements": extract_requirements(custom_desc),
                        "mode": detect_mode(custom_desc), "date_posted": "", "source": "custom"
                    }
                    st.session_state.jobs = [st.session_state.custom_job]
                    st.session_state.job_idx = 0
                    st.session_state.glassdoor_cache = {}
                    st.rerun()

        st.divider()
        st.subheader("📄 Resume")
        resume_file = st.file_uploader("Upload (PDF/DOCX/DOC/TXT)", type=["pdf", "docx", "doc", "txt", "md"])
        if resume_file:
            if "resume_filename" not in st.session_state or st.session_state.resume_filename != resume_file.name:
                st.session_state.resume_filename = resume_file.name
                st.session_state.resume_bytes = resume_file.getvalue()
                st.session_state.resume_text = parse_resume(resume_file)
                st.session_state.tailored_text = None
                if st.session_state.resume_text:
                    st.success(f"Loaded: {resume_file.name} ({len(st.session_state.resume_text)} chars)")
                else:
                    st.error("Could not read file. For .doc, try saving as .docx first.")

        if DEEPSEEK_KEY:
            st.success("DeepSeek AI connected")
            st.session_state.use_ai_tailor = True
            st.session_state.use_ai_questions = True
        else:
            st.warning("Add DEEPSEEK_API_KEY to .env or st.secrets then restart")
            st.session_state.use_ai_tailor = False
            st.session_state.use_ai_questions = False

    # ── Early exit if no search ──
    if not kw and not company_filter.strip() and not st.session_state.get("custom_job"):
        st.divider()
        st.subheader("🚀 Features")
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            st.markdown("##### 🔍 Job Search")
            st.caption("Scrape LinkedIn jobs in Singapore with smart text search and company filters.")
        with f2:
            st.markdown("##### 📄 Resume Tailor")
            st.caption("AI-powered resume rewriting to match job descriptions and beat ATS filters.")
        with f3:
            st.markdown("##### 🎤 Mock Interview")
            st.caption("Practice with AI-generated questions, get feedback, and improve your answers.")
        with f4:
            st.markdown("##### 💰 Salary Intel")
            st.caption("Glassdoor ratings, salary estimates, and AI-powered company research.")
        st.divider()
        st.info("👈 Open the sidebar to search jobs, upload your resume, and configure settings")
        return

    if "jobs" not in st.session_state or st.session_state.jobs is None:
        return
    if not st.session_state.jobs:
        st.warning("No jobs found — LinkedIn may be blocking requests, or try different keywords.")
        return

    jobs = st.session_state.jobs
    if "job_idx" not in st.session_state:
        st.session_state.job_idx = 0

    total_found = len(jobs)
    if mode_filter:
        jobs = [j for j in jobs if j.get("mode", "") in mode_filter]
    if not jobs:
        st.warning("No jobs match the selected work mode filter. Adjust filters in the sidebar.")
        return

    idx = st.session_state.job_idx
    if idx >= len(jobs):
        idx = 0
        st.session_state.job_idx = 0
    total = len(jobs)

    if mode_filter and total != total_found:
        st.success(f"Found {total_found} jobs ({total} match filter)")
    else:
        st.success(f"Found {total} jobs")

    # Quick-jump dropdown
    job_labels = []
    for i, j in enumerate(jobs):
        meta = []
        if j.get("company"):
            meta.append(j["company"])
        if j.get("date_posted"):
            meta.append(j["date_posted"])
        label = f"{i+1}. {j['title']}  —  {', '.join(meta)}" if meta else f"{i+1}. {j['title']}"
        job_labels.append(label)
    selected = st.selectbox("Jump to job", options=range(total),
                            format_func=lambda i: job_labels[i], index=idx,
                            label_visibility="collapsed")
    if selected != idx:
        st.session_state.job_idx = selected
        st.rerun()

    job = jobs[idx]

    # Glassdoor cache
    if "glassdoor_cache" not in st.session_state:
        st.session_state.glassdoor_cache = {}
    gd = st.session_state.glassdoor_cache.get(job["company"])

    # Scroll anchor
    st.markdown('<div id="job-top"></div>', unsafe_allow_html=True)
    st.markdown("""
    <script>document.getElementById('job-top')?.scrollIntoView({behavior: 'smooth'});</script>
    """, unsafe_allow_html=True)

    # ── Prev / Next ──
    st.divider()
    nav_cols = st.columns([1, 1])
    with nav_cols[0]:
        if st.button("◀  Prev", use_container_width=True, key="prev_btn", disabled=(idx == 0)):
            st.session_state.job_idx = max(0, idx - 1)
            st.rerun()
    with nav_cols[1]:
        if st.button("Next  ▶", use_container_width=True, key="next_btn", disabled=(idx >= total - 1)):
            st.session_state.job_idx = min(total - 1, idx + 1)
            st.rerun()

    # ── Job Card ──
    st.divider()
    logo_col, info_col, link_col = st.columns([1, 5, 1.4])
    with logo_col:
        if job.get("logo"):
            st.image(job["logo"], width=64)
    with info_col:
        st.markdown(f"## {re.sub(r'([#*_`~\\[\\]<>])', lambda m: '\\' + m.group(1), job['title'])}")
        card_meta = [f"**{job['company']}**"]
        if gd and gd.get("rating"):
            stars = "★" * int(gd["rating"]) + "☆" * (5 - int(gd["rating"]))
            ai_label = " (AI est.)" if gd.get("ai_guess") else ""
            card_meta.append(f"{stars} {gd['rating']:.1f}{ai_label}")
        if gd and gd.get("salary"):
            card_meta.append(f"💰 {gd['salary']}")
        card_meta.append(job.get('mode', ''))
        if job.get("date_posted"):
            card_meta.append(f"🕒 {job['date_posted']}")
        src = job.get("source", "")
        if src:
            card_meta.append(f"via {src.title()}")
        st.markdown("  ·  ".join(p for p in card_meta if p))
    with link_col:
        if job.get("url"):
            st.link_button("🔗 Open on LinkedIn", job['url'])

    # ── Section Selector ──
    if "active_section" not in st.session_state:
        st.session_state.active_section = 0
    section_names = ["📋 Details", "📄 Tailor Resume", "❓ Questions", "🎤 Mock Interview", "💬 Ask Them"]
    st.session_state.active_section = st.radio(
        "Section", options=range(5), format_func=lambda i: section_names[i],
        horizontal=True, label_visibility="collapsed", key="section_radio"
    )

    # ── Tab: Details ──
    if st.session_state.active_section == 0:
        st.subheader("Description")
        desc_text = job.get('description') or '*No description*'
        if desc_text and desc_text != "*No description*":
            safe_desc = _html.escape(json.dumps(desc_text[:10000]))
            st.markdown(f"""
            <input type="hidden" id="_desc_data" value="{safe_desc}">
            <button onclick="var d=document.getElementById('_desc_data');navigator.clipboard.writeText(JSON.parse(d.value));this.textContent='Copied!';setTimeout(()=>{{this.textContent='📋 Copy'}},2000)"
            style="margin-bottom:8px;padding:4px 12px;cursor:pointer;background:#f0f0f0;border:1px solid #ccc;border-radius:4px;font-size:13px">
            📋 Copy</button>
            """, unsafe_allow_html=True)
        st.markdown(desc_text[:5000], unsafe_allow_html=True)
        if job.get('requirements'):
            st.subheader("Requirements")
            st.markdown(job['requirements'][:2000])

        # Similar Jobs
        if "similar_jobs" not in st.session_state:
            st.session_state.similar_jobs = {}
        job_key = job.get("url", "") + job.get("title", "")
        show_similar = st.expander("🔗 Similar Jobs on LinkedIn", expanded=False)
        with show_similar:
            if job_key not in st.session_state.similar_jobs:
                with st.spinner("Finding similar jobs..."):
                    st.session_state.similar_jobs[job_key] = scrape_similar_jobs(job["title"], job["company"])
            similar = st.session_state.similar_jobs.get(job_key, [])
            if similar:
                st.caption(f"({len(similar)} found)")
                for sj in similar:
                    if sj.get("url"):
                        st.markdown(f"- **{sj['title']}** — *{sj['company']}*  [View]({sj['url']})")
                    else:
                        st.markdown(f"- **{sj['title']}** — *{sj['company']}*")
            else:
                st.caption("No similar jobs found")

        # Company Info Panel
        with st.expander("🏢 Company Info", expanded=False):
            company_key = job["company"]
            gd2 = st.session_state.glassdoor_cache.get(company_key)
            jd_salary = extract_salary_from_jd(job.get("description", "") + " " + job.get("requirements", ""))
            if jd_salary:
                st.metric("Salary in JD", jd_salary)

            if gd2 and gd2.get("error"):
                st.caption(gd2["error"])
                if DEEPSEEK_KEY:
                    if st.button("🤖 Estimate Salary (AI)", key=f"gd_ai_{company_key}_{idx}"):
                        with st.spinner("Estimating..."):
                            ai = guess_company_info(company_key, job.get("title", ""), job.get("description", ""))
                            if ai:
                                st.session_state.glassdoor_cache[company_key] = ai
                                st.rerun()
            elif gd2:
                if gd2.get("rating"):
                    stars = "★" * int(gd2["rating"]) + "☆" * (5 - int(gd2["rating"]))
                    label = "AI Est. Rating" if gd2.get("ai_guess") else "Glassdoor Rating"
                    st.metric(label, f"{gd2['rating']:.1f} / 5")
                    st.caption(stars)
                if gd2.get("salary"):
                    label = "AI Est. Monthly" if gd2.get("ai_guess") else "Est. Monthly Salary"
                    st.metric(label, gd2["salary"])
                if gd2.get("ai_guess"):
                    st.caption("⚠️ AI-generated — not from Glassdoor")
            else:
                if st.button("🔍 Lookup Company", key=f"gd_lookup_{company_key}_{idx}"):
                    with st.spinner("Searching Glassdoor..."):
                        gd_result = lookup_glassdoor(company_key)
                        if gd_result and gd_result.get("error") and DEEPSEEK_KEY:
                            ai = guess_company_info(company_key, job.get("title", ""), job.get("description", ""))
                            if ai:
                                gd_result = ai
                        st.session_state.glassdoor_cache[company_key] = gd_result
                        st.rerun()

    # ── Tab: Tailor Resume ──
    if st.session_state.active_section == 1:
        st.subheader("Resume Tailoring")
        if "resume_text" not in st.session_state or not st.session_state.resume_text:
            st.warning("Upload your resume in the sidebar first")
        else:
            st.caption("Select sections to include:")
            sc1, sc2, sc3, sc4, sc5 = st.columns(5)
            with sc1:
                st.session_state["sec_summary"] = st.checkbox("Summary", True, key="cb_summary")
            with sc2:
                st.session_state["sec_skills"] = st.checkbox("Skills", True, key="cb_skills")
            with sc3:
                st.session_state["sec_experience"] = st.checkbox("Experience", True, key="cb_experience")
            with sc4:
                st.session_state["sec_education"] = st.checkbox("Education", True, key="cb_education")
            with sc5:
                st.session_state["sec_certs"] = st.checkbox("Certifications", False, key="cb_certs")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔍 Analyze Fit (quick)", use_container_width=True):
                    with st.spinner("Analyzing..."):
                        if st.session_state.get("use_ai_tailor") and DEEPSEEK_KEY:
                            result = tailor_resume_ai(st.session_state.resume_text, job)
                            if result:
                                st.session_state.analysis = result
                            else:
                                rate, missing = tailor_resume_simple(st.session_state.resume_text, job)
                                st.session_state.analysis = f"**Keyword Match: {rate:.0f}%**\n\nMissing: {', '.join(missing[:10])}"
                        else:
                            rate, missing = tailor_resume_simple(st.session_state.resume_text, job)
                            st.session_state.analysis = f"**Keyword Match: {rate:.0f}%**\n\nMissing: {', '.join(missing[:10])}"

            with c2:
                if st.button("✏️ Generate Tailored Resume (AI rewrite)", type="primary", use_container_width=True):
                    if not DEEPSEEK_KEY:
                        st.error("Need DeepSeek API key for this feature")
                    else:
                        with st.spinner("Rewriting resume for this job..."):
                            tailored = generate_tailored_resume(st.session_state.resume_text, job)
                            if tailored:
                                st.session_state.tailored_text = tailored
                                st.session_state.analysis = None
                            else:
                                st.error("AI call failed — try again")

            if "analysis" in st.session_state and st.session_state.analysis:
                st.divider()
                st.markdown(st.session_state.analysis)

            if "tailored_text" in st.session_state and st.session_state.tailored_text:
                st.divider()
                if st.session_state.get("resume_text"):
                    with st.expander("🔍 See Changes (Original → Tailored)", expanded=False):
                        import difflib
                        orig_lines = st.session_state.resume_text.splitlines()
                        new_lines = st.session_state.tailored_text.splitlines()
                        diff_html = []
                        sm = difflib.SequenceMatcher(None, orig_lines, new_lines)
                        for tag, i1, i2, j1, j2 in sm.get_opcodes():
                            if tag == 'equal':
                                for line in orig_lines[i1:i2]:
                                    diff_html.append(line)
                            elif tag == 'replace':
                                for old, new in zip(orig_lines[i1:i2], new_lines[j1:j2]):
                                    ws = difflib.SequenceMatcher(None, old.split(), new.split())
                                    parts = []
                                    for op, a1, a2, b1, b2 in ws.get_opcodes():
                                        if op == 'equal':
                                            parts.append(' '.join(old.split()[a1:a2]))
                                        elif op == 'delete':
                                            parts.append(f'<span style="background:#f8d7da;color:#721c24;text-decoration:line-through">{" ".join(old.split()[a1:a2])}</span>')
                                        elif op == 'insert':
                                            parts.append(f'<span style="background:#d4edda;color:#155724">{" ".join(new.split()[b1:b2])}</span>')
                                        elif op == 'replace':
                                            parts.append(f'<span style="background:#f8d7da;color:#721c24;text-decoration:line-through">{" ".join(old.split()[a1:a2])}</span>')
                                            parts.append(f'<span style="background:#d4edda;color:#155724">{" ".join(new.split()[b1:b2])}</span>')
                                    diff_html.append(' '.join(parts))
                            elif tag == 'delete':
                                for line in orig_lines[i1:i2]:
                                    diff_html.append(f'<span style="background:#f8d7da;color:#721c24;text-decoration:line-through">{line}</span>')
                            elif tag == 'insert':
                                for line in new_lines[j1:j2]:
                                    diff_html.append(f'<span style="background:#d4edda;color:#155724">{line}</span>')
                        st.markdown('<br>'.join(diff_html[:150]), unsafe_allow_html=True)
                        st.caption("Red strikethrough = removed | Green = added | Inline = changed words")

                st.subheader("✏️ Tailored Resume — Edit Before Download")
                edited = st.text_area(
                    "Make any changes below. Add experience, tweak wording, or paste missing details.",
                    value=st.session_state.tailored_text, height=400, key="tailored_editor",
                )
                st.session_state.tailored_text = edited
                company_slug = re.sub(r'[^a-zA-Z0-9]', '_', job['company'])[:20]
                role_slug = job['title'][:30].replace(' ', '_')
                orig_name = st.session_state.get('resume_filename', 'resume')
                orig_base = re.sub(r'\.[^.]+$', '', orig_name)
                fname_base = f'{orig_base} - {company_slug} - {role_slug}'
                docx_buf = None
                if st.session_state.get("resume_bytes"):
                    docx_buf = build_tailored_docx(st.session_state.resume_bytes, st.session_state.tailored_text)
                    if not docx_buf:
                        st.caption("⚠️ Could not preserve original formatting — using default layout.")
                if not docx_buf:
                    docx_buf = build_docx(st.session_state.tailored_text)
                st.download_button(
                    label="⬇️ Download .docx", data=docx_buf,
                    file_name=f"{fname_base}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )

    # ── Tab: Interview Questions ──
    if st.session_state.active_section == 2:
        st.subheader("Interview Questions")
        if st.button("🎲 Generate Questions", type="primary"):
            with st.spinner("Generating..."):
                if st.session_state.get("use_ai_questions") and DEEPSEEK_KEY:
                    qs = generate_questions_ai(job)
                else:
                    qs = None
                if not qs:
                    qs = generate_questions_simple(job)
                st.session_state.interview_qs = qs

        if "interview_qs" in st.session_state and st.session_state.interview_qs:
            for i, q in enumerate(st.session_state.interview_qs, 1):
                qtext = re.sub(r'^\d+[\.\)\-]+\s*', '', q)
                st.markdown(f"{i}. {qtext}")

    # ── Tab: Mock Interview ──
    if st.session_state.active_section == 3:
        st.subheader("Mock Interview")
        if "interview_qs" not in st.session_state or not st.session_state.interview_qs:
            st.warning("Generate questions first (❓ tab)")
        else:
            qs = st.session_state.interview_qs
            if "mock_idx" not in st.session_state:
                st.session_state.mock_idx = 0
                st.session_state.mock_feedback = []
                st.session_state.mock_suggestions = {}

            midx = st.session_state.mock_idx
            if midx >= len(qs):
                st.success("🎉 Interview complete!")
                for i, fb in enumerate(st.session_state.mock_feedback):
                    with st.expander(f"Q{i+1} feedback"):
                        st.markdown(fb or "*No feedback*")
                        sug = st.session_state.mock_suggestions.get(i)
                        if sug:
                            st.divider()
                            st.caption("✨ Improved answer:")
                            st.markdown(sug)

                qa_text = ""
                for i, fb in enumerate(st.session_state.mock_feedback):
                    q_clean = re.sub(r'^\d+[\.\)\-]+\s*', '', qs[i])
                    qa_text += f"Q{i+1}: {q_clean}\nA{i+1}: {fb or '*No answer*'}\n"
                    sug = st.session_state.mock_suggestions.get(i)
                    if sug:
                        qa_text += f"Improved: {sug}\n"
                    qa_text += "\n"
                st.download_button(
                    "📥 Export Q&A (.txt)", data=qa_text,
                    file_name=f"interview_{re.sub(r'[^a-zA-Z0-9]','_',job['company'])[:20]}_{job['title'][:30].replace(' ','_')}.txt",
                    mime="text/plain", use_container_width=True,
                )

                if st.button("🔄 Restart"):
                    st.session_state.mock_idx = 0
                    st.session_state.mock_feedback = []
                    st.session_state.mock_suggestions = {}
                    st.rerun()
            else:
                st.progress(midx / len(qs), f"Question {midx+1}/{len(qs)}")
                qtext = re.sub(r'^\d+[\.\)\-]+\s*', '', qs[midx])
                st.markdown(f"##### Q{midx+1}: {qtext}")

                answer = st.text_area("Your answer:", key=f"ans_{midx}", height=120)

                if DEEPSEEK_KEY and answer.strip():
                    if st.button("✨ Improve My Answer", key=f"improve_{midx}"):
                        with st.spinner("Improving your answer..."):
                            improved = improve_answer(
                                qs[midx], answer.strip(),
                                job.get("title", ""), job.get("company", ""),
                                job.get("description", "")
                            )
                            if improved:
                                st.session_state.mock_suggestions[midx] = improved
                                st.rerun()
                sug = st.session_state.mock_suggestions.get(midx)
                if sug:
                    with st.expander("✨ Improved Answer", expanded=True):
                        st.markdown(sug)

                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("✅ Submit", type="primary", use_container_width=True):
                        if answer.strip():
                            fb = evaluate_answer(qs[midx], answer) if DEEPSEEK_KEY else None
                            if not fb:
                                wc = len(answer.split())
                                fb = "Good detail and specificity." if wc > 30 else ("Decent, add examples." if wc > 10 else "Too short — elaborate.")
                            st.session_state.mock_feedback.append(fb)
                            st.session_state.mock_idx += 1
                            st.rerun()
                with c2:
                    if st.button("⏭ Skip", use_container_width=True):
                        st.session_state.mock_feedback.append("*Skipped*")
                        st.session_state.mock_idx += 1
                        st.rerun()
                with c3:
                    if st.button("⏩ Skip to End", use_container_width=True):
                        current_fb = "*Skipped*"
                        if answer.strip():
                            current_fb = answer if not DEEPSEEK_KEY else (evaluate_answer(qs[midx], answer) or answer)
                        st.session_state.mock_feedback.append(current_fb)
                        remaining = len(qs) - midx - 1
                        if remaining > 0:
                            st.session_state.mock_feedback.extend(["*Skipped*"] * remaining)
                        st.session_state.mock_idx = len(qs)
                        st.rerun()

    # ── Tab: Ask Them ──
    if st.session_state.active_section == 4:
        st.subheader("Questions to Ask the Interviewer")
        st.caption("Asking good questions shows preparation and interest. Pick 2-3 that matter most to you.")

        candidate_qs = [
            "What does a typical day or week look like in this role?",
            "How do you measure success for this position in the first 3-6 months?",
            "What are the biggest challenges the team is facing right now?",
            "How would you describe the team culture and working style?",
            "What opportunities for growth and learning does this role offer?",
            "How does the team handle technical decisions and disagreements?",
            "What's the onboarding process like for new team members?",
            "How does the company support work-life balance?",
            "Where do you see the company/team in the next 1-2 years?",
            "What do you enjoy most about working here?",
        ]
        title_lower = job.get('title', '').lower()
        if 'senior' in title_lower or 'lead' in title_lower:
            candidate_qs.append("What's your approach to technical leadership and mentoring on the team?")
        if 'manager' in title_lower:
            candidate_qs.append("What's the team size and structure? How are reports distributed?")
        if 'engineer' in title_lower or 'developer' in title_lower:
            candidate_qs.append("What does the tech stack look like and how do you manage technical debt?")

        for i, q in enumerate(candidate_qs, 1):
            st.markdown(f"{i}. {q}")

        if DEEPSEEK_KEY:
            st.divider()
            if st.button("🤖 Generate Role-Specific Questions", key="gen_ask_them"):
                with st.spinner("Generating..."):
                    from utils import call_deepseek
                    prompt = f"""Job: {job['title']} at {job['company']}
Description: {job.get('description','')[:1500]}

Generate 5 smart questions a candidate should ask the interviewer for this specific role and company. Make them thoughtful and specific. Return as numbered list."""
                    result = call_deepseek(prompt, "You are an experienced career coach helping candidates prepare for interviews.", max_tokens=300)
                    if result:
                        st.session_state.ask_them_qs = result
                        st.rerun()
            if "ask_them_qs" in st.session_state and st.session_state.ask_them_qs:
                st.markdown("##### AI-Generated Questions")
                st.markdown(st.session_state.ask_them_qs)


    st.divider()
    st.caption("🔍 Scraping LinkedIn jobs in Singapore (last 2 weeks) — good luck out there 🍀")

if __name__ == "__main__":
    main()
