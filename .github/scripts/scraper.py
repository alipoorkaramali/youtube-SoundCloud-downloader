#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import random
import re
from pathlib import Path
from typing import List, Dict

from config_loader import Config
from playwright_downloader import PlaywrightDownloader
from output_generator import OutputGenerator

# ═══════════════════ Constants ═══════════════════
MAX_SCROLL_ATTEMPTS = 8
SCROLL_STEP_BASE = 1200  # مقدار پایه اسکرول (بدون جهت)
HOME_URL = "https://web.telegram.org/a/"
OVERALL_TIMEOUT = 35 * 60  # fallback

# ═══════════════════ Human-like sleep ═══════════════════
async def human_sleep(base: float, jitter: float = 0.4):
    time = base * (1 + random.uniform(-jitter, jitter))
    await asyncio.sleep(max(0.1, time))


class TelegramChannelScraper:

    def __init__(self, config: Config):
        self.config = config
        self.channel = config.channel.lstrip('@')
        self.channel_name = getattr(config, 'channel_name', '') or ''
        self.start_link = getattr(config, 'start_link', None)
        self.target_msg_id = None
        self.limit = config.limit
        self.max_media_bytes = config.max_media_mb * 1024 * 1024
        self.base_dir = Path(config.output_dir) / "telegram_downloads" / self.channel
        self.media_dir = self.base_dir / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.profile_dir = Path(config.profile_dir)
        self.delay_between_posts = config.delay_between_posts

        self.screenshots_dir = self.base_dir / "post_screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        self.debug_screenshots_dir = self.base_dir / "debug_screenshots"
        self.debug_mode = getattr(config, 'debug_mode', False)

        # ─── پارامتر جدید: جهت اسکرول ───
        self.scroll_direction = getattr(config, 'scroll_direction', 'up').lower()
        if self.scroll_direction not in ['up', 'down']:
            self.logger.warning(f"⚠️ مقدار نامعتبر برای scroll_direction: {self.scroll_direction}. استفاده از 'up'.")
            self.scroll_direction = 'up'

        self.logger = logging.getLogger("TelegramScraper")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        fh = logging.FileHandler(self.base_dir / "scraper.log", encoding='utf-8')
        fh.setFormatter(formatter)
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(fh)
            self.logger.addHandler(ch)

        self.logger.info(f"📁 دایرکتوری خروجی: {self.base_dir}")
        self.logger.info(f"🐞 حالت دیباگ: {'فعال' if self.debug_mode else 'غیرفعال'}")
        self.logger.info(f"🧭 جهت اسکرول: {'بالا (قدیمی‌تر)' if self.scroll_direction == 'up' else 'پایین (جدیدتر)'}")

    # ═══════════════════ متد کمکی: پاک‌سازی نام فایل ═══════════════════
    @staticmethod
    def _sanitize_filename(name: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

    # ═══════════════════ متد واحد برای اسکرین‌شات ═══════════════════
    async def _screenshot(self, page, name: str, full_page: bool = True, element=None):
        try:
            if element is not None:
                if hasattr(element, 'element_handle'):
                    element = await element.element_handle()
                if element:
                    safe_name = self._sanitize_filename(name)
                    path = self.debug_screenshots_dir / f"debug_{self.channel}_{safe_name}.png"
                    await element.screenshot(path=path)
                    self.logger.debug(f"📸 اسکرین‌شات المنت ذخیره شد: {path.name}")
            else:
                safe_name = self._sanitize_filename(name)
                if full_page:
                    path = self.screenshots_dir / f"{safe_name}.png"
                else:
                    path = self.debug_screenshots_dir / f"debug_{self.channel}_{safe_name}.png"
                await page.screenshot(path=path, full_page=full_page)
                self.logger.debug(f"📸 اسکرین‌شات صفحه ذخیره شد: {path.name}")
        except Exception as e:
            self.logger.warning(f"⚠️ خطا در ذخیره اسکرین‌شات {name}: {e}")

    async def _save_screenshot(self, page, name: str):
        await self._screenshot(page, name, full_page=True)

    async def _take_screenshot(self, page, name: str):
        self.debug_screenshots_dir.mkdir(parents=True, exist_ok=True)
        await self._screenshot(page, name, full_page=True)

    # ═══════════════════ رسم صلیب روی المنت ═══════════════════
    async def _draw_debug_cross(self, page, element_handle):
        try:
            if not element_handle:
                return
            await element_handle.scroll_into_view_if_needed()
            await page.evaluate('''(el) => {
                const rect = el.getBoundingClientRect();
                const cross = document.createElement('div');
                cross.style.position = 'fixed';
                cross.style.left = (rect.left + rect.width/2 - 15) + 'px';
                cross.style.top = (rect.top + rect.height/2 - 15) + 'px';
                cross.style.width = '30px';
                cross.style.height = '30px';
                cross.style.pointerEvents = 'none';
                cross.style.zIndex = '99999';
                cross.style.border = '3px solid red';
                cross.style.background = 'rgba(255,0,0,0.2)';
                cross.innerHTML = '✕';
                cross.style.fontSize = '24px';
                cross.style.color = 'red';
                cross.style.textAlign = 'center';
                cross.style.lineHeight = '30px';
                document.body.appendChild(cross);
                setTimeout(() => cross.remove(), 3000);
            }''', element_handle)
        except Exception as e:
            self.logger.debug(f"خطا در رسم صلیب: {e}")

    # ═══════════════════ اسکرول هوشمند با افزایش تدریجی ═══════════════════
    async def _smart_scroll(self, page, direction: str, step: int = SCROLL_STEP_BASE, max_attempts: int = 3) -> bool:
        """
        اسکرول هوشمند با سه پله افزایشی.
        - direction: 'up' یا 'down'
        - step: مقدار پایه (مثبت)
        - max_attempts: تعداد پله‌ها
        برمی‌گرداند: True اگر ارتفاع تغییر کرد، False اگر نه
        """
        old_height = await page.evaluate("document.documentElement.scrollHeight")
        scroll_multipliers = [1, 1.8, 2.8]  # پله‌های افزایشی

        for i in range(min(max_attempts, len(scroll_multipliers))):
            multiplier = scroll_multipliers[i]
            amount = int(step * multiplier)
            if direction == 'up':
                amount = -amount  # منفی = بالا
            # برای down، amount مثبت می‌ماند

            self.logger.debug(f"   اسکرول {amount}px (پله {i+1})")
            await page.evaluate(f"window.scrollBy(0, {amount})")
            await human_sleep(1.2, 0.3)

            new_height = await page.evaluate("document.documentElement.scrollHeight")
            if new_height != old_height:
                self.logger.info(f"✅ ارتفاع صفحه تغییر کرد: {old_height} → {new_height}")
                return True

        self.logger.info(f"⚠️ ارتفاع صفحه پس از {max_attempts} اسکرول تغییر نکرد.")
        return False

    # ═══════════════════ استخراج پست‌ها با JavaScript ═══════════════════
    async def _extract_posts_from_page(self, page) -> List[Dict]:
        """استخراج پست‌ها از صفحه با JavaScript (همراه با متن کامل)."""
        return await page.evaluate("""
            () => {
                const posts = [];
                document.querySelectorAll('[data-message-id]').forEach(el => {
                    const msgId = el.getAttribute('data-message-id');
                    if (!msgId) return;
                    const textEl = el.querySelector('.text, .message-text, [data-text]');
                    const text = textEl ? textEl.innerText.trim() : '';
                    const dateEl = el.querySelector('.date, .time, [data-date]');
                    const date = dateEl ? dateEl.innerText.trim() : '';
                    posts.push({ id: msgId, text: text, date: date });
                });
                return posts;
            }
        """)

    # ═══════════════════ متد اصلی با Timeout ═══════════════════
    async def run(self):
        timeout = getattr(self.config, 'timeout_seconds', OVERALL_TIMEOUT)
        try:
            await asyncio.wait_for(self._run_impl(), timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.error(f"⏰ اسکریپت به دلیل محدودیت زمانی {timeout} ثانیه متوقف شد.")
        except Exception as e:
            self.logger.critical(f"❌ خطای مرگبار در اجرای اصلی: {e}", exc_info=True)

    async def _run_impl(self):
        if self.start_link:
            self.logger.info(f"🚀 شروع اسکریپر با لینک: {self.start_link} (limit={self.limit})")
        else:
            self.logger.info(f"🚀 شروع اسکریپر مستقل برای @{self.channel} (limit={self.limit})")

        items, context, page = await self._fetch_posts_from_telegram()
        if not items:
            self.logger.warning("هیچ پستی دریافت نشد.")
            if context:
                await context.close()
            return
        self.logger.info(f"📥 {len(items)} پست استخراج شد.")

        media_map, downloaded = await self._download_media(items, page, context)
        self.logger.info(f"🖼️ {downloaded} فایل رسانه دانلود شد.")
        self.logger.info(f"📊 media_map برای {len(media_map)} پست پر شد.")

        gen = OutputGenerator(
            self.base_dir,
            self.channel,
            items,
            media_map,
            debug_mode=self.debug_mode
        )
        gen.run_all()

        if context:
            await context.close()

        self.logger.info("✅ پایان موفقیت‌آمیز.")

    # ═══════════════════ استخراج پست‌ها با پشتیبانی از جهت اسکرول ═══════════════════
    async def _fetch_posts_from_telegram(self) -> tuple[List[Dict], any, any]:
        from playwright.async_api import async_playwright

        p = await async_playwright().start()
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1366, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            self.logger.error(f"❌ صفحه اصلی باز نشد: {e}")
            await context.close()
            return [], None, None

        if self.start_link:
            entered = await self._navigate_to_start_link(page)
        else:
            entered = await self._search_and_enter_channel(page)

        if not entered:
            await context.close()
            return [], None, None
        await self._save_screenshot(page, "initial")

        # ═══════════════ پرش به ابتدا یا انتهای صفحه بر اساس جهت اسکرول ═══════════════
        if not self.start_link:
            if self.scroll_direction == 'up':
                self.logger.info("⬇️ تلاش برای پرش به جدیدترین پست‌ها...")
                clicked = False
                scroll_button_selectors = [
                    'button[title="Go to bottom"]',
                    'div[class*="scroll-to-bottom"]',
                    'div[class*="ScrollButton"]',
                    '[aria-label="Scroll to bottom"]',
                    'button:has(svg[class*="arrow-down"])',
                ]
                for sel in scroll_button_selectors:
                    try:
                        btn = page.locator(sel).first
                        if await btn.count() > 0:
                            await btn.click(timeout=5000)
                            self.logger.info("   ✅ روی دکمه فلش کلیک شد. منتظر بارگذاری جدیدترین پست‌ها...")
                            clicked = True
                            await human_sleep(3.5, 0.4)
                            break
                    except Exception:
                        continue
                if not clicked:
                    self.logger.info("   ℹ️ دکمه پرش به پایین پیدا نشد. ادامه با وضعیت فعلی.")
            else:  # scroll_direction == 'down'
                self.logger.info("⬆️ تلاش برای رفتن به بالای صفحه (قدیمی‌ترین پست‌ها)...")
                await page.evaluate("window.scrollTo(0, 0)")
                await human_sleep(2, 0.3)
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, -2000)")
                    await human_sleep(1, 0.2)
                self.logger.info("   ✅ به بالای صفحه رفتیم.")
        else:
            self.logger.info("ℹ️ در حالت start_link، پرش به پایین/بالا انجام نمی‌شود.")

        # ─── جمع‌آوری پست‌ها ────────────────────────────────────────────────
        items = []
        seen_ids = set()
        scroll_attempts = 0

        start_collecting = False
        if self.start_link and self.target_msg_id:
            self.logger.info(f"🎯 پیدا کردن پیام هدف {self.target_msg_id}...")
            try:
                target_locator = page.locator(f'[data-message-id="{self.target_msg_id}"]').first
                if await target_locator.count() > 0:
                    await target_locator.scroll_into_view_if_needed()
                    offset = -150 if self.scroll_direction == 'up' else 150
                    await page.evaluate(f"window.scrollBy(0, {offset})")
                    await human_sleep(1, 0.3)
                    self.logger.info("✅ پیام هدف به مرکز صفحه منتقل شد.")
                else:
                    self.logger.warning(f"⚠️ پیام هدف {self.target_msg_id} پیدا نشد.")
            except Exception as e:
                self.logger.warning(f"⚠️ خطا در انتقال پیام هدف: {e}")

        while len(items) < self.limit and scroll_attempts < MAX_SCROLL_ATTEMPTS:
            try:
                messages = await page.locator('div[data-message-id]').all()

                # ─── تعیین ترتیب پیمایش بر اساس جهت ──────────────────────
                if self.start_link:
                    # در حالت start_link، از نقطه شروع به سمت direction حرکت می‌کنیم
                    if self.scroll_direction == 'up':
                        msg_iter = reversed(messages)
                    else:
                        msg_iter = messages
                else:
                    # حالت عادی: اگر direction == 'up' از جدید به قدیم، اگر 'down' از قدیم به جدید
                    if self.scroll_direction == 'up':
                        msg_iter = reversed(messages)
                    else:
                        msg_iter = messages

                for msg in msg_iter:
                    try:
                        msg_id = await msg.get_attribute('data-message-id')
                        if not msg_id or msg_id in seen_ids:
                            continue

                        if self.start_link and not start_collecting:
                            if msg_id == self.target_msg_id:
                                start_collecting = True
                                self.logger.info(f"🎯 به پیام هدف رسیدیم (ID: {msg_id})، شروع جمع‌آوری...")
                                seen_ids.add(msg_id)
                            else:
                                continue

                        if not start_collecting:
                            continue

                        # ─── استخراج هوشمند متن پست ──────────────────────
                        text = ""
                        try:
                            # روش‌های مختلف استخراج متن
                            content_selectors = [
                                'div.message-content',
                                'div.text-content',
                                'div[class*="message-text"]',
                                'div[class*="text"]',
                                'div[class*="body"]'
                            ]
                            for sel in content_selectors:
                                content = msg.locator(sel).first
                                if await content.count() > 0:
                                    text = (await content.inner_text()).strip()[:1000]
                                    if text and len(text) > 3:
                                        break

                            if not text or len(text) < 5:
                                try:
                                    text = (await msg.inner_text()).strip()[:1000]
                                except Exception:
                                    pass

                            if not text or len(text) < 5:
                                try:
                                    text = (await msg.evaluate("el => el.textContent || ''")).strip()[:1000]
                                except Exception:
                                    pass

                            if not text or len(text) < 5:
                                try:
                                    text = (await page.evaluate(f"""
                                        () => {{
                                            const el = document.querySelector('[data-message-id="{msg_id}"]');
                                            return el ? el.innerText || el.textContent || '' : '';
                                        }}
                                    """)).strip()[:1000]
                                except Exception:
                                    pass

                            if text:
                                text = re.sub(r'\s+', ' ', text).strip()[:1000]

                            if not text or len(text) < 2:
                                self.logger.debug(f"⚠️ متن پست {msg_id} خالی یا بسیار کوتاه است.")

                        except Exception as e:
                            self.logger.warning(f"❌ خطا در استخراج متن پست {msg_id}: {e}")
                            text = ""

                        # ─── تاریخ ──────────────────────────────────────────
                        date_el = msg.locator('time, .message-date, .date, span[class*="date"]').first
                        date = ""
                        try:
                            if await date_el.count() > 0:
                                date = await date_el.inner_text() or await date_el.get_attribute('datetime') or ""
                        except Exception:
                            pass

                        items.append({
                            'id': msg_id,
                            'text': text,
                            'date': date,
                            'url': f"https://t.me/{self.channel}/{msg_id}"
                        })
                        seen_ids.add(msg_id)

                        if len(items) >= self.limit:
                            break
                    except Exception as e:
                        self.logger.debug(f"خطا در پردازش پیام: {e}")
                        continue
            except Exception as e:
                self.logger.error(f"❌ خطا در استخراج پست‌ها: {e}")

            if len(items) >= self.limit:
                break

            # ─── اسکرول هوشمند با جهت ──────────────────────────────────
            old_height = await page.evaluate("document.documentElement.scrollHeight")
            scrolled = await self._smart_scroll(page, self.scroll_direction, step=SCROLL_STEP_BASE, max_attempts=3)
            new_height = await page.evaluate("document.documentElement.scrollHeight")

            if new_height == old_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0

            # ─── در حالت start_link، اگر هنوز به نقطه شروع نرسیده‌ایم ───
            if self.start_link and not start_collecting:
