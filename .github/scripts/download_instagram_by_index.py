import os
import json
import subprocess
import sys
from pathlib import Path

def download_with_ytdlp(url, output_path):
    cmd = ["yt-dlp", "--no-playlist", "-o", output_path, url]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ yt-dlp error: {e.stderr}")
        return False

def main():
    index_str = os.environ.get('POST_INDEX', '').strip()
    if not index_str:
        print("❌ POST_INDEX is required")
        sys.exit(1)

    try:
        index = int(index_str) - 1
    except ValueError:
        print("❌ POST_INDEX must be a number")
        sys.exit(1)

    json_file = Path("instagram_posts.json")
    if not json_file.exists():
        print("❌ instagram_posts.json not found. Run fetch workflow first.")
        sys.exit(1)

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    posts = data.get('recent_posts', [])
    if not posts:
        print("❌ No posts found")
        sys.exit(1)

    if index < 0 or index >= len(posts):
        print(f"❌ Invalid index. Choose 1..{len(posts)}")
        sys.exit(1)

    post = posts[index]
    shortcode = post.get('shortcode')
    post_url = post.get('url')
    caption = post.get('caption', '')

    print(f"\n✅ Downloading: {shortcode}")
    print(f"   Caption: {caption[:100]}...")
    print(f"   URL: {post_url}")

    download_dir = Path("instagram_downloads") / shortcode
    download_dir.mkdir(parents=True, exist_ok=True)
    output_path = download_dir / f"{shortcode}.mp4"

    if download_with_ytdlp(post_url, str(output_path)):
        with open(download_dir / "info.txt", 'w', encoding='utf-8') as f:
            f.write(f"Shortcode: {shortcode}\nURL: {post_url}\nCaption: {caption}\n")
        print(f"✅ Saved to {output_path}")
    else:
        print("❌ Download failed")
        sys.exit(1)

if __name__ == '__main__':
    main()
