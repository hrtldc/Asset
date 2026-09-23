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

from config import (
    APP_DIR, ASSET_SOURCE_DIR, HOST, PORT, STATIC_DIR, NAME_TRANSLATIONS,
    is_batch_ignored, read_ignore_file_raw, write_ignore_file_raw,
    get_batch_status_list, get_ignore_patterns
)
from auto_classifier import classify_asset_auto

app = FastAPI(title="3D USD Asset Portal", version="1.5.0")

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

    # Gas Stove / Cooktop (燃气灶 / 灶具)
    if any(k in target for k in ["luzao", "ranqizhao", "gasstove", "cooktop", "gas_stove", "zhaoju"]):
        return ("Gas Stove", "燃气灶", "Kitchen Appliances", "Q180399", "GasStove", "燃气灶")
    # Desk Lamp / Table Lamp (台灯)
    elif any(k in target for k in ["taideng", "desklamp", "desk_lamp", "tablelamp"]):
        return ("Desk Lamp", "台灯", "Lighting", "Q1134005", "DeskLamp", "台灯")
    # Fans & Ventilation (风扇 / 吊扇 / 落地扇)
    elif any(k in target for k in ["diaoshan", "ceilingfan", "ceiling_fan"]):
        return ("Ceiling Fan", "吊扇", "Home Appliances", "Q1641320", "CeilingFan", "吊扇")
    elif any(k in target for k in ["fengshan", "electricfan", "electric_fan", "standingfan", "floorfan", "fan"]):
        return ("Electric Fan", "电风扇", "Home Appliances", "Q264923", "ElectricFan", "电风扇")
    # Bathroom & Sanitary (卫浴 / 马桶 / 坐便器 / 洗手台)
    elif any(k in target for k in ["matong", "toilet", "closestool", "closetstool", "commode", "zuobianqi", "bidet"]):
        return ("Toilet", "马桶", "Bathroom & Sanitary", "Q7338", "Toilet", "马桶")
    elif any(k in target for k in ["xishoutai", "taipen", "washbasin", "sink"]):
        return ("Washbasin", "洗手池", "Bathroom & Sanitary", "Q14056", "Washbasin", "洗手池")
    elif any(k in target for k in ["yugang", "bathtub", "huasa", "shower"]):
        return ("Bathtub", "浴缸", "Bathroom & Sanitary", "Q108877", "Bathtub", "浴缸")
    elif "bingxiang" in target or "refrigerator" in target:
        return ("Refrigerator", "冰箱", "Refrigerator", "Q37867", "Refrigerator", "冰箱")
    elif "yushigui" in target or "bathroomvanity" in target:
        return ("Bathroom Vanity", "浴室柜", "Bathroom Vanity", "Q1321517", "BathroomVanity", "浴室柜")
    elif "chuangtougui" in target or "nightstand" in target:
        return ("Nightstand", "床头柜", "Nightstand", "Q1321517", "Nightstand", "床头柜")
    elif "xiegui" in target or "shoecabinet" in target:
        return ("Shoe Cabinet", "鞋柜", "Shoe Cabinet", "Q1321517", "ShoeCabinet", "鞋柜")
    elif any(k in target for k in ["zhediemen", "tuilamen", "pingbanmen", "shuangkaimen", "door", "foldingdoor", "slidingdoor"]) or fn.startswith(("sm_men", "sm-men")):
        return ("Door", "门类", "Doors", "Q36794", "Door", "门类")
    elif any(k in target for k in ["kaoxiang", "weibolu", "xiaodugui", "xiwanji", "qihualu", "stove", "microwave", "oven", "dishwasher"]):
        return ("Kitchen Appliance", "厨房电器", "Kitchen Appliances", "Q127950", "KitchenAppliance", "厨房电器")
    elif "xiyiji" in target or "washingmachine" in target:
        return ("Washing Machine", "洗衣机", "Home Appliances", "Q124441", "WashingMachine", "洗衣机")
    elif "deng" in fn or "light" in target or "lamp" in target:
        return ("Light", "灯具", "Lighting", "Q135260", "Light", "灯具")
    elif "shuzhuangtai" in target or "dressingtable" in target:
        return ("Dressing Table", "梳妆台", "Tables & Vanities", "Q204370", "DressingTable", "梳妆台")
    elif "chaji" in target or "coffeetable" in target:
        return ("Coffee Table", "茶几", "Tables & Vanities", "Q1151608", "CoffeeTable", "茶几")
    elif "zhongdao" in target or "kitchenisland" in target:
        return ("Kitchen Island", "中岛台", "Kitchen Island", "Q148600", "KitchenIsland", "中岛台")
    elif any(k in target for k in ["chazuo", "shujuxian", "cable"]):
        return ("Cable & Outlet", "数码配件", "Cables & Outlets", "Q16865280", "Cable", "数码配件")
    elif any(k in target for k in ["guizi", "chugui", "sidecabinet", "kitchencabinet", "shounaigui", "zhuangshigui", "hongjiugui", "shuiba", "cabinet", "storage"]):
        return ("Cabinet", "柜类", "Cabinets & Storage", "Q1321517", "Cabinet", "柜类")
    elif "bed" in target:
        return ("Bed", "床具", "Beds", "Q42177", "Bed", "床具")
    # Furniture & Seating (沙发 / 座椅 / 餐桌 / 书桌)
    elif any(k in target for k in ["shafa", "sofa", "couch"]):
        return ("Sofa", "沙发", "Furniture", "Q131514", "Sofa", "沙发")
    elif any(k in target for k in ["yizi", "chair", "dengzi", "stool"]):
        return ("Chair", "座椅", "Furniture", "Q15026", "Chair", "椅子")
    elif any(k in target for k in ["canzhuo", "diningtable", "dining_table"]):
        return ("Dining Table", "餐桌", "Tables & Vanities", "Q14748", "DiningTable", "餐桌")
    elif any(k in target for k in ["shuzhuo", "desk"]):
        return ("Desk", "书桌", "Tables & Vanities", "Q1064858", "Desk", "书桌")
    # Kitchen & Home Appliances
    elif any(k in target for k in ["youyanji", "chouyouyanji", "rangehood", "range_hood"]):
        return ("Range Hood", "厨房电器", "Kitchen Appliances", "Q584447", "RangeHood", "抽油烟机")
    elif any(k in target for k in ["reshuiqi", "waterheater"]):
        return ("Water Heater", "生活电器", "Home Appliances", "Q14890", "WaterHeater", "热水器")
    elif any(k in target for k in ["yinshuiji", "waterdispenser"]):
        return ("Water Dispenser", "生活电器", "Home Appliances", "Q252033", "WaterDispenser", "饮水机")
    elif any(k in target for k in ["saodiji", "robotvacuum"]):
        return ("Robot Vacuum", "生活电器", "Home Appliances", "Q1048602", "RobotVacuum", "扫地机")
    elif any(k in target for k in ["kongdiao", "airconditioner"]):
        return ("Air Conditioner", "生活电器", "Home Appliances", "Q170560", "AirConditioner", "空调")
    # Digital Devices & Consumer Electronics (数码用品)
    elif "pingbandiannao" in fn or "tablet" in target:
        return ("Tablet", "数码用品", "Digital Devices", "Q155972", "Tablet", "平板电脑")
    elif "bijibendiannao" in fn or "laptop" in target:
        return ("Laptop", "数码用品", "Digital Devices", "Q3962", "Laptop", "笔记本电脑")
    elif "erji" in fn or "headphone" in target or "earphone" in target:
        return ("Headphones", "数码用品", "Digital Devices", "Q186694", "Headphones", "耳机")
    elif any(k in fn for k in ["shouji", "shoji"]) or any(k in sem for k in ["phone", "smartphone"]):
        return ("Phone", "数码用品", "Digital Devices", "Q193175", "Phone", "手机")
    elif "wurenji" in fn or "drone" in target:
        return ("Drone", "数码用品", "Digital Devices", "Q223557", "Drone", "无人机")
    elif "yuntai" in fn or "gimbal" in target:
        return ("Gimbal", "数码用品", "Digital Devices", "Q15328", "CameraGimbal", "云台相机")
    elif "shexiangtou" in fn or "webcam" in target or "camera" in target:
        return ("Camera", "数码用品", "Digital Devices", "Q15328", "Camera", "摄像头")

    # Strict rule: NEVER default to '其他' or '其他资产'. Dynamically extract semantic noun.
    clean_stem = re.sub(r'^(sm[-_]|sn[-_]|md[-_])', '', folder_name, flags=re.IGNORECASE)
    clean_stem = re.sub(r'[-_]\d+$', '', clean_stem).strip()
    noun = clean_stem.capitalize() if clean_stem else "CustomAsset"
    if semantic_class and semantic_class.lower() not in ("asset", "other", "physicalasset", "bowl", "unknown"):
        noun_sem = semantic_class
        return (noun_sem, noun_sem, "Custom Assets", "Q223557", noun_sem, noun_sem)
    return (noun, noun, "Custom Assets", "Q223557", noun, noun)


