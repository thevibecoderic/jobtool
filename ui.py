#!/usr/bin/env python3
"""
Job Scraper UI — Streamlit
Usage: streamlit run jobtool/ui.py
Reads DEEPSEEK_API_KEY from jobtool/.env
"""

import streamlit as st
import requests, re, json, os, time, urllib.parse, io, tempfile
from bs4 import BeautifulSoup
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

st.set_page_config(page_title="Job Scraper", page_icon="🎯", layout="wide")

# ── Config ────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
LOCATION = "Singapore"
TIME_RANGE = "r1209600"

def _load_env():
    if os.environ.get("DEEPSEEK_API_KEY"):
        return
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, ".env")
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "DEEPSEEK_API_KEY":
                    os.environ["DEEPSEEK_API_KEY"] = v
    except FileNotFoundError:
        pass

_load_env()
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

# ── Helpers ───────────────────────────────────────────

def detect_mode(desc):
    d = desc.lower()
    if "remote" in d:
        return "🏠 Remote" if "hybrid" not in d else "🏢🏠 Hybrid"
    return "🏢 In-office"


def call_deepseek(prompt, system="You are a helpful career coach.", max_tokens=800):
    if not DEEPSEEK_KEY:
        return None
    try:
        r = requests.post(DEEPSEEK_URL, headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        }, json={
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0.7,
        }, timeout=45)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
    except:
        pass
    return None


# ── Glassdoor Lookup ──────────────────────────────────

def lookup_glassdoor(company_name):
    """Try to find Glassdoor rating + salary for a company."""
    # Try DuckDuckGo first (less likely to block cloud IPs)
    rating, salary = None, None
    for engine in ["ddg", "google"]:
        try:
            if engine == "ddg":
                url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(company_name + ' glassdoor review')}"
            else:
                url = f"https://www.google.com/search?q={urllib.parse.quote(company_name + ' glassdoor review rating')}&hl=en"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract rating from search snippet
            if not rating:
                for el in soup.find_all(["span", "div", "em", "a"]):
                    t = el.get_text()
                    m = re.search(r'(\d\.\d)\s*(?:out of 5|stars|rating|★|/5)', t, re.I)
                    if m:
                        rating = float(m.group(1))
                        break

            # Try salary
            if not salary:
                salary_text = soup.get_text()
                m = re.search(r'(?:S\$\s?|SGD\s?)([\d,]+)\s*(?:–|-|to)\s*(?:S\$\s?|SGD\s?)?([\d,]+)', salary_text, re.I)
                if m:
                    salary = f"SGD {m.group(1)} - {m.group(2)}"
                else:
                    m = re.search(r'(?:S\$\s?|SGD\s?)([\d,]+)\s*(?:/yr|/year|per year|/mo|/month)', salary_text, re.I)
                    if m:
                        salary = f"SGD {m.group(1)}"

            if rating or salary:
                return {"rating": rating, "salary": salary}
        except:
            continue
    return {"error": "unavailable"}


# ── Scraper ───────────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def scrape_linkedin(keywords, max_jobs=30):
    jobs = []
    for start in range(0, max_jobs, 25):
        url = (
            f"https://www.linkedin.com/jobs/search/?"
            f"keywords={urllib.parse.quote(keywords)}"
            f"&location={urllib.parse.quote(LOCATION)}"
            f"&f_TPR={TIME_RANGE}"
            f"&position=1&pageNum={start // 25}"
        )
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", class_=re.compile(r"base-card|job-card|job-search-card"))
            if not cards:
                cards = soup.find_all("li", class_=re.compile(r"job|result"))
            if not cards:
                break
            for card in cards:
                if len(jobs) >= max_jobs:
                    break
                title_el = card.find(["h3", "a"], class_=re.compile(r"title|job", re.I))
                company_el = card.find(["h4", "span"], class_=re.compile(r"company|subtitle|employer", re.I))
                link_el = card.find("a", href=re.compile(r"/jobs/view/|/jobs/"))
                if not title_el or not link_el:
                    continue
                job_url = link_el["href"]
                if not job_url.startswith("http"):
                    job_url = "https://www.linkedin.com" + job_url
                job_url = job_url.split("?")[0]
                desc, reqs = get_job_details(job_url)
                jobs.append({
                    "title": title_el.get_text(strip=True),
                    "company": company_el.get_text(strip=True) if company_el else "Unknown",
                    "url": job_url, "description": desc,
                    "requirements": reqs, "mode": detect_mode(desc),
                })
            if len(jobs) >= max_jobs:
                break
            time.sleep(1.5)
        except:
            break
    return jobs


