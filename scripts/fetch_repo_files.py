#!/usr/bin/env python3
"""fetch_repo_files.py — 从 GitHub 仓库按需下载文件（绕开大仓库整包 clone 被掐断的问题）。

为何需要：含大媒体（gif/mp4/pdf）的 skill 仓库整包 git clone 会被沙箱 SIGTERM 掐断，
只落残缺 .git。本脚本改用 GitHub API 取文件树 + raw.githubusercontent 只下功能文件。

用法:
  # 列全树 + 字节大小（先看再决定下什么）
  python fetch_repo_files.py <owner>/<repo> --list

  # 只下指定文件
  python fetch_repo_files.py <owner>/<repo> --out DIR --files SKILL.md,references/a.md,scripts/b.py

  # 下所有 <=N KB 的文件（自动跳过 MB 级素材）
  python fetch_repo_files.py <owner>/<repo> --out DIR --max-size 200

  # 附加：只下某前缀下的文件
  python fetch_repo_files.py <owner>/<repo> --out DIR --include-prefix references/

环境: 复用 http(s)_proxy 环境变量（urllib 默认读取）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}


def api(url: str) -> dict:
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def raw(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def get_tree(repo: str, branch: str) -> list[dict]:
    data = api(f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1")
    if data.get("truncated"):
        print("WARN: 文件树被 GitHub 截断（仓库过大），--list 可能不全", file=sys.stderr)
    return [t for t in data["tree"] if t["type"] == "blob"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", help="owner/repo")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--out", default=".")
    ap.add_argument("--files", default="", help="逗号分隔的仓库内相对路径")
    ap.add_argument("--max-size", type=int, default=0, help="只下 <=N KB 的文件")
    ap.add_argument("--include-prefix", default="", help="只下该前缀下的文件")
    ap.add_argument("--list", action="store_true", help="仅列出文件树+大小")
    args = ap.parse_args()

    tree = get_tree(args.repo, args.branch)

    if args.list:
        print(f"{'size':>10}  path")
        for t in sorted(tree, key=lambda x: x["path"]):
            print(f"{t.get('size', 0):>10}  {t['path']}")
        print(f"\n共 {len(tree)} 个文件")
        return 0

    selected: list[dict] = []
    if args.files:
        want = [f.strip() for f in args.files.split(",") if f.strip()]
        by_path = {t["path"]: t for t in tree}
        for f in want:
            if f in by_path:
                selected.append(by_path[f])
            else:
                print(f"WARN: 仓库中不存在 {f}", file=sys.stderr)
    else:
        for t in tree:
            if args.include_prefix and not t["path"].startswith(args.include_prefix):
                continue
            if args.max_size and t.get("size", 0) > args.max_size * 1024:
                continue
            selected.append(t)

    base = f"https://raw.githubusercontent.com/{args.repo}/{args.branch}/"
    ok = 0
    for t in selected:
        p = os.path.join(args.out, t["path"].replace("/", os.sep))
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        try:
            d = raw(base + t["path"])
            with open(p, "wb") as fh:
                fh.write(d)
            ok += 1
            print(f"OK {len(d):>8}  {t['path']}")
        except Exception as e:  # noqa: BLE001
            print(f"ERR {type(e).__name__} {e}  {t['path']}", file=sys.stderr)
    print(f"\n下载 {ok}/{len(selected)} 个文件 → {args.out}")
    return 0 if ok == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
