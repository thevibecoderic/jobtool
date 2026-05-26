#!/usr/bin/env python3
"""
LinkedIn Job Scraper + Resume Tailor + Mock Interview
Usage: python jobtool/app.py
"""

import requests, re, json, os, sys, time, textwrap, urllib.parse
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}
LOCATION = "Singapore"
TIME_RANGE = "r1209600"  # last 2 weeks

# ── Scraper ──────────────────────────────────────────

def scrape_linkedin(keywords, max_jobs=25):
    """Scrape LinkedIn jobs search page. Falls back to Google if blocked."""
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
            resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code == 404:
                print("  [!] LinkedIn endpoint gone (404) — trying alternate method...")
                return scrape_linkedin_via_google(keywords, max_jobs)
            if resp.status_code == 429:
                print("  [!] Rate limited (429) — wait 30s or use a VPN.")
                break
            if resp.status_code != 200:
                print(f"  [!] LinkedIn returned {resp.status_code}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # Try embedded JSON-LD / __NEXT_DATA__ first
            jobs_from_embedded = _parse_embedded(soup)
            if jobs_from_embedded:
                jobs.extend(jobs_from_embedded)
                if len(jobs) >= max_jobs:
                    break
                time.sleep(2)
                continue

            # Fallback: parse visible job cards
            cards = soup.find_all("div", class_=re.compile(r"base-card|job-card|job-search-card"))
            if not cards:
                cards = soup.find_all("li", class_=re.compile(r"job|result"))
            if not cards:
                # Try any element with a job title link
                links = soup.find_all("a", href=re.compile(r"/jobs/view/"))
                if links:
                    for link in links[:max_jobs - len(jobs)]:
                        title = link.get_text(strip=True)
                        job_url = link["href"].split("?")[0]
                        if not job_url.startswith("http"):
                            job_url = "https://www.linkedin.com" + job_url
                        parent = link.find_parent("div") or link.find_parent("li") or link
                        company_el = parent.find(["h4", "span"], class_=re.compile(r"company|subtitle", re.I))
                        company = company_el.get_text(strip=True) if company_el else "Unknown"
                        desc, reqs = get_job_details(job_url)
                        jobs.append({"title": title, "company": company, "url": job_url, "description": desc, "requirements": reqs})
                if jobs:
                    break
                print("  [!] No job cards found. LinkedIn may require login.")
                break

            for card in cards:
                if len(jobs) >= max_jobs:
                    break
                title_el = card.find(["h3", "a", "span"], class_=re.compile(r"title|job", re.I))
                company_el = card.find(["h4", "span", "p"], class_=re.compile(r"company|subtitle|employer", re.I))
                link_el = card.find("a", href=re.compile(r"/jobs/view/|/jobs/"))
                if not title_el or not link_el:
                    continue
                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                job_url = link_el["href"]
                if not job_url.startswith("http"):
                    job_url = "https://www.linkedin.com" + job_url
                job_url = job_url.split("?")[0]
                desc, reqs = get_job_details(job_url)
                jobs.append({"title": title, "company": company, "url": job_url, "description": desc, "requirements": reqs})

            if len(jobs) >= max_jobs:
                break
            time.sleep(2)

        except Exception as e:
            print(f"  [!] {e}")
            break
    return jobs


def scrape_linkedin_via_google(keywords, max_jobs=25):
    """Fallback: search Google for LinkedIn job listings."""
    print("  → Falling back to Google search for LinkedIn jobs...")
    jobs = []
    query = f'site:linkedin.com/jobs "{keywords}" Singapore'
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num=30"
    try:
        resp = requests.get(url, headers={**HEADERS, "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"}, timeout=15)
        if resp.status_code != 200:
            return jobs
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a", href=re.compile(r"linkedin\.com/jobs/view/")):
            href = link["href"]
            real_url = re.search(r'(https?://[^&]+)', href)
            if real_url:
                job_url = real_url.group(1).split("?")[0]
            else:
                continue
            title_el = link.find(["h3"]) or link
            title = title_el.get_text(strip=True)
            desc, reqs = get_job_details(job_url)
            if not desc:
                continue
            # extract company from description
            company = "Unknown"
            m = re.search(r'at ([A-Z][A-Za-z &.-]+)', desc)
            if m:
                company = m.group(1).strip()
            jobs.append({"title": title, "company": company, "url": job_url, "description": desc, "requirements": reqs})
            if len(jobs) >= max_jobs:
                break
        print(f"  ✓ Found {len(jobs)} via Google")
    except Exception as e:
        print(f"  [!] Google fallback failed: {e}")
    return jobs


def _parse_embedded(soup):
    """Try to extract jobs from __NEXT_DATA__ or JSON-LD embedded in the page."""
    jobs = []
    # Try __NEXT_DATA__
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data and next_data.string:
        try:
            data = json.loads(next_data.string)
            def walk(obj, depth=0):
                if depth > 10:
                    return
                if isinstance(obj, dict):
                    if "jobPosting" in obj:
                        jp = obj["jobPosting"]
                        desc = jp.get("description", "")
                        if isinstance(desc, str) and len(desc) > 0 and desc[0] == "<":
                            desc = BeautifulSoup(desc, "html.parser").get_text()
                        company = "Unknown"
                        org = jp.get("hiringOrganization")
                        if isinstance(org, dict):
                            company = org.get("name", "Unknown")
                        jobs.append({
                            "title": jp.get("title", ""),
                            "company": company,
                            "url": jp.get("url", ""),
                            "description": desc,
                            "requirements": extract_requirements(desc),
                        })
                    for v in obj.values():
                        walk(v, depth + 1)
                elif isinstance(obj, list):
                    for v in obj[:50]:
                        walk(v, depth + 1)
            walk(data)
        except:
            pass
    if jobs:
        return jobs

    # Try JSON-LD
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "JobPosting":
                    desc = item.get("description", "")
                    if isinstance(desc, str) and len(desc) > 0 and desc[0] == "<":
                        desc = BeautifulSoup(desc, "html.parser").get_text()
                    company = "Unknown"
                    org = item.get("hiringOrganization")
                    if isinstance(org, dict):
                        company = org.get("name", "Unknown")
                    jobs.append({
                        "title": item.get("title", ""),
                        "company": company,
                        "url": item.get("url", ""),
                        "description": desc,
                        "requirements": extract_requirements(desc),
                    })
        except:
            pass
    return jobs


def get_job_details(job_url):
    try:
        resp = requests.get(job_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return "", ""
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try __NEXT_DATA__ first
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                def walk(obj, depth=0):
                    if depth > 10:
                        return None
                    if isinstance(obj, dict):
                        if "description" in obj and isinstance(obj["description"], str) and len(obj["description"]) > 100:
                            return obj["description"]
                        for v in obj.values():
                            r = walk(v, depth + 1)
                            if r:
                                return r
                    elif isinstance(obj, list):
                        for v in obj[:30]:
                            r = walk(v, depth + 1)
                            if r:
                                return r
                    return None
                desc = walk(data)
                if desc:
                    return desc, extract_requirements(desc)
            except:
                pass

        # Fallback: parse visible description
        desc_el = (soup.find("div", class_="description__text") or
                   soup.find("div", class_="show-more-less-html__markup") or
                   soup.find("div", class_=re.compile(r"description", re.I)))
        if desc_el:
            desc = desc_el.get_text("\n", strip=True)
            return desc, extract_requirements(desc)

        # JSON-LD fallback
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


# ── Resume ───────────────────────────────────────────

def parse_resume(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    elif ext in ('.txt', '.md'):
        return open(filepath, encoding='utf-8').read().strip()
    else:
        print(f"  [!] Unsupported: {ext}")
        return ""


def tailor_resume(resume_text, job):
    job_text = f"{job['title']} {job['description']} {job['requirements']}".lower()
    stop_words = {'this','that','with','from','your','have','will','they','about','their','would','which','the','and','for','are','but','not','you','all','can','had','has','was','were','been','being','more','some','than','then','its','also','what','when','where','who','how','our'}
    job_words = set(re.findall(r'\b[a-z]{4,}\b', job_text)) - stop_words
    resume_words = set(re.findall(r'\b[a-z]{4,}\b', resume_text.lower()))
    missing = sorted(job_words - resume_words)
    rate = len(job_words & resume_words) / max(len(job_words), 1) * 100
    suggestions = "\n".join(f"  - Add '{kw}'" for kw in missing[:15])
    return f"Match rate: {rate:.0f}%\n\nMissing keywords to add:\n{suggestions}"


# ── Interview Questions ──────────────────────────────

def generate_questions(job):
    desc = (job.get('description', '') + ' ' + job.get('requirements', '')).lower()
    title = job.get('title', '').lower()

    qs = []
    tech_map = {
        'python': ["Explain Python decorators and a use case.", "How does GIL affect concurrency?"],
        'javascript': ["Explain closures with an example.", "What is the event loop?"],
        'java': ["HashMap vs ConcurrentHashMap?", "Explain JVM garbage collection."],
        'sql': ["Explain different JOIN types.", "How would you optimize a slow query?"],
        'aws': ["EC2 vs Lambda: when to use which?", "Explain VPC and subnets."],
        'docker': ["Docker vs VM key differences?", "Multi-stage build best practices?"],
        'react': ["Explain virtual DOM.", "useEffect vs useLayoutEffect?"],
        'data': ["Explain ETL pipeline design.", "Star vs snowflake schema?"],
        'api': ["REST vs GraphQL?", "How do you handle API rate limiting?"],
        'cloud': ["Explain microservices architecture.", "CI/CD pipeline design?"],
    }
    for kw, questions in tech_map.items():
        if kw in desc:
            qs.extend(questions[:1])

    behavioral = [
        "Tell me about yourself and your background.",
        "Why are you interested in this role?",
        "Describe a challenging project and how you solved it.",
        "How do you handle disagreement with a coworker?",
        "Where do you see yourself in 3 years?",
        "What's your biggest weakness and how are you improving?",
    ]
    qs.extend(behavioral[:4])

    if 'senior' in title or 'lead' in title:
        qs.extend(["How do you mentor junior team members?", "Describe your leadership style."])
    if 'manager' in title:
        qs.extend(["How do you handle underperformance?", "Describe your project management approach."])

    return qs[:10]


def run_mock_interview(questions):
    print("\n" + "=" * 55)
    print("  MOCK INTERVIEW — type 'skip'/'quit'")
    print("=" * 55)
    score = 0
    for i, q in enumerate(questions, 1):
        print(f"\nQ{i}: {q}")
        try:
            ans = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if ans.lower() == 'quit': break
        if ans.lower() == 'skip': continue
        wc = len(ans.split())
        if wc < 10:
            print("  ⚠ Short — add examples.")
        elif wc < 30:
            print("  ✓ Decent. Be more specific.")
        else:
            print("  ✓ Good detail.")
            score += 1
    if score:
        print(f"\n  Detailed answers: {score}/{len(questions)}")
    print()


# ── Main ─────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Job Scraper | Resume Tailor | Mock Interview")
    print("=" * 55)

    kw = input("\nJob title / keywords: ").strip()
    if not kw:
        return

    print(f"\nSearching LinkedIn for '{kw}' in Singapore (≤2 weeks)...\n")

    jobs = scrape_linkedin(kw)

    if not jobs:
        print("No results. LinkedIn may be blocking — try a VPN or try later.\n")
        return

    for i, j in enumerate(jobs, 1):
        d = (j.get('description', '') or '(no desc)')[:120]
        print(f"  {i}. [{j['company']}] {j['title']}")
        print(f"     {j['url']}")
        print(f"     {d}\n")

    # Resume
    rp = input("Resume path (PDF/TXT) or Enter: ").strip()
    resume = ""
    if rp and os.path.exists(rp):
        resume = parse_resume(rp)
        if resume:
            print(f"  ✓ Loaded ({len(resume)} chars)")

    # Tailor
    if resume:
        c = input("\nTailor resume for job # (Enter=skip): ").strip()
        if c.isdigit() and 1 <= int(c) <= len(jobs):
            j = jobs[int(c) - 1]
            print(f"\n--- {j['title']} @ {j['company']} ---\n")
            print(tailor_resume(resume, j))

    # Questions
    c = input("\nInterview questions for job # (Enter=skip): ").strip()
    if c.isdigit() and 1 <= int(c) <= len(jobs):
        j = jobs[int(c) - 1]
        qs = generate_questions(j)
        print(f"\n--- {j['title']} @ {j['company']} ---\n")
        for i, q in enumerate(qs, 1):
            print(f"  {i}. {q}")

        if input("\nRun mock interview? (y/n): ").strip().lower() == 'y':
            run_mock_interview(qs)

    print("Done.\n")


if __name__ == "__main__":
    main()
