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

MAX_TRIES=5

# ساخت پوشه خروجی (در صورت عدم وجود)
mkdir -p "$OUTPUT_FOLDER"

# ورود به پوشه خروجی
cd "$OUTPUT_FOLDER" || exit 1

# مسیر کامل فایل کوکی (در ریشه مخزن)
COOKIE_PATH="$GITHUB_WORKSPACE/cookies.txt"

for TRY in $(seq 1 $MAX_TRIES); do
    echo "----------------------------------------"
    echo "🔄 تلاش شماره $TRY از $MAX_TRIES"
    
    rm -f "$COOKIE_PATH"
    
    if [ $TRY -le 4 ]; then
        echo "🔑 دریافت کوکی شخصی شماره $TRY ..."
        python3 "$GITHUB_WORKSPACE/.github/scripts/cookie_manager.py" next
    else
        echo "🌐 دریافت کوکی از API عمومی ..."
        python3 "$GITHUB_WORKSPACE/.github/scripts/cookie_manager.py" public
    fi
    
    if [ ! -f "$COOKIE_PATH" ]; then
        echo "❌ دریافت کوکی ناموفق بود، تلاش بعدی..."
        continue
    fi
    
    echo "✅ کوکی دریافت شد. شروع دانلود..."
    
    COMMON_OPTS="--cookies \"$COOKIE_PATH\" \
        --extractor-retries 5 \
        --retries 20 \
        --fragment-retries 20 \
        --sleep-interval 4 \
        --sleep-subtitles 2 \
        --no-warnings \
        --extractor-args youtube:player_client=web,android,ios,web_safari \
        --ignore-errors \
        --compat-options no-external-downloader-progress"
    
    if [ "$PLATFORM" = "youtube" ]; then
        if [ "$TYPE" = "video" ]; then
            if [ "$QUALITY" = "best" ]; then
                eval yt-dlp $COMMON_OPTS -f "bestvideo+bestaudio/best" --merge-output-format mp4 "$URL" -o "%(title)s.%(ext)s"
            else
                HEIGHT="${QUALITY%p}"
                eval yt-dlp $COMMON_OPTS -f "bestvideo[height<=$HEIGHT]+bestaudio/best" --merge-output-format mp4 "$URL" -o "%(title)s.%(ext)s" || \
                eval yt-dlp $COMMON_OPTS -f "bestvideo+bestaudio/best" --merge-output-format mp4 "$URL" -o "%(title)s.%(ext)s"
            fi
        else
            eval yt-dlp $COMMON_OPTS -f "bestaudio[ext=m4a]/bestaudio/best" -x --audio-format mp3 --audio-quality 0 "$URL" -o "%(title)s.%(ext)s"
        fi
    else
        # SoundCloud
        if [ "$TYPE" = "video" ]; then
            eval yt-dlp $COMMON_OPTS -f "bestvideo+bestaudio/best" --merge-output-format mp4 "$URL" -o "%(title)s.%(ext)s"
        else
            eval yt-dlp $COMMON_OPTS -f "bestaudio[ext=m4a]/bestaudio/best" -x --audio-format mp3 --audio-quality 0 "$URL" -o "%(title)s.%(ext)s"
        fi
    fi
    
    DOWNLOADED_FILE=$(ls -1 | head -1)
    if [ -n "$DOWNLOADED_FILE" ]; then
        echo "✅ دانلود موفق در تلاش $TRY: $DOWNLOADED_FILE"
        echo "DOWNLOADED_FILE=$DOWNLOADED_FILE" >> $GITHUB_ENV
        
        if [ "$SPLIT_CHOICE" = "split" ]; then
            sudo apt-get update && sudo apt-get install -y zip
            echo "✂️ تقسیم فایل به قسمت‌های ${SPLIT_SIZE}..."
            zip -s "$SPLIT_SIZE" "${DOWNLOADED_FILE}.zip" "$DOWNLOADED_FILE"
            rm "$DOWNLOADED_FILE"
            echo "✅ فایل split شد."
            # پس از split، نام فایل zip را در متغیر محیطی به‌روز می‌کنیم (اختیاری)
            NEW_ZIP=$(ls -1 *.zip 2>/dev/null | head -1)
            if [ -n "$NEW_ZIP" ]; then
                echo "DOWNLOADED_FILE=$NEW_ZIP" >> $GITHUB_ENV
            fi
        fi
        exit 0
    else
        echo "⚠️ دانلود با کوکی فعلی ناموفق بود."
        rm -f "$COOKIE_PATH"
    fi
done

echo "❌ همه تلاش‌ها (۴ کوکی شخصی + عمومی) ناموفق بود."
exit 1
