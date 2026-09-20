# -*- coding: utf-8 -*-
"""
线上一致性校验器 (Public Consistency Verifier)
==============================================================================
用途：在推送完成后，真实校验 https://asset-9n2.pages.dev/ 是否与本地
      http://127.0.0.1:8088/ 完全一致。

为什么需要它：
    Cloudflare Pages 存在 SPA 兜底路由 —— 请求一个不存在的文件时，
    它返回 HTTP 200 + index.html，而不是 404。因此只检查状态码会得到
    "全部正常" 的假象（曾经正是这个假象掩盖了 19 个缺失的媒体文件）。
    本脚本通过检查 Content-Type 与 Content-Range 总字节数来识破它。

用法：
    python verify_sync.py              # 校验一次
    python verify_sync.py --wait 180   # 等待 CDN 构建完成(最多 180 秒)，直到一致
    python verify_sync.py --quiet      # 只输出结论

退出码：0 = 完全一致；1 = 存在未同步项；2 = 校验本身失败(网络等)
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
LOCAL_DATA = BASE_DIR / "static" / "data" / "assets.json"
STATIC_DIR = BASE_DIR / "static"

REMOTE_BASE = "https://asset-9n2.pages.dev/"
REMOTE_DATA = REMOTE_BASE + "data/assets.json"

MEDIA_FIELDS = ("static_thumb_path", "static_video_path")


# --------------------------------------------------------------------------
# 网络层
# --------------------------------------------------------------------------
def _make_opener(no_proxy: bool):
    handlers = []
    if no_proxy:
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers)


def _req(path: str, extra_headers=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AssetPortalVerify/1.0)",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if extra_headers:
        headers.update(extra_headers)
    return urllib.request.Request(path, headers=headers)


def fetch_remote_json(opener, timeout=40):
    """拉取线上 assets.json（带时间戳绕开 CDN 缓存）。"""
    url = f"{REMOTE_DATA}?_t={int(time.time() * 1000)}"
    with opener.open(_req(url), timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw.decode("utf-8"))


def load_local_json():
    with open(LOCAL_DATA, "r", encoding="utf-8") as f:
        return json.load(f)


def wait_for_deploy(opener, local_ts, timeout=240, interval=10, verbose=True):
    """
    只轮询线上 assets.json 的 build_timestamp，判断 Cloudflare Pages 是否
    已完成本轮部署。比全量校验（519 次请求）轻得多，适合作为等待闸门。

    返回 True 表示线上元数据已更新到本轮版本（此时再做全量校验才有意义）。
    """
    deadline = time.time() + timeout
    attempt = 0
    while True:
        attempt += 1
        try:
            remote = fetch_remote_json(opener)
            rts = remote.get("build_timestamp")
            if rts == local_ts:
                if verbose:
                    print(f"  ✓ 线上部署已完成（第 {attempt} 次探测，约 {attempt * interval}s）")
                return True
            if verbose:
                print(f"  · 第 {attempt} 次探测：线上仍是旧版本 ({rts})，等待 Pages 构建...")
        except Exception as e:
            if verbose:
                print(f"  · 第 {attempt} 次探测失败: {type(e).__name__}，稍后重试...")
        if time.time() >= deadline:
            if verbose:
                print(f"  [超时] 等待 {timeout} 秒后线上仍未更新到本轮版本。")
            return False
        time.sleep(interval)


def wait_and_verify(seconds=240, no_proxy=False, quiet=False):
    """
    供 sync_pipeline.py 调用的便捷入口：先等部署完成，再做一次完整校验。
    返回 True / False，无法判断时返回 None。
    """
    if not LOCAL_DATA.exists():
        return None
    try:
        local = load_local_json()
    except Exception:
        return None

    opener = _make_opener(no_proxy)
    deployed = wait_for_deploy(
        opener, local.get("build_timestamp"),
        timeout=seconds, interval=10, verbose=not quiet,
    )
    if not deployed:
        if not quiet:
            print("\n  线上尚未更新到本轮版本，明细如下：")
        return run_verify(no_proxy=no_proxy, quiet=False) == 0
    if not quiet:
        print("\n  正在逐条核对线上媒体文件...")
    return run_verify(no_proxy=no_proxy, quiet=False) == 0


def probe_media(opener, rel_path: str, timeout=30):
    """
    探测单个线上媒体文件。
    返回 (kind, local_size_hint, detail)
      kind: "ok" | "missing" | "stale" | "error"
    """
    url = REMOTE_BASE + rel_path.lstrip("/")
    try:
        # 只取 2 字节，靠 Content-Range 拿真实总大小，避免下载整个视频
        with opener.open(
            _req(url, {"Range": "bytes=0-1"}), timeout=timeout
        ) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            crange = r.headers.get("Content-Range") or ""
            total = None
            if "/" in crange:
                try:
                    total = int(crange.rsplit("/", 1)[-1])
                except ValueError:
                    total = None
            if total is None:
                cl = r.headers.get("Content-Length")
                if cl and cl.isdigit():
                    total = int(cl)

            # ★ 关键：识别 SPA 兜底 —— 缺失文件被伪装成 200 text/html
            if "html" in ctype:
                return "missing", None, "返回 HTML 兜底页(文件不存在)"
            if total is None:
                return "error", None, f"无法确定体积 (ctype={ctype})"
            return "ok", total, ctype
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "missing", None, "HTTP 404"
        return "error", None, f"HTTP {e.code}"
    except Exception as e:
        return "error", None, f"{type(e).__name__}: {str(e)[:60]}"


# --------------------------------------------------------------------------
# 主校验
# --------------------------------------------------------------------------
def run_verify(no_proxy=False, quiet=False, workers=14):
    if not LOCAL_DATA.exists():
        print(f"[校验失败] 找不到本地元数据: {LOCAL_DATA}")
        print("          请先运行 sync_pipeline.py 生成静态展示包。")
        return 2

    with open(LOCAL_DATA, "r", encoding="utf-8") as f:
        local = json.load(f)

    opener = _make_opener(no_proxy)
    try:
        remote = fetch_remote_json(opener)
    except Exception as e:
        print(f"[校验失败] 无法访问线上数据: {type(e).__name__}: {e}")
        return 2

    problems = {"metadata": [], "missing": [], "stale": [], "error": []}

    # ---- 1. 元数据层 ----
    if remote.get("build_timestamp") != local.get("build_timestamp"):
        lt = local.get("build_timestamp")
        rt = remote.get("build_timestamp")
        problems["metadata"].append(
            f"build_timestamp 不一致: 本地={lt} 线上={rt}"
        )
    if remote.get("total") != local.get("total"):
        problems["metadata"].append(
            f"资产数量不一致: 本地={local.get('total')} 线上={remote.get('total')}"
        )

    local_keys = {a["batch"] + "/" + a["name"] for a in local.get("assets", [])}
    remote_keys = {a["batch"] + "/" + a["name"] for a in remote.get("assets", [])}
    only_local = sorted(local_keys - remote_keys)
    only_remote = sorted(remote_keys - local_keys)
    if only_local:
        problems["metadata"].append(
            f"本地有而线上无的资产 {len(only_local)} 个，例如: {only_local[:5]}"
        )
    if only_remote:
        problems["metadata"].append(
            f"线上有而本地无的资产 {len(only_remote)} 个，例如: {only_remote[:5]}"
        )

    # ---- 2. 媒体层（以本地 assets.json 为基准逐条核对） ----
    jobs = []          # (key, field, rel_path)
    for a in local.get("assets", []):
        key = a["batch"] + "/" + a["name"]
        for fld in MEDIA_FIELDS:
            rel = a.get(fld)
            if rel:
                jobs.append((key, fld, rel))

    def work(job):
        key, fld, rel = job
        pure = rel.split("?")[0]
        local_file = STATIC_DIR / pure.replace("/", os.sep)
        local_size = local_file.stat().st_size if local_file.exists() else None
        kind, total, detail = probe_media(opener, rel)
        return key, fld, pure, local_size, kind, total, detail

    results = []
    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(work, jobs):
                results.append(r)

    for key, fld, pure, local_size, kind, total, detail in results:
        if kind == "missing":
            problems["missing"].append((key, fld, pure))
        elif kind == "error":
            problems["error"].append((key, fld, pure, detail))
        elif kind == "ok":
            if local_size is not None and total is not None and total != local_size:
                problems["stale"].append((key, fld, pure, local_size, total))
            elif local_size is None:
                problems["missing"].append((key, fld, pure + "  (本地不存在)"))

    total_problems = sum(len(v) for v in problems.values())

    if quiet and total_problems == 0:
        print("一致")
        return 0

    print("=" * 70)
    print("  线上一致性校验报告")
    print("=" * 70)
    print(f"  校验媒体条目 : {len(jobs)}")
    print(f"  线上元数据时间: {remote.get('build_timestamp')}")
    print(f"  本地元数据时间: {local.get('build_timestamp')}")
    print("-" * 70)

    if total_problems == 0:
        print("  ★ 线上与本地完全一致，无任何差异。")
        print("=" * 70)
        return 0

    if problems["metadata"]:
        print(f"\n  [元数据滞后] {len(problems['metadata'])} 项")
        for m in problems["metadata"]:
            print(f"    - {m}")

    if problems["missing"]:
        print(f"\n  [线上文件缺失] {len(problems['missing'])} 项")
        print("    （注意：这些 URL 返回 200 + HTML，浏览器 Network 面板不会报错）")
        for key, fld, pure in problems["missing"][:40]:
            tag = "缩略图" if fld == "static_thumb_path" else "视频"
            print(f"    - [{tag}] {pure}")
        if len(problems["missing"]) > 40:
            print(f"    ... 其余 {len(problems['missing']) - 40} 项省略")

    if problems["stale"]:
        print(f"\n  [线上内容过期] {len(problems['stale'])} 项")
        for key, fld, pure, ls, ts in problems["stale"][:40]:
            print(f"    - 本地 {ls:>9} B / 线上 {ts:>9} B   {pure}")
        if len(problems["stale"]) > 40:
            print(f"    ... 其余 {len(problems['stale']) - 40} 项省略")

    if problems["error"]:
        print(f"\n  [探测失败] {len(problems['error'])} 项（可能是网络波动，可重试）")
        for key, fld, pure, detail in problems["error"][:15]:
            print(f"    - {pure}  ({detail})")

    print("\n" + "-" * 70)
    print(f"  结论：不一致，共 {total_problems} 处差异。")
    print("  处理方式：重新运行 sync_pipeline.py 完成推送后再次校验。")
    print("=" * 70)
    return 1


def main():
    ap = argparse.ArgumentParser(description="校验线上站点与本地是否一致")
    ap.add_argument("--wait", type=int, default=0,
                    help="先等待 Cloudflare Pages 构建完成，最多等待 N 秒，再校验")
    ap.add_argument("--interval", type=int, default=10,
                    help="等待模式下的轮询间隔秒数（默认 10）")
    ap.add_argument("--no-proxy", action="store_true", help="忽略系统代理直连")
    ap.add_argument("--quiet", action="store_true", help="只输出结论")
    args = ap.parse_args()

    if args.wait <= 0:
        sys.exit(run_verify(no_proxy=args.no_proxy, quiet=args.quiet))

    if not LOCAL_DATA.exists():
        print(f"[校验失败] 找不到本地元数据: {LOCAL_DATA}")
        sys.exit(2)

    local = load_local_json()
    opener = _make_opener(args.no_proxy)
    print("=" * 70)
    print(f"  等待 Cloudflare Pages 部署（最多 {args.wait} 秒）...")
    print("=" * 70)
    deployed = wait_for_deploy(
        opener, local.get("build_timestamp"),
        timeout=args.wait, interval=args.interval, verbose=not args.quiet,
    )
    if deployed:
        print("\n  部署已就绪，开始逐条核对线上媒体文件...")
    else:
        print("\n  线上仍是旧版本，下面报告的是当前实际差异：")
    sys.exit(run_verify(no_proxy=args.no_proxy, quiet=False))


if __name__ == "__main__":
    main()
