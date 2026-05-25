# 🎯 Job Scraper + Resume Tailor + Mock Interview

A Streamlit web app that scrapes LinkedIn for jobs in Singapore, tailors your resume with AI, and runs mock interviews — all in one tool.

## What it does

1. **Search LinkedIn jobs** — Enter a job title (e.g. "backend engineer"), get listings posted in the last 2 weeks from Singapore companies.

2. **See job details** — Each listing shows the job title, company, work mode (🏢 In-office / 🏠 Remote / 🏢🏠 Hybrid), full description, and requirements.

3. **Glassdoor lookup** — For each company, it tries to find Glassdoor ratings and salary estimates so you know what to expect.

4. **Tailor your resume** — Upload your resume (PDF, DOCX, DOC, or TXT). The app uses DeepSeek AI to:
   - Analyze how well your resume matches the job
   - Rewrite your resume to emphasize relevant skills and keywords
   - Export the tailored version as `.docx` or `.pdf`

5. **Interview prep** — AI generates role-specific interview questions (technical, behavioral, and scenario-based).

6. **Mock interview** — Answer questions one by one in the browser and get AI feedback on your responses.