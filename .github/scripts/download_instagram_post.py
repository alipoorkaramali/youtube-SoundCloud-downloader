import os
import json
import requests
from pathlib import Path

def download_file(url, filepath):
    """دانلود فایل با نمایش درصد پیشرفت"""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        with open(filepath, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    print(f"\r⏬ {downloaded//1024} KB / {total_size//1024} KB", end='')
        print()
        return True
    except Exception as e:
        print(f"❌ خطا در دانلود {url}: {e}")
        return False

def main():
    # دریافت ورودی‌ها
    shortcode = os.environ.get('SHORTCODE')
    if not shortcode:
        print("❌ SHORTCODE is required")
        exit(1)

    json_file = "instagram_posts.json"
    if not os.path.exists(json_file):
        print(f"❌ فایل {json_file} یافت نشد")
        exit(1)

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # پیدا کردن پست مورد نظر
    target_post = None
    for post in data.get('recent_posts', []):
        if post.get('shortcode') == shortcode:
            target_post = post
            break

    if not target_post:
        print(f"❌ پستی با shortcode {shortcode} یافت نشد")
        exit(1)

    print(f"✅ پست پیدا شد: {target_post.get('url')}")
    print(f"   نوع: {target_post.get('post_type')}")
    print(f"   کپشن: {target_post.get('caption', '')[:100]}...")

    # پوشه خروجی
    out_dir = Path("instagram_downloads") / shortcode
    out_dir.mkdir(parents=True, exist_ok=True)

    # دانلود بر اساس نوع پست
    if target_post.get('is_video') and target_post.get('video_url'):
        print("🎬 دانلود ویدیو...")
        file_path = out_dir / f"{shortcode}.mp4"
        if download_file(target_post['video_url'], file_path):
            print(f"✅ ویدیو ذخیره شد: {file_path}")
        else:
            exit(1)

    elif target_post.get('post_type') in ('IMAGE', 'CAROUSEL_ALBUM'):
        media_urls = target_post.get('media_urls', [])
        if not media_urls:
            print("⚠️ هیچ فایل رسانه‌ای یافت نشد")
            exit(1)
        print(f"🖼️ دانلود {len(media_urls)} تصویر...")
        for idx, img_url in enumerate(media_urls, start=1):
            ext = img_url.split('?')[0].split('.')[-1] or 'jpg'
            file_path = out_dir / f"{shortcode}_{idx}.{ext}"
            print(f"   دانلود تصویر {idx}...")
            if not download_file(img_url, file_path):
                print(f"❌ خطا در دانلود تصویر {idx}")
                exit(1)
        print(f"✅ همه تصاویر ذخیره شدند در {out_dir}")

    else:
        print("⚠️ نوع پست پشتیبانی نمی‌شود")
        exit(1)

    # ثبت اطلاعات دانلود در یک فایل متنی برای استفاده بعدی
    with open(out_dir / "info.txt", 'w', encoding='utf-8') as f:
        f.write(f"Shortcode: {shortcode}\n")
        f.write(f"URL: {target_post.get('url')}\n")
        f.write(f"Caption: {target_post.get('caption')}\n")
        f.write(f"Timestamp: {target_post.get('timestamp')}\n")
        f.write(f"Like count: {target_post.get('like_count')}\n")
        f.write(f"Comment count: {target_post.get('comment_count')}\n")

    print("🎉 دانلود با موفقیت انجام شد.")

if __name__ == '__main__':
    main()
