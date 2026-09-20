"""
Automated Semantic Classifier for 3D USD Asset Portal
Integrates:
1. Fast Persistent Semantic Cache (static/data/auto_semantic_cache.json)
2. Comprehensive Multi-lingual & Pinyin Ontology
3. Local Vision VLM (Qwen2.5-VL:7b via Ollama http://127.0.0.1:11434)
4. Dynamic Semantic Stem Extraction (Strictly ZERO "其他资产" fallback)
"""

import base64
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

APP_DIR = Path(__file__).parent.resolve()
CACHE_FILE = APP_DIR / "static" / "data" / "auto_semantic_cache.json"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
VISION_MODEL = "qwen2.5vl:7b"

_cache: Dict[str, dict] = {}
_cache_loaded = False


def _load_cache():
    global _cache, _cache_loaded
    if _cache_loaded:
        return
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception as e:
            print(f"[AutoClassifier] Warning loading cache: {e}")
            _cache = {}
    else:
        _cache = {}
    _cache_loaded = True


def _save_cache():
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[AutoClassifier] Warning saving cache: {e}")


# Standard category translations & canonical taxonomy
CATEGORY_MAP = {
    # Clean Class EN: (Category CN, Category EN, Wikidata Q-Code, Specific ZH)
    "Ceiling Fan": ("风扇", "Fans & Ventilation", "Q1641320", "吊扇"),
    "Electric Fan": ("风扇", "Fans & Ventilation", "Q264923", "电风扇"),
    "Toilet": ("马桶", "Bathroom & Sanitary", "Q7338", "马桶"),
    "Washbasin": ("洗手池", "Bathroom & Sanitary", "Q14056", "洗手池"),
    "Bathtub": ("浴缸", "Bathroom & Sanitary", "Q108877", "浴缸"),
    "Bathroom Vanity": ("浴室柜", "Bathroom Vanity", "Q1321517", "浴室柜"),
    "Nightstand": ("床头柜", "Nightstand", "Q1321517", "床头柜"),
    "Shoe Cabinet": ("鞋柜", "Shoe Cabinet", "Q1321517", "鞋柜"),
    "Cabinet": ("柜类", "Cabinets & Storage", "Q1321517", "柜子"),
    "Door": ("门类", "Doors", "Q36794", "门"),
    "Gas Stove": ("燃气灶", "Kitchen Appliances", "Q180399", "燃气灶"),
    "Kitchen Appliance": ("厨房电器", "Kitchen Appliances", "Q127950", "厨房电器"),
    "Range Hood": ("厨房电器", "Kitchen Appliances", "Q584447", "抽油烟机"),
    "Refrigerator": ("冰箱", "Refrigerator", "Q37867", "冰箱"),
    "Washing Machine": ("洗衣机", "Home Appliances", "Q124441", "洗衣机"),
    "Air Conditioner": ("生活电器", "Home Appliances", "Q170560", "空调"),
    "Water Heater": ("生活电器", "Home Appliances", "Q14890", "热水器"),
    "Water Dispenser": ("生活电器", "Home Appliances", "Q252033", "饮水机"),
    "Robot Vacuum": ("生活电器", "Home Appliances", "Q1048602", "扫地机"),
    "Desk Lamp": ("台灯", "Lighting", "Q1134005", "台灯"),
    "Light": ("灯具", "Lighting", "Q135260", "灯具"),
    "Dressing Table": ("梳妆台", "Tables & Vanities", "Q204370", "梳妆台"),
    "Coffee Table": ("茶几", "Tables & Vanities", "Q1151608", "茶几"),
    "Dining Table": ("餐桌", "Tables & Vanities", "Q14748", "餐桌"),
    "Desk": ("书桌", "Tables & Vanities", "Q1064858", "书桌"),
    "Kitchen Island": ("中岛台", "Kitchen Island", "Q148600", "中岛台"),
    "Sofa": ("沙发", "Furniture", "Q131514", "沙发"),
    "Chair": ("座椅", "Furniture", "Q15026", "椅子"),
    "Bed": ("床具", "Beds", "Q42177", "床具"),
    "Laptop": ("数码用品", "Digital Devices", "Q3962", "笔记本电脑"),
    "Tablet": ("数码用品", "Digital Devices", "Q155972", "平板电脑"),
    "Phone": ("数码用品", "Digital Devices", "Q193175", "手机"),
    "Headphones": ("数码用品", "Digital Devices", "Q186694", "耳机"),
    "Drone": ("数码用品", "Digital Devices", "Q223557", "无人机"),
    "Camera": ("数码用品", "Digital Devices", "Q15328", "摄像头"),
    "Gimbal": ("数码用品", "Digital Devices", "Q15328", "云台相机"),
    "Cable & Outlet": ("数码配件", "Cables & Outlets", "Q16865280", "插座数据线"),
}

