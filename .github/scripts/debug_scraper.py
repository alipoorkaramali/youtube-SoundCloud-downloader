#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسکریپت دیباگ برای Telegram Channel Scraper
– تمام مراحل اسکرپینگ (جستجو، ورود، اسکرول، استخراج) را انجام می‌دهد.
– رسانه‌ها را دانلود نمی‌کند، اما اسکرین‌شات‌های راست‌کلیک و ضربدرها را می‌گیرد.
– از همان تنظیمات config.yaml استفاده می‌کند (پشتیبانی از start_link).
– اسکرین‌شات‌های بیشتری برای تحلیل مراحل ذخیره می‌کند.
– خروجی JSON را برای بررسی داده‌های استخراج‌شده ذخیره می‌کند.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import List, Dict

# اضافه کردن مسیر پروژه به sys.path برای import ماژول‌ها
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import load_config
from scraper import TelegramChannelScraper
from output_generator import OutputGenerator
from playwright_downloader import PlaywrightDownloader


class DebugTelegramChannelScraper(TelegramChannelScraper):
    """
    نسخه‌ی دیباگ اسکرپر – تمام مراحل اسکرپینگ را انجام می‌دهد اما رسانه‌ها را دانلود نمی‌کند.
    با این حال، فرایند راست‌کلیک و اسکرین‌شات‌های ضربدر را شبیه‌سازی می‌کند.
    """

    def __init__(self, config, debug_screenshots: bool = True):
        super().__init__(config)
        self.debug_screenshots = debug_screenshots
        self.debug_screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.debug_mode = True
        self.logger.info("🐞 حالت دیباگ فعال است – دانلود رسانه انجام نمی‌شود.")
        self.logger.info(f"🐞 پوشه اسکرین‌شات‌های دیباگ: {self.debug_screenshots_dir}")

    async def _download_media(self, items: List[Dict], page, context) -> tuple[dict, int]:
        """
        در حالت دیباگ، دانلود واقعی انجام نمی‌شود، اما یک Downloader خشک (dry_run)
        اجرا می‌شود تا اسکرین‌شات‌های راست‌کلیک و ضربدرها در پوشهٔ debug_screenshots ذخیره شوند.
        """
        self.logger.info("🐞 حالت دیباگ: شبیه‌سازی دانلود با dry_run (فقط اسکرین‌شات‌های ضربدر)")
        post_ids = [str(item['id']) for item in items]
        media_map = {}

        if post_ids:
            downloader = PlaywrightDownloader(
                self.profile_dir,
                self.media_dir,
                self.max_media_bytes,
                self.delay_between_posts,
                debug_screenshots_dir=self.debug_screenshots_dir,
                quiet_base=self.config.download_quiet_seconds,
                dry_run=True   # ← فعال‌سازی حالت خشک
            )
            await downloader.download_all(page, context, post_ids, media_map)

        # چون dry_run است، media_map خالی خواهد ماند
        return media_map, 0

    async def _save_debug_screenshot(self, page, name: str):
        if not self.debug_screenshots:
            return
        try:
            self.debug_screenshots_dir.mkdir(parents=True, exist_ok=True)
            path = self.debug_screenshots_dir / f"{name}.png"
            await page.screenshot(path=path, full_page=True)
            self.logger.debug(f"🐞 اسکرین‌شات دیباگ ذخیره شد: {path.name}")
        except Exception as e:
            self.logger.warning(f"⚠️ خطا در ذخیره اسکرین‌شات دیباگ: {e}")

    async def _fetch_posts_from_telegram(self) -> tuple[List[Dict], any, any]:
        """
        همان متد اصلی اما با اسکرین‌شات‌های بیشتر برای دیباگ.
        """
        self.logger.info("🐞 شروع مرحله‌ی استخراج پست‌ها (حالت دیباگ با اسکرین‌شات‌های بیشتر)...")

        page = None
        context = None
        try:
            result = await super()._fetch_posts_from_telegram()
            items, context, page = result

            if page and items:
                await self._save_debug_screenshot(page, "final_debug")
                self.logger.info(f"🐞 {len(items)} پست در حالت دیباگ استخراج شد.")
            elif page and not items:
                self.logger.warning("🐞 هیچ پستی استخراج نشد. بررسی اسکرین‌شات‌ها...")
                await self._save_debug_screenshot(page, "no_posts_debug")

            if page:
                await self._save_debug_screenshot(page, "final_page_state")

            return result
        except Exception as e:
            self.logger.error(f"❌ خطا در استخراج دیباگ: {e}")
            if page:
                await self._save_debug_screenshot(page, "error_debug")
            return [], context, page

    async def run(self):
        """
        اجرای اصلی با ذخیره‌ی خروجی JSON اضافی برای دیباگ.
        """
        await super().run()

        # پس از اتمام، یک فایل JSON دیباگ با خلاصه اطلاعات ذخیره می‌کنیم
        try:
            debug_json_path = self.base_dir / "debug_summary.json"
            summary = {
                "channel": self.channel,
                "limit": self.limit,
                "start_link": self.start_link,
                "total_posts": len(self._last_items) if hasattr(self, '_last_items') else 0,
                "debug_mode": True
            }
            with open(debug_json_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            self.logger.info(f"🐞 خلاصه دیباگ ذخیره شد: {debug_json_path}")
        except Exception as e:
            self.logger.warning(f"⚠️ خطا در ذخیره خلاصه دیباگ: {e}")

    async def _run_impl(self):
        """
        Override برای ذخیره‌ی آیتم‌ها در متغیر کلاس و ارسال debug_mode به OutputGenerator
        """
        if self.start_link:
            self.logger.info(f"🚀 شروع اسکریپر دیباگ با لینک: {self.start_link} (limit={self.limit})")
        else:
            self.logger.info(f"🚀 شروع اسکریپر دیباگ برای @{self.channel} (limit={self.limit})")

        items, context, page = await self._fetch_posts_from_telegram()
        self._last_items = items

        if not items:
            self.logger.warning("هیچ پستی دریافت نشد.")
            if context:
                await context.close()
            return

        self.logger.info(f"📥 {len(items)} پست استخراج شد (حالت دیباگ).")

        # حالا دانلود dry_run را اجرا کن (اسکرین‌شات‌ها گرفته می‌شوند)
        media_map, downloaded = await self._download_media(items, page, context)
        self.logger.info(f"🐞 {downloaded} فایل (dry_run) – اسکرین‌شات‌های ضربدر گرفته شد.")

        gen = OutputGenerator(
            self.base_dir,
            self.channel,
            items,
            media_map,
            debug_mode=self.debug_mode
        )
        gen.generate_json()
        gen.generate_csv()
        gen.generate_html()
        gen.create_zip()

        if context:
            await context.close()

        self.logger.info("✅ پایان موفقیت‌آمیز دیباگ.")


async def main():
    print("🐞 ========================================")
    print("🐞 Telegram Channel Scraper - حالت دیباگ")
    print("🐞 ========================================")

    config_path = "config/config.yaml"
    try:
        config = load_config(config_path)
        print(f"✅ تنظیمات از {config_path} بارگذاری شد.")
        print(f"   کانال: {config.channel}")
        print(f"   limit: {config.limit}")
        if config.start_link:
            print(f"   start_link: {config.start_link}")
    except FileNotFoundError:
        print(f"❌ فایل {config_path} یافت نشد.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ خطا در بارگذاری کانفیگ: {e}")
        sys.exit(1)

    scraper = DebugTelegramChannelScraper(config, debug_screenshots=True)

    try:
        await scraper.run()
        print("\n🐞 دیباگ با موفقیت کامل شد.")
        print(f"🐞 خروجی‌ها در پوشه: {scraper.base_dir}")
        print(f"🐞 اسکرین‌شات‌های دیباگ در: {scraper.debug_screenshots_dir}")
        print(f"🐞 اسکرین‌شات‌های پست‌ها در: {scraper.screenshots_dir}")
    except Exception as e:
        print(f"\n❌ خطا در اجرای دیباگ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
