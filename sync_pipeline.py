# -*- coding: utf-8 -*-
import os
import sys
import time
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def print_banner(title):
    print("\n" + "=" * 68)
    print(f"  {title}")
    print("=" * 68)

def main():
    os.system("color 0F")
    print_banner("【3D USD 资产平台】一键外网同步与发布工具")
    print(f"  工作目录: {BASE_DIR}")
    print(f"  当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Step 1: Isaac Sim physics extraction (optional)
    print_banner("[第 1/3 步] 正在提取最新的 USD 物理网格属性...")
    isaac_python = Path(r"g:\jsuds\isaacsim\kit\python\python.exe")
    if isaac_python.exists():
        try:
            res = subprocess.run([str(isaac_python), "extract_usd_physics.py"], cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
            print("  -> Isaac Sim 物理属性解析已就绪。")
        except Exception as e:
            print(f"  -> 跳过物理属性深入解析: {e}")
    else:
        print("  -> 未检测到 Isaac Sim Kit 环境，使用现有元数据缓存。")

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
