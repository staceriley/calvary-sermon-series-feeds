#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import email.utils
import hashlib
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
PUBLIC_BASE = "https://staceriley.github.io/calvary-sermon-series-feeds"

session = requests.Session()
session.headers.update({"User-Agent": UA})


@dataclass
class Episode:
    title: str
    page_url: str
    audio_url: str
    pubdate: datetime
    description: str = ""


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def esc(s):
    return html.escape(s or "", quote=True)


async def load_all_archive_links(cfg):
    archive_url = cfg["archive_url"]
    keywords = [x.lower() for x in cfg.get("match_keywords", [cfg["slug"]])]

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            user_agent=UA,
            viewport={"width": 1400, "height": 1200},
        )
        await page.goto(
            archive_url,
            wait_until="domcontentloaded",
            timeout=90000,
        )

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
                x["href"].split("#")[0]
                for x in links
                if x["href"].startswith("https://calvarycr.com/")
                and "/archives/" not in x["href"]
                and "/wp-content/" not in x["href"]
                and (
                    x["text"].lower() == "read more"
                    or any(
                        k in (x["text"] + " " + x["parent"]).lower()
                        for k in keywords
                    )
                )
            })

            if h == last_h and c == last_c:
                stable += 1
            else:
                stable = 0
