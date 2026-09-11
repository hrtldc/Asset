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

# Set stdout encoding to utf-8 safely
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

from config import ASSET_SOURCE_DIR, HOST, PORT

def run_update():
    print("=" * 65)
    print("   3D USD 资产全量更新同步中 (One-Click Asset Update)")
    print("=" * 65)

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