# Rule-based pinyin & naming regex
RULES = [
    # Regex pattern, Clean Class EN
    (r"diaoshan|ceilingfan|ceiling_fan", "Ceiling Fan"),
    (r"fengshan|electricfan|electric_fan|standingfan|floorfan|\bfan\b", "Electric Fan"),
    (r"matong|toilet|closestool|closetstool|commode|zuobianqi|bidet", "Toilet"),
    (r"xishoutai|taipen|washbasin|wash_basin|sink", "Washbasin"),
    (r"yugang|bathtub|huasa|shower", "Bathtub"),
    (r"yushigui|bathroomvanity|bathroom_vanity", "Bathroom Vanity"),
    (r"chuangtougui|nightstand|night_stand|bedside", "Nightstand"),
    (r"xiegui|shoecabinet|shoe_cabinet", "Shoe Cabinet"),
    (r"zhediemen|tuilamen|pingbanmen|shuangkaimen|door|foldingdoor|slidingdoor|^sm[-_]men", "Door"),
    (r"luzao|ranqizhao|gasstove|cooktop|gas_stove|zhaoju", "Gas Stove"),
    (r"kaoxiang|weibolu|xiaodugui|xiwanji|qihualu|microwave|oven|dishwasher|dish_washer", "Kitchen Appliance"),
    (r"youyanji|chouyouyanji|rangehood|range_hood", "Range Hood"),
    (r"bingxiang|refrigerator|fridge", "Refrigerator"),
    (r"xiyiji|washingmachine|washing_machine", "Washing Machine"),
    (r"kongdiao|airconditioner|air_conditioner", "Air Conditioner"),
    (r"reshuiqi|waterheater|water_heater", "Water Heater"),
    (r"yinshuiji|waterdispenser|water_dispenser", "Water Dispenser"),
    (r"saodiji|robotvacuum|robot_vacuum", "Robot Vacuum"),
    (r"taideng|desklamp|desk_lamp|tablelamp", "Desk Lamp"),
    (r"deng|light|lamp|chandelier|pendant_light", "Light"),
    (r"shuzhuangtai|dressingtable|dressing_table|vanity_table", "Dressing Table"),
    (r"chaji|coffeetable|coffee_table|tea_table", "Coffee Table"),
    (r"canzhuo|diningtable|dining_table", "Dining Table"),
    (r"shuzhuo|desk|workstation", "Desk"),
    (r"zhongdao|kitchenisland|kitchen_island", "Kitchen Island"),
    (r"shafa|sofa|couch", "Sofa"),
    (r"yizi|chair|dengzi|stool", "Chair"),
    (r"guizi|chugui|sidecabinet|kitchencabinet|shounaigui|zhuangshigui|hongjiugui|shuiba|cabinet|storage|wardrobe", "Cabinet"),
    (r"bed|chuang|tatami", "Bed"),
    (r"pingbandiannao|tablet|ipad", "Tablet"),
    (r"bijibendiannao|laptop|notebook", "Laptop"),
    (r"erji|headphone|earphone|airpods", "Headphones"),
    (r"shouji|shoji|phone|smartphone|iphone", "Phone"),
    (r"wurenji|drone", "Drone"),
    (r"yuntai|gimbal", "Gimbal"),
    (r"shexiangtou|webcam|camera", "Camera"),
    (r"chazuo|shujuxian|cable|outlet|powerstrip|plug", "Cable & Outlet"),
]


