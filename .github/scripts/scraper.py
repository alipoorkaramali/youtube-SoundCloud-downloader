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
        # ─── بارگذاری وضعیت قبلی (اگر resume فعال باشد) ───
        if getattr(self.config, 'resume', False):
            state = self._load_resume_state()
            if state:
                last_post_id = state.get('last_post_id')
                downloaded_posts = state.get('downloaded_posts', [])
                if last_post_id:
                    try:
                        last_id_int = int(last_post_id)
                        if self.scroll_direction == 'up':
                            next_id = last_id_int - 1  # پست قدیمی‌تر
                        else:
                            next_id = last_id_int + 1  # پست جدیدتر
                        if next_id <= 0:
                            self.logger.warning("⚠️ شناسه محاسبه‌شده منفی است، از ابتدا شروع می‌شود.")
                            self.start_link = None
                            self.target_msg_id = None
                        else:
                            self.start_link = f"https://t.me/{self.channel}/{next_id}"
                            self.target_msg_id = str(next_id)
                            self.logger.info(f"🔄 ادامه از پست بعد از {last_post_id} → شناسه {next_id}")
                    except ValueError:
                        self.logger.warning(f"⚠️ شناسه نامعتبر در resume_state: {last_post_id}. شروع از ابتدا.")
                        self.start_link = None
                        self.target_msg_id = None
                else:
                    self.logger.info("ℹ️ resume_state خالی است، از ابتدا شروع می‌شود.")
            else:
                self.logger.info("ℹ️ resume فعال است اما وضعیتی وجود ندارد، از ابتدا شروع می‌شود.")
        else:
            self.logger.info("ℹ️ resume غیرفعال است، از ابتدا شروع می‌شود.")
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
            
            # ─── تولید گزارش نهایی retry ──────────────────────
            await self._generate_download_report(retry_items, retry_media_map, retry_failed_posts)
            if context:
                await context.close()
            self.logger.info("🏁 تلاش مجدد تمام شد.")
            return  # خروج از تابع (اجرای عادی ادامه پیدا نمی‌کند)
        # ─── متغیرهای کلی ─────────────────────────────
        max_retries = 3
        retry_count = 0
        items = []
        media_map = {}
        all_failed_posts = []
        context = None
        page = None

        while len(items) < self.limit and retry_count <= max_retries:
            if retry_count > 0:
                # تلاش مجدد با حدس شناسه
                if items:
                    last_id_str = items[-1]['id']
                    if last_id_str.isdigit():
                        last_id = int(last_id_str)
                        step = -1 if self.scroll_direction == 'up' else 1
                        guess_id = last_id + step
                        if guess_id <= 0:
                            break
                        self.logger.info(f"🔄 تلاش مجدد {retry_count}: حدس شناسه {guess_id}")
                        self.start_link = f"https://t.me/{self.channel}/{guess_id}"
                        self.target_msg_id = str(guess_id)
                    else:
                        self.logger.warning(f"⚠️ شناسه غیرعددی ({last_id_str})، از retry صرف‌نظر می‌شود.")
                        break

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

            self.logger.info(f"📥 {len(newly_added)} پست جدید جمع‌آوری شد (مجموع: {len(items)}/{self.limit})")

            # اگر هیچ پست جدیدی اضافه نشد، یعنی کار تمام است
            if not newly_added:
                self.logger.info("✅ پست جدیدی یافت نشد. احتمالاً به انتهای کانال رسیده‌ایم. اسکریپت متوقف می‌شود.")
                break

            # 🔥 دانلود فوری رسانه‌های پست‌های جدید
            self.logger.info(f"⬇️ شروع دانلود رسانه برای {len(newly_added)} پست جدید...")
            try:
                batch_media_map, downloaded_batch, batch_failed = await self._download_media(
                    newly_added, page, context
                )
                all_failed_posts.extend(batch_failed)
                media_map.update(batch_media_map)
                self.logger.info(f"✅ {downloaded_batch} فایل رسانه در این دور دانلود شد.")
                if downloaded_batch > 0:
                    self.last_download_success = True
                await human_sleep(3.0, 1.0)
            except Exception as e:
                self.logger.error(f"❌ خطا در دانلود این batch: {e}")

            # ─── چک کردن حجم و آپلود در صورت نیاز ──────────────────
            total_size = sum(f.stat().st_size for f in self.media_dir.rglob('*') if f.is_file())
            size_mb = total_size / (1024 * 1024)
            if size_mb > 1024:  # ۱ گیگابایت
                self.logger.info(f"📦 حجم پوشه media به {size_mb:.1f} MB رسید. شروع آپلود...")
                uploaded = await self._upload_and_cleanup()
                if uploaded:
                    # به‌روزرسانی resume_state برای ادامه از این نقطه
                    self._save_resume_state(str(newly_added[-1]['id']), items)
                else:
                    self.logger.warning("⚠️ آپلود ناموفق بود، ادامه با فایل‌های محلی...")

            # به‌روزرسانی start_link با آخرین پست جدید
            last_item = newly_added[-1]
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
        if not items:
            self.logger.warning("هیچ پستی دریافت نشد.")
            if context:
                await context.close()
            return

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
            
            # اگر direction 'up' است، ابتدا به پایین صفحه برو تا جدیدترین‌ها لود شوند
            if self.scroll_direction == 'up' and not self.start_link:
                self.logger.info("⬇️ پرش به پایین صفحه برای بارگذاری جدیدترین پست‌ها...")
                await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                await asyncio.sleep(3)  # افزایش تأخیر
                self.logger.info("✅ به پایین صفحه رفتیم.")
                
                # ─── منتظر بارگذاری پیام‌های جدید ──────────────────
                self.logger.info("⏳ منتظر بارگذاری پیام‌های جدید در پایین صفحه...")
                try:
                    await page.wait_for_function(
                        """() => {
                            const messages = document.querySelectorAll('div[data-message-id]');
                            if (messages.length === 0) return false;
                            // بررسی کنید که حداقل یک پیام در نیمه پایینی صفحه باشد
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
                
                self._manual_scroll_done = True  # ← تنظیم flag
            
            await asyncio.sleep(3)  # افزایش تأخیر برای رندر کامل (مشابه دیباگ)
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

        # ═══════════════ پرش به ابتدا یا انتهای صفحه بر اساس جهت اسکرول ═══════════════
        if not self.start_link and not self._manual_scroll_done:
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
        elif self._manual_scroll_done:
            self.logger.info("ℹ️ پرش دستی انجام شده، از جستجوی دکمه صرف‌نظر می‌شود.")
        else:
            self.logger.info("ℹ️ در حالت start_link، پرش به پایین/بالا انجام نمی‌شود.")

        # ─── جمع‌آوری پست‌ها ────────────────────────────────────────────────
        items = []
        seen_ids = set()
        scroll_attempts = 0
        # ─── ذخیره موقعیت اولیه برای برگشت ──────────────────────
        original_scroll_y_fetch = await page.evaluate("window.scrollY")
        scroll_stack_fetch = []  # برای ثبت اسکرول‌های اضافی

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

        # استفاده از limit پاس شده (اگر وجود داشته باشد)
        effective_limit = limit if limit is not None else self.limit
        while len(items) < effective_limit and scroll_attempts < MAX_SCROLL_ATTEMPTS:
            try:
                messages = await page.locator('div[data-message-id]').all()
                
                # ─── اگر پیامی وجود ندارد، یک بار با تأخیر بیشتر تلاش کن ───
                if not messages and scroll_attempts == 0:
                    self.logger.info("⏳ پیامی یافت نشد، ۲ ثانیه صبر می‌کنم و دوباره تلاش می‌کنم...")
                    await asyncio.sleep(2)
                    messages = await page.locator('div[data-message-id]').all()
                    if messages:
                        self.logger.info(f"✅ {len(messages)} پیام پس از تأخیر پیدا شد.")
                
                # ─── اگر باز هم خالی بود، یک اسکرول کوچک انجام بده ───
                if not messages and scroll_attempts == 0:
                    self.logger.info("🔄 هنوز پیامی نیست، یک اسکرول کوچک به پایین...")
                    await page.evaluate("window.scrollBy(0, 300)")
                    await asyncio.sleep(1)
                    messages = await page.locator('div[data-message-id]').all()
                    if messages:
                        self.logger.info(f"✅ {len(messages)} پیام پس از اسکرول پیدا شد.")
                
                # ─── اگر باز هم خالی بود، از wait_for_selector استفاده کن ───
                if not messages and scroll_attempts == 0:
                    try:
                        self.logger.info("⏳ منتظر ظاهر شدن پیام‌ها با wait_for_selector...")
                        await page.wait_for_selector('div[data-message-id]', timeout=3000)
                        messages = await page.locator('div[data-message-id]').all()
                        if messages:
                            self.logger.info(f"✅ {len(messages)} پیام پس از wait_for_selector پیدا شد.")
                    except Exception:
                        self.logger.warning("⚠️ حتی با wait_for_selector پیامی پیدا نشد.")

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
                        if msg_id:
                            try:
                                # پاک‌سازی قوی شناسه
                                msg_id = str(int(float(msg_id)))
                            except:
                                pass
                        if not msg_id or msg_id in seen_ids:
                            continue
                        # ─── فیلتر بر اساس target_ids ──────────────────
                        if target_ids and msg_id not in target_ids:
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

                        if len(items) >= effective_limit:
                            break
                    except Exception as e:
                        self.logger.debug(f"خطا در پردازش پیام: {e}")
                        continue
            except Exception as e:
                self.logger.error(f"❌ خطا در استخراج پست‌ها: {e}")

            if len(items) >= effective_limit:
                break

            # ─── اسکرول هوشمند با جهت ──────────────────────────────────
            old_height = await page.evaluate("document.documentElement.scrollHeight")
            scrolled = await self._smart_scroll(page, self.scroll_direction, step=SCROLL_STEP_BASE, max_attempts=3)
            new_height = await page.evaluate("document.documentElement.scrollHeight")

            if new_height == old_height:
                # بررسی آیا به انتهای صفحه رسیده‌ایم
                at_top = await page.evaluate("window.scrollY <= 100")
                at_bottom = await page.evaluate("window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 100")
                if (self.scroll_direction == 'up' and at_top) or (self.scroll_direction == 'down' and at_bottom):
                    self.logger.info("📌 به انتهای صفحه رسیدیم. اسکرول متوقف می‌شود.")
                    break
                scroll_attempts += 1
            else:
                scroll_attempts = 0

            # ─── در حالت start_link، اگر هنوز به نقطه شروع نرسیده‌ایم ───
            if self.start_link and not start_collecting:
                self.logger.info("🔄 هنوز به پیام هدف نرسیدیم، اسکرول اضافی...")
                extra_amount = -SCROLL_STEP_BASE * 2 if self.scroll_direction == 'up' else SCROLL_STEP_BASE * 2
                scroll_stack_fetch.append(extra_amount)   # ← ثبت اسکرول
                await page.evaluate(f"window.scrollBy(0, {extra_amount})")
                await human_sleep(1.5, 0.3)
        # ─── برگشت به نقطه‌ی اولیه ──────────────────────────────
        for amount in reversed(scroll_stack_fetch):
            await page.evaluate(f"window.scrollBy(0, {-amount})")
            await human_sleep(0.3, 0.1)
        current_y = await page.evaluate("window.scrollY")
        if abs(current_y - original_scroll_y_fetch) > 30:
            await page.evaluate(f"window.scrollTo(0, {original_scroll_y_fetch})")
            self.logger.info(f"   ↩️ برگشت به موقعیت اولیه (fetch): {original_scroll_y_fetch}px")
        items = items[:effective_limit]
        self.logger.info(f"📊 {len(items)} پست جمع‌آوری شد.")

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
