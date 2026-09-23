# -*- coding: utf-8 -*-
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path
from PIL import Image

# Safe UTF-8 stdout configuration for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
from config import ASSET_SOURCE_DIR
STATIC_DIR = BASE_DIR / "static"
STATIC_MEDIA_DIR = STATIC_DIR / "media"
STATIC_DATA_DIR = STATIC_DIR / "data"

STATIC_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DATA_DIR.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, str(BASE_DIR))
from server import scan_assets
from config import is_batch_ignored
from transcode_media import MediaTranscoder

def build_showcase():
    print("=" * 60)
    print("  正在构建外网轻量级静态展示网站包...")
    print("=" * 60)

    # Clean up any leftover ignored batch directories in static/media
    if STATIC_MEDIA_DIR.exists():
        for d in STATIC_MEDIA_DIR.iterdir():
            if d.is_dir() and is_batch_ignored(d.name):
                try:
                    shutil.rmtree(d)
                    print(f"  -> 已清理已排除的临时媒体目录: {d.name}")
                except Exception as e:
                    print(f"  -> 清理失败 {d.name}: {e}")

    t0 = time.time()
    raw_assets = scan_assets(force_reload=True)
    print(f"[1/4] 扫描到 {len(raw_assets)} 套模型资产 (已自动过滤未处理/WIP文件夹)...")

    # 构建期视频转码器：ffmpeg 自动探测（不安装进仓库、不硬编码路径）。
    # 探测不到时退化为直接复制源文件——站点功能不受影响，仅失去体积收益。
    sample_mp4 = None
    for _a in raw_assets:
        if _a.get("video_rel_path"):
            _cand = Path(_a["abs_path"]) / _a["video_rel_path"]
            if _cand.exists():
                sample_mp4 = str(_cand)
                break
    transcoder = MediaTranscoder(sample_path=sample_mp4)

    static_assets = []
    total_videos_copied = 0
    total_thumbs_copied = 0

    for idx, asset in enumerate(raw_assets, 1):
        batch = asset["batch"]
        name = asset["name"]
        asset_media_dir = STATIC_MEDIA_DIR / batch / name
        asset_media_dir.mkdir(parents=True, exist_ok=True)

        target_thumb_name = None
        target_video_name = None

        if asset.get("thumbnail_rel_path"):
            src_png = Path(asset["abs_path"]) / asset["thumbnail_rel_path"]
            dst_webp = asset_media_dir / "thumb.webp"
            if src_png.exists():
                src_mtime = src_png.stat().st_mtime
                needs_update = not dst_webp.exists() or dst_webp.stat().st_size == 0 or dst_webp.stat().st_mtime < src_mtime
                if needs_update:
                    try:
                        with Image.open(src_png) as im:
                            im_conv = im.convert("RGBA") if im.mode in ("RGBA", "LA") else im.convert("RGB")
                            im_conv.thumbnail((540, 540), Image.Resampling.LANCZOS)
                            im_conv.save(dst_webp, "WEBP", quality=85)
                    except Exception as e:
                        print(f"Thumb error {name}: {e}")
                if dst_webp.exists():
                    target_thumb_name = f"media/{batch}/{name}/thumb.webp"
                    total_thumbs_copied += 1

        if asset.get("video_rel_path"):
            src_mp4 = Path(asset["abs_path"]) / asset["video_rel_path"]
            dst_mp4 = asset_media_dir / src_mp4.name
            if src_mp4.exists():
                src_stat = src_mp4.stat()
                # 转码为发布压缩版（幂等：源未变且档位未变则跳过；失败自动退化为复制）
                transcoder.process(src_mp4, dst_mp4)
                # 版本号 = 源 mtime + 转码参数签名：源变更或档位变更都会让 URL 失效，
                # 避免 immutable 长缓存下取到旧档位产物
                v_stamp = transcoder.version_tag(src_mp4)
                target_video_name = f"media/{batch}/{name}/{src_mp4.name}?v={v_stamp}"
                total_videos_copied += 1

        if target_thumb_name and dst_webp.exists():
            target_thumb_name = f"{target_thumb_name}?v={int(dst_webp.stat().st_mtime)}"

        static_asset = dict(asset)
        static_asset["static_thumb_path"] = target_thumb_name
        static_asset["static_video_path"] = target_video_name
        static_asset.pop("abs_path", None)
        static_asset.pop("all_files", None)
        static_asset.pop("usd_files", None)
        static_asset.pop("image_files", None)
        static_assets.append(static_asset)

        if idx % 20 == 0 or idx == len(raw_assets):
            print(f"  -> 处理进度: {idx}/{len(raw_assets)} 套模型...")

    # ------------------------------------------------------------------
    # 清理孤儿媒体目录
    # 背景：资产源目录会被上游管线整体重建，某些批次目录会消失或改名。
    #      旧的 static/media/<批次> 会被永久遗留在仓库里并持续推送到 CDN，
    #      造成线上文件数远多于实际被引用的数量（占额度、拖慢构建）。
    # 安全护栏：扫描结果为 0 时绝不执行清理（例如 G 盘未挂载），
    #          否则会把整个媒体库误删。
    # ------------------------------------------------------------------
    if len(static_assets) == 0:
        print("  [警告] 本次扫描到 0 个资产，跳过孤儿媒体清理（防止误删）。")
    elif STATIC_MEDIA_DIR.exists():
        live_batches = {a["batch"] for a in static_assets}
        orphans = [d for d in STATIC_MEDIA_DIR.iterdir()
                   if d.is_dir() and d.name not in live_batches]
        if orphans:
            print(f"  -> 检测到 {len(orphans)} 个已废弃的孤儿媒体目录，正在清理...")
        for d in orphans:
            try:
                shutil.rmtree(d)
                print(f"     ✓ 已清理孤儿目录: {d.name}")
            except Exception as e:
                print(f"     ✗ 清理失败 {d.name}: {e}")

    from collections import Counter
    cat_counter = Counter(a["category"] for a in static_assets)
    sorted_categories = [cat for cat, _ in cat_counter.most_common()]
    batch_counter = Counter(a["batch"] for a in static_assets)
    sorted_batches = sorted(list(batch_counter.keys()))

    total_videos = sum(1 for a in static_assets if a["has_video"])
    total_usds = sum(1 for a in static_assets if a["has_usd"])
    total_size_gb = round(sum(a["total_size_bytes"] for a in static_assets) / (1024**3), 2)

    export_json = {
        "assets": static_assets,
        "total": len(static_assets),
        "batches": sorted_batches,
        "categories": sorted_categories,
        "category_counts": dict(cat_counter),
        "batch_counts": dict(batch_counter),
        "stats": {
            "total_assets": len(static_assets),
            "total_videos": total_videos,
            "total_usds": total_usds,
            "total_batches": len(sorted_batches),
            "total_categories": len(sorted_categories),
            "total_size_gb": total_size_gb
        },
        "build_timestamp": int(time.time()),
        "is_static_showcase": True
    }

    out_file = STATIC_DATA_DIR / "assets.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(export_json, f, ensure_ascii=False, indent=2)

    print(f"[3/4] 成功导出静态元数据: {out_file}")
    print(f"[4/4] 统计: 已复制/生成 {total_thumbs_copied} 个缩略图, {total_videos_copied} 个 360° 视频")
    print(f"      视频压缩: {transcoder.summary()}")
    print(f"Done in {time.time()-t0:.2f}s")

if __name__ == "__main__":
    build_showcase()
