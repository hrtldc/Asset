# -*- coding: utf-8 -*-
"""
停止自动同步守护进程 (watch_and_sync.py)
==============================================================================
通过命令行特征精确查找并结束守护进程，同时清理锁文件。
用独立的 Python 脚本而不是纯批处理实现，是为了避免 Windows 批处理里
多层引号嵌套导致的转义错误。
"""
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
LOCK_FILE = BASE_DIR / "logs" / ".autosync.lock"


def kill_watchers():
    ps_script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*watch_and_sync*' "
        "-and $_.Name -like '*python*' } | "
        "ForEach-Object { "
        "Write-Output ('KILLED ' + $_.ProcessId); "
        "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        out = (res.stdout or "").strip()
        killed = [l for l in out.splitlines() if l.startswith("KILLED")]
        return killed, (res.stderr or "").strip()
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"


def main():
    print("=" * 62)
    print("  正在停止自动同步守护进程...")
    print("=" * 62)

    killed, err = kill_watchers()
    if killed:
        for k in killed:
            print(f"  ✓ 已结束进程 {k.replace('KILLED ', 'PID ')}")
    else:
        print("  未发现正在运行的守护进程。")
    if err:
        print(f"  [提示] {err[:200]}")

    if LOCK_FILE.exists():
        try:
            LOCK_FILE.unlink()
            print("  ✓ 已清理锁文件。")
        except Exception as e:
            print(f"  [警告] 锁文件清理失败: {e}")

    print("=" * 62)
    print("  完成。")


if __name__ == "__main__":
    main()
