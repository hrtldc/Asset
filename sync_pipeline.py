# -*- coding: utf-8 -*-
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

def prompt_filter_settings():
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
    print("  • 直接按【回车 Enter】: 立即开始同步并推送到外网", flush=True)
    print("  • 或输入文件夹名 (如: qzs_test) 后按【回车 Enter】: 添加排除规则", flush=True)
    print("-" * 68, flush=True)
    sys.stdout.flush()
    
    try:
        user_input = input("  >>> 请按【回车 Enter】开始 (或输入排除名称): ").strip()
        if user_input:
            current_raw = read_ignore_file_raw()
            lines = [l.strip() for l in current_raw.splitlines() if l.strip()]
            if user_input not in lines:
                lines.append(user_input)
                write_ignore_file_raw("\n".join(lines))
                print(f"\n  ✓ 已成功将 [{user_input}] 添加至排除列表 (ignore_batches.txt)！", flush=True)
            else:
                print(f"\n  ℹ️ [{user_input}] 已在排除规则中。", flush=True)
        else:
            print("\n  [✓] 正在启动同步发布流程，请稍候...", flush=True)
    except (EOFError, KeyboardInterrupt):
        print("\n", flush=True)
        pass

def main():
    os.system("chcp 65001 >nul")
    os.system("color 0F")
    print_banner("【3D USD 资产平台】一键外网同步与发布工具")
    print(f"  工作目录: {BASE_DIR}", flush=True)
    print(f"  当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

    # Prompt user for optional extra ignore filters
    prompt_filter_settings()

    # Step 1: Isaac Sim physics extraction (optional)
    print_banner("[第 1/3 步] 正在检查 USD 物理网格属性缓存...")
    isaac_python = Path(r"g:\jsuds\isaacsim\kit\python\python.exe")
    cache_json = BASE_DIR / "static" / "data" / "usd_physics_cache.json"
    if cache_json.exists() and cache_json.stat().st_size > 100:
        print("  -> 物理属性元数据缓存已就绪，直接进入数据打包。", flush=True)
    elif isaac_python.exists():
        try:
            print("  -> 正在调用 Isaac Sim 解析 USD 物理碰撞体...", flush=True)
            res = subprocess.run([str(isaac_python), "extract_usd_physics.py"], cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
            print("  -> Isaac Sim 物理属性解析完成。", flush=True)
        except Exception as e:
            print(f"  -> 跳过物理属性深入解析: {e}", flush=True)
    else:
        print("  -> 未检测到 Isaac Sim Kit 环境，使用现有元数据缓存。", flush=True)

    # Step 2: Build static showcase (thumbs, videos, json)
    print_banner("[第 2/3 步] 正在扫描、提取并生成外网轻量化数据包与 360° 视频...")
    py_exe = sys.executable
    t0 = time.time()
    try:
        from build_static_showcase import build_showcase
        build_showcase()
    except Exception as e:
        print(f"  [ERROR] 构建失败: {e}")
        input("\n按回车键退出...")
        sys.exit(1)

    # Sync index.html
    static_index = BASE_DIR / "static" / "index.html"
    root_index = BASE_DIR / "index.html"
    if static_index.exists():
        shutil.copy2(static_index, root_index)

    # Step 3: Git push
    print_banner("[第 3/3 步] 正在安全提交并推送到 GitHub (带断点自动重试)...")
    from push_to_git import safe_push
    push_ok = safe_push()

    print("\n" + "=" * 68)
    if push_ok:
        print("  ★【执行成功！全部同步完毕】★")
        print("-" * 68)
        print("  1. 本地所有资产、WebP 封面与 360° 关节视频已成功推送至 GitHub！")
        print("  2. Cloudflare Pages 已自动触发全球 CDN 构建（约 20-30 秒生效）。")
        print("-" * 68)
        print("  【外网展示地址】: https://asset-9n2.pages.dev/")
        print("  【本地管理地址】: http://127.0.0.1:8088/")
        print("=" * 68)
    else:
        print("  ▲【警告：推送未完成】▲")
        print("-" * 68)
        print("  本地媒体已生成，但上传到 GitHub 时遭遇网络断开或超时。")
        print("  请检查网络/代理连接后，再次双击运行桌面脚本重试即可。")
        print("=" * 68)

if __name__ == "__main__":
    main()
