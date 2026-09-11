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
NAME_TRANSLATIONS = {
    "SM_GuiZi": "Cabinet / 柜子",
    "SM_BingXiang": "Refrigerator / 冰箱",
    "SM_ChuangTouGui": "Nightstand / 床头柜",
    "SM_YuShiGui": "Bathroom Vanity / 浴室柜",
    "SM_ZheDieMen": "Folding Door / 折叠门",
    "SM-TUILAMEN": "Sliding Door / 推拉门",
    "SM-CHAJI": "Coffee Table / 茶几",
    "SM-CHUGUI": "Kitchen Cabinet / 橱柜",
    "SM-SHUZHUANGTAI": "Dressing Table / 梳妆台",
    "SM-ZHUANGSHIGUI": "Display Cabinet / 装饰柜",
    "SM-XIEGUI": "Shoe Cabinet / 鞋柜",
    "SM-SHOUNAIGUI": "Storage Cabinet / 收纳柜",
    "SM-CHAZUOSHUJUXIAN": "Cable & Outlet / 插座数据线",
    "SM_KaoXiang": "Oven / 烤箱",
    "SM_XiaoDuGui": "Disinfection Cabinet / 消毒柜",
    "SM_Door": "Door / 门",
    "SM-ZHONGDAO": "Kitchen Island / 中岛台",
    "SM_ShuiBa": "Water Bar / 水吧台",
    "SN_ShoJiShuJuXian": "Phone Cable / 手机数据线",
}