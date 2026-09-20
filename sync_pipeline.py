# -*- coding: utf-8 -*-
"""
One-click Automated Sync Pipeline for 3D USD Asset Portal.
- Auto-starts in 3 seconds if no user interaction
- Cleans locks and heals Git repository
- Builds static data (thumbnails, 360 videos, assets.json)
- Safely batches and pushes to GitHub with real-time feedback
"""
import io
import os
import sys
import time
import subprocess
import shutil
from pathlib import Path

# Safe UTF-8 stdout configuration for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

def print_banner(title):
    print("\n" + "=" * 68, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 68, flush=True)

def prompt_filter_settings(auto_timeout=3):
    from config import get_batch_status_list, read_ignore_file_raw, write_ignore_file_raw
    
    batches = get_batch_status_list()
    ignored_batches = [b["name"] for b in batches if b["ignored"]]
    included_batches = [b["name"] for b in batches if not b["ignored"]]
    
    print("\n" + "=" * 68, flush=True)
    print("  【资产过滤与排除设置】(Ignore & Filter Settings)", flush=True)
    print("=" * 68, flush=True)
    print(f"  当前已排除的批次目录 ({len(ignored_batches)} 个):", flush=True)
    if ignored_batches:
        print(f"    🚫 {', '.join(ignored_batches)}", flush=True)
    else:
        print("    (无已排除批次)", flush=True)
    print(f"  当前待同步发布的批次目录 ({len(included_batches)} 个):", flush=True)
    print(f"    ✓ {', '.join(included_batches[:10])}{' ...' if len(included_batches) > 10 else ''}", flush=True)
    print("-" * 68, flush=True)
    print("  【操作提示】", flush=True)
    print("  • 无需操作: 3秒后自动全速启动同步与外网发布", flush=True)
    print("  • 或输入批次名后按【回车 Enter】: 添加排除规则", flush=True)
    print("-" * 68, flush=True)
    sys.stdout.flush()

    # Fast non-blocking check on Windows
    user_input = None
    try:
        import msvcrt
        print(f"  >>> 倒计时 {auto_timeout} 秒后自动开始 (按任意键暂停/输入排除批次): ", end="", flush=True)
        start_t = time.time()
        has_key = False
        while (time.time() - start_t) < auto_timeout:
            if msvcrt.kbhit():
                has_key = True
                break
            time.sleep(0.1)
        
        if has_key:
            # User pressed a key, switch to standard input
            first_char = msvcrt.getwche()
            rest = input()
            user_input = (first_char + rest).strip()
        else:
            print(" [自动启动]\n", flush=True)
    except Exception:
        # Fallback if msvcrt not available
        pass

    if user_input:
        clean_input = user_input.replace("\\", "").replace("/", "").strip()
        if clean_input:
            current_raw = read_ignore_file_raw()
            lines = [l.strip() for l in current_raw.splitlines() if l.strip()]
            if clean_input not in lines:
                lines.append(clean_input)
                write_ignore_file_raw("\n".join(lines))
                print(f"\n  ✓ 已成功将 [{clean_input}] 添加至排除列表 (ignore_batches.txt)！", flush=True)
            else:
                print(f"\n  ℹ️ [{clean_input}] 已在排除规则中。", flush=True)
    
    print("  [✓] 正在启动同步发布流程，请稍候...", flush=True)

