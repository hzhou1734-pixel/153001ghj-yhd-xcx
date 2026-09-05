#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
顾好家用户端交互原型 · GitHub 发布脚本

用法：
    python publish.py [-m "更新说明"] [--ver v1.2.3] [--token ghp_xxx]

说明：
    1. 默认自动递增 HTML 中 APP_VER 的 patch 号（如 v1.0.0 -> v1.0.1）。
    2. 自动把最新 HTML 通过 GitHub API 上传到仓库。
    3. 同步更新 README.md 中的版本徽标/当前版本字样（可选）。

Token 优先级：
    --token 参数 > GITHUB_TOKEN 环境变量 > 本地文件 .gh_token > 交互输入
"""

import argparse
import base64
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime

REPO = "hzhou1734-pixel/153001ghj-yhd-xcx"
BRANCH = "main"
HTML_FILE = "顾好家APP用户端-交互原型.html"
README_FILE = "README.md"
TOKEN_FILE = os.path.expanduser("~/.ghj_publish_token")


def get_token(args_token: str | None) -> str:
    """按优先级获取 GitHub Personal Access Token。"""
    if args_token:
        return args_token
    env = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if env:
        return env
    if os.path.exists(TOKEN_FILE):
        with io.open(TOKEN_FILE, encoding="utf-8") as f:
            t = f.read().strip()
        if t:
            return t
    t = input("请输入 GitHub Personal Access Token（仅本次会话有效）: ").strip()
    if not t:
        print("错误：缺少 GitHub Token。", file=sys.stderr)
        sys.exit(1)
    save = input("是否保存到本地 ~/.ghj_publish_token 供下次使用？(y/N) ").strip().lower()
    if save in ("y", "yes"):
        with io.open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(t)
        print("Token 已保存到", TOKEN_FILE)
    return t


def github_api(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    url = f"https://api.github.com/repos/{REPO}/contents/{urllib.parse.quote(path)}" if method in ("GET", "PUT", "DELETE") else f"https://api.github.com/repos/{REPO}/{path}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "python-urllib-ghj-publish")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read().decode("utf-8", "ignore")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        print(f"\nGitHub API 错误：{e.code} {e.reason}", file=sys.stderr)
        print(e.read().decode("utf-8", "ignore")[:500], file=sys.stderr)
        sys.exit(1)


def get_remote_sha(path: str, token: str) -> str | None:
    try:
        meta = github_api("GET", path, token)
        return meta.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def bump_version(html: str, explicit_ver: str | None) -> tuple[str, str, str]:
    """递增版本号并同步更新 APP_BUILT。返回 (新HTML, 旧版本, 新版本)。"""
    m = re.search(r"var APP_VER='(v\d+\.\d+\.\d+)';", html)
    if not m:
        print("错误：HTML 中找不到 var APP_VER='vX.Y.Z'; 声明。", file=sys.stderr)
        sys.exit(1)
    old_ver = m.group(1)

    if explicit_ver:
        new_ver = explicit_ver
    else:
        parts = old_ver[1:].split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            print(f"错误：版本号格式无法解析：{old_ver}", file=sys.stderr)
            sys.exit(1)
        major, minor, patch = map(int, parts)
        new_ver = f"v{major}.{minor}.{patch + 1}"

    today = datetime.now().strftime("%Y-%m-%d")
    html = re.sub(r"var APP_VER='v\d+\.\d+\.\d+';", f"var APP_VER='{new_ver}';", html)
    html = re.sub(r"var APP_BUILT='\d{4}-\d{2}-\d{2}';", f"var APP_BUILT='{today}';", html)
    return html, old_ver, new_ver


def update_readme_version(readme: str, new_ver: str) -> str:
    """如果 README 里写了当前版本，顺便同步更新。"""
    # 匹配 Markdown 行：当前版本：v1.0.0
    readme = re.sub(r"(当前版本[：:]\s*)v\d+\.\d+\.\d+", rf"\g<1>{new_ver}", readme)
    # 匹配徽标链接：![version](...v1.0.0...)
    readme = re.sub(r"(badge/version-)v\d+\.\d+\.\d+", rf"\g<1>{new_ver[1:]}", readme)
    return readme


def main():
    parser = argparse.ArgumentParser(description="发布顾好家交互原型到 GitHub 仓库")
    parser.add_argument("-m", "--message", default="", help="commit 附加说明")
    parser.add_argument("--ver", help="指定新版本号（默认自动递增 patch）")
    parser.add_argument("--token", help="GitHub PAT，或设置 GITHUB_TOKEN 环境变量")
    parser.add_argument("--no-readme", action="store_true", help="不同步更新 README 中的版本号")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, HTML_FILE)
    readme_path = os.path.join(base_dir, README_FILE)

    if not os.path.exists(html_path):
        print(f"错误：找不到 {html_path}", file=sys.stderr)
        sys.exit(1)

    token = get_token(args.token)

    # 1. 读取并 bump 版本
    html = io.open(html_path, encoding="utf-8").read()
    html, old_ver, new_ver = bump_version(html, args.ver)
    io.open(html_path, "w", encoding="utf-8", newline="").write(html)
    print(f"版本号：{old_ver} -> {new_ver}")

    # 2. 同步 README
    readme_changed = False
    readme_new = ""
    if os.path.exists(readme_path) and not args.no_readme:
        readme = io.open(readme_path, encoding="utf-8").read()
        readme_new = update_readme_version(readme, new_ver)
        readme_changed = readme_new != readme
        if readme_changed:
            io.open(readme_path, "w", encoding="utf-8", newline="").write(readme_new)
            print("README.md 中的版本号已同步")

    # 3. 准备 commit message
    msg = args.message.strip() or f"优化原型 v{new_ver[1:]}"
    if not msg.lower().startswith("v"):
        commit_msg = f"{new_ver}: {msg}"
    else:
        commit_msg = msg

    # 4. 上传 HTML
    html_b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
    html_sha = get_remote_sha(HTML_FILE, token)
    payload_html = {
        "message": commit_msg,
        "content": html_b64,
        "branch": BRANCH,
    }
    if html_sha:
        payload_html["sha"] = html_sha
    resp_html = github_api("PUT", HTML_FILE, token, payload_html)
    print(f"已上传 {HTML_FILE} -> {resp_html['content']['html_url']}")

    # 5. 如有 README 变更，上传 README
    if os.path.exists(readme_path) and not args.no_readme and readme_changed:
        readme_b64 = base64.b64encode(readme_new.encode("utf-8")).decode("ascii")
        readme_sha = get_remote_sha(README_FILE, token)
        payload_readme = {
            "message": f"docs: 同步 README 版本号至 {new_ver}",
            "content": readme_b64,
            "branch": BRANCH,
        }
        if readme_sha:
            payload_readme["sha"] = readme_sha
        resp_readme = github_api("PUT", README_FILE, token, payload_readme)
        print(f"已上传 {README_FILE} -> {resp_readme['content']['html_url']}")

    print(f"\n✅ 发布完成：{new_ver}")
    print(f"仓库地址：https://github.com/{REPO}")
    print(f"在线预览：https://{REPO.split('/')[0]}.github.io/{REPO.split('/')[1]}/")


if __name__ == "__main__":
    main()
