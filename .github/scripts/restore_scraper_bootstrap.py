#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore scraper + patch downloader for only-new, auto-limit, unlimited size."""
import urllib.request
from pathlib import Path

BASE_URL = (
    "https://raw.githubusercontent.com/alipoorkaramali/youtube-SoundCloud-downloader/"
    "c6f1fb1144ce028ec7e4b3f6dee51b55434a9a6b/.github/scripts/scraper.py"
)

def apply_scraper_patches(text: str) -> str:
    old_limit = (
        "        self.limit = config.limit\n"
        "        self.max_media_bytes = config.max_media_mb * 1024 * 1024"
    )
    new_limit = (
        "        self.limit = config.limit\n"
        "        self.only_new_posts = getattr(config, 'only_new_posts', False)\n"
        "        self.skip_before_id = str(getattr(config, 'skip_before_id', '') or '').strip()\n"
        "        self._auto_limit = False\n"
        "        if self.limit <= 0:\n"
        "            self._auto_limit = True\n"
        "            self.limit = int(getattr(config, 'auto_limit_max', 150) or 150)\n"
        "        # 0 MB = unlimited\n"
        "        _mm = int(getattr(config, 'max_media_mb', 0) or 0)\n"
        "        self.max_media_bytes = (_mm * 1024 * 1024) if _mm > 0 else 0\n"
    )
    if old_limit not in text:
        raise SystemExit("patch: limit block not found")
    text = text.replace(old_limit, new_limit, 1)

    old_filter2 = (
        "            newly_added = []\n"
        "            for item in new_items:\n"
        "                if item['id'] not in {i['id'] for i in items}:\n"
        "                    items.append(item)\n"
        "                    newly_added.append(item)"
    )
    new_filter = (
        "            newly_added = []\n"
        "            skip_before = self._int_id(self.skip_before_id) if getattr(self, 'skip_before_id', '') else 0\n"
        "            for item in new_items:\n"
        "                if item['id'] in {i['id'] for i in items}:\n"
        "                    continue\n"
        "                if skip_before and self._int_id(item['id']) <= skip_before:\n"
        "                    self.logger.debug(f\"skip post {item['id']} (<= {self.skip_before_id})\")\n"
        "                    continue\n"
        "                items.append(item)\n"
        "                newly_added.append(item)"
    )
    if old_filter2 not in text:
        raise SystemExit("patch: filter block not found")
    text = text.replace(old_filter2, new_filter, 1)
    return text

def patch_downloader(path: Path) -> None:
    """0 max_bytes = unlimited (do not reject large files)."""
    if not path.exists():
        print("playwright_downloader.py missing, skip")
        return
    text = path.read_text(encoding="utf-8")
    a = "if size_mb > self.max_bytes / (1024 * 1024):"
    b = "if self.max_bytes > 0 and size_mb > self.max_bytes / (1024 * 1024):"
    c = "if len(body) > self.max_bytes:"
    d = "if self.max_bytes > 0 and len(body) > self.max_bytes:"
    n = 0
    if a in text:
        text = text.replace(a, b)
        n += 1
    if c in text:
        text = text.replace(c, d)
        n += 1
    path.write_text(text, encoding="utf-8")
    print(f"playwright_downloader patched ({n} size-check(s) -> unlimited when max_bytes=0)")

def main():
    here = Path(__file__).resolve().parent
    target = here / "scraper.py"
    print("downloading base scraper...")
    with urllib.request.urlopen(BASE_URL, timeout=60) as r:
        base = r.read().decode("utf-8")
    patched = apply_scraper_patches(base)
    target.write_text(patched, encoding="utf-8")
    print(f"scraper.py written ({len(patched)} bytes)")
    patch_downloader(here / "playwright_downloader.py")

if __name__ == "__main__":
    main()
