#!/usr/bin/env python3
"""note の「今日のあなたに」に出る記事作者の X アカウント候補を収集する CLI。

使い方例:
  python follow_note_today.py --limit 10 --open-intents

前提:
- playwright をインストール済み
- 必要に応じて `playwright install chromium`
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

NOTE_HOME = "https://note.com/"
X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}


@dataclass
class AuthorXAccount:
    article_title: str
    article_url: str
    author_name: str
    author_url: str
    x_url: str


async def maybe_load_cookies(context: BrowserContext, cookies_file: Path | None) -> None:
    if not cookies_file:
        return
    cookies = json.loads(cookies_file.read_text(encoding="utf-8"))
    if not isinstance(cookies, list):
        raise ValueError("cookies ファイルは Playwright 形式の配列 JSON にしてください")
    await context.add_cookies(cookies)


async def goto_and_wait(page: Page, url: str) -> None:
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(1200)


async def collect_today_article_links(page: Page, limit: int) -> list[tuple[str, str]]:
    await goto_and_wait(page, NOTE_HOME)

    section = page.locator("section", has_text="今日のあなたに").first
    count = await section.count()
    if count == 0:
        raise RuntimeError(
            "「今日のあなたに」セクションが見つかりません。"
            "note ログインや Cookie の読み込みが必要な可能性があります。"
        )

    cards = section.locator("a[href*='note.com']")
    found = await cards.count()

    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for i in range(found):
        href = await cards.nth(i).get_attribute("href")
        if not href:
            continue
        href = href.split("?")[0]
        if "/n/" not in href:
            continue
        if href in seen:
            continue
        seen.add(href)
        title = (await cards.nth(i).inner_text()).strip() or "(タイトル不明)"
        links.append((title, href))
        if len(links) >= limit:
            break
    return links


def normalize_x_url(raw_url: str) -> str | None:
    try:
        parsed = urlparse(raw_url)
    except ValueError:
        return None
    if parsed.netloc.lower() not in X_HOSTS:
        return None

    # /intent/... や /share はフォロー対象ではないので除外
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return None
    if parts[0] in {"intent", "share", "home", "i", "search"}:
        return None

    handle = parts[0].lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
        return None
    return f"https://x.com/{handle}"


async def collect_author_x_from_article(page: Page, title: str, article_url: str) -> list[AuthorXAccount]:
    await goto_and_wait(page, article_url)

    # note 側の揺れを吸収するため、author らしき候補を複数パターンで探索
    candidate_selectors = [
        "a[rel='author']",
        "a[href*='note.com'][href*='@']",
        "header a[href*='note.com']",
    ]

    author_url = ""
    author_name = ""
    for selector in candidate_selectors:
        loc = page.locator(selector).first
        if await loc.count() == 0:
            continue
        href = await loc.get_attribute("href")
        if href and "note.com" in href and "/n/" not in href:
            author_url = href
            author_name = (await loc.inner_text()).strip() or "(作者名不明)"
            break

    if not author_url:
        return []

    await goto_and_wait(page, author_url)

    anchors = page.locator("a[href]")
    count = await anchors.count()

    results: list[AuthorXAccount] = []
    seen_x: set[str] = set()
    for i in range(count):
        href = await anchors.nth(i).get_attribute("href")
        if not href:
            continue
        x_url = normalize_x_url(href)
        if not x_url or x_url in seen_x:
            continue
        seen_x.add(x_url)
        results.append(
            AuthorXAccount(
                article_title=title,
                article_url=article_url,
                author_name=author_name,
                author_url=author_url,
                x_url=x_url,
            )
        )
    return results


def to_follow_intent(x_url: str) -> str:
    handle = x_url.rstrip("/").split("/")[-1]
    return f"https://x.com/intent/follow?screen_name={handle}"


def print_result(accounts: Iterable[AuthorXAccount]) -> None:
    rows = list(accounts)
    if not rows:
        print("X アカウントは見つかりませんでした。")
        return

    print(f"\n見つかった X アカウント: {len(rows)} 件\n")
    for i, row in enumerate(rows, start=1):
        print(f"[{i}] {row.author_name} -> {row.x_url}")
        print(f"    記事: {row.article_title} ({row.article_url})")
        print(f"    作者ページ: {row.author_url}")
        print(f"    Follow Intent: {to_follow_intent(row.x_url)}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="収集する記事数の上限")
    parser.add_argument("--cookies", type=Path, help="note ログイン用 cookies.json")
    parser.add_argument(
        "--open-intents",
        action="store_true",
        help="見つかったアカウントのフォロー Intent ページを新規タブで開く",
    )
    parser.add_argument("--headful", action="store_true", help="ブラウザを可視モードで起動")
    args = parser.parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not args.headful)
        context = await browser.new_context()
        await maybe_load_cookies(context, args.cookies)
        page = await context.new_page()

        article_links = await collect_today_article_links(page, limit=args.limit)

        all_accounts: list[AuthorXAccount] = []
        seen: set[str] = set()
        for title, article_url in article_links:
            accounts = await collect_author_x_from_article(page, title, article_url)
            for account in accounts:
                if account.x_url in seen:
                    continue
                seen.add(account.x_url)
                all_accounts.append(account)

        print_result(all_accounts)

        if args.open_intents:
            for account in all_accounts:
                await page.goto(to_follow_intent(account.x_url), wait_until="domcontentloaded")
                await page.wait_for_timeout(600)

        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
