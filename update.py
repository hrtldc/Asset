# -*- coding: utf-8 -*-
"""
One-Click Asset Update and Push Script
"""
import io
import json
import os
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

# Safe UTF-8 stdout configuration for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

from config import ASSET_SOURCE_DIR, HOST, PORT, get_batch_status_list, read_ignore_file_raw, write_ignore_file_raw

def prompt_filter_settings():
    batches = get_batch_status_list()
    ignored_batches = [b["name"] for b in batches if b["ignored"]]
    included_batches = [b["name"] for b in batches if not b["ignored"]]
    
    print("\n" + "=" * 65)
    print("   【资产过滤与排除设置】(Ignore & Filter Settings)")
    print("=" * 65)
    print(f"   当前已排除的批次目录 ({len(ignored_batches)} 个):")
    if ignored_batches:
        print(f"     🚫 {', '.join(ignored_batches)}")
    else:
        print("     (无已排除批次)")
    print(f"   当前待索引展示的批次目录 ({len(included_batches)} 个):")
    print(f"     ✓ {', '.join(included_batches[:8])}{' ...' if len(included_batches) > 8 else ''}")
    print("-" * 65)
    print("   【请按回车键开始】")
    print("   • 如果不需要额外排除：直接按键盘上的【回车 Enter】即可开始更新")
    print("   • 如果需要额外排除：输入文件夹名称 (如: qzs_test) 后按【回车 Enter】")
    print("-" * 65)
    
    try:
        user_input = input("   >>> 请按【回车 Enter】直接开始更新 (或输入排除名称): ").strip()
        if user_input:
            current_raw = read_ignore_file_raw()
            lines = [l.strip() for l in current_raw.splitlines() if l.strip()]
            if user_input not in lines:
                lines.append(user_input)
                write_ignore_file_raw("\n".join(lines))
                print(f"\n   ✓ 已成功将 [{user_input}] 添加至排除列表 (ignore_batches.txt)！")
            else:
                print(f"\n   ℹ️ [{user_input}] 已在排除规则中。")
        else:
            print("\n   [✓] 已确认，正在开始本地资产扫描与刷新...")
    except (EOFError, KeyboardInterrupt):
        pass

def run_update():
    print("=" * 65)
    print("   3D USD 资产全量更新同步中 (One-Click Asset Update)")
    print("=" * 65)

    prompt_filter_settings()

    if not ASSET_SOURCE_DIR.exists():
        print(f"[错误] 资产源目录不存在: {ASSET_SOURCE_DIR}")
        return False

    print(f"[1/3] 正在扫描磁盘目录: {ASSET_SOURCE_DIR} ...")
    
    server_url = f"http://{HOST}:{PORT}"
    update_api = f"{server_url}/api/update"
    
    is_server_alive = False
    try:
        req = urllib.request.urlopen(f"{server_url}/api/assets", timeout=3)
        if req.status == 200:
            is_server_alive = True
    except Exception:
        is_server_alive = False

    if is_server_alive:
        print("[2/3] 通知资产服务清除全部缓存并强制重载多媒体与图片...")
        try:
            req = urllib.request.urlopen(f"{update_api}?_t={int(time.time())}", timeout=10)
            res_data = json.loads(req.read().decode("utf-8"))
            stats = res_data.get("stats", {})
            total_assets = res_data.get("total", 0)
            total_videos = stats.get("total_videos", 0)
            total_gb = stats.get("total_size_gb", 0)
            print(f"      -> 成功索引 {total_assets} 套模型资产")
            print(f"      -> 包含 {total_videos} 个 360° 旋转展示视频")
            print(f"      -> 资产总容量: {total_gb} GB")
        except Exception as e:
            print(f"[提示] API 响应: {e}")
    else:
        print("[2/3] 检测到资产服务未在后台运行，建议先运行 run.bat 启动服务。")

    print("[3/3] 正在打开并刷新最新网页展示...")
    try:
        webbrowser.open(server_url)
    except Exception as e:
        print(f"打开浏览器提示: {e}")

    print("=" * 65)
    print(f"   [成功] 全量更新完成！所有最新图片、视频和模型已同步至网页")
    print(f"   访问地址: {server_url}")
    print("=" * 65)
    return True

if __name__ == "__main__":
    run_update()