def load_batch_manifests():
    """Load all _simready_manifest.json files from non-ignored batches."""
    manifests = {}
    if not ASSET_SOURCE_DIR.exists():
        return manifests
    for batch_entry in os.scandir(ASSET_SOURCE_DIR):
        if batch_entry.is_dir() and not is_batch_ignored(batch_entry.name):
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
        "Kitchen Appliances": {"mass": 18.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Gas Stove": {"mass": 3.5, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Lighting": {"mass": 3.5, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Desk Lamp": {"mass": 2.5, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Tables & Vanities": {"mass": 22.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Kitchen Island": {"mass": 85.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Beds": {"mass": 65.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Fans & Ventilation": {"mass": 4.5, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Bathroom & Sanitary": {"mass": 28.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Furniture": {"mass": 18.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Home Appliances": {"mass": 15.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05},
        "Cables & Outlets": {"mass": 0.45, "static_friction": 0.6, "dynamic_friction": 0.45, "restitution": 0.05},
        "Digital Devices": {"mass": 1.2, "static_friction": 0.45, "dynamic_friction": 0.35, "restitution": 0.05},
        "Other": {"mass": 10.0, "static_friction": 0.5, "dynamic_friction": 0.35, "restitution": 0.05}
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

    # Sanitize unreasonable manifest mass (e.g. scale errors >150kg or <=0.001kg)
    if mass is not None and (float(mass) > 150.0 or float(mass) <= 0.001):
        name_low = item_name.lower()
        if "bijibendiannao" in name_low or "laptop" in name_low:
            mass = 1.8
        elif "pingbandiannao" in name_low or "tablet" in name_low:
            mass = 0.48
        elif "shouji" in name_low or "shoji" in name_low or "phone" in name_low:
            mass = 0.19
        elif "erji" in name_low or "headphone" in name_low or "earphone" in name_low:
            mass = 0.22
        elif "wurenji" in name_low or "drone" in name_low:
            mass = 0.55
        elif "shexiangtou" in name_low or "camera" in name_low:
            mass = 0.35
        elif "yuntai" in name_low or "gimbal" in name_low:
            mass = 0.42
        else:
            mass = fallback["mass"]

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
    global _cached_assets, _manifest_cache, _last_scan_timestamp, _usd_physics_cache
    now = time.time()
    
    if _cached_assets is not None and not force_reload:
        if (now - _last_scan_timestamp) < CACHE_TTL_SECONDS:
            return _cached_assets

    _manifest_cache = load_batch_manifests()
    _usd_physics_cache = load_usd_physics_cache()
    assets = []

    if not ASSET_SOURCE_DIR.exists():
        _cached_assets = assets
        _last_scan_timestamp = now
        return assets

    ignored_batches = []
    for batch_dir in sorted(os.scandir(ASSET_SOURCE_DIR), key=lambda e: e.name):
        if not batch_dir.is_dir():
            continue
        if is_batch_ignored(batch_dir.name):
            ignored_batches.append(batch_dir.name)
            continue
        batch_name = batch_dir.name
        manifest_data = _manifest_cache.get(batch_name, {})
        manifest_items = manifest_data.get("items", [])
        
        manifest_by_subfolder = {}
        for it in manifest_items:
            sub = it.get("subfolder")
            if sub:
                manifest_by_subfolder[sub] = it

        candidate_items = []
        for item_dir in sorted(os.scandir(batch_dir.path), key=lambda e: e.name):
            if not item_dir.is_dir() or is_batch_ignored(item_dir.name):
                continue
            candidate_items.append((batch_name, item_dir))

        for current_batch, item_dir in candidate_items:
            try:
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
                        try:
                            rel_p = str(full_p.relative_to(item_dir.path)).replace("\\", "/")
                            f_stat = full_p.stat()
                            f_size = f_stat.st_size
                            f_mtime = int(f_stat.st_mtime)
                            total_size_bytes += f_size
                        except Exception:
                            continue
                        
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

                asset_key = f"{current_batch}/{item_name}"
                usd_cached = _usd_physics_cache.get(asset_key)
                if usd_cached:
                    if not semantic_class and usd_cached.get("semantic_class"):
                        semantic_class = usd_cached["semantic_class"]

                thumb_full = (Path(item_dir.path) / thumbnail_path) if thumbnail_path else None
                cls_en, cat_cn, cat_en, qcode, default_sem, specific_zh = classify_asset_auto(
                    current_batch, item_name, thumb_full, semantic_class
                )
                physics = get_physics_specs(manifest_info, cat_en, item_name, asset_key=asset_key)
                final_semantic = default_sem or semantic_class
                final_qcode = (manifest_info and manifest_info.get("wikidata_qcode")) or (usd_cached and usd_cached.get("wikidata_qcode")) or qcode

                try:
                    abs_path_str = str(Path(item_dir.path).resolve())
                except Exception:
                    abs_path_str = str(item_dir.path)

                asset_obj = {
                    "id": f"{current_batch}/{item_name}",
                    "batch": current_batch,
                    "name": item_name,
                    "category": cat_cn,
                    "category_en": cat_en,
                    "category_display": f"{cat_cn} / {cat_en}",
                    "clean_category_en": cls_en,
                    "specific_zh": specific_zh,
                    "semantic_class": final_semantic,
                    "wikidata_qcode": final_qcode,
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
                    "abs_path": abs_path_str
                }
                assets.append(asset_obj)
            except Exception as item_err:
                print(f"[scan_assets] Warning: failed to parse asset {current_batch}/{getattr(item_dir, 'name', 'unknown')}: {item_err}")
                continue

    # Sort assets by id to ensure deterministic order, then assign sequential numbers per category
    assets.sort(key=lambda a: (a["category"], a["clean_category_en"], a["batch"], a["name"]))
    category_counters = {}
    for a in assets:
        cls = a["clean_category_en"]
        spec_cn = a.get("specific_zh") or a["category"]
        category_counters[cls] = category_counters.get(cls, 0) + 1
        idx = category_counters[cls]
        a["displayName"] = f"{cls} / {spec_cn} - {idx:02d}"

    _cached_assets = assets
    _last_scan_timestamp = now
    return assets


@app.get("/")
def serve_index():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>Asset Portal UI is building...</h1>")
    return FileResponse(index_path, media_type="text/html", headers={"Cache-Control": "no-cache"})


import threading

def _background_auto_watcher():
    """Background worker that silently checks and auto-indexes new assets every 30s."""
    while True:
        try:
            time.sleep(30.0)
            scan_assets(force_reload=True)
        except Exception:
            pass

@app.on_event("startup")
def startup_event():
    # Pre-warm asset cache on startup
    scan_assets(force_reload=True)
    # Start non-blocking automated background ingestion worker
    t = threading.Thread(target=_background_auto_watcher, daemon=True)
    t.start()


@app.get("/api/update")
def force_update_assets():
    """Explicit one-click refresh endpoint."""
    assets = scan_assets(force_reload=True)
    return format_assets_response(assets)


@app.get("/api/ignore-rules")
def get_ignore_rules_api():
    """Get current ignore file text and status of all scanned batch folders."""
    content = read_ignore_file_raw()
    patterns = get_ignore_patterns()
    batches = get_batch_status_list()
    return {
        "content": content,
        "patterns": patterns,
        "batches": batches
    }


@app.post("/api/ignore-rules")
async def update_ignore_rules_api(request: Request):
    """Save user-typed ignore rules and immediately re-scan assets."""
    data = await request.json()
    content = data.get("content", "")
    write_ignore_file_raw(content)
    # Refresh cache immediately
    assets = scan_assets(force_reload=True)
    return {
        "success": True,
        "message": "过滤规则已成功更新并重新扫描",
        "total_assets": len(assets),
        "batches": get_batch_status_list()
    }


@app.post("/api/sync-public")
def trigger_sync_public():
    """Trigger background build and public push."""
    import sys
    py_exe = sys.executable
    sync_script = APP_DIR / "sync_pipeline.py"
    if sync_script.exists():
        subprocess.Popen([py_exe, str(sync_script)], cwd=str(APP_DIR))
        return {"success": True, "message": "已在后台启动外网同步与发布流程"}
    return {"success": False, "message": "sync_pipeline.py 不存在"}


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