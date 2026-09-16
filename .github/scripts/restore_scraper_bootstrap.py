#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore scraper.py with only-new + auto-limit support."""
import urllib.request
from pathlib import Path

BASE_URL = (
    "https://raw.githubusercontent.com/alipoorkaramali/youtube-SoundCloud-downloader/"
    "c6f1fb1144ce028ec7e4b3f6dee51b55434a9a6b/.github/scripts/scraper.py"
)

def apply_patches(text: str) -> str:
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
        "        self.max_media_bytes = config.max_media_mb * 1024 * 1024"
    )
    if old_limit not in text:
        raise SystemExit("patch: limit block not found")
    text = text.replace(old_limit, new_limit, 1)

    old_log = (
        "        self.logger.info(\n"
        "            f\"\U0001f4f8 \u0630\u062e\u06cc\u0631\u0647 \u0627\u0633\u06a9\u0631\u06cc\u0646\u200c\u0634\u0627\u062a: {'\u0641\u0639\u0627\u0644' if self.save_screenshots else '\u063a\u06cc\u0631\u0641\u0639\u0627\u0644'}\"\n"
        "        )"
    )
    # Use simpler marker-based patch for log section
    marker = "\U0001f4f8 \u0630\u062e\u06cc\u0631\u0647 \u0627\u0633\u06a9\u0631\u06cc\u0646\u200c\u0634\u0627\u062a"
    if marker not in text:
        raise SystemExit("patch: screenshot log marker not found")
    # Insert after the screenshot log line block - find the closing of that logger.info
    needle = "f\"\U0001f4f8 \u0630\u062e\u06cc\u0631\u0647 \u0627\u0633\u06a9\u0631\u06cc\u0646\u200c\u0634\u0627\u062a: {'\u0641\u0639\u0627\u0644' if self.save_screenshots else '\u063a\u06cc\u0631\u0641\u0639\u0627\u0644'}\""
    # Fallback: insert after scroll direction validation block end
    insert_after = "            self.scroll_direction = 'up'\n"
    extra = (
        "\n        if getattr(self, '_auto_limit', False):\n"
        "            self.logger.info(f\"\U0001f916 limit auto max={self.limit}\")\n"
        "        if getattr(self, 'only_new_posts', False) or getattr(self, 'skip_before_id', ''):\n"
        "            self.logger.info(f\"only-new after {getattr(self, 'skip_before_id', '')}\")\n"
    )
    # Prefer filter patch which is ASCII-heavy
    old_filter = (
        "            # \u0641\u06cc\u0644\u062a\u0631 \u06a9\u0631\u062f\u0646 \u067e\u0633\u062a\u200c\u0647\u0627\u06cc \u062c\u062f\u06cc\u062f (\u062d\u0630\u0641 \u062a\u06a9\u0631\u0627\u0631\u06cc\u200c\u0647\u0627)\n"
        "            newly_added = []\n"
        "            for item in new_items:\n"
        "                if item['id'] not in {i['id'] for i in items}:\n"
        "                    items.append(item)\n"
        "                    newly_added.append(item)"
    )
    new_filter = (
        "            # filter new posts + skip already downloaded\n"
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
    if old_filter not in text:
        # try without persian comment
        old_filter2 = (
            "            newly_added = []\n"
            "            for item in new_items:\n"
            "                if item['id'] not in {i['id'] for i in items}:\n"
            "                    items.append(item)\n"
            "                    newly_added.append(item)"
        )
        if old_filter2 not in text:
            raise SystemExit("patch: filter block not found")
        text = text.replace(old_filter2, new_filter, 1)
    else:
        text = text.replace(old_filter, new_filter, 1)
    return text

def main():
    target = Path(__file__).resolve().parent / "scraper.py"
    print("downloading base scraper...")
    with urllib.request.urlopen(BASE_URL, timeout=60) as r:
        base = r.read().decode("utf-8")
    patched = apply_patches(base)
    target.write_text(patched, encoding="utf-8")
    print(f"scraper.py written ({len(patched)} bytes) only-new+auto-limit")

if __name__ == "__main__":
    main()
