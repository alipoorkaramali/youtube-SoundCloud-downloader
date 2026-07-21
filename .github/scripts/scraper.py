#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging
import random
import re
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

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
def get_file_identifier(file_path: Path, use_hash: bool = True, max_hash_time: float = 3.0) -> dict:
    """
    تولید شناسه منحصربه‌فرد برای فایل بر اساس محتوا (هش) یا حجم+تاریخ
    - use_hash: اگر True باشه و فایل کوچک باشه، هش می‌گیره
    - max_hash_time: حداکثر زمان مجاز برای هش‌گیری (ثانیه)
    برمی‌گرداند: دیکشنری شامل شناسه و روش استفاده‌شده
    """
    stat = file_path.stat()
    size = stat.st_size
    mtime = stat.st_mtime

    # اگر فایل بزرگتر از ۵۰ مگابایت یا تعداد فایل‌ها زیاد باشه، use_hash رو false می‌کنیم (در کد اصلی مدیریت می‌شه)
    identifier = {
        'name': file_path.name,
        'size': size,
        'mtime': mtime,
        'method': 'size_mtime',  # پیش‌فرض
        'hash': None,
        'composite_id': f"{size}_{int(mtime)}"
    }

    if use_hash and size < 50 * 1024 * 1024:  # فقط برای فایل‌های زیر ۵۰ مگ
        try:
            start = time.time()
            md5 = hashlib.md5()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5.update(chunk)
                    if time.time() - start > max_hash_time:
                        raise TimeoutError("هش‌گیری زمان‌بر شد")
            identifier['hash'] = md5.hexdigest()
            identifier['method'] = 'hash'
            identifier['composite_id'] = md5.hexdigest()  # برای مقایسه
        except Exception:
            # فال‌بک به روش حجم+تاریخ
            identifier['method'] = 'size_mtime'
            identifier['hash'] = None
            identifier['composite_id'] = f"{size}_{int(mtime)}"

    return identifier
class TimeoutManager:
    def __init__(self, base_timeout: int):
        self.base_timeout = base_timeout
        self.extra_time = 0
        self.start_time = asyncio.get_event_loop().time()
        self.logger = logging.getLogger("TelegramScraper")
    
    def add_time(self, seconds: int):
        self.extra_time += seconds
        self.logger.info(f"⏱️ تایم‌اوت {seconds} ثانیه تمدید شد (مجموع اضافه: {self.extra_time})")
    
    def get_remaining(self) -> float:
        elapsed = asyncio.get_event_loop().time() - self.start_time
        total_timeout = self.base_timeout + self.extra_time
        remaining = total_timeout - elapsed
        return max(0, remaining)
        
