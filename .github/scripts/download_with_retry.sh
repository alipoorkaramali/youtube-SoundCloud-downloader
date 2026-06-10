#!/bin/bash

# download_with_retry.sh
# Usage: ./download_with_retry.sh <output_folder> <url> <platform> <type> <quality> <split_choice> <split_size>

set -e

OUTPUT_FOLDER="$1"
URL="$2"
PLATFORM="$3"
TYPE="$4"
QUALITY="$5"
SPLIT_CHOICE="$6"
SPLIT_SIZE="$7"

MAX_TRIES=5  # 4 تا کوکی شخصی + 1 بار fallback عمومی
cd "$OUTPUT_FOLDER" || exit 1

for TRY in $(seq 1 $MAX_TRIES); do
    echo "----------------------------------------"
    echo "🔄 تلاش شماره $TRY از $MAX_TRIES"
    
    # حذف کوکی قبلی اگر وجود داشته باشد
    rm -f ../cookies.txt
    
    if [ $TRY -le 4 ]; then
        # تلاش با کوکی‌های شخصی (به ترتیب چرخشی)
        echo "🔑 دریافت کوکی شخصی شماره $TRY ..."
        python3 .github/scripts/cookie_manager.py next
    else
        # آخرین تلاش: دریافت کوکی عمومی
        echo "🌐 دریافت کوکی از API عمومی ..."
        python3 .github/scripts/cookie_manager.py public
    fi
    
    # بررسی وجود فایل کوکی
    if [ ! -f ../cookies.txt ]; then
        echo "❌ دریافت کوکی ناموفق بود، تلاش بعدی..."
        continue
    fi
    
    echo "✅ کوکی دریافت شد. شروع دانلود..."
    
    # ساخت آرگومان‌های مشترک yt-dlp
    COMMON_OPTS="--cookies ../cookies.txt \
        --extractor-retries 5 \
        --retries 20 \
        --fragment-retries 20 \
        --sleep-interval 4 \
        --sleep-subtitles 2 \
        --no-warnings \
        --extractor-args youtube:player_client=web,android,ios,web_safari \
        --ignore-errors \
        --compat-options no-external-downloader-progress"
    
    # دستور دانلود بر اساس پلتفرم و نوع
    if [ "$PLATFORM" = "youtube" ]; then
        if [ "$TYPE" = "video" ]; then
            if [ "$QUALITY" = "best" ]; then
                yt-dlp $COMMON_OPTS -f "bestvideo+bestaudio/best" --merge-output-format mp4 "$URL" -o "%(title)s.%(ext)s"
            else
                HEIGHT="${QUALITY%p}"
                yt-dlp $COMMON_OPTS -f "bestvideo[height<=$HEIGHT]+bestaudio/best" --merge-output-format mp4 "$URL" -o "%(title)s.%(ext)s" || \
                yt-dlp $COMMON_OPTS -f "bestvideo+bestaudio/best" --merge-output-format mp4 "$URL" -o "%(title)s.%(ext)s"
            fi
        else
            # حالت صوتی
            yt-dlp $COMMON_OPTS -f "bestaudio[ext=m4a]/bestaudio/best" -x --audio-format mp3 --audio-quality 0 "$URL" -o "%(title)s.%(ext)s"
        fi
    else
        # SoundCloud
        if [ "$TYPE" = "video" ]; then
            yt-dlp $COMMON_OPTS -f "bestvideo+bestaudio/best" --merge-output-format mp4 "$URL" -o "%(title)s.%(ext)s"
        else
            yt-dlp $COMMON_OPTS -f "bestaudio[ext=m4a]/bestaudio/best" -x --audio-format mp3 --audio-quality 0 "$URL" -o "%(title)s.%(ext)s"
        fi
    fi
    
    # بررسی موفقیت دانلود
    DOWNLOADED_FILE=$(ls -1 | head -1)
    if [ -n "$DOWNLOADED_FILE" ]; then
        echo "✅ دانلود با موفقیت انجام شد در تلاش $TRY: $DOWNLOADED_FILE"
        echo "DOWNLOADED_FILE=$DOWNLOADED_FILE" >> $GITHUB_ENV
        
        # اگر فایل نیاز به split دارد، اینجا انجام می‌شود (اختیاری)
        if [ "$SPLIT_CHOICE" = "split" ]; then
            sudo apt-get update && sudo apt-get install -y zip
            echo "✂️ تقسیم فایل به قسمت‌های ${SPLIT_SIZE}..."
            zip -s "$SPLIT_SIZE" "${DOWNLOADED_FILE}.zip" "$DOWNLOADED_FILE"
            rm "$DOWNLOADED_FILE"
            echo "✅ فایل split شد."
        fi
        exit 0
    else
        echo "⚠️ دانلود با کوکی فعلی ناموفق بود. حذف کوکی و تلاش مجدد..."
        rm -f ../cookies.txt
    fi
done

echo "❌ همه تلاش‌ها (۴ کوکی شخصی + عمومی) ناموفق بود."
exit 1
