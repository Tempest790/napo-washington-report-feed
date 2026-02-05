#!/usr/bin/env python3
import re
import sys
import html
import datetime
from urllib.request import Request, urlopen

NAPO_URL = "https://www.napo.org/washington-report"
OUT_FILE = "feed.xml"
MAX_ITEMS = 3

def fetch(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; NAPO-RSS/1.0)"
        },
    )
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")

def to_rfc2822(dt: datetime.datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")

def parse_items(page_html: str):
    items = []

    link_title_pattern = re.compile(
        r'<a[^>]+href="(?P<href>/[^"]+)"[^>]*>(?P<title>[^<]{4,200})</a>',
        re.IGNORECASE,
    )

    month_date_pattern = re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
        re.IGNORECASE,
    )
    numeric_date_pattern = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")

    for m in link_title_pattern.finditer(page_html):
        href = m.group("href")
        title = html.unescape(m.group("title")).strip()

        if not title or len(title) < 6:
            continue

        url = "https://www.napo.org" + href

        start = max(0, m.start() - 500)
        end = min(len(page_html), m.end() + 500)
        window = page_html[start:end]

        date_str = None
        md = month_date_pattern.search(window)
        nd = numeric_date_pattern.search(window)
        if md:
            date_str = md.group(0)
        elif nd:
            date_str = nd.group(0)

        if any(it["link"] == url for it in items):
            continue

        items.append({"title": title, "date": date_str, "link": url})
        if len(items) >= MAX_ITEMS:
            break

    return items

def build_rss(items):
    now = datetime.datetime.utcnow()
    channel_title = "NAPO Washington Report (Latest)"
    channel_link = NAPO_URL
    channel_desc = "Latest Washington Report entries from NAPO (title + date + link)."

    rss_items = []
    for it in items:
        pub_dt = now
        if it["date"]:
            try:
                pub_dt = datetime.datetime.strptime(it["date"], "%B %d, %Y")
            except ValueError:
                try:
                    pub_dt = datetime.datetime.strptime(it["date"], "%m/%d/%Y")
                except ValueError:
                    pub_dt = now

        # description shows the date only (keeps it minimal)
        rss_items.append(f"""\
    <item>
      <title>{html.escape(it["title"])}</title>
      <link>{html.escape(it["link"])}</link>
      <guid isPermaLink="true">{html.escape(it["link"])}</guid>
      <pubDate>{to_rfc2822(pub_dt)}</pubDate>
      <description>{html.escape(it["date"] or "")}</description>
    </item>""")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{html.escape(channel_title)}</title>
    <link>{html.escape(channel_link)}</link>
    <atom:link href="https://tempest790.github.io/napo-washington-report-feed/feed.xml" rel="self" type="application/rss+xml" />
    <description>{html.escape(channel_desc)}</description>
    <lastBuildDate>{to_rfc2822(now)}</lastBuildDate>
{chr(10).join(rss_items)}
  </channel>
</rss>
"""

def main():
    page = fetch(NAPO_URL)
    items = parse_items(page)
    if not items:
        print("No items found. The page structure may have changed.", file=sys.stderr)
        sys.exit(1)

    rss = build_rss(items)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(rss)

    print(f"Wrote {OUT_FILE} with {len(items)} items.")

if __name__ == "__main__":
    main()