class TelegramChannelScraper:
    def __init__(self, config: Config):
        # ═══════════════════════════════════════════════════════════════
        # مرحله ۱: ذخیره تنظیمات اولیه (نیازی به logger ندارند)
        # ═══════════════════════════════════════════════════════════════
        self.config = config
        self.channel = config.channel.lstrip('@')
        self.channel_name = getattr(config, 'channel_name', '') or ''
        self.start_link = getattr(config, 'start_link', None)
        self.target_msg_id = None
        self.limit = config.limit
        self.max_media_bytes = config.max_media_mb * 1024 * 1024
        
        # ─── مسیرهای خروجی ────────────────────────────────────────────
        self.base_dir = Path(config.output_dir) / "telegram_downloads" / self.channel
        self.media_dir = self.base_dir / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.profile_dir = Path(config.profile_dir)
        self.delay_between_posts = config.delay_between_posts

        # ─── پوشه‌های اسکرین‌شات ──────────────────────────────────────
        self.screenshots_dir = self.base_dir / "post_screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.debug_screenshots_dir = self.base_dir / "debug_screenshots"
        
        # ─── تنظیمات مربوط به حالت دیباگ و اسکرین‌شات ────────────────
        self.debug_mode = getattr(config, 'debug_mode', False)
        self.save_screenshots = getattr(config, 'save_screenshots', True)

        # ─── تنظیمات مربوط به اسکرول (قبل از logger) ────────────────
        self.scroll_direction = getattr(config, 'scroll_direction', 'up').lower()
        self._manual_scroll_done = False
        # ─── متغیرهای مدیریت زمان ────────────────────────────────────
        self.last_download_success = False
        self._reply_posts = []
        self._missing_posts = []
        self._missing_post_ids = []

        # ═══════════════════════════════════════════════════════════════
        # مرحله ۲: راه‌اندازی logger (بعد از متغیرهای اولیه)
        # ═══════════════════════════════════════════════════════════════
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

        # ═══════════════════════════════════════════════════════════════
        # مرحله ۳: اعتبارسنجی و لاگ‌گیری (بعد از تعریف logger)
        # ═══════════════════════════════════════════════════════════════
        
        # ─── لاگ‌های نهایی (اطلاعات اولیه) ───────────────────────────
        self.logger.info(f"📁 دایرکتوری خروجی: {self.base_dir}")
        self.logger.info(f"🐞 حالت دیباگ: {'فعال' if self.debug_mode else 'غیرفعال'}")
        self.logger.info(
            f"🧭 جهت اسکرول: {'بالا (قدیمی‌تر)' if self.scroll_direction == 'up' else 'پایین (جدیدتر)'}"
        )
        self.logger.info(
            f"📸 ذخیره اسکرین‌شات: {'فعال' if self.save_screenshots else 'غیرفعال'}"
        )
        # ─── اعتبارسنجی جهت اسکرول (بعد از تعریف logger) ───
        if self.scroll_direction not in ['up', 'down']:
            self.logger.warning(f"⚠️ مقدار نامعتبر برای scroll_direction: {self.scroll_direction}. استفاده از 'up'.")
            self.scroll_direction = 'up'

    def _load_resume_state(self) -> dict:
        """بارگذاری وضعیت ذخیره‌شده از فایل resume_state.json (اگر وجود داشته باشد)"""
        import json
        resume_file = self.base_dir / "resume_state.json"
        if not resume_file.exists():
            self.logger.info("ℹ️ هیچ وضعیت قبلی یافت نشد (فایل resume_state.json وجود ندارد).")
            return {}
        
        try:
            with open(resume_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            self.logger.info(f"✅ وضعیت قبلی بارگذاری شد: آخرین پست = {state.get('last_post_id', 'N/A')}, تعداد دانلودشده = {len(state.get('downloaded_posts', []))}")
            return state
        except Exception as e:
            self.logger.warning(f"⚠️ خطا در خواندن resume_state.json: {e}")
            return {}

    def _save_resume_state(self, last_post_id: str, all_items: List[Dict]):
        """ذخیره وضعیت فعلی (آخرین پست و لیست همه پست‌های دانلودشده)"""
        import json
        resume_file = self.base_dir / "resume_state.json"
        state = {}
        if resume_file.exists():
            try:
                with open(resume_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
            except:
                pass
        state['last_post_id'] = last_post_id
        state['downloaded_posts'] = [item['id'] for item in all_items]
        with open(resume_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        self.logger.info(f"📝 وضعیت ذخیره شد: آخرین پست {last_post_id}")
    # ═══════════════════════════════════════════════════════════════
    # نکته: دانلود رسانه‌ها حالا به صورت incremental (در هر batch) انجام می‌شود
    # این کار باعث می‌شود در صورت قطع شدن اسکریپت، رسانه‌های قبلی حفظ شوند.
    # ═══════════════════════════════════════════════════════════════
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
        if not self.save_screenshots:
            return
        await self._screenshot(page, name, full_page=True)

    async def _take_screenshot(self, page, name: str):
        if not self.save_screenshots:
            return
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

            # ─── اسکرول معکوس کوچک برای تحریک بارگذاری ──────────────
            if i == 0:
                self.logger.debug("   اسکرول معکوس ۳۰۰px برای تحریک بارگذاری...")
                await page.evaluate("window.scrollBy(0, -300)")
                await human_sleep(0.5, 0.2)

            new_height = await page.evaluate("document.documentElement.scrollHeight")
            if new_height != old_height:
                self.logger.info(f"✅ ارتفاع صفحه تغییر کرد: {old_height} → {new_height}")
                return True

        self.logger.info(f"⚠️ ارتفاع صفحه پس از {max_attempts} اسکرول تغییر نکرد.")
        # ─── تلاش آخر: اسکرول بزرگ‌تر برای تحریک لود بیشتر ───
        self.logger.debug("   اسکرول نهایی ۱۵۰۰px برای تحریک بارگذاری...")
        await page.evaluate("window.scrollBy(0, 1500)")
        await human_sleep(1.2, 0.4)
        return False
        # ═══════════════════ اسکرول نرم برای پیدا کردن پست در صفحه فعلی ═══════════════════
    async def _find_post_with_slow_scroll(self, page, seen_ids: set = None) -> Tuple[bool, str]:
        """
        اسکرول نرم در صفحه فعلی برای پیدا کردن اولین پست دارای تاریخ یا کپشن.
        برمی‌گرداند: (پیدا شد یا نه, شناسه پست)
        """
        direction_text = 'بالا' if self.scroll_direction == 'up' else 'پایین'
        scroll_amount = -600 if self.scroll_direction == 'up' else 600
        found_id = None
        max_slow_steps = 20

        for step in range(max_slow_steps):
            await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            await asyncio.sleep(0.4)
            messages = await page.locator('div[data-message-id]').all()
            for msg in messages:
                msg_id = await msg.get_attribute('data-message-id')
                if not msg_id:
                    continue
                if seen_ids and msg_id in seen_ids:
                    continue

                # بررسی تاریخ با JavaScript
                has_date = False
                try:
                    date_info = await msg.evaluate("""
                        (el) => {
                            const selectors = ['time', '.date', '[class*="date"]', '[datetime]', '.message-time', '[class*="time"]', '.time', '[data-date]', '[data-timestamp]'];
                            for (const sel of selectors) {
                                const found = el.querySelector(sel);
                                if (found) {
                                    const text = found.textContent?.trim() || found.getAttribute('datetime') || '';
                                    if (text) return { has: true, text: text };
                                }
                            }
                            const fullText = el.textContent || '';
                            const datePattern = /\\d{1,2}:\\d{2}|\\d{1,2}\\s+[A-Za-z]{3}|\\d{4}-\\d{2}-\\d{2}/;
                            const match = fullText.match(datePattern);
                            if (match) return { has: true, text: match[0] };
                            return { has: false, text: '' };
                        }
                    """)
                    has_date = date_info.get('has', False)
                except Exception:
                    has_date = False

                has_caption = False
                if not has_date:
                    try:
                        text_content = (await msg.inner_text()).strip()
                        has_caption = len(text_content) > 10
                    except:
                        pass

                if has_date or has_caption:
                    found_id = msg_id
                    self.logger.info(f"🔍 پست معتبر با اسکرول نرم پیدا شد: {msg_id} (تاریخ: {has_date}, کپشن: {has_caption})")
                    return True, found_id

        return False, None
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
    #=======================================================================================
    async def _extract_text_from_message(self, msg, msg_id: str) -> str:
        """استخراج هوشمند متن پیام"""
        try:
            for sel in ['.message-text', '.text-content', 'div[class*="text"]', 'div[class*="body"]']:
                content = msg.locator(sel).first
                if await content.count() > 0:
                    text = (await content.inner_text()).strip()
                    if len(text) > 5:
                        return re.sub(r'\s+', ' ', text)[:1000]
            
            # فال‌بک
            text = (await msg.inner_text()).strip()[:1000]
            return re.sub(r'\s+', ' ', text)
        except:
            return ""
    # ═══════════════════ متد اصلی با Timeout ═══════════════════
    async def run(self):
        base_timeout = getattr(self.config, 'timeout_seconds', OVERALL_TIMEOUT)
        self.timeout_manager = TimeoutManager(base_timeout)
        self.logger.info(f"⏱️ تایم‌اوت کلی: {base_timeout} ثانیه (با قابلیت تمدید پویا)")
    
        try:
            await asyncio.wait_for(self._run_impl(), timeout=base_timeout + 3600)
        except asyncio.TimeoutError:
            self.logger.error(f"⏰ تایم‌اوت کلی {base_timeout + self.timeout_manager.extra_time} ثانیه به پایان رسید.")
        except Exception as e:
            self.logger.critical(f"❌ خطای مرگبار: {e}", exc_info=True)

    async def _run_impl(self):
        if self.start_link:
            self.logger.info(f"🚀 شروع اسکریپر با لینک: {self.start_link} (limit={self.limit})")
        else:
            self.logger.info(f"🚀 شروع اسکریپر مستقل برای @{self.channel} (limit={self.limit})")
        last_post_id = None  # ← مقداردهی اولیه برای جلوگیری از UnboundLocalError
        # ─── بارگذاری وضعیت قبلی (اگر resume فعال باشد) ───
        if getattr(self.config, 'resume', False):
            state = self._load_resume_state()
            if state:
                last_post_id = state.get('last_post_id')
                downloaded_posts = state.get('downloaded_posts', [])
                # ─── ساخت لیست fallback ───
                fallback_ids = []
                downloaded_ids = []
                if downloaded_posts:
                    try:
                        downloaded_ids = sorted([int(id) for id in downloaded_posts if id.isdigit()])
                        # ─── لاگ‌های دیباگ ──────────────────────────────────
                        self.logger.info(f"🐞 downloaded_ids: {downloaded_ids[:10]} ... (تعداد: {len(downloaded_ids)})")
        
                        try:
                            last_index = downloaded_ids.index(int(last_post_id))
                        except ValueError:
                            last_index = len(downloaded_ids) - 1
                        self.logger.info(f"🐞 last_index: {last_index}")
        
                        for i in range(last_index - 1, -1, -1):
                            fallback_ids.append(str(downloaded_ids[i]))
                    except Exception as e:
                        self.logger.warning(f"⚠️ خطا در ساخت لیست fallback: {e}")
                self.logger.info(f"🐞 fallback_ids: {fallback_ids[:10]} ... (تعداد: {len(fallback_ids)})")
                # ذخیره لیست fallback برای استفاده در حلقه اصلی
                self._fallback_ids = fallback_ids
                self._fallback_index = 0  # برای پیگیری اندیس فعلی
                
        # ─── بارگذاری وضعیت قبلی (اگر resume فعال باشد) ───
        if getattr(self.config, 'resume', False):
            state = self._load_resume_state()
            if state:
                last_post_id = state.get('last_post_id')
                if last_post_id:
                    # استفاده از خود آخرین پست به عنوان نقطه شروع (بدون حدس شناسه)
                    self.start_link = f"https://t.me/{self.channel}/{last_post_id}"
                    self.target_msg_id = str(last_post_id)
                    self.logger.info(f"🔄 ادامه از آخرین پست دانلودشده: {last_post_id}")
                else:
                    self.logger.info("ℹ️ resume_state خالی است، از ابتدا شروع می‌شود.")
                    self.start_link = None
                    self.target_msg_id = None
            else:
                self.logger.info("ℹ️ resume فعال است اما وضعیتی وجود ندارد، از ابتدا شروع می‌شود.")
                self.start_link = None
                self.target_msg_id = None
        else:
            self.logger.info("ℹ️ resume غیرفعال است، از ابتدا شروع می‌شود.")
            self.start_link = None
            self.target_msg_id = None
        
        # ─── اگر fallback تمام شد، حدس شناسه‌های قبلی (به‌عنوان آخرین راه) ───
        # این بخش باید بعد از بارگذاری resume و در سطح _run_impl باشد،
        # اما در حلقه while اجرا می‌شود (قبلاً اضافه شده است).            

            
        # ─── اگر حالت retry فعال باشد ──────────────────────────
        retry_failed = getattr(self.config, 'retry_failed', False)
        if retry_failed:
            failed_ids = self._extract_failed_posts_from_report()
            if not failed_ids:
                self.logger.info("✅ هیچ پست ناموفقی برای تلاش مجدد وجود ندارد.")
                return
            self.logger.info(f"🔄 تلاش مجدد برای {len(failed_ids)} پست ناموفق...")
            
            # ─── پردازش تک‌تک پست‌ها ──────────────────────────
            context = None
            page = None
            retry_media_map = {}
            retry_failed_posts = []
            retry_items = []  # برای گزارش نهایی
            
            for idx, post_id in enumerate(failed_ids, 1):
                self.logger.info(f"📥 [{idx}/{len(failed_ids)}] پردازش پست {post_id} ...")
                
                # تنظیم لینک مستقیم برای این پست
                self.start_link = f"https://t.me/{self.channel}/{post_id}"
                self.target_msg_id = str(post_id)
                
                # اطمینان از مرورگر
                context, page = await self._ensure_browser(context, page)
                
                # دریافت فقط همین پست
                items, context, page = await self._fetch_posts_from_telegram(
                    existing_seen_ids=set(),
                    keep_browser_open=True,
                    existing_context=context,
                    existing_page=page,
                    limit=1,
                    target_ids=[str(post_id)]  # ← فقط این پست را بگیر
                )
                
                if not items:
                    self.logger.warning(f"⚠️ پست {post_id} پیدا نشد!")
                    retry_failed_posts.append({
                        'id': str(post_id),
                        'reason': 'پست پیدا نشد',
                        'url': f"https://t.me/{self.channel}/{post_id}"
                    })
                    continue
                
                # دانلود رسانه‌های این پست
                post_data = items[0]
                media_map, downloaded, failed = await self._download_media([post_data], page, context)
                
                if media_map:
                    retry_media_map.update(media_map)
                    retry_items.append(post_data)
                    self.logger.info(f"✅ پست {post_id} با {downloaded} فایل دانلود شد.")
                else:
                    retry_failed_posts.append({
                        'id': str(post_id),
                        'reason': 'دانلود نشد (بدون فایل یا خطا)',
                        'url': f"https://t.me/{self.channel}/{post_id}"
                    })
                    self.logger.warning(f"❌ پست {post_id} ناموفق بود.")            
            # ─── تولید گزارش نهایی retry ──────────────────────────────
            await self._generate_download_report(retry_items, retry_media_map, retry_failed_posts)
            if context:
                await context.close()
            self.logger.info("🏁 تلاش مجدد تمام شد.")
            return  # خروج از تابع (اجرای عادی ادامه پیدا نمی‌کند)
        
        # ─── ادامه کد عادی (زمانی که retry_failed == False) ──────────
        # ─── متغیرهای کلی ─────────────────────────────
        items = []
        media_map = {}
        all_failed_posts = []
        context = None
        page = None

        while len(items) < self.limit:
            # ─── اطمینان از مرورگر ──────────────────────
            context, page = await self._ensure_browser(context, page)

            # ─── جمع‌آوری پست‌های جدید ─────────────────
            new_items, context, page = await self._fetch_posts_from_telegram(
                existing_seen_ids={item['id'] for item in items} if items else None,
                keep_browser_open=True,
                existing_context=context,
                existing_page=page,
                limit=self.limit - len(items)
            )

            # فیلتر کردن پست‌های جدید (حذف تکراری‌ها)
            newly_added = []
            for item in new_items:
                if item['id'] not in {i['id'] for i in items}:
                    items.append(item)
                    newly_added.append(item)
            # ─── اگر fallback فعال بود و پست جدیدی پیدا شد، آن را غیرفعال کن ───
            if newly_added and hasattr(self, '_fallback_ids'):
                self._fallback_ids = []  # پاکسازی تا دیگر تلاش نشود
                self.logger.debug("✅ fallback غیرفعال شد (پست جدید پیدا شد).")
            self.logger.info(f"📥 {len(newly_added)} پست جدید جمع‌آوری شد (مجموع: {len(items)}/{self.limit})")
            # ─── پر کردن شکاف‌های شناسه در newly_added ──────────────────
            if newly_added:
                # مرتب‌سازی برای تشخیص شکاف‌ها
                newly_added_sorted = sorted(newly_added, key=lambda x: int(x['id']))
                complete_list = []
    
                for i in range(len(newly_added_sorted) - 1):
                    current_id = int(newly_added_sorted[i]['id'])
                    next_id = int(newly_added_sorted[i+1]['id'])
                    complete_list.append(newly_added_sorted[i])
        
                    # اگر فاصله بیشتر از ۱ بود، یعنی پست‌هایی جا افتاده‌اند
                    if next_id - current_id > 1:
                        for missing_id in range(current_id + 1, next_id):
                            self.logger.warning(f"🔍 پست گم‌شده شناسایی شد: {missing_id} (ذخیره برای واکشی بعدی)")
                            self._missing_post_ids.append(str(missing_id))  # ← ذخیره شناسه
    
                # اضافه کردن آخرین پست به لیست کامل
                if newly_added_sorted:
                    complete_list.append(newly_added_sorted[-1])
    
                # به‌روزرسانی newly_added_sorted با لیست کامل
                newly_added_sorted = complete_list
            else:
                newly_added_sorted = []  # اگر newly_added خالی است
            # اگر هیچ پست جدیدی اضافه نشد، یعنی کار تمام است
            if not newly_added:
                # ─── اگر fallback_ids داریم و هنوز fallback باقی مانده ───
                if hasattr(self, '_fallback_ids') and self._fallback_ids:
                    self._fallback_index += 1
                    if self._fallback_index < len(self._fallback_ids):
                        next_fallback = self._fallback_ids[self._fallback_index]
                        self.start_link = f"https://t.me/{self.channel}/{next_fallback}"
                        self.target_msg_id = next_fallback
                        self.logger.info(f"🔄 تلاش با fallback بعدی: {next_fallback}")
                        continue
                    else:
                        self.logger.info("✅ تمام گزینه‌های fallback بررسی شدند.")
                
                self.logger.info("✅ به نظر می‌رسد تمام پست‌های در دسترس جمع‌آوری شدند.")
                if self.debug_mode:
                    await self._save_screenshot(page, "end_of_channel")
                break

            # 🔥 دانلود فوری رسانه‌های پست‌های جدید
            # 🔥 دانلود فوری رسانه‌های پست‌های جدید
            self.logger.info(f"⬇️ شروع دانلود رسانه برای {len(newly_added)} پست جدید...")
            try:
                # دیگر نیازی به مرتب‌سازی مجدد نیست چون از قبل sorted است
                batch_media_map, downloaded_batch, batch_failed = await self._download_media(
                    newly_added_sorted,  # ← استفاده از لیست کامل‌شده
                    page,
                    context
                )
                all_failed_posts.extend(batch_failed)
                media_map.update(batch_media_map)
                self.logger.info(f"✅ {downloaded_batch} فایل رسانه در این دور دانلود شد.")
                if downloaded_batch > 0:
                    self.last_download_success = True
                await human_sleep(3.0, 1.0)
            except Exception as e:
                self.logger.error(f"❌ خطا در دانلود این batch: {e}")
                # اگر خطا رخ داد، همچنان متغیر را تعریف کن تا از خطا در ادامه جلوگیری شود
                newly_added_sorted = newly_added

            # ─── چک کردن حجم و آپلود در صورت نیاز ──────────────────
            total_size = sum(f.stat().st_size for f in self.media_dir.rglob('*') if f.is_file())
            size_mb = total_size / (1024 * 1024)
            if size_mb > 1024:  # ۱ گیگابایت
                self.logger.info(f"📦 حجم پوشه media به {size_mb:.1f} MB رسید. شروع آپلود...")
                uploaded = await self._upload_and_cleanup()
                if uploaded:
                    # ✅ استفاده از newly_added_sorted
                    self._save_resume_state(str(newly_added_sorted[-1]['id']), items)
                else:
                    self.logger.warning("⚠️ آپلود ناموفق بود، ادامه با فایل‌های محلی...")

            # به‌روزرسانی start_link با آخرین پست جدید
            # ✅ استفاده از newly_added_sorted
            last_item = newly_added_sorted[-1]
            last_id_str = str(last_item['id']).strip()
            try:
                if '.' in last_id_str:
                    last_id = int(float(last_id_str))
                else:
                    last_id = int(last_id_str)
            except:
                last_id = last_id_str

            new_start_link = f"https://t.me/{self.channel}/{last_id}"
            self.start_link = new_start_link
            self.target_msg_id = str(last_id)
            self.logger.info(f"🔄 نقطه شروع دور بعدی: {self.start_link} (id: {last_id})")   #ریست شمارنده

        # ─── بعد از اتمام تمام دورها ─────────────────────────────
        # ─── واکشی پست‌های گم‌شده در پایان (فقط در صورت پر شدن limit) ──
        if len(items) == self.limit and hasattr(self, '_missing_post_ids') and self._missing_post_ids:
            self.logger.info(f"🔍 شروع واکشی {len(self._missing_post_ids)} پست گم‌شده در پایان کار...")
            fetched_missing_items = []
    
            for missing_id in self._missing_post_ids:
                # بررسی اینکه آیا پست قبلاً در items وجود دارد
                if missing_id in {i['id'] for i in items}:
                    continue
        
                self.logger.info(f"   🔍 تلاش برای واکشی پست گم‌شده: {missing_id}")
                try:
                    # ذخیره لینک فعلی
                    old_link = self.start_link
                    old_target = self.target_msg_id
            
                    # تنظیم لینک مستقیم
                    self.start_link = f"https://t.me/{self.channel}/{missing_id}"
                    self.target_msg_id = str(missing_id)
            
                    # واکشی فقط همان پست
                    fetched_items, _, _ = await self._fetch_posts_from_telegram(
                        existing_seen_ids={item['id'] for item in items},
                        keep_browser_open=True,
                        existing_context=context,
                        existing_page=page,
                        limit=1,
                        target_ids=[str(missing_id)]
                    )
            
                    # برگرداندن لینک قبلی
                    self.start_link = old_link
                    self.target_msg_id = old_target
            
                    if fetched_items:
                        for item in fetched_items:
                            if item['id'] not in {i['id'] for i in items}:
                                items.append(item)
                                fetched_missing_items.append(item)
                                self.logger.info(f"   ✅ پست گم‌شده {missing_id} با موفقیت واکشی شد")
                    else:
                        self.logger.warning(f"   ⚠️ پست {missing_id} وجود ندارد (یا حذف شده)")
                        if not hasattr(self, '_missing_posts'):
                            self._missing_posts = []
                        self._missing_posts.append({
                            'id': missing_id,
                            'reason': 'پست وجود ندارد (احتمالاً حذف شده)',
                            'url': f"https://t.me/{self.channel}/{missing_id}"
                        })
                except Exception as e:
                    self.logger.debug(f"   خطا در واکشی پست {missing_id}: {e}")
    
            # ─── دانلود پست‌های واکشی‌شده ──────────────────────────────
            if fetched_missing_items:
                self.logger.info(f"⬇️ شروع دانلود {len(fetched_missing_items)} پست واکشی‌شده...")
                try:
                    # مرتب‌سازی پست‌های واکشی‌شده
                    fetched_sorted = sorted(fetched_missing_items, key=lambda x: int(x['id']))
                    # دانلود با همان page و context
                    missing_media_map, missing_downloaded, missing_failed = await self._download_media(
                        fetched_sorted, page, context
                    )
                    all_failed_posts.extend(missing_failed)
                    media_map.update(missing_media_map)
                    self.logger.info(f"✅ {missing_downloaded} فایل رسانه از پست‌های واکشی‌شده دانلود شد.")
                except Exception as e:
                    self.logger.error(f"❌ خطا در دانلود پست‌های واکشی‌شده: {e}")
    
            # پاکسازی لیست (بعد از واکشی)
            self._missing_post_ids = []
        else:
            # اگر به limit نرسیدیم، فقط لاگ بگیر و لیست رو پاک کن
            if hasattr(self, '_missing_post_ids') and self._missing_post_ids:
                self.logger.info(f"ℹ️ به limit نرسیدیم ({len(items)}/{self.limit})، واکشی پست‌های گم‌شده انجام نشد.")
                self._missing_post_ids = []  # پاکسازی برای جلوگیری از تداخل

        # ─── ادامه کد (همیشه اجرا میشه) ──────────────────────────────
        self.logger.info(f"🎉 جمع‌آوری تمام شد. مجموع {len(items)} پست.")

        # تولید خروجی نهایی (فقط در حالت دیباگ)
        if self.debug_mode:
            self.logger.info("🐞 حالت دیباگ: تولید خروجی‌های کامل (JSON, CSV, HTML, ZIP)")
            gen = OutputGenerator(
                self.base_dir,
                self.channel,
                items,
                media_map,
                debug_mode=self.debug_mode
            )
            gen.run_all()
        else:
            self.logger.info("📁 حالت عادی: فقط رسانه‌ها دانلود شدند و برای آپلود آماده هستند.")
            # در حالت عادی هیچ خروجی اضافی تولید نمی‌شود

        # ─── ذخیره وضعیت نهایی (اگر آیتمی وجود داشته باشد) ───
        if items:
            self._save_resume_state(str(items[-1]['id']), items)

        # ─── تولید گزارش نهایی ──────────────────────────────
        await self._generate_download_report(items, media_map, all_failed_posts)

        if context:
            await context.close() 
        
    async def _ensure_browser(self, context, page):
        """اطمینان از باز بودن مرورگر."""
        if context is None:
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
            self.logger.info("🔄 مرورگر جدید راه‌اندازی شد (زیرا context وجود نداشت).")
        elif page is None:
            page = await context.new_page()
            self.logger.info("🔄 صفحه‌ی جدید در context موجود ساخته شد.")
        return context, page
    # ═══════════════════ استخراج پست‌ها با پشتیبانی از جهت اسکرول ═══════════════════
    async def _fetch_posts_from_telegram(self, existing_seen_ids: set = None, keep_browser_open: bool = False, existing_context: Any = None, existing_page: Any = None, limit: int = None, target_ids: List[str] = None) -> Tuple[List[Dict], Any, Any]:
        from playwright.async_api import async_playwright

        # ─── اگر context و page از قبل وجود دارند، از آن‌ها استفاده کن ──
        if existing_context is not None and existing_page is not None:
            context = existing_context
            page = existing_page
            p = None  # برای اینکه در انتها بسته نشود
            self.logger.info("♻️ استفاده مجدد از context و page موجود")
        else:
            # ─── راه‌اندازی مرورگر ──────────────────────────────────
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

        # ─── منتظر بارگذاری پیام‌های کانال ──────────────────────────
        self.logger.info("⏳ منتظر بارگذاری پیام‌های کانال...")
        try:
            # منتظر بمان تا حداقل یک پیام با محتوای غیرخالی ظاهر شود
            await page.wait_for_function(
                """() => {
                    const messages = document.querySelectorAll('div[data-message-id]');
                    if (messages.length === 0) return false;
                    for (const msg of messages) {
                        const text = msg.innerText?.trim() || '';
                        if (text.length > 10) return true;
                    }
                    return false;
                }""",
                timeout=15000
            )
            self.logger.info("✅ پیام‌ها با محتوا بارگذاری شدند.")
            
            # ─── اگر direction 'up' است، به جدیدترین پست‌ها برو ──────────
            if self.scroll_direction == 'up' and not self.start_link:
                self.logger.info("⬇️ تلاش برای رفتن به جدیدترین پست‌ها...")
                
                # ─── جستجوی دکمه فلش (فقط یک بار) ──────────────────────────
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
                
                # ─── اگر دکمه فلش پیدا نشد، فقط لاگ کن و ادامه بده ──────────
                if not clicked:
                    self.logger.info("   ℹ️ دکمه فلش پیدا نشد. ادامه با وضعیت فعلی (مانند نسخه دیباگ).")
                else:
                    # ─── منتظر بارگذاری پیام‌های جدید ──────────────────────────
                    self.logger.info("⏳ منتظر بارگذاری پیام‌های جدید در پایین صفحه...")
                    try:
                        await page.wait_for_function(
                            """() => {
                                const messages = document.querySelectorAll('div[data-message-id]');
                                if (messages.length === 0) return false;
                                const viewportHeight = window.innerHeight;
                                for (const msg of messages) {
                                    const rect = msg.getBoundingClientRect();
                                    if (rect.top > viewportHeight * 0.3 && rect.top < viewportHeight * 0.9) {
                                        const text = msg.innerText?.trim() || '';
                                        if (text.length > 10) return true;
                                    }
                                }
                                return false;
                            }""",
                            timeout=10000
                        )
                        self.logger.info("✅ پیام‌های جدید در پایین صفحه بارگذاری شدند.")
                    except Exception as e:
                        self.logger.warning(f"⚠️ timeout در انتظار پیام‌های جدید: {e}")

                # ★★★ فقط یک بار، صرف‌نظر از پیدا شدن دکمه ★★★
                self._manual_scroll_done = True

            # ─── منتظر رندر کامل ──────────────────────────────
            await asyncio.sleep(3)
            self.logger.info("⏳ منتظر رندر کامل پیام‌ها...")
            
            # ─── اطمینان از وجود حداقل یک پیام با محتوا قبل از شروع ───
            self.logger.info("🔍 بررسی مجدد وجود پیام‌های با محتوا در صفحه...")
            try:
                await page.wait_for_function(
                    """() => {
                        const messages = document.querySelectorAll('div[data-message-id]');
                        if (messages.length === 0) return false;
                        for (const msg of messages) {
                            const text = msg.innerText?.trim() || '';
                            if (text.length > 5) return true;
                        }
                        return false;
                    }""",
                    timeout=5000
                )
                self.logger.info("✅ پیام‌های با محتوا در صفحه وجود دارند.")
            except Exception:
                self.logger.warning("⚠️ پیامی با محتوا در صفحه یافت نشد، ادامه با اسکرول...")
            
        except Exception as e:
            self.logger.warning(f"⚠️ timeout در انتظار پیام‌ها: {e}. ادامه با اسکرول...")

        await self._save_screenshot(page, "initial")
        # ─── صبر اضافی برای بارگذاری کامل ────────────────────────────
        if not self.start_link and self.scroll_direction == 'up':
            self.logger.info("⏳ ۴ ثانیه صبر اضافی برای بارگذاری کامل...")
            await asyncio.sleep(4)

        # ─── استخراج مقاوم (حداکثر ۳ تلاش با تأخیر هوشمند) ──────────────────
        items = []
        seen_ids = set()
        scroll_attempts = 0
        effective_limit = limit if limit is not None else self.limit

        self.logger.info(f"🔍 شروع استخراج مقاوم — حد: {effective_limit} پست")

        # ─── متغیر start_collecting ─────────────────────────────────────
        start_collecting = not bool(self.start_link)  # اگر start_link نداشته باشیم، از اول شروع می‌کنیم

        for attempt in range(5):  # ← افزایش به ۵ تلاش
            if attempt > 0:
                self.logger.info(f"🔄 تلاش استخراج {attempt+1}/5 (با تأخیر برای بارگذاری)...")
                # اسکرول با گام کوچک‌تر و تعداد تلاش بیشتر
                await self._smart_scroll(page, self.scroll_direction, step=600, max_attempts=2)
                # اسکرول معکوس مختصر برای تحریک بارگذاری (در تلاش‌های زوج)
                if attempt % 2 == 0:
                    self.logger.debug("   🔄 اسکرول معکوس ۲۰۰px برای تحریک بارگذاری...")
                    await page.evaluate("window.scrollBy(0, 200)")
                    await human_sleep(0.8, 0.2)
                # تأخیر بیشتر برای بارگذاری کامل
                self.logger.info("⏳ صبر ۴ ثانیه برای بارگذاری محتوای جدید...")
                await human_sleep(4.0, 0.5)

            # ─── دریافت پیام‌ها با روش‌های مختلف ──────────────────────────
            # ─── روش اصلی: استخراج با JavaScript (همه پست‌های موجود در DOM) ───
            messages = []
            try:
                js_posts = await self._extract_posts_from_page(page)
                messages = js_posts  # ← JS همیشه استفاده می‌شود
                self.logger.info(f"   📊 استخراج با JS: {len(messages)} پست")
            except Exception as e:
                self.logger.debug(f"   ⚠️ خطا در استخراج JS: {e}، استفاده از locator...")
                # Fallback به locator در صورت خطا
                messages = await page.locator('div[data-message-id]').all()
                if len(messages) < 5:
                    messages = await page.locator('div.message, div[class*="bubble"], div[class*="message"], div[class*="post"]').all()

            # اگر JS موفق بود ولی تعدادش کم است، از locator هم استفاده کن (تکمیل)
            if messages and len(messages) < 20:
                try:
                    locator_msgs = await page.locator('div[data-message-id]').all()
                    if len(locator_msgs) > len(messages):
                        self.logger.info(f"   📊 locator پست‌های بیشتری پیدا کرد: {len(locator_msgs)}")
                        # ترکیب دو لیست (بدون تکرار)
                        existing_ids = {msg['id'] for msg in messages}
                        for msg in locator_msgs:
                            msg_id = await msg.get_attribute('data-message-id')
                            if msg_id and msg_id not in existing_ids:
                                text = await self._extract_text_from_message(msg, msg_id)
                                date = ""
                                try:
                                    date_el = msg.locator('time, .date, .message-date, [datetime]').first
                                    if await date_el.count() > 0:
                                        date = await date_el.inner_text() or ""
                                except:
                                    pass
                                messages.append({
                                    'id': msg_id,
                                    'text': text,
                                    'date': date
                                })
                                existing_ids.add(msg_id)
                except Exception as e:
                    self.logger.debug(f"   ⚠️ خطا در تکمیل با locator: {e}")

            self.logger.info(f"   📋 تلاش {attempt+1}: {len(messages)} المان پیام پیدا شد")

            if not messages:
                # اگر پیامی وجود نداشت، یک بار دیگر صبر کن (بدون اسکرول مجدد)
                if attempt < 2:
                    self.logger.info("⏳ پیامی وجود ندارد، ۲ ثانیه صبر می‌کنم...")
                    await human_sleep(2.0, 0.3)
                    messages = await page.locator('div[data-message-id]').all()
                    if messages:
                        self.logger.info(f"   ✅ پس از صبر، {len(messages)} پیام پیدا شد")
                if not messages:
                    continue

            # ─── تعیین ترتیب ─────────────────────────────────────────────
            # اگر start_link داریم یا جهت 'up' است، از جدید به قدیم برویم
            if self.start_link or self.scroll_direction == 'up':
                msg_iter = reversed(messages)
            else:
                msg_iter = messages

            for msg in msg_iter:
                try:
                    # ─── تشخیص نوع msg (دیکشنری یا المان Playwright) ───
                    if isinstance(msg, dict):
                        # msg از _extract_posts_from_page آمده است
                        msg_id = msg.get('id')
                        text = msg.get('text', '')
                        date = msg.get('date', '')
                        # برای ریپلای، از المان اصلی استفاده نمی‌کنیم، پس فرض می‌کنیم ریپلای نیست
                        is_reply = False
                        # برای داده‌های JS، نیازی به استخراج مجدد نیست
                        # ولی برای یکسان‌سازی، می‌توانیم از همان مقادیر استفاده کنیم
                    else:
                        # msg المان Playwright است
                        msg_id = await msg.get_attribute('data-message-id')
                        if msg_id:
                            msg_id = str(int(float(msg_id)))
            
                        # بررسی پست ریپلای شده (فقط برای المان‌ها)
                        is_reply = await msg.locator('.EmbeddedMessage').count() > 0
                        if is_reply:
                            self.logger.info(f"🔁 پست {msg_id} یک ریپلای است (نادیده گرفته شد)")
                            if not hasattr(self, '_reply_posts'):
                                self._reply_posts = []
                            self._reply_posts.append({
                                'id': msg_id,
                                'text': '',
                                'date': '',
                                'url': f"https://t.me/{self.channel}/{msg_id}"
                            })
                            continue  # رد شدن از ادامه پردازش این پیام
            
                        # استخراج متن و تاریخ از المان
                        text = await self._extract_text_from_message(msg, msg_id)
                        date = ""
                        try:
                            date_el = msg.locator('time, .date, .message-date, [datetime]').first
                            if await date_el.count() > 0:
                                date = await date_el.inner_text() or ""
                        except:
                            pass

                    # ─── ادامه پردازش مشترک ──────────────────────────────
                    self.logger.debug(f"   → پردازش پیام {msg_id}")
        
                    if not msg_id or msg_id in seen_ids:
                        continue

                    # ─── فیلتر target_ids ──────────────────────────────────
                    if target_ids and msg_id not in target_ids:
                        continue

                    # ─── اگر start_link داریم، صبر کن تا به پیام هدف برسیم ──
                    if self.start_link and not start_collecting:
                        if msg_id == self.target_msg_id:
                            start_collecting = True
                            self.logger.info(f"🎯 پیام هدف پیدا شد: {msg_id}")
                        else:
                            continue

                    if not start_collecting:
                        continue

                    # ─── اگر msg دیکشنری است، قبلاً text و date را داریم ──
                    # ولی اگر المان است، قبلاً استخراج شده، پس نیازی به کار اضافی نیست

                    items.append({
                        'id': msg_id,
                        'text': text,
                        'date': date,
                        'url': f"https://t.me/{self.channel}/{msg_id}"
                    })
                    seen_ids.add(msg_id)

                    if len(items) >= effective_limit:
                        break

                except Exception as e:
                    self.logger.debug(f"خطا در پردازش پیام: {e}")
                    continue
            if len(items) >= effective_limit:
                 break

            # ─── فقط در صورتی اسکرول کنیم که پیامی پیدا نشد ──────────────
            if len(items) == 0 and attempt < 4:  # ← افزایش تعداد دفعات
                self.logger.info(f"🔄 اسکرول به {self.scroll_direction} برای تلاش بعدی...")
                # اسکرول با گام‌های مختلف
                if attempt % 2 == 0:
                    scrolled = await self._smart_scroll(page, self.scroll_direction, step=800, max_attempts=2)
                else:
                    scrolled = await self._smart_scroll(page, self.scroll_direction, step=1200, max_attempts=1)
                if not scrolled:
                    self.logger.info("ℹ️ اسکرول تغییری ایجاد نکرد. تلاش با اسکرول نرم...")
                    # استفاده از اسکرول نرم برای پیدا کردن پست‌های پنهان
                    found, found_id = await self._find_post_with_slow_scroll(page, seen_ids)
                    if found:
                        self.logger.info(f"   ✅ پست جدید با اسکرول نرم پیدا شد: {found_id}")
                        # اضافه کردن پست به items (با استخراج متن و تاریخ)
                        try:
                            msg = page.locator(f'[data-message-id="{found_id}"]').first
                            text = await self._extract_text_from_message(msg, found_id)
                            date = ""
                            try:
                                date_el = msg.locator('time, .date, .message-date, [datetime]').first
                                if await date_el.count() > 0:
                                    date = await date_el.inner_text() or ""
                            except:
                                pass
    
                            # ✅ اینجا باید باشد (داخل try اصلی)
                            items.append({
                                'id': found_id,
                                'text': text,
                                'date': date,
                                'url': f"https://t.me/{self.channel}/{found_id}"
                            })
                            seen_ids.add(found_id)
                            self.logger.info(f"   ✅ پست {found_id} به لیست اضافه شد (اسکرول نرم)")
                        except Exception as e:
                            self.logger.debug(f"   ⚠️ خطا در اضافه کردن پست از اسکرول نرم: {e}")         
                    else:
                        self.logger.info("ℹ️ اسکرول نرم نیز پستی پیدا نکرد. صبر برای بارگذاری...")
                        await human_sleep(3.0, 0.5)

        self.logger.info(f"📊 در مجموع {len(items)} پست جمع‌آوری شد.")
        items = items[:effective_limit]
        await self._save_screenshot(page, "final")
        await self._capture_post_screenshots(page, items)

        if items:
            first_id = items[0]['id']
            try:
                await page.locator(f'[data-message-id="{first_id}"]').scroll_into_view_if_needed()
                await human_sleep(1, 0.3)
            except Exception:
                pass

        return items, context, page

    # ═══════════════════ جستجو و ورود به کانال (روش معمولی) ═══════════════════
    async def _search_and_enter_channel(self, page) -> bool:
        search_input = None
        for sel in [
            'input[placeholder*="Search"]',
            'input[role="textbox"]',
            '[data-testid="search-input"]'
        ]:
            try:
                search_input = await page.wait_for_selector(sel, timeout=10000)
                if search_input:
                    self.logger.info("🔍 نوار جستجو پیدا شد.")
                    break
            except Exception:
                continue
        if not search_input:
            self.logger.error("❌ نوار جستجو پیدا نشد.")
            return False

        await search_input.click()
        await human_sleep(0.3, 0.2)
        await search_input.fill('')
        await human_sleep(0.2, 0.1)
        await search_input.type(self.channel, delay=random.randint(80, 150))
        self.logger.info(f"🔍 در حال جستجوی: @{self.channel}")
        await self._take_screenshot(page, "search_input_filled")
        await human_sleep(1.5, 0.3)
        await page.keyboard.press("Enter")
        self.logger.info("⏳ منتظر نتایج...")

        search_term = self.channel_name if self.channel_name else self.channel
        found = False

        self.logger.info("🕐 مرحله اول انتظار (۱۰ ثانیه)...")
        await human_sleep(10, 0.5)
        if await self._check_text_on_page(page, search_term):
            found = True
            self.logger.info(f"   ✅ عبارت '{search_term}' در مرحله اول یافت شد.")

        if not found:
            self.logger.info("🕑 مرحله دوم انتظار (۱۵ ثانیه)...")
            await human_sleep(15, 0.5)
            if await self._check_text_on_page(page, search_term):
                found = True
                self.logger.info(f"   ✅ عبارت '{search_term}' در مرحله دوم یافت شد.")

        if not found:
            self.logger.info("🕒 مرحله سوم انتظار (۲۰ ثانیه)...")
            await human_sleep(20, 0.5)
            if await self._check_text_on_page(page, search_term):
                found = True
                self.logger.info(f"   ✅ عبارت '{search_term}' در مرحله سوم یافت شد.")

        if not found:
            self.logger.info("📑 کلیک روی تب Channels (در صورت وجود)...")
            try:
                channels_tab = page.get_by_role("tab", name="Channels").first
                if await channels_tab.count() > 0:
                    await channels_tab.click()
                    await human_sleep(4, 0.4)
                    self.logger.info("   📑 تب Channels انتخاب شد.")
            except Exception:
                pass

            for attempt in range(15):
                await human_sleep(2, 0.3)
                if await self._check_text_on_page(page, search_term):
                    found = True
                    self.logger.info(f"   ✅ عبارت '{search_term}' بعد از کلیک Channels یافت شد (تلاش {attempt+1}).")
                    break

        if not found:
            self.logger.error(f"❌ نتایج جستجو برای '{search_term}' پیدا نشد (حتی پس از ۴۵+ ثانیه).")
            await self._take_screenshot(page, "search_failed")
            return False

        self.logger.info("✅ نتایج جستجو ظاهر شدند.")
        await self._take_screenshot(page, f"search_results_{self.channel}")
        await human_sleep(2, 0.3)

        return await self._click_search_result(page, search_term)

    # ═══════════════════ کلیک روی نتیجه جستجو ═══════════════════
    async def _click_search_result(self, page, search_term: str) -> bool:
        click_selectors = [
            'div.chatlist-item', 'div[role="button"]', 'div.search-result',
            'a[data-peer-id]', 'div[class*="chatlist"] div[class*="item"]',
            'div[class*="ListItem"]', 'div[class*="search-result"]'
        ]
        for sel in click_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                await loc.click(timeout=8000, force=True)
                # به جای sleep، منتظر بارگذاری پیام‌ها باشیم
                try:
                    await page.wait_for_selector('div[data-message-id]', timeout=10000)
                    # ─── تأخیر کوتاه برای رندر ──────────────────────
                    await asyncio.sleep(1.5)
                    self.logger.info("✅ کانال با موفقیت باز شد (سلکتور %s).", sel)
                    return True
                except Exception:
                    await asyncio.sleep(3)
                    if await page.locator('div.message, div[data-message-id]').count() > 0:
                        self.logger.info("✅ کانال با موفقیت باز شد (سلکتور %s).", sel)
                        return True
            except Exception as e:
                self.logger.debug("سلکتور %s ناموفق: %s", sel, e)

        self.logger.info("🔄 تلاش کلیک با JavaScript روی عبارت جستجو...")
        try:
            await page.evaluate(f'''(term) => {{
                const els = Array.from(document.querySelectorAll('h3, .fullName, [dir="auto"], div[class*="name"], span[class*="peer-title"]'));
                const target = els.find(el => el.textContent.trim().toLowerCase() === term.toLowerCase());
                if (target) {{
                    target.closest('div[role="button"], div.chatlist-item, a')?.click();
                }}
            }}''', search_term)
            await human_sleep(5, 0.4)
            if await page.locator('div.message, div[data-message-id]').count() > 0:
                self.logger.info("✅ با JavaScript (عبارت جستجو) وارد شدیم.")
                return True
        except Exception as e:
            self.logger.debug("JavaScript name click: %s", e)

        self.logger.info("🔄 تلاش کلیک با JavaScript روی اولین نتیجه...")
        try:
            await page.evaluate('''() => {
                const item = document.querySelector('div.chatlist-item, div[role="button"], div.search-result, a[data-peer-id]');
                if (item) item.click();
            }''')
            await human_sleep(5, 0.4)
            if await page.locator('div.message, div[data-message-id]').count() > 0:
                self.logger.info("✅ با JavaScript (اولین نتیجه) وارد شدیم.")
                return True
        except Exception as e:
            self.logger.debug("JavaScript generic click: %s", e)

        self.logger.error("❌ تمام روش‌های کلیک شکست خورد.")
        await self._take_screenshot(page, "click_failed")
        return False

    # ═══════════════════ متد جستجو با لینک (start_link) ═══════════════════
    async def _navigate_to_start_link(self, page) -> bool:
        self.logger.info(f"🔗 تلاش برای رفتن به لینک: {self.start_link}")

        try:
            parts = self.start_link.rstrip('/').split('/')
            if parts:
                self.target_msg_id = parts[-1] # ← هر چیزی که هست، بگیر
                self.logger.info(f"🎯 شناسه پیام هدف: {self.target_msg_id}")
            else:
                self.logger.warning("⚠️ نمی‌توان شناسه پیام را از لینک استخراج کرد.")
                self.target_msg_id = None
        except Exception as e:
            self.logger.warning(f"⚠️ خطا در استخراج شناسه پیام: {e}")
            self.target_msg_id = None

        # === پاک‌سازی target_msg_id (جلوگیری از اعشار) ===
        if self.target_msg_id:
            try:
                cleaned_id = str(int(float(self.target_msg_id)))
                if cleaned_id != self.target_msg_id:
                    self.logger.warning(f"⚠️ target_msg_id تصحیح شد: {self.target_msg_id} → {cleaned_id}")
                    self.target_msg_id = cleaned_id
                    self.start_link = f"https://t.me/{self.channel}/{cleaned_id}"
            except Exception as e:
                self.logger.error(f"خطا در پاک‌سازی target_msg_id: {e}")

        async def perform_search_and_click():
            search_input = None
            for sel in [
                'input[placeholder*="Search"]',
                'input[role="textbox"]',
                '[data-testid="search-input"]'
            ]:
                try:
                    search_input = await page.wait_for_selector(sel, timeout=10000)
                    if search_input:
                        self.logger.info("🔍 نوار جستجو پیدا شد.")
                        break
                except Exception:
                    continue
            if not search_input:
                self.logger.error("❌ نوار جستجو پیدا نشد.")
                return False

            await search_input.click()
            await human_sleep(0.3, 0.2)
            await search_input.fill('')
            await human_sleep(0.2, 0.1)
            await search_input.type(self.start_link, delay=random.randint(80, 150))
            self.logger.info(f"🔍 لینک تایپ شد: {self.start_link}")
            await self._take_screenshot(page, "search_link_filled")
            await human_sleep(1.5, 0.3)
            await page.keyboard.press("Enter")
            self.logger.info("⏳ منتظر نتایج جستجو...")
            await human_sleep(5, 0.5)
            await self._take_screenshot(page, "search_results_loaded")

            clicked = False
            result_selectors = [
                'div[data-message-id]',
                'div[class*="search-result"] a',
                'div[class*="message"] a',
                'div[role="button"][class*="item"]',
                'div.chatlist-item',
                'a[data-peer-id]',
            ]
            for sel in result_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=5000)
                    first_result = page.locator(sel).first
                    if await first_result.count() > 0:
                        await first_result.scroll_into_view_if_needed()
                        handle = await first_result.element_handle()
                        if handle:
                            await self._draw_debug_cross(page, handle)
                        await first_result.click(timeout=5000, force=True)
                        self.logger.info(f"✅ روی اولین نتیجه با سلکتور '{sel}' کلیک شد.")
                        clicked = True
                        break
                except Exception as e:
                    self.logger.debug(f"سلکتور {sel} ناموفق: {e}")
                    continue

            if not clicked:
                self.logger.info("🔄 تلاش کلیک با JavaScript روی اولین پیام...")
                try:
                    await page.evaluate('''() => {
                        const firstMsg = document.querySelector('[data-message-id]');
                        if (firstMsg) {
                            firstMsg.style.outline = '3px solid red';
                            firstMsg.style.outlineOffset = '2px';
                            firstMsg.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            setTimeout(() => { firstMsg.click(); }, 500);
                        }
                    }''')
                    await human_sleep(2, 0.3)
                    await self._take_screenshot(page, "after_js_click")
                    self.logger.info("✅ کلیک با JavaScript انجام شد.")
                    clicked = True
                except Exception as e:
                    self.logger.error(f"❌ کلیک با JavaScript شکست خورد: {e}")

            if not clicked:
                self.logger.error("❌ نتوانستیم روی هیچ نتیجه‌ای کلیک کنیم.")
                await self._take_screenshot(page, "click_result_failed")
                return False

            # ─── مرحله ۱: منتظر بارگذاری پیام‌ها ──────────────────
            try:
                await page.wait_for_selector('div[data-message-id]', timeout=20000)
                self.logger.info("✅ پیام‌ها در صفحه بارگذاری شدند.")
                await self._take_screenshot(page, "messages_loaded")
            except Exception:
                self.logger.warning("⚠️ پیام‌ها با timeout بارگذاری نشدند. تلاش با روش‌های جایگزین...")
                # ادامه می‌دهیم تا مراحل بعدی (جستجوی جایگزین و اسکرول نرم) اجرا شوند

            # ─── مرحله ۲: جستجوی دقیق با data-message-id ──────────
            target_exists = await page.locator(f'[data-message-id="{self.target_msg_id}"]').count() > 0
            if target_exists:
                self.logger.info(f"✅ پست هدف {self.target_msg_id} با data-message-id دقیق پیدا شد.")
                return True

            # ─── مرحله ۳: جستجوی جایگزین در همان صفحه ─────────────
            self.logger.warning(f"⚠️ پست با data-message-id دقیق پیدا نشد. جستجوی جایگزین در صفحه...")
            all_messages = await page.locator('div[data-message-id]').all()
            
            # ─── دیباگ: نمایش تمام شناسه‌های موجود ──────────────────
            found_ids = []
            for msg in all_messages:
                msg_id = await msg.get_attribute('data-message-id')
                if msg_id:
                    found_ids.append(msg_id)
            
            # ─── اگر صفحه خالی است، اسکرین‌شات بگیر ──────────────
            if not found_ids:
                try:
                    safe_name = self._sanitize_filename(f"empty_page_{self.target_msg_id}")
                    path = self.debug_screenshots_dir / f"{safe_name}.png"
                    await page.screenshot(path=path, full_page=True)
                    self.logger.info(f"📸 اسکرین‌شات صفحه خالی ذخیره شد: {path.name}")
                except Exception as e:
                    self.logger.warning(f"⚠️ خطا در ذخیره اسکرین‌شات صفحه خالی: {e}")
            
            self.logger.info(f"🐞 شناسه‌های موجود در صفحه: {found_ids}")
            self.logger.info(f"🐞 شناسه مورد جستجو: {self.target_msg_id}")
            
            for idx, msg in enumerate(all_messages):
                msg_id = await msg.get_attribute('data-message-id')
                msg_text = await msg.inner_text()
                msg_html = await msg.inner_html()
                
                # دیباگ: نمایش ۳ پیام اول به‌طور کامل‌تر
                if idx < 3:
                    self.logger.info(f"🐞 پیام {idx+1}: id={msg_id}, متن={msg_text[:100]}...")
                
                if self.target_msg_id in msg_html or f'/{self.target_msg_id}' in msg_html:
                    self.logger.info(f"🔍 پست هدف با جستجوی جایگزین پیدا شد: {msg_id}")
                    self.target_msg_id = msg_id
                    return True
                else:
                    self.logger.debug(f"   پیام {msg_id}: شامل '{self.target_msg_id}' نیست.")
            # ─── مرحله ۴: اسکرول نرم در همان صفحه ───────────────────
            self.logger.warning(f"⚠️ پست هدف در صفحه پیدا نشد. شروع اسکرول نرم در همان صفحه...")
            found, found_id = await self._find_post_with_slow_scroll(page, seen_ids=None)
            if found:
                self.target_msg_id = found_id
                self.logger.info(f"✅ پست هدف با اسکرول نرم پیدا شد: {self.target_msg_id}")
                return True
            else:
                self.logger.error("❌ حتی با اسکرول نرم هم پستی پیدا نشد.")
                return False

        for retry in range(2):
            if retry > 0:
                self.logger.info(f"🔄 تلاش مجدد ({retry+1})... بازگشت به صفحه قبل و دوباره جستجو")
                await page.go_back()
                await human_sleep(2, 0.3)
            success = await perform_search_and_click()
            if success:
                return True
            else:
                self.logger.warning(f"❌ تلاش {retry+1} ناموفق بود.")
        return False

    # ═══════════════════ متد کمکی: بررسی وجود عبارت ═══════════════════
    async def _check_text_on_page(self, page, term: str) -> bool:
        try:
            return await page.evaluate(f'''(t) => {{
                const bodyText = document.body.innerText || '';
                return bodyText.toLowerCase().includes(t.toLowerCase());
            }}''', term)
        except Exception:
            return False

    # ═══════════════════ اسکرین‌شات از تکتک پست‌ها ═══════════════════
    async def _capture_post_screenshots(self, page, items: List[Dict]):
        if not self.save_screenshots:
            self.logger.info("⏭️ ذخیره اسکرین‌شات پست‌ها غیرفعال است.")
            return
        self.logger.info(f"📸 گرفتن اسکرین‌شات از {len(items)} پست...")
        for idx, item in enumerate(items):
            msg_id = item['id']
            try:
                locator = page.locator(f'[data-message-id="{msg_id}"]').first
                if await locator.count() == 0:
                    self.logger.warning(f"⚠️ المان پست {msg_id} پیدا نشد، رد می‌شود.")
                    continue

                await locator.scroll_into_view_if_needed()
                await human_sleep(0.5, 0.2)

                safe_channel = self._sanitize_filename(self.channel)
                safe_msg_id = self._sanitize_filename(str(msg_id))
                path = self.screenshots_dir / f"{safe_channel}_post_{safe_msg_id}.png"
                await locator.screenshot(path=path)
                self.logger.debug(f"📸 اسکرین‌شات ذخیره شد: {path.name}")

                if (idx + 1) % 10 == 0:
                    self.logger.info(f"   {idx+1}/{len(items)} اسکرین‌شات گرفته شد.")
            except Exception as e:
                self.logger.warning(f"⚠️ خطا در اسکرین‌شات پست {msg_id}: {e}")
                continue

        self.logger.info(f"✅ اسکرین‌شات‌ها تمام شد. مجموع: {len(items)}")

    # ═══════════════════ دانلود رسانه‌ها ═══════════════════
    async def _download_media(self, items: List[Dict], page, context) -> Tuple[dict, int, List]:
        post_ids = [str(item['id']) for item in items]
        media_map = {}
        downloaded = 0
        failed_posts = []
        if post_ids:
            try:
                downloader = PlaywrightDownloader(
                    self.profile_dir,
                    self.media_dir,
                    self.max_media_bytes,
                    self.delay_between_posts,
                    debug_screenshots_dir=self.debug_screenshots_dir,
                    quiet_base=getattr(self.config, 'download_quiet_seconds', 1.0),
                    timeout_manager=self.timeout_manager,
                    channel=self.channel          # ← پارامتر جدید
                )
                media_map, failed_posts = await downloader.download_all(page, context, post_ids, media_map)
            except Exception as e:
                self.logger.error(f"❌ خطا در فرآیند دانلود: {e}")
            finally:
                for files in media_map.values():
                    downloaded += len(files)
        return media_map, downloaded, failed_posts
    #==========================متد ساخت گذارش=======================================
    async def _generate_download_report(self, items: List[Dict], media_map: Dict, failed_posts: List[Dict]):
        """تولید گزارش نهایی دانلودها با کپشن پست‌ها (به‌روزرسانی هوشمند)"""
        report_path = self.base_dir / "download_report.txt"
        
        # ─── خواندن گزارش قبلی (اگر وجود داشته باشد) ──────────────
        previous_successful = set()
        previous_failed = {}
        
        if report_path.exists():
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # استخراج موفق‌های قبلی
                in_success = False
                for line in content.split('\n'):
                    if "✅ پست‌های دانلود شده (موفق):" in line:
                        in_success = True
                        continue
                    if in_success and line.strip().startswith("❌"):
                        break
                    if in_success and line.strip().startswith("  "):
                        match = re.search(r'پست (\d+)', line)
                        if match:
                            previous_successful.add(match.group(1))
                
                # استخراج ناموفق‌های قبلی
                in_failed = False
                for line in content.split('\n'):
                    if "❌ پست‌های ناموفق (شکست خورده):" in line:
                        in_failed = True
                        continue
                    if in_failed and line.strip().startswith("⚠️"):
                        break
                    if in_failed and line.strip().startswith("  "):
                        match = re.search(r'پست (\d+)', line)
                        if match:
                            previous_failed[match.group(1)] = True
            except Exception as e:
                self.logger.warning(f"⚠️ خطا در خواندن گزارش قبلی: {e}")
                
        # ─── ساخت دیکشنری برای دسترسی سریع به کپشن هر پست ───
        post_text = {item['id']: item.get('text', '') for item in items}
        
        # ─── ادغام داده‌ها ──────────────────────────────────────────
        # موفق‌های جدید
        new_successful = set(media_map.keys())
        
        # ناموفق‌های جدید
        new_failed = {item['id']: item for item in failed_posts}
        
        # شروع با موفق‌های قبلی
        all_successful = set(previous_successful)
        all_failed = dict(previous_failed)  # فقط شناسه‌ها برای سرعت
        
        # اضافه کردن موفق‌های جدید
        for post_id in new_successful:
            all_successful.add(post_id)
            # اگر قبلاً ناموفق بود، از ناموفق‌ها حذفش کن
            if post_id in all_failed:
                del all_failed[post_id]
        
        # اضافه کردن ناموفق‌های جدید (فقط اگر در موفق‌ها نباشند)
        for post_id, item in new_failed.items():
            if post_id not in all_successful:
                all_failed[post_id] = item
        
        # ─── تولید گزارش نهایی ──────────────────────────────────────
        # ساخت لیست نهایی آیتم‌ها (برای تعداد کل)
        all_items = []
        for post_id in all_successful:
            # پیدا کردن کپشن از items جدید یا پیش‌فرض
            caption = post_text.get(post_id, '')
            all_items.append({'id': post_id, 'text': caption})
        for post_id in all_failed.keys():
            if post_id not in all_successful:
                caption = post_text.get(post_id, '')
                all_items.append({'id': post_id, 'text': caption})
        
        # مرتب‌سازی بر اساس شناسه
        all_items.sort(key=lambda x: int(x['id']))
        
        # ─── نوشتن گزارش ──────────────────────────────────────────────
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write(f"📊 گزارش نهایی دانلود - کانال: @{self.channel}\n")
            f.write(f"📅 تاریخ: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"📈 تعداد کل پست‌های بررسی‌شده: {len(all_items)}\n")
            f.write("=" * 60 + "\n\n")
            
            # ─── پست‌های موفق ──────────────────────────────────
            f.write("✅ پست‌های دانلود شده (موفق):\n")
            f.write("-" * 40 + "\n")
            if all_successful:
                for i, post_id in enumerate(sorted(all_successful, key=int), 1):
                    url = f"https://t.me/{self.channel}/{post_id}"
                    count = len(media_map.get(post_id, []))
                    # اگر پست در media_map نبود (از قبلی)، از previous_successful استفاده کن
                    if count == 0 and post_id in previous_successful:
                        count = 1  # یا هر عددی که برای نمایش مناسب است
                    caption = post_text.get(post_id, '')
                    caption_summary = caption[:50] + ('...' if len(caption) > 50 else '')
                    f.write(f"  {i}. پست {post_id} - {count} فایل - {url}\n")
                    if caption_summary:
                        f.write(f"      📝 کپشن: {caption_summary}\n")
            else:
                f.write("  (هیچ پستی دانلود نشد)\n")
            f.write("\n")
            
            # ─── پست‌های ناموفق ──────────────────────────────────
            f.write("❌ پست‌های ناموفق (شکست خورده):\n")
            f.write("-" * 40 + "\n")
            if all_failed:
                sorted_failed = sorted(all_failed.values(), key=lambda x: int(x['id']))
                for i, item in enumerate(sorted_failed, 1):
                    post_id = item['id']
                    reason = item.get('reason', 'نامشخص')
                    url = item.get('url', f"https://t.me/{self.channel}/{post_id}")
                    caption = post_text.get(post_id, '')
                    caption_summary = caption[:50] + ('...' if len(caption) > 50 else '')
                    f.write(f"  {i}. پست {post_id} - {reason} - {url}\n")
                    if caption_summary:
                        f.write(f"      📝 کپشن: {caption_summary}\n")
            else:
                f.write("  (هیچ پست ناموفقی وجود ندارد)\n")
            f.write("\n")
            # ─── پست‌های ریپلای شده ──────────────────────────────────
            if hasattr(self, '_reply_posts') and self._reply_posts:
                f.write("🔁 پست‌های ریپلای شده (نادیده گرفته شدند):\n")
                f.write("-" * 40 + "\n")
                for i, item in enumerate(self._reply_posts, 1):
                    url = item.get('url', f"https://t.me/{self.channel}/{item['id']}")
                    f.write(f"  {i}. پست {item['id']} - {url}\n")
                    if item.get('text'):
                        f.write(f"      📝 کپشن: {item['text'][:50]}...\n")
                f.write("\n")
            # ─── پست‌های ناموجود (حذف شده) ──────────────────────────────────
            if hasattr(self, '_missing_posts') and self._missing_posts:
                f.write("🚫 پست‌های ناموجود (حذف شده یا وجود ندارند):\n")
                f.write("-" * 40 + "\n")
                for i, item in enumerate(self._missing_posts, 1):
                    url = item.get('url', f"https://t.me/{self.channel}/{item['id']}")
                    f.write(f"  {i}. پست {item['id']} - {url}\n")
                f.write("\n")
            # ─── پست‌های پردازش نشده (اختیاری) ──────────────────
            # پیدا کردن پست‌هایی که در هیچ لیستی نیستند
            all_known = set(all_successful) | set(all_failed.keys())
            unprocessed = []
            for item in items:
                if item['id'] not in all_known:
                    unprocessed.append(item['id'])
            
            if unprocessed:
                f.write("⚠️ پست‌های پردازش نشده:\n")
                f.write("-" * 40 + "\n")
                for i, post_id in enumerate(sorted(unprocessed, key=int), 1):
                    url = f"https://t.me/{self.channel}/{post_id}"
                    caption = post_text.get(post_id, '')
                    caption_summary = caption[:50] + ('...' if len(caption) > 50 else '')
                    f.write(f"  {i}. پست {post_id} - {url}\n")
                    if caption_summary:
                        f.write(f"      📝 کپشن: {caption_summary}\n")
                f.write("\n")
            
            f.write("=" * 60 + "\n")
            f.write("🏁 پایان گزارش\n")
        
        self.logger.info(f"📄 گزارش نهایی در {report_path} ذخیره شد.")
    def _extract_failed_posts_from_report(self) -> List[str]:
        """استخراج شناسه پست‌های ناموفق از فایل گزارش"""
        report_path = self.base_dir / "download_report.txt"
        if not report_path.exists():
            self.logger.warning("⚠️ فایل گزارش یافت نشد!")
            return []
        
        failed_ids = []
        in_failed_section = False
        with open(report_path, 'r', encoding='utf-8') as f:
            for line in f:
                if "❌ پست‌های ناموفق (شکست خورده):" in line:
                    in_failed_section = True
                    continue
                if in_failed_section and line.startswith("  "):
                    match = re.search(r'پست (\d+)', line)
                    if match:
                        failed_ids.append(match.group(1))
                elif in_failed_section and line.startswith("="):
                    break
        return failed_ids

# ═══════════════════ آپلود و پاکسازی ═══════════════════
    async def _upload_and_cleanup(self) -> bool:
        """
        آپلود هوشمند پوشه media به مگا با جلوگیری از آپلود تکراری
        برمی‌گرداند: True اگر آپلود موفق بود یا چیزی برای آپلود نبود
        """
        import subprocess
        import shutil
        import json

        media_path = self.media_dir
        if not media_path.exists() or not any(media_path.iterdir()):
            return True

        # ─── جمع‌آوری فایل‌های جدید ──────────────────────────
        all_files = list(media_path.rglob('*'))
        total_files = len([f for f in all_files if f.is_file()])
        
        # اگر تعداد فایل‌ها زیاد است، از هش استفاده نکن (برای سرعت)
        use_hash = total_files < 50  # آستانه: کمتر از ۵۰ فایل

        new_files = []
        for f in all_files:
            if f.is_file():
                identifier = get_file_identifier(f, use_hash=use_hash)
                new_files.append({
                    'name': f.name,
                    'path': str(f.relative_to(media_path)),
                    'size': identifier['size'],
                    'mtime': identifier['mtime'],
                    'hash': identifier.get('hash'),
                    'method': identifier['method'],
                    'composite_id': identifier.get('composite_id', f"{identifier['size']}_{int(identifier['mtime'])}")
                })

        if not new_files:
            return True

        # ─── بارگذاری لیست فایل‌های آپلود شده قبلی ─────────────
        state_file = self.base_dir / "uploaded_files.json"
        uploaded_ids = set()
        uploaded_hashes = set()
        
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    uploaded_data = json.load(f)
                    for item in uploaded_data:
                        if item.get('method') == 'hash' and item.get('hash'):
                            uploaded_hashes.add(item['hash'])
                        else:
                            uploaded_ids.add(item.get('composite_id', f"{item['size']}_{int(item['mtime'])}"))
            except Exception as e:
                self.logger.warning(f"⚠️ خطا در خواندن لیست آپلود: {e}")

        # ─── فیلتر کردن فایل‌های جدید ──────────────────────────
        files_to_upload = []
        for f in new_files:
            is_uploaded = False
            if f['method'] == 'hash' and f['hash']:
                if f['hash'] in uploaded_hashes:
                    is_uploaded = True
            else:
                if f['composite_id'] in uploaded_ids:
                    is_uploaded = True
            
            if not is_uploaded:
                files_to_upload.append(f)

        if not files_to_upload:
            self.logger.info("✅ همه فایل‌ها قبلاً آپلود شده‌اند (بر اساس شناسه).")
            # پوشه محلی رو پاک کن چون همه فایل‌ها آپلود شدن
            shutil.rmtree(media_path)
            media_path.mkdir(parents=True, exist_ok=True)
            return True

        # ─── آپلود فقط فایل‌های جدید ────────────────────────────
        self.logger.info(f"☁️ شروع آپلود {len(files_to_upload)} فایل جدید به مگا...")
        self.logger.info(f"   📊 روش شناسایی: {'هش (MD5)' if use_hash else 'حجم + تاریخ'}")

        try:
            channel = self.channel
            mega_folder = getattr(self.config, 'mega_folder', 'TelegramArchive')

            cmd = [
                "rclone", "copy",
                str(media_path),
                f"mega:{mega_folder}/{channel}/media",
                "--progress",
                "--transfers", "4",
                "--ignore-existing",  # برای امنیت بیشتر
                "-vv"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode == 0:
                self.logger.info(f"✅ آپلود {len(files_to_upload)} فایل جدید با موفقیت انجام شد")

                # ─── به‌روزرسانی لیست فایل‌های آپلود شده ──────────
                if state_file.exists():
                    with open(state_file, 'r') as f:
                        existing = json.load(f)
                else:
                    existing = []
                
                # اضافه کردن فایل‌های جدید
                existing.extend(files_to_upload)
                
                # حذف تکراری‌ها بر اساس composite_id یا hash
                seen = set()
                unique_files = []
                for item in existing:
                    key = item.get('hash') if item.get('method') == 'hash' else item.get('composite_id')
                    if key and key not in seen:
                        seen.add(key)
                        unique_files.append(item)
                
                with open(state_file, 'w') as f:
                    json.dump(unique_files, f, indent=2)
                
                self.logger.info(f"📝 لیست آپلود شده‌ها به‌روزرسانی شد (مجموع: {len(unique_files)} فایل).")

                # پاکسازی فایل‌های محلی
                shutil.rmtree(media_path)
                media_path.mkdir(parents=True, exist_ok=True)
                self.logger.info("🧹 فایل‌های محلی پاکسازی شدند")
                return True
            else:
                self.logger.error(f"❌ خطا در آپلود: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"❌ خطا در آپلود: {e}")
            return False
