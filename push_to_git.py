# -*- coding: utf-8 -*-
import os
import sys
import time
import subprocess
from pathlib import Path

GIT_EXE = r"C:\Program Files\Git\bin\git.exe"
if not os.path.exists(GIT_EXE):
    GIT_EXE = "git"

BASE_DIR = Path(__file__).resolve().parent

def run_cmd(args):
    return subprocess.run(args, cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")

def push_with_retry(max_retries=5):
    for attempt in range(1, max_retries + 1):
        print(f"[Git Push] 正在推送到 GitHub origin/main (第 {attempt}/{max_retries} 次尝试)...")
        push_res = run_cmd([GIT_EXE, "push", "origin", "main"])
        if push_res.returncode == 0:
            return True
        else:
            err = push_res.stderr.strip()
            print(f"[Git Push] 推送遇到网络波动: {err}")
            time.sleep(3)
    return False

def safe_push():
    print("=" * 60)
    print("  [Git Push] 正在检测本地待推送改动与媒体文件...")
    print("=" * 60)

    # 1. First push code, JSON, and web assets
    code_files = ["config.py", "server.py", "build_static_showcase.py", "push_to_git.py", "sync_pipeline.py",
                  "index.html", "static/index.html", "static/data", "static/js", "static/css"]
    existing_code = [f for f in code_files if (BASE_DIR / f).exists()]
    run_cmd([GIT_EXE, "add"] + existing_code)

    status_res = run_cmd([GIT_EXE, "status", "--porcelain"])
    staged = [l for l in status_res.stdout.splitlines() if l.startswith(('M ', 'A ', 'D ', 'R '))]
    if staged:
        commit_msg = f"update: sync asset configs and metadata ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        run_cmd([GIT_EXE, "commit", "-m", commit_msg])
        if not push_with_retry():
            print("[Git Push] 元数据推送失败，请检查网络。")
            return False

    # 2. Check remaining files (mainly media)
    status_res = run_cmd([GIT_EXE, "status", "--porcelain"])
    unstaged_lines = [l.strip() for l in status_res.stdout.splitlines() if l.strip()]
    if not unstaged_lines:
        print("[Git Push] 本地已与 GitHub 完全一致，无需重复推送。")
        return True

    # 3. Micro-batch media files by batch directory to stay well under GitHub HTTP 408 limits
    media_dir = BASE_DIR / "static" / "media"
    if media_dir.exists():
        batches = sorted([d.name for d in media_dir.iterdir() if d.is_dir()])
        for b_name in batches:
            rel_b_path = f"static/media/{b_name}"
            run_cmd([GIT_EXE, "add", rel_b_path])
            st = run_cmd([GIT_EXE, "status", "--porcelain"]).stdout
            if any(l.startswith(('M ', 'A ', 'D ', 'R ')) for l in st.splitlines()):
                print(f"[Git Push] 正在提交媒体批次: {b_name}...")
                run_cmd([GIT_EXE, "commit", "-m", f"media: sync {b_name} videos and thumbnails"])
                if not push_with_retry():
                    print(f"[Git Push] 批次 {b_name} 推送失败。")
                    return False

    # 4. Add any other residual files
    run_cmd([GIT_EXE, "add", "-A"])
    st = run_cmd([GIT_EXE, "status", "--porcelain"]).stdout
    if any(l.startswith(('M ', 'A ', 'D ', 'R ')) for l in st.splitlines()):
        run_cmd([GIT_EXE, "commit", "-m", "update: sync remaining project files"])
        if not push_with_retry():
            return False

    print("[Git Push] 成功推送所有更新至 GitHub！")
    return True

if __name__ == "__main__":
    success = safe_push()
    sys.exit(0 if success else 1)
