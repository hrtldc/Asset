"""
3D USD Asset Portal Backend Server
FastAPI + Uvicorn
"""
import io
import json
import mimetypes
import os
import re
import subprocess
import time
import zipfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

import uvicorn
from PIL import Image
from fastapi import FastAPI, HTTPException, Request, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import ASSET_SOURCE_DIR, HOST, PORT, STATIC_DIR, NAME_TRANSLATIONS

app = FastAPI(title="3D USD Asset Portal", version="1.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure static directories exist
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "css").mkdir(parents=True, exist_ok=True)
THUMB_CACHE_DIR = STATIC_DIR / "cache" / "thumbs"
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if (STATIC_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=str(STATIC_DIR / "js")), name="js")
if (STATIC_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=str(STATIC_DIR / "css")), name="css")
if (STATIC_DIR / "data").exists():
    app.mount("/data", StaticFiles(directory=str(STATIC_DIR / "data")), name="data")

# Cache for asset manifests & assets
_manifest_cache: Dict[str, dict] = {}
_cached_assets: Optional[List[dict]] = None
_last_scan_timestamp: float = 0.0
CACHE_TTL_SECONDS = 30.0


def get_or_create_thumbnail(source_file: Path) -> Path:
    """Generate or retrieve compressed WebP thumbnail (~15-30 KB instead of 3MB)."""
    try:
        mtime_int = int(source_file.stat().st_mtime)
        batch = source_file.parent.parent.name
        asset = source_file.parent.name
        cache_name = f"{batch}_{asset}_{source_file.stem}_{mtime_int}.webp"
        cache_path = THUMB_CACHE_DIR / cache_name
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return cache_path

        with Image.open(source_file) as im:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                im_conv = im.convert("RGBA")
            else:
                im_conv = im.convert("RGB")
            im_conv.thumbnail((540, 540), Image.Resampling.LANCZOS)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            im_conv.save(cache_path, "WEBP", quality=85, method=4)
        return cache_path
    except Exception as e:
        print(f"[Thumbnail Error] {source_file}: {e}")
        return source_file


def classify_category(folder_name: str, semantic_class: Optional[str] = None):
    """Accurately classify asset into human-friendly Chinese & English categories, class and QCode."""
    fn = folder_name.lower()
    sem = (semantic_class or "").lower()
    target = fn + " " + sem

    if "bingxiang" in target or "refrigerator" in target:
        return ("Refrigerator", "冰箱", "Refrigerator", "Q37867", "Refrigerator")
    elif "yushigui" in target or "bathroomvanity" in target:
        return ("Bathroom Vanity", "浴室柜", "Bathroom Vanity", "Q1321517", "BathroomVanity")
    elif "chuangtougui" in target or "nightstand" in target:
        return ("Nightstand", "床头柜", "Nightstand", "Q1321517", "Nightstand")
    elif "xiegui" in target or "shoecabinet" in target:
        return ("Shoe Cabinet", "鞋柜", "Shoe Cabinet", "Q1321517", "ShoeCabinet")
    elif any(k in target for k in ["zhediemen", "tuilamen", "pingbanmen", "shuangkaimen", "door", "foldingdoor", "slidingdoor"]) or fn.startswith(("sm_men", "sm-men")):
        return ("Door", "门类", "Doors", "Q36794", "Door")
    elif any(k in target for k in ["kaoxiang", "weibolu", "xiaodugui", "xiwanji", "microwave", "oven", "dishwasher"]):
        return ("Kitchen Appliance", "厨房电器", "Kitchen Appliances", "Q127950", "KitchenAppliance")
    elif "shuzhuangtai" in target or "dressingtable" in target:
        return ("Dressing Table", "梳妆台", "Tables & Vanities", "Q204370", "DressingTable")
    elif "chaji" in target or "coffeetable" in target:
        return ("Coffee Table", "茶几", "Tables & Vanities", "Q1151608", "CoffeeTable")
    elif "zhongdao" in target or "kitchenisland" in target:
        return ("Kitchen Island", "中岛台", "Kitchen Island", "Q148600", "KitchenIsland")
    elif any(k in target for k in ["chazuo", "shujuxian", "cable"]):
        return ("Cable & Outlet", "数码配件", "Cables & Outlets", "Q16865280", "Cable")
    elif any(k in target for k in ["guizi", "chugui", "sidecabinet", "kitchencabinet", "shounaigui", "zhuangshigui", "hongjiugui", "shuiba", "cabinet", "storage"]):
        return ("Cabinet", "柜类", "Cabinets & Storage", "Q1321517", "Cabinet")
    elif "bed" in target:
        return ("Bed", "床具", "Beds", "Q42177", "Bed")
    return ("Asset", "其他资产", "Other", "Q223557", "PhysicalAsset")


