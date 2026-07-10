#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسکریپت دیباگ برای Telegram Channel Scraper – هماهنگ با نسخه اصلی
– تمام مراحل اسکرپینگ (جستجو، ورود، اسکرول، استخراج) را انجام می‌دهد.
– از همان تنظیمات config.yaml استفاده می‌کند (پشتیبانی از start_link و scroll_direction).
– رسانه‌ها را دانلود نمی‌کند (فقط لاگ).
– اسکرین‌شات‌های بیشتری برای تحلیل مراحل ذخیره می‌کند.
– خروجی JSON را برای بررسی داده‌های استخراج‌شده ذخیره می‌کند.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import load_config
from scraper import TelegramChannelScraper
from output_generator import OutputGenerator


class DebugTelegramChannelScraper(TelegramChannelScraper):
    """
    نسخهٔ دیباگ اسکرپر – با اسکرین‌شات‌های بیشتر و غیرفعال‌سازی دانلود.
    """

    def __init__(self, config, debug_screenshots: bool = True):
        # فعال‌سازی حالت دیباگ در config قبل از فراخوانی والد
        config.debug_mode = True
        super().__init__(config)
        self.debug_screenshots = debug_screenshots
        self.debug_screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info("🐞 حالت دیباگ فعال است – دانلود رسانه انجام نمی‌شود.")
        self.logger.info(f"🐞 پوشه اسکرین‌شات‌های دیباگ: {self.debug_screenshots_dir}")
        # لاگ جهت اسکرول (والد قبلاً لاگ کرده، اما برای اطمینان مجدد)
        self.logger.info(f"🧭 جهت اسکرول: {'بالا (قدیمی‌تر)' if self.scroll_direction == 'up' else 'پایین (جدیدتر)'}")

    async def _download_media(self, items: List[Dict], page, context) -> tuple[dict, int]:
        """در حالت دیباگ دانلود رسانه غیرفعال است."""
        self.logger.info("🐞 حالت دیباگ: دانلود رسانه غیرفعال است.")
        media_map = {}
        for item in items:
            msg_id = item['id']
            self.logger.info(f"   🖼️ [دیباگ] پست {msg_id}: دانلود رسانه انجام نشد.")
            media_map[msg_id] = []
        return media_map, 0

    async def _save_debug_screenshot(self, page, name: str):
        if not self.save_screenshots:   # ← این خط جدید
            return
        if not self.debug_screenshots:
            return
        try:
            self.debug_screenshots_dir.mkdir(parents=True, exist_ok=True)
            safe_name = self._sanitize_filename(name)
            path = self.debug_screenshots_dir / f"{safe_name}.png"
            await page.screenshot(path=path, full_page=True)
            self.logger.debug(f"🐞 اسکرین‌شات دیباگ ذخیره شد: {path.name}")
        except Exception as e:
            self.logger.warning(f"⚠️ خطا در ذخیره اسکرین‌شات دیباگ: {e}")

    # ═══════════════ Override برای اضافه کردن اسکرین‌شات‌های بیشتر ═══════════════
    async def _fetch_posts_from_telegram(self) -> tuple[List[Dict], any, any]:
        self.logger.info("🐞 شروع مرحلهٔ استخراج پست‌ها (حالت دیباگ با اسکرین‌شات‌های بیشتر)...")

        page = None
        context = None
        try:
            # والد تمام منطق اسکرول و جهت‌یابی را دارد
            result = await super()._fetch_posts_from_telegram()
            items, context, page = result

            # اسکرین‌شات‌های اضافی برای دیباگ
            if page and items:
                await self._save_debug_screenshot(page, "final_debug")
                self.logger.info(f"🐞 {len(items)} پست در حالت دیباگ استخراج شد.")
            elif page and not items:
                self.logger.warning("🐞 هیچ پستی استخراج نشد. بررسی اسکرین‌شات‌ها...")
                await self._save_debug_screenshot(page, "no_posts_debug")

            # اگر start_link داریم، اطلاعات بیشتری لاگ کن
            if self.start_link and self.target_msg_id and page:
                await self._save_debug_screenshot(page, "debug_start_link_state")
                msg_count = await page.locator('div[data-message-id]').count()
                self.logger.info(f"🐞 تعداد پیام‌های موجود در صفحه: {msg_count}")
                if msg_count > 0:
                    first_id = await page.locator('div[data-message-id]').first.get_attribute('data-message-id')
                    last_id = await page.locator('div[data-message-id]').last.get_attribute('data-message-id')
                    self.logger.info(f"🐞 اولین id: {first_id}, آخرین id: {last_id}")

            return result
        except Exception as e:
            self.logger.error(f"❌ خطا در استخراج دیباگ: {e}")
            if page:
                await self._save_debug_screenshot(page, "error_debug")
            return [], context, page

    async def run(self):
        """اجرای اصلی با ذخیرهٔ خلاصه JSON."""
        await super().run()

        try:
            debug_json_path = self.base_dir / "debug_summary.json"
            summary = {
                "channel": self.channel,
                "limit": self.limit,
                "start_link": self.start_link,
                "scroll_direction": self.scroll_direction,
                "total_posts": len(self._last_items) if hasattr(self, '_last_items') else 0,
                "debug_mode": True
            }
            with open(debug_json_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            self.logger.info(f"🐞 خلاصه دیباگ ذخیره شد: {debug_json_path}")
        except Exception as e:
            self.logger.warning(f"⚠️ خطا در ذخیره خلاصه دیباگ: {e}")

    async def _run_impl(self):
        """Override برای ذخیرهٔ آیتم‌ها و تولید خروجی با استفاده از run_all."""
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

        try:
            gen = OutputGenerator(
                self.base_dir,
                self.channel,
                items,
                {},  # media_map خالی
                debug_mode=self.debug_mode
            )
            # استفاده از run_all برای هماهنگی با خروجی اصلی
            gen.run_all()
            self.logger.info(f"🐞 فایل‌های خروجی دیباگ در: {self.base_dir}")
        except Exception as e:
            self.logger.warning(f"⚠️ خطا در تولید خروجی دیباگ: {e}", exc_info=True)

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
        # نمایش جهت اسکرول از config
        scroll_dir = getattr(config, 'scroll_direction', 'up')
        print(f"   جهت اسکرول: {'بالا (قدیمی‌تر)' if scroll_dir == 'up' else 'پایین (جدیدتر)'}")
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
