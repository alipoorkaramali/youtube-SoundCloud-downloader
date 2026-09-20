#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore scraper + patch for only-new, auto-limit, unlimited size, skip text-only posts."""
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

    # --- Patch 3: JS extract detects has_media ---
    old_js = (
        "                    const textEl = el.querySelector('.text, .message-text, [data-text]');\n"
        "                    const text = textEl ? textEl.innerText.trim() : '';\n"
        "                    const dateEl = el.querySelector('.date, .time, [data-date]');\n"
        "                    const date = dateEl ? dateEl.innerText.trim() : '';\n"
        "                    posts.push({ id: msgId, text: text, date: date });"
    )
    new_js = (
        "                    const textEl = el.querySelector('.text, .message-text, [data-text]');\n"
        "                    const text = textEl ? textEl.innerText.trim() : '';\n"
        "                    const dateEl = el.querySelector('.date, .time, [data-date]');\n"
        "                    const date = dateEl ? dateEl.innerText.trim() : '';\n"
        "                    const mediaSel = 'div.media-photo, div.media-video, div.media-inner, video, audio, '\n"
        "                        + 'div.audio-message, div[class*=\"Voice\"], div[class*=\"voice\"], '\n"
        "                        + 'div.document, div[class*=\"Document\"], div[class*=\"document\"], '\n"
        "                        + 'div[class*=\"media-photo\"], div[class*=\"media-video\"], '\n"
        "                        + 'img.thumbnail, a[download], div.File, div[class*=\"FileName\"]';\n"
        "                    const has_media = !!el.querySelector(mediaSel);\n"
        "                    posts.push({ id: msgId, text: text, date: date, has_media: has_media });"
    )
    if old_js not in text:
        raise SystemExit("patch: JS extract block not found")
    text = text.replace(old_js, new_js, 1)

    # --- Patch 4: skip text-only when collecting ---
    old_append = (
        "                    # ─── اگر msg دیکشنری است، قبلاً text و date را داریم ──\n"
        "                    # ولی اگر المان است، قبلاً استخراج شده، پس نیازی به کار اضافی نیست\n"
        "\n"
        "                    items.append({\n"
        "                        'id': msg_id,\n"
        "                        'text': text,\n"
        "                        'date': date,\n"
        "                        'url': f\"https://t.me/{self.channel}/{msg_id}\"\n"
        "                    })\n"
        "                    seen_ids.add(msg_id)\n"
        "                    new_posts_added += 1  # ★★★ افزایش شمارنده"
    )
    new_append = (
        "                    # ─── رد پست بدون مدیای قابل‌دانلود (متن/لینک خالی) ──\n"
        "                    has_media = True\n"
        "                    if isinstance(msg, dict):\n"
        "                        has_media = bool(msg.get('has_media', True))\n"
        "                    else:\n"
        "                        try:\n"
        "                            media_loc = msg.locator(\n"
        "                                'div.media-photo, div.media-video, div.media-inner, video, audio, '\n"
        "                                'div.audio-message, div[class*=\"Voice\"], div[class*=\"voice\"], '\n"
        "                                'div.document, div[class*=\"Document\"], div[class*=\"document\"], '\n"
        "                                'div[class*=\"media-photo\"], div[class*=\"media-video\"], '\n"
        "                                'img.thumbnail, a[download], div.File, div[class*=\"FileName\"]'\n"
        "                            )\n"
        "                            has_media = (await media_loc.count()) > 0\n"
        "                        except Exception:\n"
        "                            has_media = True  # در صورت خطا، اجازه دانلود بده\n"
        "                    if not has_media:\n"
        "                        self.logger.info(f\"⏭️ رد پست {msg_id}: بدون مدیای قابل‌دانلود (فقط متن/لینک)\")\n"
        "                        continue\n"
        "\n"
        "                    items.append({\n"
        "                        'id': msg_id,\n"
        "                        'text': text,\n"
        "                        'date': date,\n"
        "                        'url': f\"https://t.me/{self.channel}/{msg_id}\"\n"
        "                    })\n"
        "                    seen_ids.add(msg_id)\n"
        "                    new_posts_added += 1  # ★★★ افزایش شمارنده"
    )
    if old_append not in text:
        raise SystemExit("patch: items.append block not found")
    text = text.replace(old_append, new_append, 1)

    return text


def patch_downloader(path: Path) -> None:
    """0 max_bytes = unlimited + early skip when no downloadable media."""
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

    # Early skip in _process_post after message found: no media -> return without failed
    old_ready = (
        "        # ─── ادامه فرایند دانلود (پست پیدا شده است) ──────────────────\n"
        "        logger.info(f\"   📍 پست {post_id} آماده شد.\")\n"
        "        await human_sleep(0.5, 0.2)\n"
        "\n"
        "        # ──────────────── هدف دقیق برای راست‌کلیک ────────────────\n"
    )
    new_ready = (
        "        # ─── ادامه فرایند دانلود (پست پیدا شده است) ──────────────────\n"
        "        logger.info(f\"   📍 پست {post_id} آماده شد.\")\n"
        "        await human_sleep(0.5, 0.2)\n"
        "\n"
        "        # ─── رد سریع: بدون مدیای قابل‌دانلود ──────────────────\n"
        "        try:\n"
        "            _media_check = message_locator.locator(\n"
        "                'div.media-photo, div.media-video, div.media-inner, video, audio, '\n"
        "                'div.audio-message, div[class*=\"Voice\"], div[class*=\"voice\"], '\n"
        "                'div.document, div[class*=\"Document\"], div[class*=\"document\"], '\n"
        "                'div[class*=\"media-photo\"], div[class*=\"media-video\"], '\n"
        "                'img.thumbnail, a[download], div.File, div[class*=\"FileName\"]'\n"
        "            )\n"
        "            if await _media_check.count() == 0:\n"
        "                logger.info(f\"   ⏭️ پست {post_id}: بدون مدیا — رد شد (وقت تلف نشد)\")\n"
        "                return\n"
        "        except Exception:\n"
        "            pass\n"
        "\n"
        "        # ──────────────── هدف دقیق برای راست‌کلیک ────────────────\n"
    )
    if old_ready in text:
        text = text.replace(old_ready, new_ready, 1)
        n += 1
        print("playwright_downloader: early no-media skip added")
    else:
        print("WARNING: downloader ready-block not found; only size patches applied")

    path.write_text(text, encoding="utf-8")
    print(f"playwright_downloader patched ({n} change(s))")


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