def _query_vision_ai(image_path: Path) -> Optional[dict]:
    """Query local Qwen2.5-VL via Ollama to classify asset directly from its rendered thumbnail."""
    if not image_path or not image_path.exists():
        return None
    try:
        b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        prompt = (
            "Analyze this 3D model render. Identify the exact physical object and classify it. "
            "Reply strictly with a JSON object: "
            '{"class_en": "<Specific English Noun>", "class_zh": "<精确中文名称>", "category_zh": "<中文大类>", "category_en": "<English Category>"}. '
            "Do NOT return generic terms like 'Asset' or 'Other'."
        )
        payload = {
            "model": VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": [b64]
            }],
            "stream": False,
            "options": {"temperature": 0.1}
        }
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "").strip()
            m = re.search(r"\{.*?\}", content, re.DOTALL)
            if m:
                return json.loads(m.group(0))
    except Exception:
        pass
    return None


def classify_asset_auto(
    batch_name: str,
    item_name: str,
    image_path: Optional[Path] = None,
    semantic_class: Optional[str] = None
) -> Tuple[str, str, str, str, str, str]:
    """
    Automated classification pipeline:
    Returns: (clean_category_en, category_cn, category_en, wikidata_qcode, semantic_class, specific_zh)
    Guarantee: STRICTLY ZERO '其他' or '其他资产'.
    """
    _load_cache()
    asset_id = f"{batch_name}/{item_name}"

    # 1. Fast Cache Hit
    if asset_id in _cache:
        c = _cache[asset_id]
        return (
            c["clean_category_en"],
            c["category"],
            c["category_en"],
            c["wikidata_qcode"],
            c["semantic_class"],
            c["specific_zh"]
        )

    norm_target = f"{item_name} {semantic_class or ''}".lower()

    # 2. High-confidence Rule & Ontology Matching
    matched_class_en = None
    for pattern, cls_en in RULES:
        if re.search(pattern, norm_target):
            matched_class_en = cls_en
            break

    # 3. Vision AI Verification if naming is unknown or generic
    if not matched_class_en or (semantic_class and semantic_class.lower() in ("bowl", "genericprop", "asset")):
        if image_path and image_path.exists():
            v_res = _query_vision_ai(image_path)
            if v_res and v_res.get("class_en"):
                v_class_en = v_res.get("class_en", "").title().strip()
                for _, cls_en in RULES:
                    if cls_en.lower() in v_class_en.lower() or v_class_en.lower() in cls_en.lower():
                        matched_class_en = cls_en
                        break
                if not matched_class_en:
                    v_cat_cn = v_res.get("category_zh") or "生活用品"
                    v_cat_en = v_res.get("category_en") or "Household"
                    v_spec_zh = v_res.get("class_zh") or v_class_en
                    res = (v_class_en, v_cat_cn, v_cat_en, "Q223557", v_class_en.replace(" ", ""), v_spec_zh)
                    _cache[asset_id] = {
                        "clean_category_en": res[0],
                        "category": res[1],
                        "category_en": res[2],
                        "wikidata_qcode": res[3],
                        "semantic_class": res[4],
                        "specific_zh": res[5],
                        "source": "qwen2.5vl_vision"
                    }
                    _save_cache()
                    return res

    # 4. Standard mapping resolution
    if matched_class_en and matched_class_en in CATEGORY_MAP:
        cat_cn, cat_en, qcode, spec_zh = CATEGORY_MAP[matched_class_en]
        sem_cls = matched_class_en.replace(" ", "").replace("&", "")
        res = (matched_class_en, cat_cn, cat_en, qcode, sem_cls, spec_zh)
        _cache[asset_id] = {
            "clean_category_en": res[0],
            "category": res[1],
            "category_en": res[2],
            "wikidata_qcode": res[3],
            "semantic_class": res[4],
            "specific_zh": res[5],
            "source": "naming_ontology"
        }
        _save_cache()
        return res

    # 5. Smart Dynamic Extraction (Strictly NO "其他")
    clean_stem = re.sub(r"^(sm[-_]|sn[-_]|md[-_]|sk[-_]|m[-_])", "", item_name, flags=re.IGNORECASE)
    clean_stem = re.sub(r"[-_]\d+$", "", clean_stem).strip()
    noun = clean_stem.capitalize() if clean_stem else "Prop"

    res = (noun, noun, "Custom Assets", "Q223557", noun, noun)
    _cache[asset_id] = {
        "clean_category_en": res[0],
        "category": res[1],
        "category_en": res[2],
        "wikidata_qcode": res[3],
        "semantic_class": res[4],
        "specific_zh": res[5],
        "source": "dynamic_stem"
    }
    _save_cache()
    return res
