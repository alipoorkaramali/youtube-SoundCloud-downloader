

```markdown
# 🎬🎵 دانلودر حرفه‌ای چندپلتفرمی + آپلود مستقیم به Mega.nz

[![GitHub release](https://img.shields.io/github/v/release/alipoorkaramali/youtube-SoundCloud-downloader)](https://github.com/alipoorkaramali/youtube-SoundCloud-downloader/releases/latest)
[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/alipoorkaramali/youtube-SoundCloud-downloader/.github/workflows/Multi-Platform-Downloader-auto-Mega.yml)](https://github.com/alipoorkaramali/youtube-SoundCloud-downloader/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Mega.nz](https://img.shields.io/badge/Storage-Mega.nz-red)](https://mega.nz)

**یک راه‌حل کامل، سریع و امن** برای دانلود از **YouTube • SoundCloud • Instagram • Telegram** و آپلود مستقیم به فضای ابری شخصی **Mega.nz** — بدون نیاز به سرور، بدون ذخیره فایل در مخزن، و با کنترل کامل.

> ✨ **ویژگی‌های کلیدی**  
> • دانلود دستی با تنظیمات دلخواه  
> • دانلود خودکار ویدیوهای جدید کانال‌ها  
> • دانلود اینستاگرام از طریق کامنت Issue  
> • دانلود تلگرام با **سشن دائمی**  
> • امنیت بالا با رمزگذاری GPG  
> • تقسیم فایل‌های بزرگ به ZIP volumes  

---

## 🚀 چرا این پروژه متفاوت است؟

- **چندپلتفرمی کامل**: YouTube, SoundCloud, Instagram, Telegram
- **انعطاف‌پذیری بالا**: دستی، خودکار، و از طریق کامنت
- **امنیت حرفه‌ای**: کوکی‌ها، تنظیمات rclone و سشن تلگرام با **GPG** رمزگذاری می‌شوند
- **سرعت و بهینه‌سازی**: کش هوشمند `yt-dlp` و `rclone`
- **بدون ردپا**: همه عملیات روی runner موقتی GitHub انجام شده و هیچ فایلی در مخزن باقی نمی‌ماند
- **تقسیم فایل**: پشتیبانی از ZIP volumes برای راحتی دانلود فایل‌های بزرگ

---

## 🖐️ دانلود دستی (کنترل کامل)

ورک‌فلو **`Multi-Platform-Downloader-costume-Mega.yml`** یا نسخه بهبودیافته **`NEW3-costume-Multi-Platform Downloader.yml`** را Manual Dispatch کنید.

| گزینه            | مقادیر ممکن                                      | توضیح |
|------------------|--------------------------------------------------|-------|
| **platform**     | `youtube`, `soundcloud`, `instagram`             | پلتفرم |
| **url**          | لینک کامل یا shortcode اینستاگرام               | آدرس محتوا |
| **type**         | `audio` / `video`                                | نوع خروجی |
| **quality**      | `144p` تا `1080p` یا `best`                      | کیفیت ویدیو |
| **mega_folder**  | دلخواه (پیش‌فرض `Downloads`)                    | پوشه مقصد در Mega |
| **split_choice** | `single` / `split`                               | تقسیم به قطعات |
| **split_size**   | `100M`, `500M`, `1G`, ...                        | حجم هر قطعه |

---

## 📱 دانلود اینستاگرام (از طریق کامنت)

- ورک‌فلو: **`download-on-comment.yml`**
- کافیست در هر Issue کامنت زیر را بگذارید:
  ```
  /download C123abc456
  ```
- سیستم به‌صورت هوشمند از JSON محلی (در `instagram_data/`) یا `yt-dlp` (با fallback و پشتیبانی کوکی) استفاده می‌کند.
- متادیتا (caption, likes, comments) ذخیره و فایل به Mega آپلود می‌شود.

---

## 📱 دانلود از تلگرام (کانال‌های عمومی)

ورک‌فلو: **`⚡ Telegram2Mega.yml`**

**تنظیم یک‌باره سشن دائمی (روی کامپیوتر خودتان):**

```bash
pip install playwright
playwright install chromium
python save_session.py
```

پس از لاگین کامل در مرورگر و دیدن لیست چت‌ها، Enter بزنید. سپس:

```bash
tar -czf config/browser_profile.tar.gz -C config browser_profile
```

فایل `browser_profile.tar.gz` را با GPG رمزگذاری کرده و در `config/` قرار دهید.

تنظیمات اصلی در فایل `config/config.yaml` انجام می‌شود (نام کانال، limit، delay و غیره).

---

## 🤖 دانلود خودکار

1. مخزن **`youtube-news-watcher`** را راه‌اندازی کنید (هر ۱۵ دقیقه لینک‌های جدید را ذخیره می‌کند).
2. ورک‌فلو **`🔐check_log.yml`** هر ۱۰ دقیقه لاگ را بررسی می‌کند.
3. لینک‌های جدید به ورک‌فلو **`Multi-Platform-Downloader-auto-Mega.yml`** ارسال شده و به‌طور خودکار دانلود و به پوشه `YoutubeNews` در Mega آپلود می‌شوند.

---

## 🗂️ ساختار مهم مخزن

- **`.github/workflows/`** — تمام workflowها
- **`config/`** — `config.yaml`, `rclone_mega.conf.gpg`, کوکی‌ها، `browser_profile.tar.gz.gpg`
- **`State/`** — فایل‌های پردازش‌شده، failed titles، upload logs
- **`instagram_data/`** — JSON پست‌های اینستاگرام
- **`save_session.py`** — ساخت سشن تلگرام

---

## 🔧 راه‌اندازی اولیه

1. مخزن را کلون کنید.
2. Secrets لازم را در **Repository Settings → Secrets and variables** تعریف کنید (`RCLONE_PASSPHRASE`, `COOKIE_DECRYPT_KEY` و غیره).
3. فایل‌های کانفیگ رمزگذاری‌شده را در پوشه `config/` قرار دهید.
4. workflowهای مورد نظر را فعال کنید.
5. برای تست، از Manual Dispatch یا کامنت Issue استفاده کنید.

---

## ⚠️ نکات مهم

- **امنیت**: هرگز فایل‌های `.gpg` نشده حساس را commit نکنید.
- **VPN**: برای اینستاگرام و تلگرام توصیه می‌شود.
- **به‌روزرسانی کوکی/سشن**: در صورت نیاز، سشن جدید بسازید.
- **مشکلات**: لاگ workflowها را بررسی کنید.

---

**License**: MIT

هرگونه سوال یا پیشنهاد در **Issues** خوشحال می‌شویم.

---

*تهیه‌شده با ❤️ برای کاربران فارسی‌زبان*
```

---
