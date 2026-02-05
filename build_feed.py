#!/usr/bin/env python3
import re
import html
import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Source page (list of Washington Report items)
NAPO_URL = "https://www.napo.org/washington-report"

# Output feed file (repo root)
OUT_FILE = "feed.xml"

# How many items to include
MAX_ITEMS = 3

# The public URL of your feed (GitHub Pages)
FEED_SELF = "https://tempest790.github.io/napo-washington-report-feed/feed.xml"

# --------- Fetch helpers ---------

MONTH_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)

NEWS_HREF_RE = re.compile(r'href="(?P<href>/news/[^"#?]+)"', re.IGNORECASE)


def fetch(url: str) -> str:
    """Fetch HTML with browser-ish headers to reduce blocks."""
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.napo.org/",
        },
    )
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def to_rfc2822(dt: datetime.datetime) -> str:
    """RSS pubDate format."""
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


# --------- Parsing helpers ---------

def parse_article_date(article_html: str):
    """
    Extract a publish date from an article page.
    Tries:
      - meta property="article:published_time"
      - time datetime="..."
      - Month Day, Year text
    Returns a naive UTC-ish datetime or None.
    """
    m = re.search(
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        article_html,
        re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip()
        try:
            raw2 = raw.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(raw2)
            if dt.tzinfo:
                dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            pass

    m = re.search(r"<time[^>]+datetime=[\"']([^\"']+)[\"']", article_html, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
        try:
            raw2 = raw.replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(raw2)
            if dt.tzinfo:
                dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            try:
                return datetime.datetime.strptime(raw[:10], "%Y-%m-%d")
            except Exception:
                pass

    m = MONTH_DATE_RE.search(article_html)
    if m:
        try:
            return datetime.datetime.strptime(m.group(0), "%B %d, %Y")
        except Exception:
            pass

    return None


def parse_article_title(article_html: str):
    """Prefer og:title, fallback to <title>."""
    m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        article_html,
        re.IGNORECASE,
    )
    if m:
        return html.unescape(m.group(1)).strip()

    m = re.search(r"<title>(.*?)</title>", article_html, re.IGNORECASE | re.DOTALL)
    if m:
        t = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
        return t

    return None


def get_candidates_from_washington_report(page_html: str):
    """Extract a small list of /news/ links from the Washington Report listing page."""
    seen = set()
    urls = []
    for m in NEWS_HREF_RE.finditer(page_html):
        href = m.group("href").strip()
        url = "https://www.napo.org" + href
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls[:15]  # check a few to reliably get the newest 3


def collect_latest_items():
    """Fetch listing page, then fetch candidate news pages to get real titles/dates."""
    try:
        wr_html = fetch(NAPO_URL)
    except (HTTPError, URLError) as e:
        print(f"ERROR fetching Washington Report page: {e}")
        return []

    candidates = get_candidates_from_washington_report(wr_html)
    items = []

    for url in candidates:
        try:
            ahtml = fetch(url)
        except Exception:
            continue

        dt = parse_article_date(ahtml)
        title = parse_article_title(ahtml)

        if not dt or not title:
            continue

        items.append({"title": title, "date_dt": dt, "link": url})

    items.sort(key=lambda x: x["date_dt"], reverse=True)
    return items[:MAX_ITEMS]


# --------- RSS build ---------

def build_rss(items):
    now = datetime.datetime.utcnow()
    channel_title = "NAPO Washington Report (Latest)"
    channel_link = NAPO_URL
    channel_desc = "Latest Washington Report entries from NAPO (title + date + link)."

    rss_items = []
    for it in items:
        pub_dt = it["date_dt"]
        date_str = pub_dt.strftime("%B %d, %Y")

        # GoodBarber sometimes ignores <link> unless the body contains a clickable URL.
        link_html = f'<p><a href="{html.escape(it["link"])}">Open the full article on NAPO</a></p>'

        rss_items.append(f"""\
    <item>
      <title>{html.escape(it["title"])}</title>
      <link>{html.escape(it["link"])}</link>
      <guid isPermaLink="true">{html.escape(it["link"])}</guid>
      <pubDate>{to_rfc2822(pub_dt)}</pubDate>
      <description><![CDATA[{date_str}<br/>{link_html}]]></description>
      <content:encoded><![CDATA[{link_html}]]></content:encoded>
    </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{html.escape(channel_title)}</title>
    <link>{html.escape(channel_link)}</link>
    <atom:link href="{html.escape(FEED_SELF)}" rel="self" type="application/rss+xml" />
    <description>{html.escape(channel_desc)}</description>
    <lastBuildDate>{to_rfc2822(now)}</lastBuildDate>
{chr(10).join(rss_items)}
  </channel>
</rss>
"""


def main():
    items = collect_latest_items()

    # Never fail the workflow—write a valid feed even if empty.
    if not items:
        print("WARNING: No items found (writing empty feed).")

    rss = build_rss(items)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(rss)

    print(f"Wrote {OUT_FILE} with {len(items)} items.")
    for it in items:
        print(f"- {it['date_dt'].strftime('%Y-%m-%d')} | {it['title']} -> {it['link']}")


if __name__ == "__main__":
    main()
