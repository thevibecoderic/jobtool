# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app locally
streamlit run app.py

# Install dependencies
pip install -r requirements.txt
```

The app reads `DEEPSEEK_API_KEY` from `.env` or Streamlit secrets. There are no tests, linters, or type checkers configured.

## Architecture

Multi-module Streamlit app. All state lives in `st.session_state` — no database, no router, no separate backend.

| Module | Purpose |
|---|---|
| `app.py` (558 lines) | Streamlit UI — sidebar, job card, all 5 tabs |
| `scraper.py` (617 lines) | LinkedIn scraping: `scrape_linkedin`, `get_job_details`, `scrape_similar_jobs`, embedded JSON parsers, card snippet extraction |
| `glassdoor.py` (128 lines) | Company research: `lookup_glassdoor` (multi-engine), `guess_company_info` (DeepSeek salary estimation) |
| `resume.py` (258 lines) | Resume: parse PDF/DOCX/DOC/TXT, tailor via AI, export `.docx` |
| `interview.py` (73 lines) | Interview: AI question generation, mock interview evaluation |
| `utils.py` (154 lines) | Config, `call_deepseek`, text extraction (`extract_requirements`, `extract_salary_from_jd`, `clean_html`) |

- **Scraper** uses two User-Agent profiles (Chrome + Googlebot). Parses embedded JSON (`__NEXT_DATA__`, `__INITIAL_STATE__`, JSON-LD) first, falls back to HTML card parsing. `@st.cache_data` (10-min TTL) on `scrape_linkedin`.
- **Glassdoor** tries Glassdoor direct → Google → Bing. Falls back to DeepSeek AI (button-triggered only — no auto API burn).
- **Resume** supports PDF (PyPDF2), DOCX (python-docx), DOC (antiword subprocess), plain text. AI rewrite uses UK English, ATS keyword weaving. `build_tailored_docx` preserves original DOCX formatting.

## Config & secrets

- `.env` — `DEEPSEEK_API_KEY` (gitignored)
- Streamlit Cloud reads from `st.secrets["DEEPSEEK_API_KEY"]`
- DeepSeek model: `deepseek-chat`, endpoint: `https://api.deepseek.com/chat/completions`

## UI

- JavaScript injected via `st.markdown` for left/right arrow keyboard nav and scroll-to-top
- Streamlit branding hidden via CSS
- The `jobtool/` directory is a nested copy of the repo (not a submodule); `skills/` is gitignored Claude Code skills
