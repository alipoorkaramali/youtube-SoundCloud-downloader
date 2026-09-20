#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore scraper + patch for only-new, auto-limit, unlimited size, skip text-only, anchor fallback."""
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
        "        self._did_full_channel_fallback = False\n"
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

    # --- Patch 5: if navigate to anchor fails → search channel from scratch ---
    old_nav = (
        "        if self.start_link:\n"
        "            entered = await self._navigate_to_start_link(page, quick_check=quick_check)\n"
        "        else:\n"
        "            entered = await self._search_and_enter_channel(page)\n"
        "\n"
        "        if not entered:\n"
        "            await context.close()\n"
        "            return [], None, None\n"
    )
    new_nav = (
        "        if self.start_link:\n"
        "            entered = await self._navigate_to_start_link(page, quick_check=quick_check)\n"
        "            if not entered and not quick_check:\n"
        "                lost = self.target_msg_id or self.start_link\n"
        "                self.logger.warning(\n"
        "                    f\"⚠️ پست لنگر پیدا نشد ({lost}) → ورود عادی به کانال و اسکرپ از صفر\"\n"
        "                )\n"
        "                self._clear_anchor_and_only_new()\n"
        "                entered = await self._search_and_enter_channel(page)\n"
        "        else:\n"
        "            entered = await self._search_and_enter_channel(page)\n"
        "\n"
        "        if not entered:\n"
        "            await context.close()\n"
        "            return [], None, None\n"
    )
    if old_nav not in text:
        raise SystemExit("patch: navigate block not found")
    text = text.replace(old_nav, new_nav, 1)

    # --- Patch 6: if anchor never appears in DOM → full channel re-fetch ---
    old_return = (
        "        return items, context, page\n"
        "\n"
        "    # ═══════════════════ جستجو و ورود به کانال (روش معمولی) ═══════════════════\n"
        "    async def _search_and_enter_channel(self, page) -> bool:\n"
    )
    new_return = (
        "        # ─── لنگر در DOM نبود → مثل اسکرپ از صفر ───\n"
        "        if (\n"
        "            require_anchor\n"
        "            and not items\n"
        "            and not quick_check\n"
        "            and not getattr(self, '_did_full_channel_fallback', False)\n"
        "        ):\n"
        "            self.logger.warning(\n"
        "                f\"⚠️ پست لنگر {anchor_id} در پیام‌ها پیدا نشد → جستجوی کانال و اسکرپ از صفر\"\n"
        "            )\n"
        "            self._did_full_channel_fallback = True\n"
        "            self._clear_anchor_and_only_new()\n"
        "            try:\n"
        "                ok = await self._search_and_enter_channel(page)\n"
        "            except Exception as e:\n"
        "                self.logger.error(f\"❌ ورود مجدد به کانال ناموفق: {e}\")\n"
        "                ok = False\n"
        "            if ok:\n"
        "                return await self._fetch_posts_from_telegram(\n"
        "                    existing_seen_ids=existing_seen_ids,\n"
        "                    keep_browser_open=True,\n"
        "                    existing_context=context,\n"
        "                    existing_page=page,\n"
        "                    limit=limit,\n"
        "                    target_ids=target_ids,\n"
        "                    quick_check=False,\n"
        "                )\n"
        "\n"
        "        return items, context, page\n"
        "\n"
        "    def _clear_anchor_and_only_new(self):\n"
        "        \"\"\"Clear start_link / only_new so scraper behaves like a fresh channel scrape.\"\"\"\n"
        "        self.start_link = None\n"
        "        self.target_msg_id = None\n"
        "        self.skip_before_id = ''\n"
        "        self.only_new_posts = False\n"
        "        if hasattr(self, '_fallback_ids'):\n"
        "            self._fallback_ids = []\n"
        "\n"
        "    # ═══════════════════ جستجو و ورود به کانال (روش معمولی) ═══════════════════\n"
        "    async def _search_and_enter_channel(self, page) -> bool:\n"
    )
    if old_return not in text:
        raise SystemExit("patch: return/search block not found")
    text = text.replace(old_return, new_return, 1)

    # --- Patch 7: track require_anchor at start of collection ---
    old_sc = (
        "        # ─── متغیر start_collecting ─────────────────────────────────────\n"
        "        start_collecting = not bool(self.start_link)  # اگر start_link نداشته باشیم، از اول شروع می‌کنیم\n"
    )
    new_sc = (
        "        # ─── متغیر start_collecting ─────────────────────────────────────\n"
        "        require_anchor = bool(self.start_link)\n"
        "        anchor_id = self.target_msg_id\n"
        "        start_collecting = not require_anchor  # اگر start_link نداشته باشیم، از اول شروع می‌کنیم\n"
    )
    if old_sc not in text:
        raise SystemExit("patch: start_collecting block not found")
    text = text.replace(old_sc, new_sc, 1)

    # --- Patch 8: outer loop — after fallback IDs exhausted → full channel once ---
    old_fb = (
        "            if not newly_added:\n"
        "                # ─── اگر fallback_ids داریم و هنوز fallback باقی مانده ───\n"
        "                if hasattr(self, '_fallback_ids') and self._fallback_ids:\n"
        "                    self._fallback_index += 1\n"
        "                    if self._fallback_index < len(self._fallback_ids):\n"
        "                        next_fallback = self._fallback_ids[self._fallback_index]\n"
        "                        self.start_link = f\"https://t.me/{self.channel}/{next_fallback}\"\n"
        "                        self.target_msg_id = next_fallback\n"
        "                        self.logger.info(f\"🔄 تلاش با fallback بعدی: {next_fallback}\")\n"
        "                        continue\n"
        "                    else:\n"
        "                        self.logger.info(\"✅ تمام گزینه‌های fallback بررسی شدند.\")\n"
        "                \n"
        "                self.logger.info(\"✅ به نظر می‌رسد تمام پست‌های در دسترس جمع‌آوری شدند.\")\n"
        "                if self.debug_mode:\n"
        "                    await self._save_screenshot(page, \"end_of_channel\")\n"
        "                break\n"
    )
    new_fb = (
        "            if not newly_added:\n"
        "                # ─── اگر fallback_ids داریم و هنوز fallback باقی مانده ───\n"
        "                if hasattr(self, '_fallback_ids') and self._fallback_ids:\n"
        "                    self._fallback_index += 1\n"
        "                    if self._fallback_index < len(self._fallback_ids):\n"
        "                        next_fallback = self._fallback_ids[self._fallback_index]\n"
        "                        self.start_link = f\"https://t.me/{self.channel}/{next_fallback}\"\n"
        "                        self.target_msg_id = next_fallback\n"
        "                        self.logger.info(f\"🔄 تلاش با fallback بعدی: {next_fallback}\")\n"
        "                        continue\n"
        "                    else:\n"
        "                        self.logger.info(\"✅ تمام گزینه‌های fallback بررسی شدند.\")\n"
        "\n"
        "                # ─── آخرین راه: اسکرپ کامل کانال از صفر (یک‌بار) ───\n"
        "                if not getattr(self, '_did_full_channel_fallback', False) and len(items) == 0:\n"
        "                    self._did_full_channel_fallback = True\n"
        "                    self.logger.warning(\n"
        "                        \"⚠️ هیچ پستی با لنگر/fallback جمع نشد → جستجوی کانال و اسکرپ از صفر\"\n"
        "                    )\n"
        "                    self._clear_anchor_and_only_new()\n"
        "                    continue\n"
        "\n"
        "                self.logger.info(\"✅ به نظر می‌رسد تمام پست‌های در دسترس جمع‌آوری شدند.\")\n"
        "                if self.debug_mode:\n"
        "                    await self._save_screenshot(page, \"end_of_channel\")\n"
        "                break\n"
    )
    if old_fb not in text:
        raise SystemExit("patch: outer fallback block not found")
    text = text.replace(old_fb, new_fb, 1)

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
