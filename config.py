# -*- coding: utf-8 -*-
"""
Configuration settings for 3D USD Asset Portal
"""
from pathlib import Path

# Base directory where 3D assets are located
ASSET_SOURCE_DIR = Path(r"G:\Simreay\output")

# Server settings - Port 8088
HOST = "127.0.0.1"
PORT = 8088

# Base directory of the web application
APP_DIR = Path(__file__).parent.resolve()
STATIC_DIR = APP_DIR / "static"

# Translation & Display Mappings for common Chinese pinyin/model names
# Formatted strictly as: "English / 中文"
NAME_TRANSLATIONS = {
    # Cabinets & Storage
    "SM_GuiZi": "Cabinet / 柜子",
    "SM-SHOUNAIGUI": "Storage Cabinet / 收纳柜",
    "SM-ZHUANGSHIGUI": "Display Cabinet / 装饰柜",
    "SM-XIEGUI": "Shoe Cabinet / 鞋柜",
    "SM_XieGui": "Shoe Cabinet / 鞋柜",
    "SM-CHUGUI": "Kitchen Cabinet / 橱柜",
    "SM-hongjiugui": "Wine Cabinet / 红酒柜",
    "SM_XiaoDuGui": "Disinfection Cabinet / 消毒柜",
    "SM_ShuiBa": "Water Bar / 水吧台",
    "SM-ZHONGDAO": "Kitchen Island / 中岛台",

    # Bathroom
    "SM_YuShiGui": "Bathroom Vanity / 浴室柜",
    "SM-YUSHIGUI": "Bathroom Vanity / 浴室柜",

    # Doors
    "SM-PINGBANMEN": "Flat Door / 平板门",
    "SM-SHUANGKAIMEN": "Double Door / 双开门",
    "SM-ZHEDIEMEN": "Folding Door / 折叠门",
    "SM_ZheDieMen": "Folding Door / 折叠门",
    "SM-TUILAMEN": "Sliding Door / 推拉门",
    "SM_Men": "Door / 门",
    "SM_Door": "Door / 门",

    # Bedroom & Furniture
    "SM_ChuangTouGui": "Nightstand / 床头柜",
    "SM-CHUANGTOUGUI": "Nightstand / 床头柜",
    "SM-SHUZHUANGTAI": "Dressing Table / 梳妆台",
    "SM-CHAJI": "Coffee Table / 茶几",

    # Kitchen & Home Appliances
    "SM_BingXiang": "Refrigerator / 冰箱",
    "SM-bingxiang": "Refrigerator / 冰箱",
    "SM_KaoXiang": "Oven / 烤箱",
    "SM-WEIBOLU": "Microwave Oven / 微波炉",
    "SM-XIWANJI": "Dishwasher / 洗碗机",
    "SM_QiHuaLu": "Gas Stove / 气化炉",
    "SM_XiYiJi": "Washing Machine / 洗衣机",

    # Lighting
    "SM_Deng": "Light / 灯具",

    # Cables & Outlets
    "SM-CHAZUOSHUJUXIAN": "Cable & Outlet / 插座数据线",
    "SN_ShoJiShuJuXian": "Phone Cable / 手机数据线",

    # Digital Devices & Electronics (数码用品)
    "SM_BiJiBenDianNao": "Laptop / 笔记本电脑",
    "SM-BIJIBENDIANNAO": "Laptop / 笔记本电脑",
    "SM-PINGBANDIANNAO": "Tablet / 平板电脑",
    "SM_ShoJi": "Phone / 手机",
    "SM-SHOUJI": "Phone / 手机",
    "SM_ErJi": "Headphones / 耳机",
    "SM-ERJI": "Headphones / 耳机",
    "SM_DaJiangWuRenJi": "Drone / 无人机",
    "SM-WURENJI": "Drone / 无人机",
    "SM_SheXiangTou": "Camera / 摄像头",
    "SM-SHEXIANGTOU": "Camera / 摄像头",
    "SM-YUNTAI": "Gimbal / 云台相机",
}

import fnmatch

# Default patterns for batches/folders that should NEVER be ingested or pushed
DEFAULT_IGNORE_PATTERNS = [
    "*_Joint",
    "*_joint",
    "*_Processed",
    "*_processed",
    "*_SimReady_Processed*",
    "*_wip*",
    "*_temp*",
    "*_tmp*",
    "*_draft*",
    "*_raw*",
    "*_bak*",
    "*_backup*",
    ".*",
    "_*"
]

IGNORE_FILE = APP_DIR / "ignore_batches.txt"

def get_ignore_patterns():
    patterns = list(DEFAULT_IGNORE_PATTERNS)
    if IGNORE_FILE.exists():
        try:
            with open(IGNORE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    clean = line.strip()
                    if clean and not clean.startswith("#"):
                        patterns.append(clean)
        except Exception:
            pass
    return patterns

def is_batch_ignored(batch_name: str) -> bool:
    """Check if a batch directory should be filtered out from local scan and public push."""
    name = batch_name.strip()
    if not name:
        return True
    patterns = get_ignore_patterns()
    for pat in patterns:
        if fnmatch.fnmatch(name.lower(), pat.lower()):
            return True
    return False