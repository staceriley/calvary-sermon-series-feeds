#!/usr/bin/env python3
from __future__ import annotations
import asyncio, email.utils, hashlib, html, json, re, sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
session = requests.Session()
session.headers.update({"User-Agent": UA})

@dataclass
class Episode:
    title: str
    page_url: str
    audio_url: str
    pubdate: datetime
    description: str = ""

def clean(s): return re.sub(r"\s+", " ", s or "").strip()
def esc(s): return html.escape(s or "", quote=True)

async def load_all_archive_links(cfg):
    archive_url = cfg["archive_url"]
    keywords = [x.lower() for x in cfg.get("match_keywords", [cfg["slug"]])]
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(user_agent=UA, viewport={"width":1400,"height":1200})
        await page.goto(archive_url, wait_until="domcontentloaded", timeout=90000)

        stable = 0
        last_h = last_c = -1
        for _ in range(140):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1200)
            h = await page.evaluate("document.body.scrollHeight")
            links = await page.locator("a[href]").evaluate_all(
                """els => els.map(a => ({
                    href:a.href,
                    text:(a.innerText||'').trim(),
                    parent:(a.parentElement?.innerText||'').trim()
                }))"""
            )
            c = len({
                x["href"].split("#")[0] for x in links
                if x["href"].startswith("https://calvarycr.com/")
                and "/archives/" not in x["href"]
                and "/wp-content/" not in x["href"]
                and (
                    x["text"].lower() == "read more"
                    or any(k in (x["text"]+" "+x["parent"]).lower() for k in keywords)
                )
            })
            if h == last_h and c == last_c: stable += 1
            else: stable = 0
            last_h, last_c = h, c
            if stable >= 4: break

        links = await page.locator("a[href]").evaluate_all(
            """els => els.map(a => ({
                href:a.href,
                text:(a.innerText||'').trim(),
                parent:(a.parentElement?.innerText||'').trim()
            }))"""
        )
        await browser.close()

    out = set()
    for x in links:
        href = x["href"].split("#")[0]
        if not href.startswith("https://calvarycr.com/"): continue
        if any(b in href for b in ["/archives/","/wp-content/","/category/","/tag/","/author/"]): continue
        hay = (x["text"]+" "+x["parent"]).lower()
        if x["text"].lower() == "read more" or any(k in hay for k in keywords):
            out.add(href)
    return sorted(out)

def fetch(url):
    r = session.get(url, timeout=40)
    r.raise_for_status()
    return r.text

def find_audio(soup, page_url):
    cands=[]
    for tag in soup.find_all(["audio","source"]):
        if tag.get("src"): cands.append(urljoin(page_url, tag["src"]))
    for a in soup.find_all("a", href=True):
        u=urljoin(page_url,a["href"])
        if re.search(r"\.(mp3|m4a|aac|ogg)(?:$|\?)",u,re.I): cands.append(u)
    cands += re.findall(r'https?://[^"\'<>\s]+?\.mp3(?:\?[^"\'<>\s]*)?', str(soup), re.I)
    for u in cands:
        if re.search(r"\.(mp3|m4a|aac|ogg)(?:$|\?)",u,re.I): return html.unescape(u)
    return None

def parse_date(soup, text):
    for tag in soup.find_all(["time","meta"]):
        val=tag.get("datetime") or tag.get("content")
        if val:
            try:
                dt=datetime.fromisoformat(val.replace("Z","+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except: pass
    m=re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,\s+(20\d{2})\b",text,re.I)
    if m:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}","%B %d %Y").replace(tzinfo=timezone.utc)
    return datetime(2000,1,1,tzinfo=timezone.utc)

def parse_episode(url):
    try: body=fetch(url)
    except Exception as e:
        print("WARN",url,e,file=sys.stderr); return None
    soup=BeautifulSoup(body,"html.parser")
    audio=find_audio(soup,url)
    if not audio: return None
    h1=soup.find("h1")
    title=clean(h1.get_text(" ",strip=True)) if h1 else clean(soup.title.get_text() if soup.title else "")
    title=re.sub(r"\s+[|–-]\s+Calvary Castle Rock.*$","",title,flags=re.I)
    text=clean(soup.get_text(" ",strip=True))
    return Episode(title,url,audio,parse_date(soup,text),f"Teaching from Calvary Castle Rock. Original page: {url}")

def build_feed(cfg, episodes):
    items=[]
    for ep in sorted(episodes,key=lambda e:e.pubdate,reverse=True):
        guid=hashlib.sha256(ep.audio_url.encode()).hexdigest()
        items.append(f"""    <item>
      <title>{esc(ep.title)}</title>
      <link>{esc(ep.page_url)}</link>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{email.utils.format_datetime(ep.pubdate)}</pubDate>
      <description>{esc(ep.description)}</description>
      <enclosure url="{esc(ep.audio_url)}" length="0" type="audio/mpeg"/>
    </item>""")
    art=cfg.get("art_url","")
    image_xml=f"""    <image>
      <url>{esc(art)}</url>
      <title>{esc(cfg["feed_title"])}</title>
      <link>{esc(cfg["archive_url"])}</link>
    </image>
    <itunes:image href="{esc(art)}"/>""" if art else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{esc(cfg["feed_title"])}</title>
    <link>{esc(cfg["archive_url"])}</link>
    <description>{esc(cfg.get("description","Unofficial RSS wrapper for a Calvary Castle Rock archive."))}</description>
    <language>en-us</language>
{image_xml}
    <itunes:author>{esc(cfg.get("author","Calvary Castle Rock"))}</itunes:author>
    <itunes:explicit>false</itunes:explicit>
{chr(10).join(items)}
  </channel>
</rss>
"""

async def build_one(config_path):
    cfg=json.loads(Path(config_path).read_text(encoding="utf-8"))
    print(f"\n=== {cfg['feed_title']} ===")
    links=await load_all_archive_links(cfg)
    print("Candidate links:",len(links))
    eps=[]
    for i,u in enumerate(links,1):
        print(f"[{i}/{len(links)}] {u}")
        ep=parse_episode(u)
        if ep: eps.append(ep)
    eps=list({e.audio_url:e for e in eps}.values())
    expected=cfg.get("expected_titles",[])
    found={clean(e.title).lower() for e in eps}
    missing=[t for t in expected if clean(t).lower() not in found]
    print("Audio episodes found:",len(eps))
    if missing:
        print("WARNING unmatched expected titles:")
        for t in missing: print(" -",t)
    min_count=cfg.get("minimum_episode_count", max(1, int(len(expected)*0.75))) if expected else 1
    if len(eps)<min_count:
        raise RuntimeError(f"Too few episodes for {cfg['slug']}: {len(eps)} < {min_count}")
    outdir=Path("docs")/cfg["slug"]
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/"feed.xml").write_text(build_feed(cfg,eps),encoding="utf-8")
    print("Wrote",outdir/"feed.xml")

async def main():
    paths=sorted(Path("series").glob("*.json"))
    if not paths: raise SystemExit("No series/*.json configs found")
    for p in paths: await build_one(p)

if __name__=="__main__":
    asyncio.run(main())
