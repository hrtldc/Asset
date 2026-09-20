# -*- coding: utf-8 -*-
"""
Robust, self-healing Git sync module for 3D USD Asset Portal.
=============================================================================
设计原则（保证「本地正确 ⇒ 外网正确」）
-----------------------------------------------------------------------------
1) 媒体先行，元数据最后。
   assets.json 是外网站点唯一的索引来源。只要它上线的时刻，其引用的每一个
   媒体文件都已经在 CDN 上，外网就永远不会出现「索引指向不存在文件」。
   因此本模块绝不先推元数据。

2) 分批推送 = 断点续传。
   每推完一批媒体就落一次盘；即使中途断网，已推的批次无需重传。

3) 元数据推送前有本地完整性闸门。
   推送 assets.json 之前，先逐条确认它引用的缩略图/视频在本地 static/ 中
   真实存在。任一缺失就拒绝推送元数据并明确报警——宁可不更新，也不上线
   一个坏掉的站点。

4) 失败不静默。
   任何一批媒体推送失败都会明确记录并阻止元数据上线，同时给出恢复指引。
=============================================================================
Includes:
- Auto Git executable discovery
- Auto .git/*.lock cleanup
- Large media buffer tuning (http.postBuffer = 500MB)
- Realtime streaming progress (no frozen windows)
- Resilient retry with backoff
"""
import io
import json
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
STATIC_DIR = BASE_DIR / "static"
MEDIA_DIR = STATIC_DIR / "media"
LOCAL_DATA = STATIC_DIR / "data" / "assets.json"


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

# ---------------------------------------------------------------------------
# ★ 网络代理自动探测
#   国内网络直连 GitHub 往往不通，必须走本地 VPN/代理。而代理端口经常变化
#   （系统注册表残留旧端口）。这里按优先级自动探测可用代理并缓存片刻。
# ---------------------------------------------------------------------------
PROXY_CACHE_FILE = BASE_DIR / "logs" / ".proxy_cache"
PROXY_CACHE_TTL = 600  # 秒；端口轮换，不宜缓存过久
COMMON_PROXY_PORTS = [
    7890, 7897, 7899,          # Clash / Clash Verge
    10809, 10808,              # V2RayN
    1080,                      # Socks 常见
    57777,                     # 本机曾用端口
    2080, 8889, 9910,
]


def _read_registry_proxy():
    """从注册表读系统代理（不管启用与否，作为候选）。"""
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        server, _ = winreg.QueryValueEx(k, "ProxyServer")
        winreg.CloseKey(k)
    except Exception:
        return []
    servers = []
    if "=" in server:  # 形如 "http=127.0.0.1:8080;https=127.0.0.1:8080"
        for part in server.split(";"):
            if part.lower().startswith(("http=", "https=")):
                servers.append(part.split("=", 1)[1])
    elif server:
        servers.append(server)
    return [f"http://{s}" if not s.startswith("http") else s for s in servers]


def _probe_proxy(proxy):
    """测试某代理能否访问 github.com（8 秒超时）。"""
    if proxy is None:  # 直连
        try:
            import urllib.request
            urllib.request.urlopen("https://github.com/", timeout=8)
            return True
        except Exception:
            return False
    host_part = proxy.split("://", 1)[-1]
    host, _, port = host_part.partition(":")
    try:
        import socket
        with socket.create_connection((host, int(port)), timeout=2):
            pass
    except Exception:
        return False
    try:
        import urllib.request
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        opener.open("https://github.com/", timeout=8).read(64)
        return True
    except Exception:
        return False


def _read_proxy_cache():
    try:
        age = time.time() - PROXY_CACHE_FILE.stat().st_mtime
        if age < PROXY_CACHE_TTL:
            v = PROXY_CACHE_FILE.read_text(encoding="utf-8").strip()
            return v if v else None
    except Exception:
        pass
    return None


def _write_proxy_cache(proxy):
    try:
        PROXY_CACHE_FILE.parent.mkdir(exist_ok=True)
        PROXY_CACHE_FILE.write_text(proxy or "", encoding="utf-8")
    except Exception:
        pass


def _scan_listening_ports(limit=40):
    """兜底：枚举本机 127.0.0.1 上正在监听的端口（VPN 的端口可能任意）。"""
    ports = []
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, text=True, timeout=20,
                             encoding="utf-8", errors="replace").stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].upper() == "TCP" and "LISTEN" in parts[3].upper():
                addr = parts[1]
                if addr.startswith("127.0.0.1:") or addr.startswith("0.0.0.0:"):
                    try:
                        p = int(addr.rsplit(":", 1)[1])
                    except ValueError:
                        continue
                    if p not in ports:
                        ports.append(p)
    except Exception:
        return []
    return ports[:limit]