def get_job_details(job_url):
    try:
        resp = requests.get(job_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return "", ""
        soup = BeautifulSoup(resp.text, "html.parser")
        desc_el = (soup.find("div", class_="description__text") or
                   soup.find("div", class_="show-more-less-html__markup") or
                   soup.find("div", class_=re.compile(r"description", re.I)))
        if desc_el:
            desc = desc_el.get_text("\n", strip=True)
            return desc, extract_requirements(desc)
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string)
                if "description" in data:
                    desc = BeautifulSoup(data["description"], "html.parser").get_text()
                    return desc, extract_requirements(desc)
            except:
                pass
        return "", ""
    except:
        return "", ""


def extract_requirements(text):
    m = re.search(r'(?:requirement|qualification|what you.{0,15}need|must have|required.{0,10}skill)', text, re.IGNORECASE)
    if m:
        section = text[m.start():]
        stop = len(section)
        for kw in ['responsibilities', 'about the role', 'we offer', 'benefits']:
            m2 = re.search(kw, section[80:], re.IGNORECASE)
            if m2:
                stop = min(stop, 80 + m2.start())
        return section[:stop].strip()
    lines = text.split('\n')
    req_lines = [l for l in lines if any(w in l.lower() for w in ['require', 'qualif', 'skill', 'experience', 'degree', 'year'])]
    return '\n'.join(req_lines[:10]) if req_lines else text[:400]


# ── Resume Parse ──────────────────────────────────────

def parse_resume(uploaded_file):
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext == '.pdf':
        from PyPDF2 import PdfReader
        reader = PdfReader(uploaded_file)
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if ext == '.docx':
        doc = Document(uploaded_file)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
    if ext == '.doc':
        return _try_read_doc(uploaded_file)
    return uploaded_file.read().decode("utf-8", errors="ignore").strip()


def _try_read_doc(uploaded_file):
    content = uploaded_file.read()
    text = content.decode("utf-8", errors="ignore")
    lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 3 and not all(c < ' ' or c > '~' or c == '\x00' for c in l.strip())]
    result = '\n'.join(lines)
    if len(result) > 50:
        return result
    try:
        import subprocess
        with tempfile.NamedTemporaryFile(suffix='.doc', delete=False) as tf:
            tf.write(content)
            tf.flush()
            out = subprocess.check_output(['antiword', tf.name], timeout=10)
            os.unlink(tf.name)
            return out.decode("utf-8", errors="ignore").strip()
    except:
        pass
    return result if len(result) > 50 else ""


# ── Resume Tailoring ──────────────────────────────────

def tailor_resume_simple(resume, job):
    job_text = f"{job['title']} {job['description']} {job['requirements']}".lower()
    stop_words = {'this','that','with','from','your','have','will','they','about','their','would','which','the','and','for','are','but','not','you','all','can','had','has','was','were','been','being','more','some','than','then','its','also','what','when','where','who','how','our'}
    job_words = set(re.findall(r'\b[a-z]{4,}\b', job_text)) - stop_words
    resume_words = set(re.findall(r'\b[a-z]{4,}\b', resume.lower()))
    missing = sorted(job_words - resume_words)
    rate = len(job_words & resume_words) / max(len(job_words), 1) * 100
    return rate, missing[:20]


def tailor_resume_ai(resume, job):
    prompt = f"""Job: {job['title']} at {job['company']}
Description: {job.get('description','')[:2000]}
Requirements: {job.get('requirements','')[:1000]}

My current resume:
{resume[:3000]}

Analyze my resume against this job. Return:
1. Match percentage (estimate)
2. Top 5 missing skills/keywords I should add
3. 3 bullet points to add to my resume
4. Brief summary of my strengths
Keep it concise."""
    return call_deepseek(prompt, "You are an expert resume reviewer. Be honest and specific.")


