# 🎬🎵 دانلودر حرفه‌ای چندپلتفرمی + آپلود مستقیم به Mega.nz

[![GitHub release](https://img.shields.io/github/v/release/alipoorkaramali/youtube-SoundCloud-downloader)](https://github.com/alipoorkaramali/youtube-SoundCloud-downloader/releases/latest)
[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/alipoorkaramali/youtube-SoundCloud-downloader/.github/workflows/Multi-Platform-Downloader-auto-Mega.yml)](https://github.com/alipoorkaramali/youtube-SoundCloud-downloader/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Mega.nz](https://img.shields.io/badge/Storage-Mega.nz-red)](https://mega.nz)

**یک راه‌حل کامل، سریع و امن** برای دانلود از **YouTube • SoundCloud • Instagram • Telegram** و آپلود مستقیم به فضای ابری **Mega.nz** – بدون ردپا، کاملاً خودکار یا دستی، با قابلیت تقسیم فایل و کنترل کیفیت.

> ✨ **برجسته‌ترین ویژگی‌ها**  
> - **دانلود دستی** با انتخاب کیفیت، نوع خروجی و پوشه مقصد  
> - **دانلود خودکار** از کانال‌های مورد نظر (به‌کمک مخزن `youtube-news-watcher`)  
> - **دانلود اینستاگرام** با کامنت `/download shortcode` در Issues  
> - **دانلود از تلگرام** (کانال‌های عمومی) با سشن دائمی  
> - **امنیت کامل** – همه اطلاعات حساس با GPG رمزگذاری می‌شوند  
> - **بدون باقی‌ماندن فایل** در مخزن گیت‌هاب  

---

## 🚀 چرا این پروژه؟

- **چندپلتفرمی** – YouTube، SoundCloud، Instagram، Telegram
- **انعطاف‌پذیر** – هم خودکار، هم دستی، هم از طریق کامنت
- **سرعت بالا** – با کش باینری‌های `yt‑dlp` و `rclone`
- **تقسیم فایل‌های بزرگ** به ZIP volumes با حجم دلخواه
- **سشن دائمی تلگرام** – بدون نیاز به ورود مجدد در هر اجرا
- **پشتیبانی از کوکی** – برای دسترسی به محتوای محدود یا سن
- **کاملاً امن** – رمزگذاری تمام فایل‌های تنظیمات با GPG

---

## 🖐️ دانلود دستی (کنترل کامل)

ورک‌فلو **`Multi-Platform-Downloader-costume-Mega.yml`** (یا نسخه جدیدتر `NEW3-...`) را اجرا کنید و گزینه‌های زیر را تنظیم نمایید:

| گزینه          | مقادیر ممکن                                   | توضیح |
|----------------|-----------------------------------------------|-------|
| **platform**   | `youtube`, `soundcloud`, `instagram`          | پلتفرم مقصد |
| **url**        | لینک کامل یا shortcode اینستاگرام            | آدرس محتوا |
| **type**       | `audio` یا `video`                            | نوع خروجی (برای صدا، کیفیت نادیده گرفته می‌شود) |
| **quality**    | `144p`, `240p`, `360p`, `480p`, `720p`, `1080p`, `best` | کیفیت ویدیو |
| **mega_folder**| دلخواه (پیش‌فرض `YoutubeDownloads`)          | پوشه مقصد در حساب مگا |
| **split_choice**| `single` یا `split`                          | در صورت `split`، فایل به قطعات ZIP تقسیم می‌شود |
| **split_size** | `100M`, `500M`, `1G` و غیره                   | حجم هر قطعه (فقط در حالت split) |

پس از اجرا، فایل با کیفیت مورد نظر دانلود شده، در صورت نیاز تقسیم می‌شود و مستقیماً به پوشه مشخص‌شده در مگا آپلود می‌گردد. **هیچ فایلی در مخزن باقی نمی‌ماند.**

---

## 🤖 دانلود خودکار (نظارت بر کانال‌ها)

برای دانلود خودکار ویدیوهای جدید از کانال‌های YouTube یا SoundCloud:

1. مخزن **`youtube-news-watcher`** را راه‌اندازی کنید (طبق راهنمای آن). این مخزن هر ۱۵ دقیقه کانال‌های شما را بررسی کرده و لینک‌های جدید را در فایل `logs/new_videos.txt` ذخیره می‌کند.
2. در مخزن فعلی، ورک‌فلو **`check_log.yml`** هر ۱۰ دقیقه اجرا شده و لینک‌های جدید را به ورک‌فلو خودکار (`auto-Mega.yml`) ارسال می‌کند.
3. ورک‌فلو خودکار با تنظیمات پیش‌فرض (صوتی، بهترین کیفیت، پوشه مگا `YoutubeNews`) فایل را دانلود و آپلود می‌کند.

**نتیجه:** به‌محض انتشار ویدیو، بدون دخالت شما در مگا ذخیره می‌شود.

---

## 📱 دانلود اینستاگرام (از طریق کامنت)

- ورک‌فلو **`download-on-comment.yml`** فعال است.
- کافی است در یک Issue جدید (یا موجود) کامنت بگذارید:  
  `/download C123abc456` (shortcode پست یا Reel)
- سیستم با استفاده از JSON محلی (اگر اطلاعات ذخیره شده باشد) یا `yt‑dlp` (با fallback) محتوا را دانلود کرده و متادیتا را در `instagram_data/` ذخیره می‌کند.
- فایل نهایی به پوشه `Instagram` در مگا آپلود می‌شود.

> ⚠️ **توجه:** برای عملکرد بهتر، کوکی اینستاگرام خود را رمزگذاری کرده و در مخزن قرار دهید (مراحل در بخش تنظیمات).

---

## 📱 دانلود از تلگرام (کانال‌های عمومی)

ورک‌فلو **`⚡ Telegram2Mega.yml`** با استفاده از سشن دائمی، محتوای کانال‌های عمومی را دانلود می‌کند.

**تنظیم سشن تلگرام (یک بار در محیط محلی):**
```bash
pip install playwright
playwright install chromium
python save_session.py
# پس از ورود موفق (اسکن QR یا شماره تلفن)، پروفایل ذخیره می‌شود:
tar -czf config/browser_profile.tar.gz -C config browser_profile