# -*- coding: utf-8 -*-
"""
Robust, self-healing Git sync module for 3D USD Asset Portal.
Includes:
- Auto Git executable discovery
- Auto .git/*.lock cleanup
- Large media buffer tuning (http.postBuffer = 500MB)
- Realtime streaming progress (no frozen windows)
- Resilient retry with backoff
"""
import io
import os
import sys
import time
import shutil
import subprocess
from pathlib import Path

# Safe UTF-8 stdout configuration for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent

def find_git_exe():
    """Discover valid git.exe on Windows."""
    candidates = [
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files\Git\bin\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Git\cmd\git.exe"),
        "git"
    ]
    for c in candidates:
        if c == "git":
            path = shutil.which("git")
            if path:
                return path
        elif os.path.exists(c):
            return c
    return "git"

GIT_EXE = find_git_exe()

def clean_git_locks():
    """Clean up any stale git lock files left by interrupted processes."""
    git_dir = BASE_DIR / ".git"
    if not git_dir.exists():
        return
    lock_files = list(git_dir.glob("**/*.lock"))
    for lk in lock_files:
        try:
            if time.time() - lk.stat().st_mtime > 5:
                lk.unlink(missing_ok=True)
                print(f"  [Git Auto-Heal] 清理了残留的锁定文件: {lk.name}")
        except Exception:
            pass

def init_git_configs():
    """Ensure repository Git configs are optimized for large video/asset uploads."""
    configs = [
        ("http.postBuffer", "524288000"),        # 500 MB upload buffer
        ("http.lowSpeedLimit", "1000"),           # 1KB/s min speed
        ("http.lowSpeedTime", "120"),             # 120s timeout on dead connections
        ("core.longpaths", "true"),               # Support deep Windows paths
        ("core.autocrlf", "false"),               # Preserve LF/CRLF as-is
    ]
    for key, val in configs:
        try:
            subprocess.run([GIT_EXE, "config", key, val], cwd=str(BASE_DIR), capture_output=True)
        except Exception:
            pass

def run_cmd_live(args, desc="执行命令"):
    """Run git command with live output streaming to prevent silent blocking."""
    clean_git_locks()
    try:
        process = subprocess.Popen(
            args,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
        output_lines = []
        for line in process.stdout:
            line_str = line.strip()
            if line_str:
                output_lines.append(line_str)
                if any(k in line_str for k in ["Writing objects", "Counting objects", "Compressing", "Resolving", "Total", "error", "fatal"]):
                    print(f"    {line_str}", flush=True)
        process.wait()
        return process.returncode, "\n".join(output_lines)
    except Exception as e:
        return 1, str(e)

def run_cmd_quiet(args):
    """Run quick git commands silently."""
    clean_git_locks()
    return subprocess.run(args, cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")

def push_with_retry(max_retries=4):
    """Push commits with progressive retry and real-time streaming."""
    for attempt in range(1, max_retries + 1):
        print(f"  [Git Push] 正在推送到 GitHub origin/main (第 {attempt}/{max_retries} 次尝试)...", flush=True)
        code, out = run_cmd_live([GIT_EXE, "push", "origin", "main"], desc="git push")
        if code == 0:
            print("  [Git Push] ✓ 推送成功！", flush=True)
            return True
        else:
            print(f"  [Git Push] 提示: 第 {attempt} 次推送网络波动，正在重试...", flush=True)
            time.sleep(2 * attempt)
    return False

def safe_push():
    print("=" * 68)
    print("  [Git Push] 正在检测本地待推送改动与媒体文件...")
    print("=" * 68)

    # 0. Self-heal and init configs
    clean_git_locks()
    init_git_configs()

    # 1. First push code, JSON, and web assets
    code_files = ["config.py", "server.py", "build_static_showcase.py", "push_to_git.py", "sync_pipeline.py",
                  "ignore_batches.txt", "index.html", "static/index.html", "static/data", "static/js", "static/css"]
    existing_code = [f for f in code_files if (BASE_DIR / f).exists()]
    run_cmd_quiet([GIT_EXE, "add"] + existing_code)

    status_res = run_cmd_quiet([GIT_EXE, "status", "--porcelain"])
    staged = [l for l in status_res.stdout.splitlines() if l.startswith(('M ', 'A ', 'D ', 'R '))]
    if staged:
        commit_msg = f"update: sync asset configs and metadata ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        run_cmd_quiet([GIT_EXE, "commit", "-m", commit_msg])
        print("  -> 正在推送资产元数据与配置文件...", flush=True)
        if not push_with_retry():
            print("  [警告] 元数据推送超时，请检查网络连接。")
            return False

    # 2. Check remaining files (mainly media)
    status_res = run_cmd_quiet([GIT_EXE, "status", "--porcelain"])
    unstaged_lines = [l.strip() for l in status_res.stdout.splitlines() if l.strip()]
    if not unstaged_lines:
        print("  [Git Push] ✓ 本地与 GitHub 已经是最新状态，无需重复推送。")
        return True

    # 3. Micro-batch media files by batch directory to guarantee fast, chunked uploads
    media_dir = BASE_DIR / "static" / "media"
    if media_dir.exists():
        batches = sorted([d.name for d in media_dir.iterdir() if d.is_dir()])
        for b_name in batches:
            rel_b_path = f"static/media/{b_name}"
            run_cmd_quiet([GIT_EXE, "add", rel_b_path])
            st = run_cmd_quiet([GIT_EXE, "status", "--porcelain"]).stdout
            if any(l.startswith(('M ', 'A ', 'D ', 'R ')) for l in st.splitlines()):
                print(f"  [Git Push] 正在打包提交媒体批次: [{b_name}] ...", flush=True)
                run_cmd_quiet([GIT_EXE, "commit", "-m", f"media: sync {b_name} videos and thumbnails"])
                if not push_with_retry():
                    print(f"  [Git Push] 批次 {b_name} 推送遇到网络中断。")
                    return False

    # 4. Add any other residual files
    run_cmd_quiet([GIT_EXE, "add", "-A"])
    st = run_cmd_quiet([GIT_EXE, "status", "--porcelain"]).stdout
    if any(l.startswith(('M ', 'A ', 'D ', 'R ')) for l in st.splitlines()):
        run_cmd_quiet([GIT_EXE, "commit", "-m", "update: sync remaining project files"])
        if not push_with_retry():
            return False

    print("  [Git Push] ★ 成功推送所有更新至 GitHub！", flush=True)
    return True

if __name__ == "__main__":
    success = safe_push()
    sys.exit(0 if success else 1)