def generate_tailored_resume(resume, job):
    prompt = f"""Job Title: {job['title']}
Company: {job['company']}
Job Description: {job.get('description','')[:2000]}
Requirements: {job.get('requirements','')[:1000]}

My current resume:
{resume[:3000]}

Rewrite my resume to be tailored for this specific job. Do NOT invent experience I don't have — rephrase, reorder, and emphasize relevant skills/experience already in my resume. Use these section headers exactly:

NAME: [Full Name from resume]
SUMMARY: [2-3 sentence professional summary tailored to this role]
SKILLS: [comma-separated skills, prioritize those matching the job]
EXPERIENCE: [keep same roles, rewrite bullets to match job keywords]
EDUCATION: [keep as-is]
CERTIFICATIONS: [keep as-is, if any]

Return the full rewritten resume with those exact headers."""
    return call_deepseek(prompt, "You are a professional resume writer. Be honest — only use information from the original resume.", max_tokens=1500)


def build_docx(tailored_text):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(11)
    lines = tailored_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("NAME:"):
            p = doc.add_paragraph()
            run = p.add_run(line.replace("NAME:", "").strip())
            run.bold = True
            run.font.size = Pt(18)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif any(line.startswith(h) for h in ["SUMMARY:", "SKILLS:", "EXPERIENCE:", "EDUCATION:", "CERTIFICATIONS:"]):
            p = doc.add_paragraph()
            parts = line.split(":", 1)
            run = p.add_run(parts[0] + ":")
            run.bold = True
            run.font.size = Pt(13)
            if len(parts) > 1 and parts[1].strip():
                p.add_run(" " + parts[1].strip())
        elif line.startswith("- ") or line.startswith("• "):
            doc.add_paragraph(line, style='List Bullet')
        else:
            doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def _sanitize(text):
    """Strip or replace characters that Helvetica can't render."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def build_pdf(tailored_text):
    """Build a clean PDF resume using fpdf2."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    lines = tailored_text.split('\n')
    for line in lines:
        line = _sanitize(line.strip())
        if not line:
            pdf.ln(3)
            continue

        if line.startswith("NAME:"):
            pdf.set_font("Helvetica", "B", 18)
            pdf.cell(0, 10, _sanitize(line.replace("NAME:", "").strip()), ln=True, align="C")
        elif any(line.startswith(h) for h in ["SUMMARY:", "SKILLS:", "EXPERIENCE:", "EDUCATION:", "CERTIFICATIONS:"]):
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 12)
            parts = line.split(":", 1)
            pdf.cell(0, 8, _sanitize(parts[0]) + ":", ln=True)
            if len(parts) > 1 and parts[1].strip():
                pdf.set_font("Helvetica", "", 10)
                pdf.multi_cell(0, 5, parts[1].strip())
        elif line.startswith("- ") or line.startswith("• "):
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(8, 5, "•")
            pdf.multi_cell(0, 5, line[2:].strip())
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, line)

    buf = io.BytesIO()
    buf.write(pdf.output())
    buf.seek(0)
    return buf


# ── Interview ─────────────────────────────────────────

def generate_questions_ai(job):
    prompt = f"""Job: {job['title']} at {job['company']}
Description: {job.get('description','')[:2000]}
Requirements: {job.get('requirements','')[:1000]}

Generate 8 interview questions. Mix: 3-4 technical, 2-3 behavioral, 1-2 scenario.
Return as numbered list. Make them role-specific."""
    result = call_deepseek(prompt, "You are a senior hiring manager. Be specific and challenging.")
    if result:
        return [q.strip() for q in result.split('\n') if q.strip() and any(q.strip().startswith(str(i)) for i in range(1,15))][:10]
    return None


def generate_questions_simple(job):
    desc = (job.get('description', '') + ' ' + job.get('requirements', '')).lower()
    title = job.get('title', '').lower()
    qs = []
    tech_map = {
        'python': "Explain Python decorators and a use case.",
        'javascript': "Explain closures with an example and the event loop.",
        'java': "HashMap vs ConcurrentHashMap? Explain JVM GC.",
        'sql': "Explain JOIN types. How would you optimize a slow query?",
        'aws': "EC2 vs Lambda: when to use which? Explain VPC.",
        'docker': "Docker vs VM key differences? Multi-stage builds?",
        'react': "Explain virtual DOM. useEffect vs useLayoutEffect?",
        'data': "Explain ETL pipeline design. Star vs snowflake schema?",
        'api': "REST vs GraphQL? How do you handle API rate limiting?",
        'cloud': "Explain microservices. CI/CD pipeline design?",
    }
    for kw, q in tech_map.items():
        if kw in desc and len(qs) < 4:
            qs.append(q)
    behavioral = [
        "Tell me about yourself and your background.",
        "Why are you interested in this role?",
        "Describe a challenging project and how you solved it.",
        "How do you handle disagreement with a coworker?",
    ]
    qs.extend(behavioral)
    if 'senior' in title or 'lead' in title:
        qs.append("How do you mentor junior team members?")
    return qs[:8]