def main():
    os.system("chcp 65001 >nul")
    os.system("color 0F")
    print_banner("【3D USD 资产平台】一键外网同步与发布工具 (稳定发布版)")
    print(f"  工作目录: {BASE_DIR}", flush=True)
    print(f"  当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

    # Prompt user with 3s auto countdown
    if "--auto" not in sys.argv:
        prompt_filter_settings(auto_timeout=3)

    # Step 1: Isaac Sim physics extraction (fast incremental update)
    print_banner("[第 1/3 步] 正在检查 USD 物理网格属性与语义元数据缓存...")
    isaac_python = Path(r"G:\JSUDS\isaac-sim-standalone-6.0.1-windows-x86_64\kit\python\python.exe")
    cache_json = BASE_DIR / "static" / "data" / "usd_physics_cache.json"
    if isaac_python.exists():
        try:
            print("  -> 正在调用 Isaac Sim 解析 USD 物理碰撞体、真实质量与语义元数据...", flush=True)
            subprocess.run([str(isaac_python), "extract_usd_physics.py"], cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
            print("  -> Isaac Sim 物理属性解析完成。", flush=True)
        except Exception as e:
            print(f"  -> 跳过物理属性深入解析: {e}", flush=True)
    elif cache_json.exists() and cache_json.stat().st_size > 100:
        print("  -> 物理属性元数据缓存已就绪，直接进入数据打包。", flush=True)
    else:
        print("  -> 未检测到 Isaac Sim Kit 环境，使用现有元数据缓存。", flush=True)

    # Step 2: Build static showcase (thumbs, videos, json)
    print_banner("[第 2/3 步] 正在扫描、提取并生成外网轻量化数据包与 360° 视频...")
    t0 = time.time()
    try:
        from build_static_showcase import build_showcase
        build_showcase()
    except Exception as e:
        print(f"  [ERROR] 构建失败: {e}", flush=True)
        input("\n按回车键退出...")
        sys.exit(1)

    # Sync index.html
    static_index = BASE_DIR / "static" / "index.html"
    root_index = BASE_DIR / "index.html"
    if static_index.exists():
        shutil.copy2(static_index, root_index)

    # Sync 404.html into the deploy output directory.
    # ★ Cloudflare Pages 的构建输出目录是 static/（不是仓库根目录），
    #   404.html 必须放在 static/ 里才会被部署；否则 Pages 会启用 SPA 兜底，
    #   把所有不存在的文件都返回 200 + index.html，从而隐藏真实的缺失。
    root_404 = BASE_DIR / "404.html"
    static_404 = BASE_DIR / "static" / "404.html"
    if root_404.exists():
        shutil.copy2(root_404, static_404)
        print("  已同步 404.html 到构建输出目录 static/", flush=True)

    # Step 3: Git push
    print_banner("[第 3/4 步] 正在安全提交并推送到 GitHub (媒体先行·元数据最后·自动断点重试)...")
    from push_to_git import safe_push
    push_ok = safe_push()

    # Step 4: Verify the public site truly matches local
    print_banner("[第 4/4 步] 正在校验外网站点与本地是否完全一致...")
    verify_ok = None
    if push_ok:
        try:
            from verify_sync import wait_and_verify
            verify_ok = wait_and_verify(seconds=240)
        except Exception as e:
            print(f"  [提示] 校验模块不可用: {e}", flush=True)
    else:
        print("  [跳过] 推送未完成，无需校验。", flush=True)

    print("\n" + "=" * 68)
    if push_ok and verify_ok is True:
        print("  ★【全部同步完毕，且外网校验通过】★")
        print("-" * 68)
        print("  1. 本地媒体已全部推送到 GitHub。")
        print("  2. Cloudflare Pages 已自动构建，线上内容与本地逐条核对一致。")
        print("-" * 68)
        print("  【外网展示地址】: https://asset-9n2.pages.dev/")
        print("  【本地管理地址】: http://127.0.0.1:8088/")
        print("=" * 68)
    elif push_ok and verify_ok is None:
        print("  ★【推送成功】★  (但线上校验未执行，建议稍后手动确认)")
        print("-" * 68)
        print("  可手动运行:  python verify_sync.py --wait 180")
        print("-" * 68)
        print("  【外网展示地址】: https://asset-9n2.pages.dev/")
        print("=" * 68)
    elif push_ok and verify_ok is False:
        print("  ▲【推送成功，但外网尚未完全一致】▲")
        print("-" * 68)
        print("  最常见原因: Cloudflare Pages 正在构建中（约 30-60 秒）。")
        print("  请稍候执行:  python verify_sync.py --wait 180")
        print("  若仍不一致，重新运行本脚本即可补齐剩余项。")
        print("=" * 68)
    else:
        print("  ▲【警告：推送未全部完成】▲")
        print("-" * 68)
        print("  本地媒体与元数据已生成，但上传到 GitHub 时遭遇网络断开或超时。")
        print("  保护机制已生效：元数据没有上线，所以外网站点仍是上一个完整状态，")
        print("  不会出现图片/视频打不开的情况。")
        print("  请检查网络/代理连接后，再次双击运行本脚本重试即可（已推批次无需重传）。")
        print("=" * 68)

if __name__ == "__main__":
    main()

