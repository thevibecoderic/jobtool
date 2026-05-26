"""LinkedIn job scraping: search, details, similar jobs, text extraction."""

import re, json, time, urllib.parse, requests
from bs4 import BeautifulSoup
import streamlit as st

from utils import (HEADERS, GOOGLEBOT_HEADERS, LOCATION, TIME_RANGE,
                   DEEPSEEK_KEY, detect_mode, extract_requirements, clean_html)


# ── Embedded data parser ──

def _parse_embedded(soup):
    """Extract jobs from __NEXT_DATA__, __INITIAL_STATE__, __APOLLO_STATE__, or JSON-LD."""
    jobs = []
    seen_urls = set()

    def _add_job(jp):
        def _s(v, default=""):
            if v is None:
                return default
            if isinstance(v, str):
                return v
            if isinstance(v, (int, float)):
                return str(v)
            if isinstance(v, bool):
                return str(v) if v else default
            return default

        url = ""
        entity_urn = _s(jp.get("entityUrn"))
        if entity_urn and ":" in entity_urn:
            url = f"https://www.linkedin.com/jobs/view/{entity_urn.split(':')[-1]}/"
        if not url:
            url = _s(jp.get("url")) or _s(jp.get("applyUrl"))
        if not url:
            return
        if url in seen_urls:
            return
        seen_urls.add(url)

        desc = ""
        desc_keys = ["description", "descriptionText", "jobDescription", "descriptionHtml",
                     "detailDescription", "summary", "body", "content", "text", "html"]
        for dk in desc_keys:
            raw = jp.get(dk, "")
            if isinstance(raw, str) and raw.strip():
                if raw[0] == "<" or "<" in raw[:200]:
                    desc = BeautifulSoup(raw, "html.parser").get_text().strip()
                else:
                    desc = raw.strip()
                if len(desc) > 80:
                    break
                desc = ""
            elif isinstance(raw, dict):
                for ik in ["text", "html", "plainText", "content", "body"]:
                    inner = raw.get(ik, "")
                    if isinstance(inner, str) and inner.strip():
                        if inner[0] == "<" or "<" in inner[:200]:
                            desc = BeautifulSoup(inner, "html.parser").get_text().strip()
                        else:
                            desc = inner.strip()
                        if len(desc) > 80:
                            break
                        desc = ""
                if len(desc) > 80:
                    break
        if not desc:
            best = ""
            def _find_longest(obj, depth=0):
                nonlocal best
                if depth > 6:
                    return
                if isinstance(obj, str) and len(obj) > len(best) and len(obj) > 150:
                    best = obj
                elif isinstance(obj, dict):
                    for v in obj.values():
                        _find_longest(v, depth + 1)
                elif isinstance(obj, list):
                    for v in obj[:30]:
                        _find_longest(v, depth + 1)
            _find_longest(jp)
            if best:
                if best[0] == "<" or "<" in best[:200]:
                    desc = BeautifulSoup(best, "html.parser").get_text().strip()
                else:
                    desc = best.strip()

        company = "Unknown"
        logo = ""
        company_keys = ["hiringOrganization", "companyDetails", "company", "companyName",
                        "employer", "hiringCompany", "organization", "org"]
        for ck in company_keys:
            org = jp.get(ck)
            if isinstance(org, dict):
                for nk in ["name", "companyName", "title", "label"]:
                    v = org.get(nk)
                    if isinstance(v, str) and v.strip():
                        company = v.strip()
                        break
                # Extract logo from same dict
                if not logo:
                    for lk in ["logo", "logoUrl", "companyLogoUrl", "logoImageUrl", "squareLogoUrl"]:
                        lv = org.get(lk)
                        if isinstance(lv, str) and lv.strip() and "http" in lv:
                            logo = lv.strip()
                            break
                if company != "Unknown":
                    break
            elif isinstance(org, str) and org.strip():
                company = org.strip()
                break
        if not isinstance(company, str) or company in ("0", "1", "None", "null", ""):
            company = "Unknown"
        # Try top-level logo keys
        if not logo:
            for lk in ["logo", "logoUrl", "companyLogoUrl", "squareLogoUrl"]:
                lv = jp.get(lk)
                if isinstance(lv, str) and lv.strip() and "http" in lv:
                    logo = lv.strip()
                    break

        title = ""
        for tk in ["title", "jobTitle", "name", "headline", "position", "role"]:
            v = jp.get(tk)
            if isinstance(v, str) and v.strip() and len(v) > 2:
                title = v.strip()
                break
        if not title:
            title = "Untitled"

        date_posted = ""
        for dk in ["datePosted", "listedAt", "createdAt", "publishedAt", "postDate", "postedDate", "postedAt"]:
            dv = jp.get(dk)
            if dv is not None:
                date_posted = str(dv)
                break
        if date_posted and date_posted.isdigit() and len(date_posted) >= 10:
            try:
                import datetime
                ts_digits = int(date_posted)
                if ts_digits > 1_000_000_000_000:
                    ts = ts_digits / 1000
                else:
                    ts = ts_digits
                dt = datetime.datetime.fromtimestamp(ts)
                days_ago = (datetime.datetime.now() - dt).days
                date_posted = f"{days_ago} days ago" if days_ago > 0 else "Today"
            except Exception:
                pass

        if title == "Untitled" and not desc:
            return

        jobs.append({
            "title": title,
            "company": company,
            "url": url, "description": desc,
            "requirements": extract_requirements(desc),
            "mode": detect_mode(desc), "logo": logo,
            "date_posted": date_posted,
        })

    # 1) __NEXT_DATA__
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data and next_data.string:
        try:
            data = json.loads(next_data.string)
            def walk(obj, depth=0):
                if depth > 20:
                    return
                if isinstance(obj, dict):
                    if "jobPosting" in obj:
                        _add_job(obj["jobPosting"])
                    keys = set(obj.keys())
                    has_job_keys = keys & {"title", "companyName", "hiringOrganization", "jobPosting", "description", "entityUrn"}
                    has_desc_signal = keys & {"description", "descriptionText", "jobDescription", "hiringOrganization", "companyName", "companyDetails"}
                    has_url = keys & {"url", "applyUrl", "entityUrn"}
                    if len(has_job_keys) >= 2 and len(has_url) >= 1 and len(has_desc_signal) >= 1:
                        url_val = str(obj.get("url", "") or obj.get("entityUrn", ""))
                        if "linkedin.com/jobs" in url_val or "linkedin.com" in url_val or "job" in url_val.lower():
                            _add_job(obj)
                    for v in obj.values():
                        walk(v, depth + 1)
                elif isinstance(obj, list):
                    for v in obj[:100]:
                        walk(v, depth + 1)
            walk(data)
        except:
            pass

    # 2) window.__INITIAL_STATE__ / window.__APOLLO_STATE__
    for script in soup.find_all("script"):
        if not script.string:
            continue
        for prefix in ["window.__INITIAL_STATE__", "window.__APOLLO_STATE__"]:
            if prefix not in script.string:
                continue
            try:
                start = script.string.index(prefix)
                after = script.string[start + len(prefix):]
                eq = after.find("=")
                if eq == -1:
                    eq = after.find("{")
                else:
                    eq = after.find("{", eq)
                if eq == -1:
                    continue
                depth_count = 0
                end = eq
                in_string = False
                esc = False
                for i, ch in enumerate(after[eq:], eq):
                    if esc:
                        esc = False
                        continue
                    if ch == '\\':
                        esc = True
                        continue
                    if ch == '"' and not in_string:
                        in_string = True
                    elif ch == '"' and in_string:
                        in_string = False
                    elif not in_string:
                        if ch == "{":
                            depth_count += 1
                        elif ch == "}":
                            depth_count -= 1
                            if depth_count == 0:
                                end = i + 1
                                break
                if end <= eq:
                    continue
                raw = after[eq:end]
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                def walk2(obj, d=0):
                    if d > 20:
                        return
                    if isinstance(obj, dict):
                        for k in ["jobs", "jobPostings", "results", "items", "data", "included"]:
                            if k in obj and isinstance(obj[k], list):
                                for item in obj[k][:50]:
                                    if isinstance(item, dict):
                                        _add_job(item)
                        for v in obj.values():
                            walk2(v, d + 1)
                    elif isinstance(obj, list):
                        for v in obj[:100]:
                            walk2(v, d + 1)
                walk2(data)
            except:
                continue

    # 3) JSON-LD
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "JobPosting":
                    _add_job(item)
        except:
            pass

    # 4) Heading-based fallback
    for h in soup.find_all(["h1", "h2", "h3"]):
        title = h.get_text(strip=True)
        if not title or len(title) < 3 or len(title) > 120:
            continue
        parent = h.find_parent(["div", "section", "article"])
        if not parent:
            continue
        desc_candidates = parent.find_all(["p", "div", "span", "section", "article"])
        for dc in desc_candidates:
            txt = dc.get_text(" ", strip=True)
            if len(txt) > 200:
                link = parent.find("a", href=re.compile(r"/jobs/"))
                url = ""
                if link:
                    url = link["href"]
                    if not url.startswith("http"):
                        url = "https://www.linkedin.com" + url
                if url and url in seen_urls:
                    break
                if url:
                    seen_urls.add(url)
                jobs.append({
                    "title": title,
                    "company": "Unknown",
                    "url": url,
                    "description": txt[:3000],
                    "requirements": extract_requirements(txt),
                    "mode": detect_mode(txt), "logo": "",
                    "date_posted": "",
                })
                break
        if len(jobs) >= 10:
            break
    return jobs


