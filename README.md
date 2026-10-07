# 🎬🎵 دانلودر حرفه‌ای چندپلتفرمی + آپلود مستقیم به Mega.nz

[![GitHub release](https://img.shields.io/github/v/release/alipoorkaramali/youtube-SoundCloud-downloader)](https://github.com/alipoorkaramali/youtube-SoundCloud-downloader/releases/latest)
[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/alipoorkaramali/youtube-SoundCloud-downloader/.github/workflows/Multi-Platform-Downloader-auto-Mega.yml)](https://github.com/alipoorkaramali/youtube-SoundCloud-downloader/actions)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Mega.nz](https://img.shields.io/badge/Storage-Mega.nz-red)](https://mega.nz)

**یک راه‌حل کامل، سریع و امن** برای دانلود از **YouTube • SoundCloud • Instagram • Telegram** و آپلود مستقیم به فضای ابری **Mega.nz** – بدون ردپا، کاملاً خودکار یا دستی، با قابلیت تقسیم فایل و کنترل کیفیت.
---

 ✨ **برجسته‌ترین ویژگی‌ها**  
 - **دانلود دستی** با انتخاب کیفیت، نوع خروجی و پوشه مقصد  
 - **دانلود خودکار** از کانال‌های مورد نظر (به‌کمک مخزن `youtube-news-watcher`)  
 - **دانلود اینستاگرام** با کامنت `/download shortcode` در Issues  
 - **دانلود از تلگرام** (کانال‌های عمومی) با سشن دائمی  
 - **امنیت کامل** – همه اطلاعات حساس با GPG رمزگذاری می‌شوند  
 - **بدون باقی‌ماندن فایل** در مخزن گیت‌هاب  


## 🚀 چرا این پروژه؟

- **چندپلتفرمی** – YouTube، SoundCloud، Instagram، Telegram
- **انعطاف‌پذیر** – هم خودکار، هم دستی، هم از طریق کامنت
- **سرعت بالا** – با کش باینری‌های `yt‑dlp` و `rclone`
- **تقسیم فایل‌های بزرگ** به ZIP volumes با حجم دلخواه
- **سشن دائمی تلگرام** – بدون نیاز به ورود مجدد در هر اجرا
- **پشتیبانی از کوکی** – برای دسترسی به محتوای محدود یا سن
- **کاملاً امن** – رمزگذاری تمام فایل‌های تنظیمات با GPG



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



## 🤖 دانلود خودکار (نظارت بر کانال‌ها)

برای دانلود خودکار ویدیوهای جدید از کانال‌های YouTube یا SoundCloud:

1. مخزن **`youtube-news-watcher`** را راه‌اندازی کنید (طبق راهنمای آن). این مخزن هر ۱۵ دقیقه کانال‌های شما را بررسی کرده و لینک‌های جدید را در فایل `logs/new_videos.txt` ذخیره می‌کند.
2. در مخزن فعلی، ورک‌فلو **`check_log.yml`** هر ۱۰ دقیقه اجرا شده و لینک‌های جدید را به ورک‌فلو خودکار (`auto-Mega.yml`) ارسال می‌کند.
3. ورک‌فلو خودکار با تنظیمات پیش‌فرض (صوتی، بهترین کیفیت، پوشه مگا `YoutubeNews`) فایل را دانلود و آپلود می‌کند.

**نتیجه:** به‌محض انتشار ویدیو، بدون دخالت شما در مگا ذخیره می‌شود.



## 📱 دانلود اینستاگرام (از طریق کامنت)

- ورک‌فلو **`download-on-comment.yml`** فعال است.
- کافی است در یک Issue جدید (یا موجود) کامنت بگذارید:  
  `/download C123abc456` (shortcode پست یا Reel)
- سیستم با استفاده از JSON محلی (اگر اطلاعات ذخیره شده باشد) یا `yt‑dlp` (با fallback) محتوا را دانلود کرده و متادیتا را در `instagram_data/` ذخیره می‌کند.
- فایل نهایی به پوشه `Instagram` در مگا آپلود می‌شود.

> ⚠️ **توجه:** برای عملکرد بهتر، کوکی اینستاگرام خود را رمزگذاری کرده و در مخزن قرار دهید (مراحل در بخش تنظیمات).


## 📱 دانلود از تلگرام (کانال‌های عمومی)

ورک‌فلو **`⚡ Telegram2Mega.yml`** با استفاده از سشن دائمی، محتوای کانال‌های عمومی را دانلود می‌کند.

**تنظیم سشن تلگرام (یک بار در محیط محلی):**
```bash
pip install playwright
playwright install chromium
python save_session.py
# پس از ورود موفق (اسکن QR یا شماره تلفن)، پروفایل ذخیره می‌شود:
tar -czf config/browser_profile.tar.gz -C config browser_profile

```

سپس فایل `browser_profile.tar.gz` را با GPG رمزگذاری کنید و در مخزن قرار دهید.

تنظیمات مربوط به کانال‌ها و پوشه مقصد در `config/config.yaml` انجام می‌شود.


## ☁️ تنظیم حساب Mega.nz با rclone (مهم)

ورک‌فلوهای آپلود به مگا از **rclone** استفاده می‌کنند. کانفیگ داخل مخزن به‌صورت رمزگذاری‌شده ذخیره می‌شود:

| فایل در مخزن | Secret در GitHub |
|--------------|------------------|
| `config/rclone_mega.conf.gpg` | `RCLONE_PASSPHRASE` (رمز باز کردن همین فایل) |

نام remote در rclone باید دقیقاً **`mega`** باشد (چون در ورک‌فلوها دستور به‌صورت `mega:FolderName/...` نوشته شده).

### پیش‌نیاز روی سیستم خودت (لپ‌تاپ / Termux / لینوکس)

```bash
# نصب rclone
# لینوکس:
curl https://rclone.org/install.sh | sudo bash
# یا Termux:
pkg install rclone -y

# نصب gpg (معمولاً هست)
# Termux:
pkg install gnupg -y
```

### گام ۱ — ساخت remote برای Mega

```bash
rclone config
```

پاسخ‌ها تقریباً این‌طور:

```
n) New remote
name> mega
Storage> mega          # عدد مربوط به Mega را انتخاب کن یا بنویس mega
user> ایمیل_حساب_مگا@example.com
y) Yes type in my own password
password> ********     # رمز مگا
Confirm password> ********
```

- اگر روی حساب Mega **تأیید دو مرحله‌ای (2FA)** داری، در نسخه‌های جدید rclone گزینه `2fa` هم پرسیده می‌شود؛ کد یک‌بارمصرف را همان لحظه وارد کن.
- در پایان با `y` تأیید کن و با `q` خارج شو.

تست اتصال:

```bash
rclone lsd mega:
rclone about mega:
```

اگر لیست پوشه‌ها یا فضای آزاد را دیدی، کانفیگ درست است.

### گام ۲ — پیدا کردن فایل کانفیگ

معمولاً اینجاست:

| سیستم | مسیر |
|--------|------|
| لینوکس / macOS | `~/.config/rclone/rclone.conf` |
| Termux | `~/.config/rclone/rclone.conf` |
| ویندوز | `%APPDATA%\rclone\rclone.conf` |

محتوای مربوط به مگا شبیه این است (رمزها از قبل obscure شده‌اند):

```ini
[mega]
type = mega
user = you@example.com
pass = ***ENCRYPTED_BY_RCLONE***
```

فقط بخش `[mega]` لازم است. اگر remoteهای دیگر داری، می‌توانی فقط همین بلوک را در یک فایل جدا کپی کنی:

```bash
# فقط بلوک mega را جدا کن (اختیاری)
mkdir -p config
grep -A5 '^\[mega\]' ~/.config/rclone/rclone.conf > config/rclone_mega.conf
# یا کل فایل:
cp ~/.config/rclone/rclone.conf config/rclone_mega.conf
```

### گام ۳ — رمزگذاری با GPG

یک **رمز عبور قوی** انتخاب کن (همین رمز بعداً Secret می‌شود). **هرگز** فایل `.conf` خام را commit نکن.

```bash
cd /path/to/youtube-SoundCloud-downloader

# رمزگذاری متقارن (-c)
gpg --symmetric --cipher-algo AES256 -o config/rclone_mega.conf.gpg config/rclone_mega.conf

# تست باز کردن (اختیاری)
gpg --batch --yes --passphrase "YOUR_PASSPHRASE" \
  --decrypt config/rclone_mega.conf.gpg | head

# فایل خام را پاک کن
rm -f config/rclone_mega.conf
```

### گام ۴ — قرار دادن در مخزن

```bash
git add config/rclone_mega.conf.gpg
git commit -m "chore: update encrypted rclone mega config"
git push
```

### گام ۵ — Secret در GitHub

1. برو به مخزن → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**
3. Name: دقیقاً  
   `RCLONE_PASSPHRASE`
4. Value: همان رمزی که در `gpg --symmetric` وارد کردی

> اگر از مخزن **`new-youtube-SoundCloud-downloader`** هم آپلود Mega می‌کنی (مثلاً دانلود تلگرام با گزینه `mega`)، **همین Secret** را در آن مخزن هم بساز.  
> ورک‌فلو آنجا در صورت نبودن `config/rclone_mega.conf.gpg` محلی، فایل را از این مخزن می‌گیرد؛ پس passphrase باید یکی باشد.

### گام ۶ — تست از Actions

یک ورک‌فلو دستی (مثلاً costume-Mega) را با یک لینک کوتاه اجرا کن و در لاگ دنبال این‌ها بگرد:

- `rclone version`
- باز شدن `rclone.conf` بدون خطای GPG
- `rclone copy ... mega:...` با موفقیت

خطاهای رایج:

| پیام | علت احتمالی |
|------|-------------|
| `gpg: decryption failed` | اشتباه بودن `RCLONE_PASSPHRASE` |
| `didn't find backend called "mega"` | rclone قدیمی / نصب ناقص در runner |
| `couldn't login` / 2FA | حساب Mega با 2FA؛ کانفیگ را با rclone جدید دوباره بساز |
| `Failed to create file system for "mega:..."` | نام remote چیز دیگری است (باید `mega` باشد) |

### تعویض حساب مگا

1. روی سیستم خودت دوباره `rclone config` → remote `mega` را edit یا حذف و از نو بساز  
2. دوباره `config/rclone_mega.conf.gpg` بساز  
3. اگر passphrase را عوض کردی، Secret گیت‌هاب را هم آپدیت کن  
4. push کن و یک run تست بزن  

**هرگز** ایمیل/رمز مگا یا فایل `rclone.conf` رمزگذاری‌نشده را در Issue یا README ننویس.


## 🛡️ امنیت و رمزگذاری

همه فایل‌های حساس (کوکی‌ها، تنظیمات rclone، پروفایل تلگرام) با استفاده از **GPG** رمزگذاری می‌شوند و تنها با کلیدهای تعیین‌شده در Secrets قابل دسترسی هستند.

فایل‌های رمزگذاری‌شده در مخزن:
- `rclone_mega.conf.gpg`
- `cookies.txt.gpg` (یوتیوب)
- `INSTAGRAM_COOKIES.gpg` / `INSTAGRAM_COOCKIES.gpg`
- `browser_profile.tar.gz.gpg` (تلگرام)

**هرگز فایل‌های رمزگذاری‌نشده را commit نکنید!**


## 🗂️ ساختار مخزن

| مسیر / فایل                          | نقش |
|--------------------------------------|------|
| `.github/workflows/`                 | همه ورک‌فلوها (دستی، خودکار، اینستاگرام، تلگرام) |
| `config/`                            | فایل‌های تنظیمات (`config.yaml`) و فایل‌های `.gpg` |
| `State/`                             | فایل‌های وضعیت (پردازش‌شده، شکست‌خورده، زمان آپلود) |
| `instagram_data/`                    | ذخیره JSON پست‌های اینستاگرام (برای جلوگیری از دانلود مجدد) |
| `save_session.py`                    | اسکریپت ساخت سشن تلگرام |
| `check_and_trigger.py`               | پردازش لاگ و جلوگیری از تکراری |
| `processed.txt`, `processed_titles.txt` | وضعیت دانلود خودکار |


## 🔧 راه‌اندازی سریع (گام‌به‌گام)

### ۱. کلون مخزن
```
git clone https://github.com/alipoorkaramali/youtube-SoundCloud-downloader.git
cd youtube-SoundCloud-downloader
```

### ۲. تنظیم Secrets در GitHub
به `Settings > Secrets and variables > Actions` بروید و کلیدهای زیر را اضافه کنید:

| Secret | توضیح |
|--------|--------|
| **`RCLONE_PASSPHRASE`** | رمز GPG فایل `config/rclone_mega.conf.gpg` (حساب Mega) |
| `COOKIE_DECRYPT_KEY` | کلید رمزگشایی کوکی‌های یوتیوب/صوتی |
| `TELEGRAM_DECRYPT_KEY` | در صورت استفاده از تلگرام |
| سایر | مطابق نیاز ورک‌فلوها |

جزئیات ساخت فایل rclone در بخش **☁️ تنظیم حساب Mega.nz با rclone** آمده است.

### ۳. آماده‌سازی فایل‌های کانفیگ
- فایل `rclone_mega.conf` را با تنظیمات مگا خود ایجاد کنید و با `gpg -c` / `gpg --symmetric` رمزگذاری کنید → `config/rclone_mega.conf.gpg`
- کوکی‌های یوتیوب و اینستاگرام را به‌صورت فایل ذخیره و رمزگذاری کنید
- برای تلگرام، سشن را بسازید، فشرده و رمزگذاری کنید

### ۴. تنظیم `config/config.yaml`
این فایل شامل تنظیمات پیش‌فرض (کیفیت، پوشه‌ها، کانال‌های تلگرام و …) است. آن را مطابق نیاز ویرایش کنید.

### ۵. فعال‌سازی Workflowها
در تب `Actions` مخزن، تمام workflowها را فعال کنید. برای استفاده از دانلود خودکار، مخزن `youtube-news-watcher` را نیز تنظیم نمایید.


## 📋 نکات مهم و عیب‌یابی

- **به‌روزرسانی کوکی:** در صورت انقضای کوکی، فایل جدید ساخته و جایگزین کنید.
- **مشکلات شبکه:** برای اینستاگرام و تلگرام ممکن است نیاز به VPN داشته باشید.
- **حجم فایل:** برای فایل‌های بسیار بزرگ، از گزینه `split` استفاده کنید تا آپلود با خطا مواجه نشود.
- **لاگ‌ها:** تمام لاگ‌های اجرا در خروجی workflow و همچنین پوشه `State/` در دسترس است.
- **رفع مشکل GPG:** مطمئن شوید رمز عبور در Secrets به‌درستی تنظیم شده است.
- **Mega / rclone:** نام remote باید `mega` باشد؛ Secret باید همان passphrase فایل `.gpg` باشد.


## 🤝 مشارکت و مجوز

- مجوز: **MIT** – استفاده آزاد با ذکر منبع
- خوشحال می‌شویم Pull Requestهای شما را ببینیم. حتماً قبل از ارسال، تغییرات را با آخرین نسخه اصلی همگام کنید.


**تهیه‌شده با ❤️ برای کاربران فارسی‌زبان**  
هر سوال یا پیشنهادی دارید، در بخش Issues مطرح کنید.