def load_batch_manifests():
    """Load all _simready_manifest.json files from batches."""
    manifests = {}
    if not ASSET_SOURCE_DIR.exists():
        return manifests
    for batch_entry in os.scandir(ASSET_SOURCE_DIR):
        if batch_entry.is_dir():
            manifest_file = Path(batch_entry.path) / "_simready_manifest.json"
            if manifest_file.exists():
                try:
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        manifests[batch_entry.name] = data
                except Exception as e:
                    print(f"Error loading manifest from {manifest_file}: {e}")
    return manifests


def load_usd_physics_cache():
    """Load pre-extracted authored USD physics properties (mass, frictions)."""
    cache_path = STATIC_DIR / "data" / "usd_physics_cache.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading usd_physics_cache: {e}")
    return {}


_usd_physics_cache = load_usd_physics_cache()


def get_physics_specs(manifest_info: Optional[dict], category_en: str, item_name: str, asset_key: str = ""):
    """Extract physical properties or compute realistic physics defaults based on category."""
    global _usd_physics_cache
    if not _usd_physics_cache:
        _usd_physics_cache = load_usd_physics_cache()

    DEFAULTS = {
        "Cabinets & Storage": {"mass": 45.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Bathroom Vanity": {"mass": 38.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Doors": {"mass": 28.5, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Nightstand": {"mass": 18.2, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Shoe Cabinet": {"mass": 32.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Kitchen Appliances": {"mass": 55.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Tables & Vanities": {"mass": 22.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Kitchen Island": {"mass": 85.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Beds": {"mass": 65.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Cables & Outlets": {"mass": 0.45, "static_friction": 0.6, "dynamic_friction": 0.45, "restitution": 0.05},
        "Other": {"mass": 25.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05}
    }
    fallback = DEFAULTS.get(category_en, DEFAULTS["Other"])

    mass = None
    static_f = None
    dynamic_f = None
    restitution = None

    # 1. Check direct USD authored physics cache first (exact mass as in Isaac Sim)
    usd_info = _usd_physics_cache.get(asset_key)
    if usd_info:
        mass = usd_info.get("mass_kg")
        static_f = usd_info.get("static_friction")
        dynamic_f = usd_info.get("dynamic_friction")
        restitution = usd_info.get("restitution")

    # 2. Check manifest info if not in USD cache
    if mass is None and manifest_info:
        mass = manifest_info.get("mass_kg")
    if static_f is None and manifest_info:
        static_f = manifest_info.get("static_friction")
    if dynamic_f is None and manifest_info:
        dynamic_f = manifest_info.get("dynamic_friction")
    if restitution is None and manifest_info:
        restitution = manifest_info.get("restitution")

    # 3. Fallback to realistic category preset
    if mass is None:
        mass = fallback["mass"]
    if static_f is None:
        static_f = fallback["static_friction"]
    if dynamic_f is None:
        dynamic_f = fallback["dynamic_friction"]
    if restitution is None:
        restitution = fallback["restitution"]

    return {
        "mass_kg": round(float(mass), 3) if mass is not None else 0.0,
        "static_friction": round(float(static_f), 2) if static_f is not None else 0.5,
        "dynamic_friction": round(float(dynamic_f), 2) if dynamic_f is not None else 0.35,
        "restitution": round(float(restitution), 2) if restitution is not None else 0.05
    }


def scan_assets(force_reload: bool = False) -> List[dict]:
    """Scan ASSET_SOURCE_DIR and return all indexed 3D assets."""
    global _cached_assets, _manifest_cache, _last_scan_timestamp
    now = time.time()
    
    if _cached_assets is not None and not force_reload:
        if (now - _last_scan_timestamp) < CACHE_TTL_SECONDS:
            return _cached_assets

    _manifest_cache = load_batch_manifests()
    assets = []

    if not ASSET_SOURCE_DIR.exists():
        _cached_assets = assets
        _last_scan_timestamp = now
        return assets

    for batch_dir in sorted(os.scandir(ASSET_SOURCE_DIR), key=lambda e: e.name):
        if not batch_dir.is_dir():
            continue
        batch_name = batch_dir.name
        manifest_data = _manifest_cache.get(batch_name, {})
        manifest_items = manifest_data.get("items", [])
        
        manifest_by_subfolder = {}
        for it in manifest_items:
            sub = it.get("subfolder")
            if sub:
                manifest_by_subfolder[sub] = it

        for item_dir in sorted(os.scandir(batch_dir.path), key=lambda e: e.name):
            if not item_dir.is_dir():
                continue
            item_name = item_dir.name
            manifest_info = manifest_by_subfolder.get(item_name)

            usd_files = []
            video_files = []
            image_files = []
            all_files = []
            total_size_bytes = 0

            for root, _, files in os.walk(item_dir.path):
                for f in files:
                    full_p = Path(root) / f
                    rel_p = str(full_p.relative_to(item_dir.path)).replace("\\", "/")
                    f_stat = full_p.stat()
                    f_size = f_stat.st_size
                    f_mtime = int(f_stat.st_mtime)
                    total_size_bytes += f_size
                    
                    file_record = {
                        "name": f,
                        "rel_path": rel_p,
                        "size_bytes": f_size,
                        "mtime": f_mtime,
                        "size_str": f"{f_size / (1024 * 1024):.2f} MB" if f_size > 1024 * 1024 else f"{f_size / 1024:.1f} KB"
                    }
                    all_files.append(file_record)

                    lower_f = f.lower()
                    if lower_f.endswith((".usd", ".usdc", ".usda")):
                        usd_files.append(file_record)
                    elif lower_f.endswith((".mp4", ".webm", ".mov")):
                        video_files.append(file_record)
                    elif lower_f.endswith((".png", ".jpg", ".jpeg", ".webp")):
                        if lower_f.startswith("t_"):
                            image_files.insert(0, file_record)
                        else:
                            image_files.append(file_record)

            thumbnail_path = image_files[0]["rel_path"] if image_files else None
            thumbnail_mtime = image_files[0]["mtime"] if image_files else 0
            
            video_path = video_files[0]["rel_path"] if video_files else None
            video_mtime = video_files[0]["mtime"] if video_files else 0

            primary_usd = None
            if usd_files:
                pure_usd = [u for u in usd_files if u["name"].lower().endswith(".usd")]
                primary_usd = (pure_usd[0] if pure_usd else usd_files[0])["rel_path"]

            semantic_class = None
            mass_kg = None
            friction = None
            status = "Ready"

            if manifest_info:
                semantic_class = manifest_info.get("semantic_class")
                mass_kg = manifest_info.get("mass_kg")
                static_friction = manifest_info.get("static_friction")
                dynamic_friction = manifest_info.get("dynamic_friction")
                if static_friction is not None:
                    friction = f"{static_friction} / {dynamic_friction}"
                status = manifest_info.get("status", "PASS")

            cls_en, cat_cn, cat_en, qcode, default_sem = classify_category(item_name, semantic_class)
            asset_key = f"{batch_name}/{item_name}"
            physics = get_physics_specs(manifest_info, cat_en, item_name, asset_key=asset_key)
            final_semantic = semantic_class or default_sem

            asset_obj = {
                "id": f"{batch_name}/{item_name}",
                "batch": batch_name,
                "name": item_name,
                "category": cat_cn,
                "category_en": cat_en,
                "category_display": f"{cat_cn} / {cat_en}",
                "clean_category_en": cls_en,
                "semantic_class": final_semantic,
                "wikidata_qcode": qcode,
                "mass_kg": physics["mass_kg"],
                "static_friction": physics["static_friction"],
                "dynamic_friction": physics["dynamic_friction"],
                "restitution": physics["restitution"],
                "friction": f"{physics['static_friction']} / {physics['dynamic_friction']}",
                "status": status,
                "has_video": len(video_files) > 0,
                "has_usd": len(usd_files) > 0,
                "thumbnail_rel_path": thumbnail_path,
                "thumbnail_mtime": thumbnail_mtime,
                "video_rel_path": video_path,
                "video_mtime": video_mtime,
                "primary_usd_rel_path": primary_usd,
                "total_size_bytes": total_size_bytes,
                "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
                "usd_files": usd_files,
                "video_files": video_files,
                "image_files": image_files,
                "all_files": all_files,
                "abs_path": str(Path(item_dir.path).resolve())
            }
            assets.append(asset_obj)

    # Sort assets by id to ensure deterministic order, then assign sequential numbers per category
    assets.sort(key=lambda a: (a["clean_category_en"], a["batch"], a["name"]))
    category_counters = {}
    for a in assets:
        cls = a["clean_category_en"]
        cat_cn = a["category"]
        category_counters[cls] = category_counters.get(cls, 0) + 1
        idx = category_counters[cls]
        a["displayName"] = f"{cls} / {cat_cn} - {idx:02d}"

    _cached_assets = assets
    _last_scan_timestamp = now
    return assets


@app.get("/")
def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>Asset Portal UI is building...</h1>")
    return FileResponse(index_path, media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.on_event("startup")
def startup_event():
    # Pre-warm asset cache on startup
    scan_assets(force_reload=True)


@app.get("/api/update")
def force_update_assets():
    """Explicit one-click refresh endpoint."""
    assets = scan_assets(force_reload=True)
    return format_assets_response(assets)


@app.get("/api/assets")
def get_assets(refresh: bool = Query(False)):
    """Fast cached asset endpoint."""
    assets = scan_assets(force_reload=refresh)
    return format_assets_response(assets)


def format_assets_response(assets: List[dict]):
    cat_counter = Counter(a["category"] for a in assets)
    sorted_categories = [cat for cat, _ in cat_counter.most_common()]
    
    batch_counter = Counter(a["batch"] for a in assets)
    sorted_batches = sorted(list(batch_counter.keys()))

    total_videos = sum(1 for a in assets if a["has_video"])
    total_usds = sum(1 for a in assets if a["has_usd"])
    total_size_gb = round(sum(a["total_size_bytes"] for a in assets) / (1024**3), 2)

    headers = {
        "Cache-Control": "public, max-age=15"
    }

    return JSONResponse(
        content={
            "assets": assets,
            "total": len(assets),
            "batches": sorted_batches,
            "categories": sorted_categories,
            "category_counts": dict(cat_counter),
            "batch_counts": dict(batch_counter),
            "stats": {
                "total_assets": len(assets),
                "total_videos": total_videos,
                "total_usds": total_usds,
                "total_batches": len(sorted_batches),
                "total_categories": len(sorted_categories),
                "total_size_gb": total_size_gb
            },
            "timestamp": int(time.time())
        },
        headers=headers
    )


def get_safe_file_path(batch: str, asset: str, filepath: str) -> Path:
    """Validate and return safe absolute Path within ASSET_SOURCE_DIR."""
    target_dir = (ASSET_SOURCE_DIR / batch / asset).resolve()
    target_file = (target_dir / filepath).resolve()
    try:
        target_file.relative_to(target_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: outside asset directory")
    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return target_file


@app.get("/api/thumbnail/{batch}/{asset}/{filepath:path}")
def stream_thumbnail(batch: str, asset: str, filepath: str):
    """Serve ultra-fast WebP compressed thumbnail (~10-30KB)."""
    file_path = get_safe_file_path(batch, asset, filepath)
    thumb_path = get_or_create_thumbnail(file_path)
    media_type = "image/webp" if thumb_path.suffix.lower() == ".webp" else "image/png"
    return FileResponse(
        thumb_path,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=604800, immutable",
            "ETag": f'"{int(thumb_path.stat().st_mtime)}"'
        }
    )


@app.get("/api/media/{batch}/{asset}/{filepath:path}")
def stream_media(batch: str, asset: str, filepath: str, request: Request):
    """Stream media files with HTTP Range support and strict cache-control."""
    file_path = get_safe_file_path(batch, asset, filepath)
    file_size = file_path.stat().st_size
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        if file_path.suffix.lower() == ".usd":
            mime_type = "model/vnd.usd"
        elif file_path.suffix.lower() == ".usdc":
            mime_type = "model/vnd.usdc"
        else:
            mime_type = "application/octet-stream"

    range_header = request.headers.get("range")
    if range_header:
        range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            start = max(0, start)
            end = min(file_size - 1, end)
            content_length = end - start + 1

            def range_generator():
                with open(file_path, "rb") as f:
                    f.seek(start)
                    bytes_remaining = content_length
                    chunk_size = 64 * 1024
                    while bytes_remaining > 0:
                        read_size = min(chunk_size, bytes_remaining)
                        data = f.read(read_size)
                        if not data:
                            break
                        bytes_remaining -= len(data)
                        yield data

            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": mime_type,
                "Cache-Control": "no-cache, must-revalidate",
            }
            return StreamingResponse(range_generator(), status_code=206, headers=headers)

    return FileResponse(
        file_path,
        media_type=mime_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache, must-revalidate",
            "Pragma": "no-cache"
        }
    )


@app.get("/api/download/file/{batch}/{asset}/{filepath:path}")
def download_single_file(batch: str, asset: str, filepath: str):
    """Download a single asset file directly with attachment disposition."""
    file_path = get_safe_file_path(batch, asset, filepath)
    return FileResponse(
        file_path,
        filename=file_path.name,
        media_type="application/octet-stream"
    )


@app.get("/api/download/zip/{batch}/{asset}")
def download_asset_zip(batch: str, asset: str):
    """Create a ZIP archive of the entire asset folder and stream it."""
    asset_dir = (ASSET_SOURCE_DIR / batch / asset).resolve()
    if not asset_dir.exists() or not asset_dir.is_dir():
        raise HTTPException(status_code=404, detail="Asset folder not found")

    zip_filename = f"{asset}.zip"

    mem_file = io.BytesIO()
    with zipfile.ZipFile(mem_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(asset_dir):
            for f in files:
                file_p = Path(root) / f
                arcname = file_p.relative_to(asset_dir)
                zf.write(file_p, arcname=str(arcname))
    
    zip_bytes = mem_file.getvalue()
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
            "Content-Length": str(len(zip_bytes))
        }
    )


@app.post("/api/open-folder")
async def open_local_folder(request: Request):
    """Open asset directory directly in Windows Explorer."""
    data = await request.json()
    batch = data.get("batch")
    asset = data.get("asset")
    if not batch or not asset:
        raise HTTPException(status_code=400, detail="Missing batch or asset")
    
    target_dir = (ASSET_SOURCE_DIR / batch / asset).resolve()
    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="Folder not found")
    
    try:
        os.startfile(str(target_dir))
        return {"success": True, "path": str(target_dir)}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print(f"Starting 3D USD Asset Portal on http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)