# ── Card parsing helpers ──

def _extract_card_date(card):
    for el in card.find_all(["time", "span", "p"]):
        text = el.get_text(strip=True).lower()
        if any(w in text for w in ["day", "week", "month", "hour", "minute", "ago", "just now"]):
            return el.get_text(strip=True)
        if el.get("datetime"):
            return el["datetime"]
    return ""


def _extract_card_snippet(card):
    """Extract visible description snippet from a job card."""
    def _is_metadata(text):
        t = text.lower().strip()
        if re.match(r'^[a-z]+(,\s*[a-z]+)+$', t) and len(t) < 60:
            return True
        if re.search(r'\d+\s*(day|week|month|hour|minute|yr|year)s?\s*ago|today|yesterday|just now', t):
            if len(t) < 80:
                return True
        if re.match(r'^\d{4}-\d{2}-\d{2}$', t.strip()):
            return True
        if re.match(r'^[A-Z][a-z]+,\s*[A-Z][a-z]+(\s+\d+)?$', t.strip()) and len(t) < 40:
            return True
        return False

    for cls_pat in [r"snippet", r"metadata", r"description", r"summary", r"detail", r"info", r"body", r"text"]:
        el = card.find(["p", "div", "span", "section"], class_=re.compile(cls_pat, re.I))
        if el:
            text = el.get_text(" ", strip=True)
            if len(text) > 80 and not _is_metadata(text):
                return text
    for tag in ["p", "span", "div"]:
        for el in card.find_all(tag):
            text = el.get_text(" ", strip=True)
            if len(text) > 80:
                if not re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+){0,3}$', text):
                    if not _is_metadata(text):
                        return text
    all_text = card.get_text("\n", strip=True)
    lines = [l.strip() for l in all_text.split("\n") if l.strip()]
    meaningful = [l for l in lines if len(l) > 60
                  and not re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+){0,3}$', l)
                  and not _is_metadata(l)]
    if meaningful:
        return " ".join(meaningful[:5])
    parent = card.find_parent(["div", "li", "section"])
    if parent:
        for el in parent.find_all(recursive=False):
            text = el.get_text(" ", strip=True)
            if len(text) > 100 and not _is_metadata(text):
                return text[:2000]
    return ""


