"""Glassdoor lookup and AI salary estimation."""

import re, urllib.parse, requests
from bs4 import BeautifulSoup
from utils import HEADERS, DEEPSEEK_KEY, call_deepseek


def lookup_glassdoor(company_name):
    """Try to find Glassdoor rating + salary for a company."""
    rating, salary = None, None
    try:
        gd_url = f"https://www.glassdoor.com/Search/results.htm?keyword={urllib.parse.quote(company_name + ' Singapore')}"
        resp = requests.get(gd_url, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for el in soup.find_all(["span", "div"], class_=re.compile(r"rating|score", re.I)):
                t = el.get_text().strip()
                m = re.search(r'(\d\.\d)', t)
                if m and 1 <= float(m.group(1)) <= 5:
                    rating = float(m.group(1))
                    break
            salary_text = soup.get_text()
            m = re.search(r'(?:S\$\s?|SGD\s?)([\d,]+)\s*(?:–|-|to)\s*(?:S\$\s?|SGD\s?)?([\d,]+)', salary_text, re.I)
            if m:
                salary = _to_monthly(f"SGD {m.group(1)} - {m.group(2)}")
            if rating or salary:
                return {"rating": rating, "salary": salary}
    except:
        pass
    for engine in ["google", "bing"]:
        try:
            if engine == "google":
                url = f"https://www.google.com/search?q={urllib.parse.quote(company_name + ' glassdoor review rating')}&hl=en"
            else:
                url = f"https://www.bing.com/search?q={urllib.parse.quote(company_name + ' glassdoor review')}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            if not rating:
                for el in soup.find_all(["span", "div", "em", "a"]):
                    t = el.get_text()
                    m = re.search(r'(\d\.\d)\s*(?:out of 5|stars|rating|★|/5)', t, re.I)
                    if m:
                        rating = float(m.group(1))
                        break
            if not salary:
                salary_text = soup.get_text()
                m = re.search(r'(?:S\$\s?|SGD\s?)([\d,]+)\s*(?:–|-|to)\s*(?:S\$\s?|SGD\s?)?([\d,]+)', salary_text, re.I)
                if m:
                    salary = _to_monthly(f"SGD {m.group(1)} - {m.group(2)}")
                else:
                    m = re.search(r'(?:S\$\s?|SGD\s?)([\d,]+)\s*(?:/yr|/year|per year|/mo|/month)', salary_text, re.I)
                    if m:
                        suffix = "/mo" if re.search(r'/mo|/month', m.group(0), re.I) else ""
                        raw = f"SGD {m.group(1)}"
                        salary = raw + suffix if suffix else _to_monthly(raw)
            if rating or salary:
                return {"rating": rating, "salary": salary}
        except:
            continue
    return {"error": "Falling back to AI search (Glassdoor unreachable)."}


def _to_monthly(salary_str):
    if not salary_str:
        return salary_str
    already_monthly = bool(re.search(r'/mo|/month|per month', salary_str, re.I))
    nums = re.findall(r'([\d,]+)', salary_str)
    if not nums:
        return salary_str
    converted = []
    for n in nums:
        try:
            val = int(n.replace(',', ''))
            if not already_monthly:
                val = round(val / 12)
            converted.append(f"{val:,}")
        except Exception:
            converted.append(n)
    if len(converted) >= 2:
        return f"SGD {converted[0]} - {converted[1]}/mo"
    elif converted:
        return f"SGD {converted[0]}/mo"
    return salary_str


def guess_company_info(company_name, job_title="", jd_text=""):
    """Use DeepSeek to estimate rating + monthly salary when Glassdoor is unavailable."""
    if not DEEPSEEK_KEY:
        return None
    prompt = f"""Company: {company_name}
Role: {job_title}
Location: Singapore
Job Description: {jd_text[:2000]}

Estimate for this specific role in Singapore:
1. Company rating out of 5 (based on reputation, size, industry standing)
2. Monthly salary RANGE in SGD (e.g. "SGD 5,000 - 8,000/mo")
3. A 2-3 sentence justification explaining what drives this range

Factor in: seniority implied by the JD, YOE required, skills scarcity, company tier, and current Singapore tech market rates.

Format exactly:
Rating: X.X/5
Salary: SGD X,XXX - X,XXX/mo
Why: <your 2-3 sentence justification here>"""
    result = call_deepseek(prompt, "You are a compensation analyst with deep knowledge of Singapore tech salaries. Always return MONTHLY salary range. Be specific in your justification — cite concrete factors like YOE, skill demand, company tier.", max_tokens=250)
    if not result:
        return None
    info = {}
    m = re.search(r'Rating:\s*(\d\.?\d?)', result)
    if m:
        try:
            info["rating"] = float(m.group(1))
        except:
            pass
    m = re.search(r'Salary:\s*(SGD\s*[\d,]+)\s*(?:–|-|to)\s*(SGD\s*[\d,]+)', result, re.I)
    if m:
        sl = f"{m.group(1).strip()} - {m.group(2).strip()}"
        info["salary"] = sl if sl.endswith("/mo") else sl + "/mo"
    else:
        m = re.search(r'Salary:\s*(SGD\s*[\d,]+)', result, re.I)
        if m:
            sl = m.group(1).strip()
            info["salary"] = sl if sl.endswith("/mo") else sl + "/mo"
    m = re.search(r'Why:\s*(.+?)(?:\n|$)', result, re.I)
    if m:
        info["why"] = m.group(1).strip()
    if info:
        info["ai_guess"] = True
    return info if info else None
