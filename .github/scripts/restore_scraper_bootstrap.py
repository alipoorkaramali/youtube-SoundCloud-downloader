#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Restore scraper + patch for only-new, auto-limit, unlimited size, anchor fallback.
Media skip = natural: if Download menu item missing, post is not downloaded.
Last saved post is used as an anchor (must be found) but is never downloaded again.
"""
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
        "                    self.logger.info(f\"⏭️ رد پست {item['id']} (مرز ذخیره‌شده {self.skip_before_id} — پیدا شد، دانلود نمی‌شود)\")\n"
        "                    continue\n"
        "                items.append(item)\n"
        "                newly_added.append(item)"
    )
    if old_filter2 not in text:
        raise SystemExit("patch: filter block not found")
    text = text.replace(old_filter2, new_filter, 1)

    old_dl = (
        "            self.logger.info(f\"⬇️ شروع دانلود رسانه برای {len(newly_added)} پست جدید...\")\n"
    )
    new_dl = (
        "            skip_before = self._int_id(self.skip_before_id) if getattr(self, 'skip_before_id', '') else 0\n"
        "            if skip_before:\n"
        "                before_n = len(newly_added_sorted)\n"
        "                newly_added_sorted = [p for p in newly_added_sorted if self._int_id(p.get('id')) > skip_before]\n"
        "                skipped = before_n - len(newly_added_sorted)\n"
        "                if skipped:\n"
        "                    self.logger.info(\n"
        "                        f\"⏭️ {skipped} پست مرزی/قدیمی‌تر از {self.skip_before_id} از صف دانلود حذف شد\"\n"
        "                    )\n"
        "            if not newly_added_sorted:\n"
        "                self.logger.info(\"ℹ️ در این دور فقط پست ذخیره‌شده/قدیمی بود — دانلود تکراری انجام نشد\")\n"
        "            else:\n"
        "                self.logger.info(f\"⬇️ شروع دانلود رسانه برای {len(newly_added_sorted)} پست جدید...\")\n"
    )
    if old_dl not in text:
        raise SystemExit("patch: download-start log not found")
    text = text.replace(old_dl, new_dl, 1)

    # wrap the download call so empty list after skip does not download
    old_try = (
        "            try:\n"
        "                # دیگر نیازی به مرتب‌سازی مجدد نیست چون از قبل sorted است\n"
        "                batch_media_map, downloaded_batch, batch_failed = await self._download_media(\n"
        "                    newly_added_sorted,  # ← استفاده از لیست کامل‌شده\n"
        "                    page,\n"
        "                    context\n"
        "                )\n"
    )
    new_try = (
        "            try:\n"
        "                if not newly_added_sorted:\n"
        "                    batch_media_map, downloaded_batch, batch_failed = {}, 0, []\n"
        "                else:\n"
        "                    batch_media_map, downloaded_batch, batch_failed = await self._download_media(\n"
        "                        newly_added_sorted,\n"
        "                        page,\n"
        "                        context\n"
        "                    )\n"
    )
    if old_try not in text:
        raise SystemExit("patch: download try-block not found")
    text = text.replace(old_try, new_try, 1)

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
        "                    f\"⚠️ پست لنگر پیدا نشد ({lost}) → ورود عادی به کانال (مرز دانلود حفظ می‌شود)\"\n"
        "                )\n"
        "                self._clear_anchor_keep_skip()\n"
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

    old_return = (
        "        return items, context, page\n"
        "\n"
        "    # ═══════════════════ جستجو و ورود به کانال (روش معمولی) ═══════════════════\n"
        "    async def _search_and_enter_channel(self, page) -> bool:\n"
    )
    new_return = (
        "        if (\n"
        "            require_anchor\n"
        "            and not items\n"
        "            and not quick_check\n"
        "            and not getattr(self, '_did_full_channel_fallback', False)\n"
        "        ):\n"
        "            self.logger.warning(\n"
        "                f\"⚠️ پست لنگر {anchor_id} در پیام‌ها پیدا نشد → ورود دوباره (بدون دانلود تکراری)\"\n"
        "            )\n"
        "            self._did_full_channel_fallback = True\n"
        "            self._clear_anchor_keep_skip()\n"
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
        "    def _clear_anchor_keep_skip(self):\n"
        "        \"\"\"Drop start_link so we can re-enter the channel, but keep skip_before_id.\"\"\"\n"
        "        self.start_link = None\n"
        "        self.target_msg_id = None\n"
        "        if hasattr(self, '_fallback_ids'):\n"
        "            self._fallback_ids = []\n"
        "        # skip_before_id / only_new_posts must stay: find posts, do not re-download them\n"
        "        if self.skip_before_id:\n"
        "            self.only_new_posts = True\n"
        "\n"
        "    # ═══════════════════ جستجو و ورود به کانال (روش معمولی) ═══════════════════\n"
        "    async def _search_and_enter_channel(self, page) -> bool:\n"
    )
    if old_return not in text:
        raise SystemExit("patch: return/search block not found")
    text = text.replace(old_return, new_return, 1)

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
        "                if not getattr(self, '_did_full_channel_fallback', False) and len(items) == 0:\n"
        "                    self._did_full_channel_fallback = True\n"
        "                    self.logger.warning(\n"
        "                        \"⚠️ هیچ پست جدیدی بعد از مرز نبود → ورود دوباره به کانال (دانلود تکراری ممنوع)\"\n"
        "                    )\n"
        "                    self._clear_anchor_keep_skip()\n"
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
    """0 max_bytes = unlimited only (no early media-element skip)."""
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
