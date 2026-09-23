# -*- coding: utf-8 -*-
"""
资产源目录守护进程 (Auto Sync Watcher)
==============================================================================
目的：让「127 正确」自动等于「外网正确」。

它持续监视上游物理化管线（SimReadyBatch）的输出目录
    G:\\Simreay\\output
一旦检测到新资产落地 / 已有资产被改写，就在"静默期"（确认上游写完之后）
自动执行一次 sync_pipeline.py，并完成线上一致性校验。

特性：
  - 防抖：文件还在写入时不会触发，等目录安静下来才开始同步
  - 幂等：内容是"快照签名"比对，重复触发不会重复上传
  - 单实例：通过锁文件防止多个同步进程互相踩踏
  - 日志：全部输出写入 logs/autosync.log，便于事后追溯

用法：
    python watch_and_sync.py                # 常驻守护（默认 30s 轮询 / 60s 静默）
    python watch_and_sync.py --once         # 只做一次检查，不常驻（用于测试）
    python watch_and_sync.py --interval 15 --debounce 45
    python watch_and_sync.py --dry-run      # 只打印将要执行的动作，不真的同步
"""
import argparse
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "autosync.log"
LOCK_FILE = LOG_DIR / ".autosync.lock"

from config import ASSET_SOURCE_DIR as SOURCE_DIR, is_batch_ignored


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 目录快照签名
# ---------------------------------------------------------------------------
def snapshot(root: Path):
    """返回 (签名, 文件数, 总字节)。签名变化即代表源目录内容有变。"""
    items = []
    total_bytes = 0
    root_str = str(root).rstrip("\\/")
    for dirpath, dirnames, filenames in os.walk(root):
        # 过滤顶层被忽略的批次（如 *_Joint, *_wip, .* 等）
        if dirpath.rstrip("\\/") == root_str:
            dirnames[:] = [d for d in dirnames if not is_batch_ignored(d)]
        dirnames.sort()
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            items.append((os.path.relpath(p, root), st.st_size, int(st.st_mtime)))
            total_bytes += st.st_size
    items.sort()
    sig = hashlib.md5(repr(items).encode("utf-8", "replace")).hexdigest()
    return sig, len(items), total_bytes


def acquire_lock():
    """单实例锁。返回 False 表示已有同步在进行。"""
    if LOCK_FILE.exists():
        try:
            age = time.time() - LOCK_FILE.stat().st_mtime
            pid = LOCK_FILE.read_text(encoding="utf-8").strip()
            if age < 6 * 3600:
                log(f"已有同步进程在运行 (pid={pid}, 锁定 {int(age)}s)，本次跳过。")
                return False
            log("检测到过期锁文件，自动清理。")
        except Exception:
            pass
    try:
        LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception as e:
        log(f"无法创建锁文件: {e}")
        return False


def release_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 同步执行
# ---------------------------------------------------------------------------
def run_sync(dry_run=False):
    if dry_run:
        log("[DRY-RUN] 将执行: python sync_pipeline.py --auto")
        return True

    log("=" * 62)
    log("检测到源目录变更，开始自动同步到外网...")
    log("=" * 62)

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.run(
            [sys.executable, str(BASE_DIR / "sync_pipeline.py"), "--auto"],
            cwd=str(BASE_DIR), env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=3600,
        )
        tail = (proc.stdout or "").strip().splitlines()[-25:]
        for line in tail:
            log("  | " + line)
        if proc.returncode != 0:
            log(f"同步流程返回非零退出码: {proc.returncode}")
            err = (proc.stderr or "").strip()
            if err:
                log("  stderr: " + err[-400:])
            return False
        log("自动同步完成。")
        return True
    except subprocess.TimeoutExpired:
        log("同步超时（超过 1 小时），已中止。")
        return False
    except Exception as e:
        log(f"同步执行异常: {type(e).__name__}: {e}")
        return False


def main():
    ap = argparse.ArgumentParser(description="监视源目录并自动同步到外网")
    ap.add_argument("--interval", type=int, default=30, help="轮询间隔秒数（默认 30）")
    ap.add_argument("--debounce", type=int, default=60, help="静默等待秒数（默认 60）")
    ap.add_argument("--once", action="store_true", help="只检查一次，不常驻")
    ap.add_argument("--dry-run", action="store_true", help="只打印动作，不真的同步")
    ap.add_argument("--source", default=str(SOURCE_DIR), help="源资产目录")
    args = ap.parse_args()

    source = Path(args.source)
    if not source.exists():
        # 若是常驻模式，尝试等待网络连接 (最多重试 6 次，共 30 秒)
        if not args.once:
            log(f"[提示] 源目录暂不可达: {source}，正在等待网络共享连接...")
            for retry in range(6):
                time.sleep(5)
                if source.exists():
                    break
        if not source.exists():
            log(f"[错误] 源目录不可达: {source}")
            log("       请确认网络畅通且共享服务器 \\\\TOP2 处于连接状态。守护进程退出。")
            sys.exit(2)

    log("=" * 62)
    log("  3D USD 资产平台 · 自动同步守护进程已启动")
    log("=" * 62)
    log(f"  监视目录 : {source}")
    log(f"  轮询间隔 : {args.interval} 秒")
    log(f"  静默等待 : {args.debounce} 秒")
    log(f"  日志文件 : {LOG_FILE}")
    log("  (按 Ctrl+C 退出)")

    try:
        last_sig, count, nbytes = snapshot(source)
        log(f"  初始状态 : {count} 个文件 / {nbytes / 1024 ** 3:.2f} GB")
    except Exception as e:
        log(f"[错误] 无法读取源目录: {e}")
        sys.exit(2)

    # ---- 单次检查模式：只比一次就退出，便于测试与人工触发 ----
    if args.once:
        time.sleep(args.interval)
        sig, count, nbytes = snapshot(source)
        if sig == last_sig:
            log("源目录无变化，无需同步。")
            sys.exit(0)
        log(f"检测到变更 ({count} 个文件 / {nbytes / 1024 ** 3:.2f} GB)，执行一次同步。")
        if acquire_lock():
            try:
                ok = run_sync(args.dry_run)
            finally:
                release_lock()
            sys.exit(0 if ok else 1)
        sys.exit(0)

    pending_since = None

    while True:
        try:
            time.sleep(args.interval)
            sig, count, nbytes = snapshot(source)

            if sig != last_sig:
                # 内容变化：开始/延长静默窗口
                pending_since = time.time()
                last_sig = sig
                log(f"检测到变更 ({count} 个文件 / {nbytes / 1024 ** 3:.2f} GB)，"
                    f"等待 {args.debounce} 秒静默期...")
                continue

            if pending_since is not None:
                quiet = time.time() - pending_since
                if quiet >= args.debounce:
                    pending_since = None
                    if acquire_lock():
                        try:
                            run_sync(args.dry_run)
                            # 同步后重新取签名，避免构建期间的读写造成误判
                            last_sig, count, nbytes = snapshot(source)
                        finally:
                            release_lock()
                else:
                    log(f"静默期剩余 {int(args.debounce - quiet)} 秒...")

        except KeyboardInterrupt:
            log("收到中断信号，守护进程退出。")
            release_lock()
            sys.exit(0)
        except Exception as e:
            log(f"[警告] 轮询异常（将继续运行）: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