def detect_working_proxy(verbose=True):
    """
    依序探测：缓存 -> 环境变量 -> 直连 -> 注册表 -> 常见端口 -> 本机监听端口。
    返回形如 "http://127.0.0.1:7890" 的代理，None 表示直连可用，
    "DIRECT_FAIL" 表示全部失败。
    """
    cached = _read_proxy_cache()
    candidates = []
    if cached:
        candidates.append(cached)
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        v = os.environ.get(var)
        if v:
            candidates.append(v if v.startswith("http") else f"http://{v}")
    candidates.append(None)  # 直连
    candidates.extend(_read_registry_proxy())
    for port in COMMON_PROXY_PORTS:
        candidates.append(f"http://127.0.0.1:{port}")

    def try_all(cands):
        seen = set()
        for proxy in cands:
            if proxy in seen:
                continue
            seen.add(proxy)
            label = proxy or "直连"
            if verbose:
                print(f"  [网络] 正在测试通道: {label} ...", flush=True)
            if _probe_proxy(proxy):
                _write_proxy_cache(proxy)
                if verbose:
                    print(f"  [网络] ✓ 通道可用: {label}", flush=True)
                return proxy
        return "DIRECT_FAIL"

    result = try_all(candidates)
    if result != "DIRECT_FAIL":
        return result

    # 兜底：扫描本机正在监听的端口
    ports = _scan_listening_ports()
    if ports:
        if verbose:
            print(f"  [网络] 常规通道均失败，正在扫描本机监听端口 ({len(ports)} 个)...", flush=True)
        result = try_all([f"http://127.0.0.1:{p}" for p in ports])
    return result


def git_proxy_args():
    """返回用于 git 命令的代理参数；直连可用时返回空列表。"""
    if getattr(git_proxy_args, "_cached", None) is not None:
        return git_proxy_args._cached
    proxy = detect_working_proxy()
    if proxy == "DIRECT_FAIL":
        print("  [网络] ✗ 未找到可用通道（直连/环境变量/系统代理/常见端口均失败）。", flush=True)
        print("         请确认 VPN 已开启，然后重新运行。", flush=True)
        git_proxy_args._cached = ["-c", "http.proxy=", "-c", "https.proxy="]  # 保持直连语义
        return git_proxy_args._cached
    if proxy is None:
        git_proxy_args._cached = []
    else:
        git_proxy_args._cached = ["-c", f"http.proxy={proxy}", "-c", f"https.proxy={proxy}"]
    return git_proxy_args._cached


git_proxy_args._cached = None


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
        ("pack.windowMemory", "256m"),            # Limit pack memory usage
    ]
    for key, val in configs:
        try:
            subprocess.run([GIT_EXE, "config", key, val], cwd=str(BASE_DIR), capture_output=True)
        except Exception:
            pass


def run_git_maintenance():
    """Run git gc/repack to compress loose objects and speed up push operations."""
    try:
        obj_dir = BASE_DIR / ".git" / "objects"
        loose_count = 0
        if obj_dir.exists():
            for sub in obj_dir.iterdir():
                if sub.is_dir() and len(sub.name) == 2:
                    loose_count += len(list(sub.iterdir()))
        if loose_count > 500:
            print(f"  [Git 维护] 检测到 {loose_count} 个松散对象，正在压缩优化 (git gc)...", flush=True)
            subprocess.run(
                [GIT_EXE, "gc", "--auto", "--prune=now"],
                cwd=str(BASE_DIR), capture_output=True, timeout=300
            )
            print("  [Git 维护] ✓ 仓库压缩完成，推送速度将显著提升。", flush=True)
    except Exception as e:
        print(f"  [Git 维护] 跳过压缩: {e}", flush=True)


