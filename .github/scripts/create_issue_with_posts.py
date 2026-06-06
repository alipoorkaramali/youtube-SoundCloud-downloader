import os
import json
import requests
from pathlib import Path

def main():
    repo = os.environ.get('GITHUB_REPOSITORY')   # مثل alipoorkaramali/new-youtube...
    token = os.environ.get('GH_PAT')
    if not token:
        print("❌ GH_PAT not set")
        exit(1)

    json_file = Path("instagram_posts.json")
    if not json_file.exists():
        print("❌ instagram_posts.json not found")
        exit(1)

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    posts = data.get('recent_posts', [])
    if not posts:
        print("No posts to show")
        exit(0)

    username = data.get('target_username', 'unknown')
    fetched_at = data.get('fetched_at', '')[:10]

    body = f"## 📸 پست‌های جدید اینستاگرام – @{username} – {fetched_at}\n\n"
    body += "برای دانلود هر پست، **شماره** آن را در یک کامنت جدید بنویسید:\n"
    body += "`/download 1`  یا  `/download 2`  و ...\n\n"
    body += "| شماره | شورت‌کد | کپشن (بخشی) |\n"
    body += "|-------|----------|--------------|\n"

    for idx, post in enumerate(posts, start=1):
        shortcode = post.get('shortcode', '')
        caption = post.get('caption', '')[:80].replace('\n', ' ').replace('|', '\\|')
        body += f"| {idx} | `{shortcode}` | {caption} |\n"

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "title": f"📸 پست‌های اینستاگرام - @{username} - {fetched_at}",
        "body": body,
        "labels": ["instagram-download"]
    }
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code == 201:
        print(f"✅ Issue created: {resp.json()['html_url']}")
    else:
        print(f"❌ Failed to create issue: {resp.status_code} - {resp.text}")
        exit(1)

if __name__ == '__main__':
    main()
