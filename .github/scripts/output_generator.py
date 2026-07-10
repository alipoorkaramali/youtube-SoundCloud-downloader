#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import csv
import os
import re
import zipfile
import subprocess
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

# تلاش برای وارد کردن BeautifulSoup برای خواندن فایل‌های HTML
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
    print("⚠️ BeautifulSoup نصب نیست. برای حالت append_mode لطفاً نصب کنید: pip install beautifulsoup4")


class OutputGenerator:
    """
    تولید فایل‌های خروجی JSON، CSV، HTML و ZIP با پشتیبانی از append_mode.
    """

    def __init__(
        self,
        base_dir: Path,
        channel: str,
        posts: list,
        media_map: dict,
        debug_mode: bool = False,
        append_mode: bool = False
    ):
        self.base_dir = base_dir
        self.channel = channel
        self.posts = posts
        self.media_map = media_map
        self.debug_mode = debug_mode
        self.append_mode = append_mode
        self.logger = logging.getLogger("TelegramScraper")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._safe_name = self._sanitize_filename(self.channel)
        self._initial_post_count = len(self.posts)

    # ═══════════════════════════════════════════════════════════════════
    # متدهای کمکی
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

    def _validate_post_structure(self, post: Dict) -> bool:
        if not isinstance(post, dict):
            return False
        if 'id' not in post or not post['id']:
            return False
        return True

    def _extract_posts_from_html(self, html_path: Path) -> List[Dict]:
        if BeautifulSoup is None:
            self.logger.warning("⚠️ BeautifulSoup نصب نیست، نمی‌توان HTML را خواند.")
            return []
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
            existing_posts = []
            post_divs = soup.find_all('div', class_='post')
            for div in post_divs:
                msg_id = div.get('data-msg-id')
                if msg_id:
                    text_div = div.find('div', class_='text')
                    date_div = div.find('div', class_='date')
                    post_data = {
                        'id': str(msg_id).strip(),
                        'text': text_div.get_text(strip=True) if text_div else '',
                        'date': date_div.get_text(strip=True) if date_div else ''
                    }
                    if self._validate_post_structure(post_data):
                        existing_posts.append(post_data)
            return existing_posts
        except Exception as e:
            self.logger.warning(f"⚠️ خطا در خواندن HTML: {e}")
            return []

    def _merge_with_existing_posts(self) -> list:
        if not self.append_mode:
            return self.posts

        self.logger.info("🔄 شروع فرآیند ادغام با داده‌های قبلی...")
        json_path = self.base_dir / f"{self._safe_name}_posts.json"
        html_path = self.base_dir / f"{self._safe_name}_posts.html"
        existing_posts = []

        # تلاش از JSON
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                if isinstance(raw_data, list):
                    for post in raw_data:
                        if self._validate_post_structure(post):
                            existing_posts.append(post)
                self.logger.info(f"📄 {len(existing_posts)} پست از JSON قبلی بارگذاری شد.")
            except Exception as e:
                self.logger.warning(f"⚠️ خطا در خواندن JSON: {e}")
                existing_posts = []

        # اگر JSON موفق نبود، از HTML
        if not existing_posts and html_path.exists():
            self.logger.info("📄 تلاش برای خواندن از HTML...")
            existing_posts = self._extract_posts_from_html(html_path)
            if existing_posts:
                self.logger.info(f"📄 {len(existing_posts)} پست از HTML استخراج شد.")

        if not existing_posts:
            self.logger.info("ℹ️ هیچ پست قبلی یافت نشد.")
            return self.posts

        # ترکیب و حذف تکراری‌ها
        all_posts = existing_posts + self.posts
        seen_ids = set()
        unique_posts = []
        for post in all_posts:
            pid = post.get('id')
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                unique_posts.append(post)

        # مرتب‌سازی نزولی
        try:
            unique_posts.sort(key=lambda x: int(x.get('id', 0)), reverse=True)
        except:
            unique_posts.sort(key=lambda x: str(x.get('id', '0')), reverse=True)

        self.logger.info(f"🔄 ادغام: {len(existing_posts)} قبلی + {len(self.posts)} جدید = {len(unique_posts)} کل")
        return unique_posts

    # ═══════════════════════════════════════════════════════════════════
    # تولید فایل‌ها
    # ═══════════════════════════════════════════════════════════════════

    def generate_json(self):
        json_path = self.base_dir / f"{self._safe_name}_posts.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self.posts, f, indent=2, ensure_ascii=False)
        self.logger.info(f"📄 JSON: {json_path} ({len(self.posts)} پست)")

    def generate_csv(self):
        csv_path = self.base_dir / f"{self._safe_name}_posts.csv"
        if not self.posts:
            return
        fieldnames = ['id', 'date', 'text', 'url', 'views', 'forwards', 'replies']
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for post in self.posts:
                row = {field: post.get(field, '') for field in fieldnames}
                writer.writerow(row)
        self.logger.info(f"📊 CSV: {csv_path} ({len(self.posts)} پست)")

    def generate_html(self):
        if self.append_mode:
            self.logger.info("🔄 append_mode فعال است. تلاش برای ادغام با داده‌های قبلی...")
            merged_posts = self._merge_with_existing_posts()
            if len(merged_posts) != len(self.posts):
                self.logger.info(f"📊 تعداد پست‌ها پس از ادغام: {len(merged_posts)} (قبلاً {len(self.posts)})")
                self.posts = merged_posts
            else:
                self.logger.info(f"📊 تعداد پست‌ها بدون تغییر باقی ماند: {len(self.posts)}")
        else:
            self.logger.info("ℹ️ append_mode غیرفعال است. فایل HTML از نو ساخته می‌شود.")

        html_path = self.base_dir / f"{self._safe_name}_posts.html"
        current_iran = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=30)).strftime('%Y/%m/%d - %H:%M')
        try:
            html = self._build_html_content(current_iran)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            self.logger.info(f"🌐 HTML: {html_path} ({len(self.posts)} پست)")
        except FileNotFoundError as e:
            self.logger.warning(f"⚠️ تولید HTML انجام نشد: {e}")
        except Exception as e:
            self.logger.error(f"❌ خطا در تولید HTML: {e}")

    def _build_html_content(self, current_iran: str) -> str:
        script_dir = Path(__file__).resolve().parent
        template_dirs = [
            script_dir / "templates",
            script_dir.parent / "templates",
            Path.cwd() / "templates",
            Path.cwd() / ".github" / "templates",
        ]
        for template_dir in template_dirs:
            template_file = template_dir / "post_template.html"
            if template_file.exists():
                env = Environment(
                    loader=FileSystemLoader(template_dir),
                    autoescape=select_autoescape(['html', 'xml'])
                )
                def hashtagify(text):
                    return Markup(re.sub(r'(#\w+)', r'<span class="hashtag">\1</span>', str(text)))
                env.filters['hashtagify'] = hashtagify
                template = env.get_template('post_template.html')
                return template.render(
                    channel=self.channel,
                    posts=self.posts,
                    media_map=self.media_map,
                    current_time=current_iran
                )
        raise FileNotFoundError(
            "❌ پوشه templates پیدا نشد. لطفاً فایل post_template.html را در یکی از مسیرهای زیر قرار دهید:\n" +
            "\n".join(f"  - {d}" for d in template_dirs)
        )

    def create_zip(self):
        zip_name = f"{self._safe_name}_archive.zip"
        zip_path = self.base_dir / zip_name

        # حذف ZIPهای قبلی
        for f in os.listdir(self.base_dir):
            if f.startswith(f"{self._safe_name}_archive") and (f.endswith('.zip') or '.z' in f):
                (self.base_dir / f).unlink(missing_ok=True)

        temp_zip = self.base_dir / "temp_archive.zip"
        with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(self.base_dir):
                for file in files:
                    if file.startswith("temp_archive") or file.startswith(f"{self._safe_name}_archive"):
                        continue
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, self.base_dir)

                    # ── حذف اسکرین‌شات‌ها در حالت غیر دیباگ ──
                    if not self.debug_mode:
                        if arcname.startswith("post_screenshots/") or arcname.startswith("debug_screenshots/"):
                            self.logger.debug(f"⏭️ حذف اسکرین‌شات از ZIP: {arcname}")
                            continue

                    zipf.write(file_path, arcname)

        size_mb = os.path.getsize(temp_zip) / (1024 * 1024)
        self.logger.info(f"📦 حجم فایل ZIP: {size_mb:.1f} MB")
        MAX_SPLIT_MB = 30

        if size_mb > MAX_SPLIT_MB:
            self.logger.info(f"📦 تقسیم فایل ZIP به قطعات {MAX_SPLIT_MB} مگابایتی...")
            try:
                subprocess.run(["zip", "--version"], check=True, capture_output=True)
                cmd = ["zip", "-s", f"{MAX_SPLIT_MB}m", str(temp_zip), "--out", str(zip_path)]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                os.remove(temp_zip)
                parts = sorted([f for f in os.listdir(self.base_dir) if f.startswith(f"{self._safe_name}_archive")])
                self.logger.info(f"✅ فایل ZIP به {len(parts)} قطعه تقسیم شد:")
                for p in parts:
                    part_size = os.path.getsize(self.base_dir / p) / (1024 * 1024)
                    self.logger.info(f"   - {p} ({part_size:.1f} MB)")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"❌ خطا در تقسیم ZIP: {e.stderr}")
                os.rename(temp_zip, zip_path)
                self.logger.warning(f"⚠️ تقسیم ناموفق – فایل کامل ZIP ذخیره شد: {zip_name}")
            except FileNotFoundError:
                self.logger.error("❌ دستور 'zip' پیدا نشد. لطفاً zip را نصب کنید (apt install zip).")
                os.rename(temp_zip, zip_path)
                self.logger.warning(f"⚠️ فایل کامل ZIP (بدون تقسیم) ذخیره شد: {zip_name}")
        else:
            os.rename(temp_zip, zip_path)
            self.logger.info(f"ℹ️ حجم ZIP کمتر از {MAX_SPLIT_MB}MB است – تقسیم نیاز نیست")
            self.logger.info(f"✅ فایل ZIP آماده شد: {zip_name}")

    def run_all(self):
        self.logger.info("🚀 شروع تولید فایل‌های خروجی...")
        self.logger.info(f"📊 تعداد پست‌های ورودی: {self._initial_post_count}")
        self.logger.info(f"📌 append_mode: {self.append_mode}")

        try:
            # ─── ادغام اولیه اگر append_mode فعال باشد ───
            if self.append_mode:
                merged_posts = self._merge_with_existing_posts()
                if len(merged_posts) != len(self.posts):
                    self.logger.info(f"📊 تعداد پست‌ها پس از ادغام: {len(merged_posts)} (قبلاً {len(self.posts)})")
                    self.posts = merged_posts
                else:
                    self.logger.info(f"📊 تعداد پست‌ها بدون تغییر باقی ماند: {len(self.posts)}")
            else:
                self.logger.info("ℹ️ append_mode غیرفعال است. بدون ادغام ادامه می‌یابد.")

            # ─── تولید JSON ───
            self.generate_json()

            # ─── تولید CSV ───
            self.generate_csv()

            # ─── تولید HTML (با غیرفعال کردن موقت append_mode) ───
            original_append_mode = self.append_mode
            if original_append_mode:
                self.append_mode = False
            self.generate_html()
            self.append_mode = original_append_mode

            # ─── تولید ZIP ───
            self.create_zip()

            self.logger.info("✅ تمام فایل‌های خروجی با موفقیت تولید شدند.")
            final_count = len(self.posts)
            if original_append_mode and final_count != self._initial_post_count:
                self.logger.info(f"📊 خلاصه نهایی: {self._initial_post_count} پست ورودی → {final_count} پست خروجی (افزایش {final_count - self._initial_post_count} پست از ادغام)")
            else:
                self.logger.info(f"📊 تعداد نهایی پست‌ها: {final_count}")

        except Exception as e:
            self.logger.error(f"❌ خطا در تولید خروجی: {e}")
            raise