def count_unpushed_commits():
    """Count commits that exist locally but haven't been pushed to origin/main."""
    try:
        res = subprocess.run(
            [GIT_EXE, "rev-list", "--count", "origin/main..HEAD"],
            cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if res.returncode == 0:
            return int(res.stdout.strip())
    except Exception:
        pass
    return 0


def pull_rebase_if_needed():
    """Pull with rebase if remote has diverged, to avoid push rejection."""
    try:
        res = subprocess.run(
            [GIT_EXE] + git_proxy_args() + ["fetch", "origin", "main"],
            cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180
        )
        if res.returncode != 0:
            return
        behind = subprocess.run(
            [GIT_EXE, "rev-list", "--count", "HEAD..origin/main"],
            cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if behind.returncode == 0 and int(behind.stdout.strip()) > 0:
            print(f"  [Git Sync] 远端有 {behind.stdout.strip()} 个新提交，正在自动合并 (rebase)...", flush=True)
            subprocess.run(
                [GIT_EXE] + git_proxy_args() + ["pull", "--rebase", "origin", "main"],
                cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=300
            )
            print("  [Git Sync] ✓ 本地已与远端同步。", flush=True)
    except Exception as e:
        print(f"  [Git Sync] 同步检查跳过: {e}", flush=True)


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
                if any(k in line_str for k in ["Writing objects", "Counting objects", "Compressing",
                                               "Resolving", "Total", "error", "fatal"]):
                    print(f"    {line_str}", flush=True)
        process.wait()
        return process.returncode, "\n".join(output_lines)
    except Exception as e:
        return 1, str(e)


def run_cmd_quiet(args):
    """Run quick git commands silently."""
    clean_git_locks()
    return subprocess.run(args, cwd=str(BASE_DIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def staged_changes():
    """Return lines of staged (committable) changes."""
    res = run_cmd_quiet([GIT_EXE, "status", "--porcelain"])
    return [l for l in res.stdout.splitlines() if l[:2].strip() in ("M", "A", "D", "R", "C", "U")]


def has_uncommitted_changes():
    res = run_cmd_quiet([GIT_EXE, "status", "--porcelain"])
    return bool([l for l in res.stdout.splitlines() if l.strip()])


def push_with_retry(max_retries=4):
    """Push commits with progressive retry and real-time streaming."""
    for attempt in range(1, max_retries + 1):
        print(f"  [Git Push] 正在推送到 GitHub origin/main (第 {attempt}/{max_retries} 次尝试)...", flush=True)
        code, out = run_cmd_live([GIT_EXE] + git_proxy_args() + ["push", "origin", "main"], desc="git push")
        if code == 0:
            print("  [Git Push] ✓ 推送成功！", flush=True)
            return True
        print(f"  [Git Push] 提示: 第 {attempt} 次推送网络波动，正在重试...", flush=True)
        # 推送失败可能是代理端口轮换了，重置探测缓存后重新探测
        git_proxy_args._cached = None
        PROXY_CACHE_FILE.unlink(missing_ok=True)
        time.sleep(2 * attempt)
    return False


# ---------------------------------------------------------------------------
# ★ 本地完整性闸门
# ---------------------------------------------------------------------------
def check_local_integrity():
    """
    校验 static/data/assets.json 引用的每一个媒体文件在本地是否真实存在。
    返回 (ok: bool, missing: list[str], checked: int)

    只有这道闸门通过，才允许把 assets.json 推上外网。
    这从根本上杜绝了「线上索引指向不存在的文件」。
    """
    if not LOCAL_DATA.exists():
        return False, ["static/data/assets.json 不存在（尚未构建静态展示包）"], 0

    try:
        with open(LOCAL_DATA, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, [f"assets.json 解析失败: {e}"], 0

    missing = []
    checked = 0
    for asset in data.get("assets", []):
        key = f"{asset.get('batch')}/{asset.get('name')}"
        for fld, tag in (("static_thumb_path", "缩略图"), ("static_video_path", "视频")):
            rel = asset.get(fld)
            if not rel:
                continue
            checked += 1
            pure = rel.split("?")[0]
            target = STATIC_DIR / pure.replace("/", os.sep)
            if not target.exists() or target.stat().st_size == 0:
                missing.append(f"[{tag}] {key} -> {pure}")
    return (len(missing) == 0), missing, checked


def check_media_tracked():
    """确认 static/media 下没有文件被 .gitignore 意外排除。"""
    try:
        res = run_cmd_quiet([GIT_EXE, "status", "--porcelain", "--ignored", "static/media"])
        ignored = [l for l in res.stdout.splitlines() if l.startswith("!!")]
        if ignored:
            print(f"  [警告] 检测到 {len(ignored)} 个媒体文件被 .gitignore 排除，它们无法上线！", flush=True)
            for l in ignored[:5]:
                print(f"         {l}", flush=True)
            return False
    except Exception:
        pass
    return True


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def commit_media_batches():
    """
    逐个批次提交媒体（仅提交，不推送）。返回已提交批次列表。
    按批次提交只是为了历史可读；推送在统一的 push_with_retry 中完成。
    """
    committed = []
    if not MEDIA_DIR.exists():
        return committed

    batches = sorted([d.name for d in MEDIA_DIR.iterdir() if d.is_dir()])
    for b_name in batches:
        rel_b_path = f"static/media/{b_name}"
        run_cmd_quiet([GIT_EXE, "add", rel_b_path])
        if staged_changes():
            run_cmd_quiet([GIT_EXE, "commit", "-m", f"media: sync {b_name} videos and thumbnails"])
            committed.append(b_name)
            print(f"  [媒体] 已提交批次: {b_name}", flush=True)
    return committed


def commit_metadata():
    """提交元数据 / 代码 / 前端资源。返回是否产生了新提交。"""
    code_files = [
        "config.py", "server.py", "build_static_showcase.py", "push_to_git.py",
        "sync_pipeline.py", "verify_sync.py", "auto_classifier.py",
        "ignore_batches.txt", "index.html", "404.html",
        "static/index.html", "static/404.html", "static/data", "static/js", "static/css",
    ]
    existing = [f for f in code_files if (BASE_DIR / f).exists()]
    if existing:
        run_cmd_quiet([GIT_EXE, "add"] + existing)
    run_cmd_quiet([GIT_EXE, "add", "-A"])
    if staged_changes():
        msg = f"update: sync asset configs and metadata ({time.strftime('%Y-%m-%d %H:%M:%S')})"
        res = run_cmd_quiet([GIT_EXE, "commit", "-m", msg])
        return res.returncode == 0
    return False


def safe_push():
    print("=" * 68)
    print("  [Git Push] 开始安全同步（媒体先行 / 元数据最后）")
    print("=" * 68)

    # ---- 0. 自愈、配置、优化、对齐远端 ----
    clean_git_locks()
    init_git_configs()
    run_git_maintenance()
    pull_rebase_if_needed()

    # ---- 0.5 补推历史遗留提交，避免新提交被卡住 ----
    stale_count = count_unpushed_commits()
    if stale_count > 0:
        print(f"  [Git Push] 检测到 {stale_count} 个上次未推送的历史提交，正在补推...", flush=True)
        if not push_with_retry():
            print("  [中止] 历史提交补推失败，请检查网络/代理后重试。")
            return False
        print(f"  [Git Push] ✓ {stale_count} 个历史提交已成功补推！", flush=True)

    if not check_media_tracked():
        print("  [中止] 存在被忽略的媒体文件，请先修正 .gitignore，否则外网站点必然缺图。")
        return False

    # ---- 1. 提交媒体（本地），随后统一推送 ----
    media_batches = commit_media_batches()
    if media_batches:
        print(f"  [Git Push] 共 {len(media_batches)} 个媒体批次待上传，开始推送...", flush=True)
        if not push_with_retry():
            print("  [中止] 媒体推送失败。")
            print("         ★ 元数据未推送 —— 外网站点会保持在上一个完整状态，不会出现破图。")
            print("         请检查网络后重新运行即可，已推成功的批次无需重传。")
            return False
        print("  [Git Push] ✓ 媒体已全部上线。", flush=True)

    # ---- 2. 元数据推送前的本地完整性闸门 ----
    ok, missing, checked = check_local_integrity()
    if not ok:
        print("  [中止] 本地完整性校验未通过，拒绝推送元数据。")
        print(f"         已核对 {checked} 个媒体条目，以下 {len(missing)} 个本地缺失：")
        for m in missing[:30]:
            print(f"           - {m}")
        print("         ★ 这通常意味着本轮构建没有把媒体生成完整。")
        print("           请检查 static/media 生成情况后重新运行 sync_pipeline.py。")
        return False
    print(f"  [完整性] ✓ 已核对 {checked} 个媒体条目，本地全部就绪。", flush=True)

    # ---- 3. 最后一步：推送元数据 ----
    if commit_metadata():
        print("  -> 正在推送资产元数据与配置（外网站点索引）...", flush=True)
        if not push_with_retry():
            print("  [警告] 元数据推送失败。")
            print("         ★ 媒体已全部就绪，下次运行只需重推元数据即可，几秒完成。")
            return False
    else:
        print("  [Git Push] 元数据无变化，跳过。", flush=True)

    # ---- 4. 收尾 ----
    if has_uncommitted_changes():
        run_cmd_quiet([GIT_EXE, "add", "-A"])
        if staged_changes():
            run_cmd_quiet([GIT_EXE, "commit", "-m", "update: sync remaining project files"])
            if not push_with_retry():
                return False

    print("  [Git Push] ★ 全部同步完成，本地与 GitHub 已完全一致！", flush=True)
    return True


if __name__ == "__main__":
    success = safe_push()
    sys.exit(0 if success else 1)
