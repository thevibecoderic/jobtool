"""Config, helpers, and text extraction shared across modules."""

import os, re, requests, urllib.parse, html as _html

from bs4 import BeautifulSoup

# ── Config ──
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
GOOGLEBOT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
LOCATION = "Singapore"
TIME_RANGE = "r1209600"

DEEPSEEK_KEY = ""
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def _load_env():
    if os.environ.get("DEEPSEEK_API_KEY"):
        return
    try:
        import streamlit as _st
        if _st.secrets.get("DEEPSEEK_API_KEY"):
            os.environ["DEEPSEEK_API_KEY"] = _st.secrets["DEEPSEEK_API_KEY"]
            return
    except Exception:
        pass
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()
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


def detect_mode(desc):
    if not desc:
        return ""
    d = desc.lower()
    if "remote" in d:
        return "🏠 Remote" if "hybrid" not in d else "🏢🏠 Hybrid"
    if "hybrid" in d:
        return "🏢🏠 Hybrid"
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
    except Exception:
        pass
    return None


def clean_html(html_str):
    """Unescape LinkedIn double-encoded HTML, keeping formatting tags."""
    text = _html.unescape(html_str)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.I | re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.I | re.DOTALL)
    text = re.sub(r'\s+on\w+="[^"]*"', '', text, flags=re.I)
    text = re.sub(r'<(?!br\b|strong\b|b\b|em\b|i\b|u\b|ul\b|ol\b|li\b|p\b|h[1-6]\b|/\s*(?:br|strong|b|em|i|u|ul|ol|li|p|h[1-6])\s*)[^>]+>', '', text, flags=re.I)
    return text.strip()


def extract_salary_from_jd(text):
    """Extract salary range from job description text. Returns formatted string or None."""
    if not text:
        return None
    # Monthly range
    m = re.search(r'(?:SGD|S\$)\s*([\d,]+)\s*(?:–|-|to)\s*(?:SGD|S\$)?\s*([\d,]+)\s*(?:/mo|/month|per\s+month)', text, re.I)
    if m:
        return f"SGD {m.group(1)} - {m.group(2)}/mo"
    # Annual range
    m = re.search(r'(?:SGD|S\$)\s*([\d,]+)\s*(?:–|-|to)\s*(?:SGD|S\$)?\s*([\d,]+)\s*(?:/yr|/year|per\s+year|/annum|per\s+annum)', text, re.I)
    if m:
        v1 = round(int(m.group(1).replace(',', '')) / 12)
        v2 = round(int(m.group(2).replace(',', '')) / 12)
        return f"SGD {v1:,} - {v2:,}/mo"
    # $Xk - $Yk
    m = re.search(r'\$(\d+)k\s*(?:–|-|to)\s*\$(\d+)k', text, re.I)
    if m:
        v1 = int(m.group(1)) * 1000 // 12
        v2 = int(m.group(2)) * 1000 // 12
        return f"SGD {v1:,} - {v2:,}/mo"
    # Single monthly
    m = re.search(r'(?:SGD|S\$)\s*([\d,]+)\s*(?:/mo|/month)', text, re.I)
    if m:
        return f"SGD {m.group(1)}/mo"
    # Range near salary keyword
    m = re.search(r'(?:salary|compensation|pay|remuneration).{0,80}?([\d,]+)\s*(?:–|-|to)\s*([\d,]+)', text, re.I)
    if m:
        v1 = int(m.group(1).replace(',', ''))
        v2 = int(m.group(2).replace(',', ''))
        if v1 >= 1000 and v2 >= 1000:
            if v1 > 100000:
                v1, v2 = round(v1 / 12), round(v2 / 12)
            return f"SGD {v1:,} - {v2:,}/mo"
    return None


def extract_requirements(text):
    if not text:
        return ""
    section_pat = r'(?:requirements?|qualifications?|what (?:we|you|we\'re|you\'ll).{0,20}need|must have|required.{0,10}(?:skill|experience)|who (?:you are|we\'re looking for)|(?:your|key) (?:background|skills|qualifications)|what you\'ll bring|we are looking for|you\'ll need|about you|the ideal candidate|minimum qualifications|preferred qualifications|what we\'re looking for)'
    m = re.search(section_pat, text, re.IGNORECASE)
    if m:
        section = text[m.start():]
        stop = len(section)
        for kw in ['responsibilities', 'about the role', 'we offer', 'benefits', 'what we offer', 'why join', 'about us', 'the role', 'job description', 'overview', 'who we are']:
            m2 = re.search(kw, section[80:], re.IGNORECASE)
            if m2:
                stop = min(stop, 80 + m2.start())
        result = section[:stop].strip()
        if len(result) > 40:
            return result
    lines = text.split('\n')
    req_keywords = ['require', 'qualif', 'skill', 'experience', 'degree', 'year', 'proficien', 'knowledge of', 'familiar', 'ability to', 'strong', 'excellent', 'background in']
    req_lines = [l for l in lines if len(l.strip()) > 10 and any(w in l.lower() for w in req_keywords)]
    if req_lines:
        return '\n'.join(req_lines[:15])
    return text[:400]