# ── Main scraper ──

@st.cache_data(ttl=600, show_spinner=False)
def scrape_linkedin(keywords, max_jobs=30):
    jobs = []
    seen = set()
    for start in range(0, max_jobs, 25):
        url = (
            f"https://www.linkedin.com/jobs/search/?"
            f"keywords={urllib.parse.quote(keywords)}"
            f"&location={urllib.parse.quote(LOCATION)}"
            f"&f_TPR={TIME_RANGE}"
            f"&position=1&pageNum={start // 25}"
        )
        for headers in (HEADERS, GOOGLEBOT_HEADERS):
            if len(jobs) >= max_jobs:
                break
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
            except:
                continue

            # 1) Embedded data
            embedded = _parse_embedded(soup)
            for j in (embedded or []):
                u = j.get("url", "")
                if u and u not in seen:
                    seen.add(u)
                    jobs.append(j)
            if len(jobs) >= max_jobs:
                break

            # 2) Card parsing
            cards = soup.find_all("div", class_=re.compile(r"base-card|job-card|job-search-card"))
            if not cards:
                cards = soup.find_all("li", class_=re.compile(r"job|result"))
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
                if job_url in seen:
                    continue
                seen.add(job_url)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                date_posted = _extract_card_date(card)
                # Try to find logo near the card
                logo = ""
                img = card.find("img")
                if img and img.get("src"):
                    logo = img["src"]
                desc, reqs = get_job_details(job_url)
                if not desc:
                    desc = _extract_card_snippet(card)
                jobs.append({
                    "title": title_el.get_text(strip=True),
                    "company": company,
                    "url": job_url, "description": desc,
                    "requirements": reqs, "mode": detect_mode(desc),
                    "logo": logo, "date_posted": date_posted,
                })
            if len(jobs) >= max_jobs:
                break
            time.sleep(1.5)
        if len(jobs) >= max_jobs:
            break
    return jobs


