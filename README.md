# 🎯 Job Scraper + Resume Tailor + Mock Interview

A Streamlit web app that scrapes LinkedIn for jobs in Singapore, tailors your resume with AI, and runs mock interviews — all in one tool.

## What it does

1. **Search LinkedIn jobs** — Enter a job title (e.g. "backend engineer"), get listings posted in the last 2 weeks from Singapore companies.

2. **See job details** — Each listing shows the job title, company, work mode (🏢 In-office / 🏠 Remote / 🏢🏠 Hybrid), full description, and requirements.

3. **Glassdoor lookup** — For each company, it tries to find Glassdoor ratings and salary estimates so you know what to expect.

4. **Tailor your resume** — Upload your resume (PDF, DOCX, DOC, or TXT). The app uses DeepSeek AI to:
   - Analyse how well your resume matches the job
   - Rewrite your resume to emphasise relevant skills and keywords (UK English)
   - Export the tailored version as `.docx`

5. **Interview prep** — AI generates role-specific interview questions (technical, behavioural, and scenario-based).

6. **Mock interview** — Answer questions one by one in the browser and get AI feedback on your responses.

## Quick start (local)

```bash
git clone https://github.com/thevibecoderic/jobtool.git
cd jobtool
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Add your DeepSeek API key
echo 'DEEPSEEK_API_KEY=sk-your-key-here' > .env

streamlit run ui.py
```

## Deploy to Streamlit Community Cloud

1. Fork or push this repo to your GitHub account
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
3. Click **New app** → select your repo / branch `main`
4. **Main file path:** `ui.py`
5. Under **Advanced settings** → **Secrets**, add:

   ```toml
   DEEPSEEK_API_KEY = "sk-your-deepseek-api-key"
   ```

6. Click **Deploy**

Your app will be live at `https://<your-app>.streamlit.app`.

## Requirements

- Python 3.10+
- DeepSeek API key ([platform.deepseek.com](https://platform.deepseek.com))
- Streamlit, requests, BeautifulSoup, python-docx, PyPDF2
