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

def safe_push():
    print("=" * 60)
    print("  [Git Push] 正在检测本地待推送改动与媒体文件...")
    print("=" * 60)

    run_cmd([GIT_EXE, "add", "-A"])
    
    status_res = run_cmd([GIT_EXE, "status", "--porcelain"])
    staged = [l for l in status_res.stdout.splitlines() if l.startswith(('M ', 'A ', 'D ', 'R '))]
    
    if staged:
        commit_msg = f"update: sync latest 3D assets and videos ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        res = run_cmd([GIT_EXE, "commit", "-m", commit_msg])
        if res.returncode != 0 and "nothing to commit" not in res.stdout:
            print(f"[Git Push] 提交提示: {res.stderr.strip()}")
    else:
        print("[Git Push] 无新增提交，准备检查未推送的提交...")

    # Check if local ahead of remote
    status_text = run_cmd([GIT_EXE, "status"]).stdout
    if "Your branch is up to date" in status_text and not staged:
        print("[Git Push] 本地已与 GitHub 完全一致，无需重复推送。")
        return True

    # Push with retry logic
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        print(f"[Git Push] 正在推送到 GitHub origin/main (第 {attempt}/{max_retries} 次尝试)...")
        push_res = run_cmd([GIT_EXE, "push", "origin", "main"])
        if push_res.returncode == 0:
            print("[Git Push] 成功推送所有更新至 GitHub！")
            return True
        else:
            err = push_res.stderr.strip()
            print(f"[Git Push] 推送遇到网络波动: {err}")
            time.sleep(3)

    print("[Git Push] 多次重试后仍失败，请检查网络或代理连接。")
    return False

if __name__ == "__main__":
    success = safe_push()
    sys.exit(0 if success else 1)