def evaluate_answer(question, answer):
    if not DEEPSEEK_KEY or len(answer.split()) < 5:
        return None
    prompt = f"""Question: {question}
Candidate's answer: {answer}
Brief feedback (2-3 sentences): what was strong, what to improve, score 1-10."""
    return call_deepseek(prompt, "You are an interview coach. Be constructive and brief.")


# ── UI ────────────────────────────────────────────────

def main():
    st.title("🎯 Job Scraper + Resume Tailor + Mock Interview")
    st.caption("Scrapes LinkedIn jobs in Singapore (last 2 weeks) | Powered by DeepSeek")

    # Keyboard navigation JS
    st.markdown("""
    <script>
    document.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowLeft') {
            var btn = parent.document.querySelector('button[kind="secondary"][data-testid="stBaseButton-secondary"]');
            var btns = parent.document.querySelectorAll('button');
            for (var b of btns) { if (b.innerText.includes('◀')) b.click(); }
        }
        if (e.key === 'ArrowRight') {
            var btns = parent.document.querySelectorAll('button');
            for (var b of btns) { if (b.innerText.includes('▶')) b.click(); }
        }
    });
    </script>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        kw = st.text_input("Job title / keywords", placeholder="e.g. software engineer")
        max_jobs = st.slider("Max jobs", 10, 50, 25)
        st.divider()

        st.subheader("📄 Resume")
        resume_file = st.file_uploader("Upload (PDF/DOCX/DOC/TXT)", type=["pdf", "docx", "doc", "txt", "md"])
        if resume_file:
            if "resume_filename" not in st.session_state or st.session_state.resume_filename != resume_file.name:
                st.session_state.resume_filename = resume_file.name
                st.session_state.resume_text = parse_resume(resume_file)
                st.session_state.tailored_text = None
                if st.session_state.resume_text:
                    st.success(f"Loaded: {resume_file.name} ({len(st.session_state.resume_text)} chars)")
                else:
                    st.error("Could not read file. For .doc, try saving as .docx first.")

        st.divider()
        st.subheader("🤖 AI")
        if DEEPSEEK_KEY:
            st.success("DeepSeek API connected")
            st.checkbox("Use AI for tailoring", value=True, key="use_ai_tailor")
            st.checkbox("Use AI for questions", value=True, key="use_ai_questions")
        else:
            st.warning("Add key to jobtool/.env then restart")
            st.session_state.use_ai_tailor = False
            st.session_state.use_ai_questions = False

    if not kw:
        st.info("👈 Enter a job title in the sidebar to start")
        return

    if st.button("🔍 Search LinkedIn", type="primary", use_container_width=True):
        st.session_state.jobs = None
        st.session_state.job_idx = 0
        st.session_state.glassdoor_cache = {}
        with st.spinner(f"Searching '{kw}'..."):
            st.session_state.jobs = scrape_linkedin(kw, max_jobs)
        st.rerun()

    if "jobs" not in st.session_state or not st.session_state.jobs:
        return

    jobs = st.session_state.jobs
    if "job_idx" not in st.session_state:
        st.session_state.job_idx = 0
    idx = st.session_state.job_idx
    total = len(jobs)

    # ── Navigation ──
    st.success(f"Found {total} jobs")

    nav_cols = st.columns([1, 2, 1])
    with nav_cols[0]:
        if st.button("◀  Prev", use_container_width=True, key="prev_btn", disabled=(idx == 0)):
            st.session_state.job_idx = max(0, idx - 1)
            st.rerun()
    with nav_cols[1]:
        st.markdown(f"<h3 style='text-align:center'>{idx+1} / {total}</h3>", unsafe_allow_html=True)
    with nav_cols[2]:
        if st.button("Next  ▶", use_container_width=True, key="next_btn", disabled=(idx >= total - 1)):
            st.session_state.job_idx = min(total - 1, idx + 1)
            st.rerun()

    job = jobs[idx]

    # ── Job Card ──
    st.divider()
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"## {job['title']}")
        st.markdown(f"**{job['company']}**  ·  {job['mode']}")
    with col2:
        st.link_button("🔗 LinkedIn", job['url'])

    # ── Glassdoor Panel ──
    with st.expander("🏢 Glassdoor Info", expanded=False):
        if "glassdoor_cache" not in st.session_state:
            st.session_state.glassdoor_cache = {}
        company = job['company']
        if company not in st.session_state.glassdoor_cache:
            with st.spinner(f"Looking up {company} on Glassdoor..."):
                gd = lookup_glassdoor(company)
                st.session_state.glassdoor_cache[company] = gd
        gd = st.session_state.glassdoor_cache.get(company)
        if gd and gd.get("error"):
            st.caption("Glassdoor lookup blocked from cloud — try locally")
        elif gd:
            c1, c2 = st.columns(2)
            with c1:
                if gd.get("rating"):
                    stars = "★" * int(gd["rating"]) + "☆" * (5 - int(gd["rating"]))
                    st.metric("Glassdoor Rating", f"{gd['rating']:.1f} / 5")
                    st.caption(stars)
                else:
                    st.caption("No rating found")
            with c2:
                if gd.get("salary"):
                    st.metric("Est. Salary", gd["salary"])
                else:
                    st.caption("No salary data")
        else:
            st.caption("No Glassdoor data found for this company")

    # ── Tabs ──
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Details", "📄 Tailor Resume", "❓ Questions", "🎤 Mock Interview"])

    with tab1:
        st.subheader("Description")
        st.markdown((job.get('description') or '*No description*')[:3000])
        if job.get('requirements'):
            st.subheader("Requirements")
            st.markdown(job['requirements'][:2000])

    with tab2:
        st.subheader("Resume Tailoring")
        if "resume_text" not in st.session_state or not st.session_state.resume_text:
            st.warning("Upload your resume in the sidebar first")
        else:
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
                st.subheader("✨ Tailored Resume Preview")
                st.markdown(st.session_state.tailored_text)

                company_slug = re.sub(r'[^a-zA-Z0-9]', '_', job['company'])[:20]
                fname_base = f"resume_tailored_{company_slug}_{job['title'][:30].replace(' ','_')}"

                dl1, dl2 = st.columns(2)
                with dl1:
                    docx_buf = build_docx(st.session_state.tailored_text)
                    st.download_button(
                        label="⬇️ Download .docx",
                        data=docx_buf,
                        file_name=f"{fname_base}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
                with dl2:
                    try:
                        pdf_buf = build_pdf(st.session_state.tailored_text)
                        st.download_button(
                            label="⬇️ Download .pdf",
                            data=pdf_buf,
                            file_name=f"{fname_base}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                    except ImportError:
                        st.caption("Install fpdf2 for PDF: pip install fpdf2")

    with tab3:
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
                st.markdown(f"**{i}.** {q}")

    with tab4:
        st.subheader("Mock Interview")
        if "interview_qs" not in st.session_state or not st.session_state.interview_qs:
            st.warning("Generate questions first (❓ tab)")
        else:
            qs = st.session_state.interview_qs
            if "mock_idx" not in st.session_state:
                st.session_state.mock_idx = 0
                st.session_state.mock_feedback = []

            midx = st.session_state.mock_idx
            if midx >= len(qs):
                st.success("🎉 Interview complete!")
                for i, fb in enumerate(st.session_state.mock_feedback):
                    with st.expander(f"Q{i+1} feedback"):
                        st.markdown(fb or "*No feedback*")
                if st.button("🔄 Restart"):
                    st.session_state.mock_idx = 0
                    st.session_state.mock_feedback = []
                    st.rerun()
            else:
                st.progress(midx / len(qs), f"Question {midx+1}/{len(qs)}")
                st.markdown(f"### Q{midx+1}: {qs[midx]}")
                answer = st.text_area("Your answer:", key=f"ans_{midx}", height=120)

                c1, c2 = st.columns(2)
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


if __name__ == "__main__":
    main()