def _extract_desc_from_json(data, depth=0):
    """Recursively find a description string in a parsed JSON object."""
    if depth > 10:
        return None
    if isinstance(data, str) and len(data) > 200:
        return data
    if isinstance(data, dict):
        for k in ["description", "descriptionText", "jobDescription", "descriptionHtml"]:
            v = data.get(k)
            if isinstance(v, str) and len(v) > 200:
                return v
        for v in data.values():
            r = _extract_desc_from_json(v, depth + 1)
            if r:
                return r
    elif isinstance(data, list):
        for item in data[:50]:
            r = _extract_desc_from_json(item, depth + 1)
            if r:
                return r
    return None


def get_job_details(job_url):
    """Fetch full job description from individual LinkedIn job page."""
    for ua_headers in [GOOGLEBOT_HEADERS, HEADERS]:
        try:
            resp = requests.get(job_url, headers=ua_headers, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                continue
            if len(resp.text) < 500 or "authwall" in resp.text.lower():
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            desc_el = (soup.find("div", class_="description__text") or
                       soup.find("div", class_="show-more-less-html__markup") or
                       soup.find("div", class_=re.compile(r"description", re.I)) or
                       soup.find("div", class_=re.compile(r"jobs-description", re.I)) or
                       soup.find("section", class_=re.compile(r"description", re.I)))
            if desc_el:
                desc = desc_el.get_text("\n", strip=True)
                if len(desc) > 200:
                    return desc, extract_requirements(desc)

            for s in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(s.string)
                    if "description" in data:
                        desc = data["description"]
                        if isinstance(desc, str) and len(desc) > 200:
                            desc = clean_html(desc)
                            return desc, extract_requirements(desc)
                except:
                    pass

            meta = soup.find("meta", attrs={"name": "description"})
            if meta and meta.get("content"):
                desc = meta["content"].strip()
                if len(desc) > 200:
                    return desc, extract_requirements(desc)

            for script in soup.find_all("script"):
                if not script.string:
                    continue
                if '"description"' not in script.string or '"title"' not in script.string:
                    continue
                try:
                    for m in re.finditer(r'\{', script.string):
                        start = m.start()
                        depth = 0
                        in_str = False
                        esc = False
                        end = start
                        for i, ch in enumerate(script.string[start:], start):
                            if esc:
                                esc = False
                                continue
                            if ch == '\\':
                                esc = True
                                continue
                            if ch == '"':
                                in_str = not in_str
                            elif not in_str:
                                if ch == '{':
                                    depth += 1
                                elif ch == '}':
                                    depth -= 1
                                    if depth == 0:
                                        end = i + 1
                                        break
                        if end <= start:
                            continue
                        block = script.string[start:end]
                        data = json.loads(block)
                        desc_val = _extract_desc_from_json(data)
                        if desc_val and len(desc_val) > 200:
                            desc = clean_html(desc_val)
                            return desc, extract_requirements(desc)
                except:
                    continue
        except:
            continue
    return "", ""


def scrape_similar_jobs(job_title, company, max_jobs=5):
    """Find similar jobs on LinkedIn by searching with the same title."""
    query = urllib.parse.quote(f"{job_title} NOT {company}", safe=" ")
    url = f"https://www.linkedin.com/jobs/search/?keywords={query}&location=Singapore&f_TPR=r1209600&position=1&pageNum=0"
    try:
        resp = requests.get(url, headers=GOOGLEBOT_HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all("div", class_=re.compile(r"base-card|job-card"))
        if not cards:
            cards = soup.find_all("li", class_=re.compile(r"job|result"))
        similar = []
        seen_titles = set()
        for card in cards:
            if len(similar) >= max_jobs:
                break
            title_el = card.find(["h3", "h2", "span"], class_=re.compile(r"title", re.I))
            company_el = card.find(["h4", "span", "div"], class_=re.compile(r"subtitle|company", re.I))
            link_el = card.find("a", href=re.compile(r"/jobs/"))
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            comp = company_el.get_text(strip=True) if company_el else "?"
            if title.lower() in seen_titles or title.lower() == job_title.lower():
                continue
            seen_titles.add(title.lower())
            url = ""
            if link_el:
                url = link_el["href"]
                if not url.startswith("http"):
                    url = "https://www.linkedin.com" + url
            similar.append({"title": title, "company": comp, "url": url})
        return similar
    except:
        return []


# ── Text extraction for custom/pasted jobs ──

def extract_title(text, use_ai=True):
    """Extract job title from pasted job description or LinkedIn URL."""
    if not text:
        return "Custom Job"
    m = re.search(r'linkedin\.com/jobs/view/([^/]+)-\d+', text)
    if m:
        return m.group(1).replace('-', ' ').title()
    if use_ai and DEEPSEEK_KEY:
        from utils import call_deepseek
        result = call_deepseek(
            f"Extract ONLY the job title from this text. Return just the title, nothing else:\n\n{text[:1500]}",
            "You extract job titles. Return only the title, no explanation.", max_tokens=50
        )
        if result and len(result.strip()) > 2 and len(result.strip()) < 80:
            return result.strip()
    lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 3]
    for line in lines[:5]:
        if re.match(r'^(at |@|[A-Z][a-z]+(?: [A-Z][a-z]+){0,2}$)', line):
            continue
        if re.match(r'^(Singapore|Remote|Hybrid|In.office|Full.time|Part.time|Contract|S\$|Posted|\d+ (day|week|month)s? ago)', line, re.I):
            continue
        if 5 < len(line) < 80 and not line.startswith('http'):
            return line[:80]
    return "Custom Job"


def extract_company(text, use_ai=True):
    """Extract company name from pasted job description."""
    if not text:
        return "Unknown"
    if use_ai and DEEPSEEK_KEY:
        from utils import call_deepseek
        result = call_deepseek(
            f"Extract ONLY the company name from this job posting. Return just the company name, nothing else:\n\n{text[:1500]}",
            "You extract company names. Return only the name, no explanation.", max_tokens=30
        )
        if result and len(result.strip()) > 1 and len(result.strip()) < 50:
            return result.strip()
    m = re.search(r'\bat\s+([A-Z][A-Za-z0-9 .&,-]+?)(?:\s+is\b|\s+in\b|\s+Singapore|\s*$|\.)', text)
    if m and len(m.group(1)) > 2:
        return m.group(1).strip().rstrip('.,')
    m = re.search(r'@\s*([A-Z][A-Za-z0-9 .&,-]+?)(?:\s|$|\.|,)', text)
    if m and len(m.group(1)) > 2:
        return m.group(1).strip()
    m = re.search(r'([A-Z][A-Za-z0-9 .&,-]{2,30})\s+is\s+(hiring|looking)', text)
    if m:
        return m.group(1).strip()
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:5]:
        if re.match(r'^[A-Z][A-Za-z0-9 .&,-]{2,30}$', line) and not re.match(r'^(Singapore|Remote|Hybrid)', line, re.I):
            return line[:40]
    return "Unknown"
