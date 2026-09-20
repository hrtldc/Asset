---
name: usd-asset-portal
description: >-
  Complete operational, architectural, and automated classification guide for the 3D USD Asset Portal (http://127.0.0.1:8088/ at G:\JSUDS\Asset).
  Activate and read this entire skill using view_file IMMEDIATELY whenever the user mentions "http://127.0.0.1:8088/", "127.0.0.1:8088", "8088", "Asset Portal", "资产展示平台", "资产入库", or asks about asset categorization, physicalization tags, or server endpoints in G:\JSUDS\Asset.
  Enforces strict asset ingestion rules: MUST recognize semantic meanings via automated ontology & local Qwen2.5-VL vision AI, producing precise Chinese/English category tags. STRICTLY PROHIBITS generic fallback categories like "其他" or "其他资产".
  ALSO covers the local→public sync pipeline (GitHub hrtldc/Asset → Cloudflare Pages at https://asset-9n2.pages.dev/) — activate whenever the user mentions "同步", "外网", "内网外网不一致", "无法同步", "破图", "asset-9n2.pages.dev", pushing assets online, or asks why the public site differs from 127.0.0.1:8088.
---

# 3D USD Asset Portal Architecture & Semantic Ingestion Skill

This skill is the single source of truth for the **3D USD Asset Portal** (running at `http://127.0.0.1:8088/`), located locally at `G:\JSUDS\Asset`. It governs the asset cataloging pipeline from `G:\Simreay\output`, backend endpoints (`server.py`), configuration (`config.py`), automated semantic classifier (`auto_classifier.py`), frontend interface (`index.html`, `static/js/app.js`), and public sync pipelines.

---

## 1. 核心资产入库与全自动语义标签引擎 (Automated Ingestion & Zero-Generic Pipeline)

### 1.1 自动化处理原则 (Fully Automated Lifecycle)
**拒绝人工逐个修复，实行全自动端到端语义识别与持续入库**：
平台不再依赖脆弱的手写 `if-elif` 硬编码，而是通过四级级联自动化引擎进行资产解析：
1. **第一级：毫秒级持久化记忆库 (`static/data/auto_semantic_cache.json`)**
   - 记录已解析资产的语义类别、Q-code、中英文标签，命中即 0ms 返回，避免重复计算。
2. **第二级：拼音与本体知识库匹配 (`RULES` & `CATEGORY_MAP`)**
   - 涵盖 100+ 种常用家具、厨卫、家电、数码及机械组件（如 `diaoshan`, `fengshan`, `matong`, `chugui`, `yushigui` 等）。
3. **第三级：本地 Qwen2.5-VL 视觉多模态大模型自主识别 (`qwen2.5vl:7b` via Ollama `http://127.0.0.1:11434`)**
   - 当遇到生僻命名、代码编号（如 `UNKNOWN_MODEL_99`）或标注错误（如风扇被误标为 `Bowl`）时，系统**自动提取资产的高清渲染缩略图（`t_*.png` / `T_*.png`）送入本地视觉模型**。
   - 视觉大模型直接分析模型的三维外形特征，自主推断出准确的中英文分类并持久化入库。
4. **第四级：动态词根语义萃取 (Dynamic Stem Synthesis)**
   - 剥离前缀（`SM_`、`SN_`、`MD_`）与尾部序号，自动将词根首字母大写作为实体类，**绝对禁止输出“其他”或“其他资产”**。

### 1.2 后台静默自动监听器 (Background Auto-Watcher)
- 服务端常驻后台守护线程 `_background_auto_watcher`，每 30 秒自动扫描 `G:\Simreay\output` 目录。
- 一旦用户或上游物理化批处理管线（SimReadyBatch）向目录输出新资产，后端自动检测、通过视觉与本体引擎打标、预热缓存并推送到前台。用户无需手动点击刷新或反馈人工修改。

---

## 2. 资产语义分类与映射标准表 (Taxonomy Matrix)

| 资产类型 / 拼音标识 | 中文主类别 (`category`) | 英文分类 (`category_en`) | 具体细分中文 (`specific_zh`) | 英文简类 (`clean_category_en`) | Wikidata Q-Code |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`diaoshan` / `ceilingfan`** | **风扇** | Fans & Ventilation | 吊扇 | Ceiling Fan | `Q1641320` |
| **`fengshan` / `fan` / `electricfan`** | **风扇** | Fans & Ventilation | 电风扇 / 落地扇 | Electric Fan | `Q264923` |
| **`matong` / `toilet` / `commode`** | **马桶** | Bathroom & Sanitary | 马桶 | Toilet | `Q7338` |
| **`xishoutai` / `washbasin`** | **洗手池** | Bathroom & Sanitary | 洗手池 | Washbasin | `Q14056` |
| **`yugang` / `bathtub`** | **浴缸** | Bathroom & Sanitary | 浴缸 | Bathtub | `Q108877` |
| **`yushigui` / `vanity`** | **浴室柜** | Bathroom Vanity | 浴室柜 | Bathroom Vanity | `Q1321517` |
| **`ranqizhao` / `luzao` / `gasstove`** | **燃气灶** | Kitchen Appliances | 燃气灶 | Gas Stove | `Q180399` |
| **`kaoxiang` / `weibolu` / `xiwanji`** | **厨房电器** | Kitchen Appliances | 烤箱 / 微波炉 / 洗碗机 | Kitchen Appliance | `Q127950` |
| **`youyanji` / `rangehood`** | **厨房电器** | Kitchen Appliances | 抽油烟机 | Range Hood | `Q584447` |
| **`bingxiang` / `refrigerator`** | **冰箱** | Refrigerator | 冰箱 | Refrigerator | `Q37867` |
| **`xiyiji` / `washingmachine`** | **洗衣机** | Home Appliances | 洗衣机 | Washing Machine | `Q124441` |
| **`kongdiao` / `airconditioner`** | **生活电器** | Home Appliances | 空调 | Air Conditioner | `Q170560` |
| **`taideng` / `desklamp`** | **台灯** | Lighting | 台灯 | Desk Lamp | `Q1134005` |
| **`deng` / `light` / `lamp`** | **灯具** | Lighting | 灯具 / 吊灯 | Light | `Q135260` |
| **`men` / `door` (`pingbanmen`, etc.)** | **门类** | Doors | 平板门 / 双开门 / 折叠门 | Door | `Q36794` |
| **`guizi` / `chugui` / `shounaigui`** | **柜类** | Cabinets & Storage | 柜子 / 橱柜 / 收纳柜 | Cabinet | `Q1321517` |
| **`xiegui` / `shoecabinet`** | **鞋柜** | Shoe Cabinet | 鞋柜 | Shoe Cabinet | `Q1321517` |
| **`chuangtougui` / `nightstand`** | **床头柜** | Nightstand | 床头柜 | Nightstand | `Q1321517` |
| **`zhongdao` / `kitchenisland`** | **中岛台** | Kitchen Island | 中岛台 | Kitchen Island | `Q148600` |
| **`shuzhuangtai` / `dressingtable`** | **梳妆台** | Tables & Vanities | 梳妆台 | Dressing Table | `Q204370` |
| **`chaji` / `coffeetable`** | **茶几** | Tables & Vanities | 茶几 | Coffee Table | `Q1151608` |
| **`canzhuo` / `diningtable`** | **餐桌** | Tables & Vanities | 餐桌 | Dining Table | `Q14748` |
| **`shuzhuo` / `desk`** | **书桌** | Tables & Vanities | 书桌 | Desk | `Q1064858` |
| **`shafa` / `sofa`** | **沙发** | Furniture | 沙发 | Sofa | `Q131514` |
| **`yizi` / `chair`** | **座椅** | Furniture | 椅子 | Chair | `Q15026` |
| **`bijibendiannao` / `laptop`** | **数码用品** | Digital Devices | 笔记本电脑 | Laptop | `Q3962` |
| **`pingbandiannao` / `tablet`** | **数码用品** | Digital Devices | 平板电脑 | Tablet | `Q155972` |
| **`shouji` / `phone`** | **数码用品** | Digital Devices | 手机 | Phone | `Q193175` |
| **`erji` / `headphones`** | **数码用品** | Digital Devices | 耳机 | Headphones | `Q186694` |
| **`wurenji` / `drone`** | **数码用品** | Digital Devices | 无人机 | Drone | `Q223557` |
| **`chazuo` / `shujuxian` / `cable`** | **数码配件** | Cables & Outlets | 插座 / 数据线 | Cable & Outlet | `Q16865280` |

---

## 3. 系统架构与关键文件索引 (Architecture Index)

平台主目录：`G:\JSUDS\Asset`

- **`auto_classifier.py`**:
  - 自动化语义解析核心模块。
  - 整合本地 Qwen2.5-VL 视觉大模型接口、本体正则表、持久化缓存机制。
- **`server.py`**:
  - FastAPI 服务主程序，监听 `http://127.0.0.1:8088/`。
  - `classify_asset_auto(...)`: 自动分类调用入口。
  - `_background_auto_watcher`: 后台自动轮询检测新资产线程。
  - `get_physics_specs(...)`: 自动估算资产质量 (kg)、摩擦系数、弹性系数。
  - `scan_assets(force_reload)`: 扫描 `G:\Simreay\output`，构建资产模型元数据树。
  - `/api/update`: 强制全量重新扫描与缓存强刷端点。
- **`config.py`**:
  - `ASSET_SOURCE_DIR = Path(r"G:\Simreay\output")`
  - `PORT = 8088`
  - `NAME_TRANSLATIONS`: 拼音前缀到中文/英文显示名称映射字典。
- **`static/data/auto_semantic_cache.json`**:
  - 自动沉淀的语义识别结果持久化数据库。
- **`index.html` & `static/js/app.js`**:
  - 赛博风格 Cyber Studio 资产可视化前端，支持 360° 视频悬停播放与直接下载。

---

## 4. 本地 ↔ 外网同步机制 (Local → Public Sync Pipeline)

### 4.1 双站数据来源本质差异

| | 本地管理站 | 外网展示站 |
| :--- | :--- | :--- |
| 地址 | `http://127.0.0.1:8088/` | `https://asset-9n2.pages.dev/` |
| 数据来源 | `scan_assets()` **实时扫描** `G:\Simreay\output` | `static/data/assets.json` **构建快照** |
| 媒体来源 | `/api/media/*` 直出 **原始分辨率** PNG / MP4 | `static/media/*` **540px WebP 缩略图** + 拷贝版 MP4 |
| 新增资产可见 | 后台 watcher 约 30 秒内自动出现 | 必须跑同步管线并等 Pages 构建完成 |

**因此「本地正确」不会自动等于「外网正确」，两者之间有一道显式同步工序。**

### 4.2 同步管线执行顺序（★ 不可颠倒）

```
G:\Simreay\output
      ↓  build_static_showcase.py    压缩 WebP / 拷贝 MP4 / 清理孤儿目录 / 写 assets.json
   static/
      ↓  push_to_git.py  safe_push()
      ├─ ① 媒体（static/media/**）  先提交、先推送 —— 分批推送即断点续传
      └─ ② 元数据（static/data/assets.json）  最后提交、最后推送
      ↓  verify_sync.py              推送后逐条核对线上是否与本地一致
Cloudflare Pages (hrtldc/Asset → asset-9n2.pages.dev)
```

**核心铁律：`assets.json` 必须最后上线。**
它是外网站点唯一的索引来源。只要它上线的瞬间其引用的每个媒体文件都已在 CDN 上，
外网就永远不会出现「索引指向不存在文件」的半同步态。
若中途断网，宁可**元数据不上线**（外网停留在上一个完整状态），也不上线一个破图站点。

### 4.3 关键脚本索引

- **`sync_pipeline.py`** — 一键总入口，四步：物理属性解析 → 构建静态包 → 安全推送 → 线上校验。
- **`push_to_git.py`** — 推送核心。含 `check_local_integrity()` 完整性闸门：
  推送元数据前逐条确认其引用的媒体在本地真实存在，缺失即拒绝上线。
- **`verify_sync.py`** — 线上一致性校验器。用法：
  - `python verify_sync.py` 单次校验
  - `python verify_sync.py --wait 180` 等 Pages 构建完成后校验
- **`build_static_showcase.py`** — 构建静态包，并清理**孤儿媒体目录**
  （已从源目录消失、但残留在 `static/media` 中会持续污染 CDN 的批次目录）。
  安全护栏：扫描到 0 个资产时跳过清理，防止 G 盘未挂载时误删整个媒体库。
- **`watch_and_sync.py`** — 源目录守护进程，实现「上游出资产 ⇒ 外网自动更新」。
  带防抖（等上游写完）、单实例锁、日志 `logs/autosync.log`。
- **`start_autosync_silent.vbs`** / **`stop_autosync.bat`** — 守护进程的启动/停止。

### 4.4 ⚠️ 已知陷阱：Cloudflare Pages 的 SPA 兜底路由

**本平台最危险的假象来源**：请求线上一个不存在的文件时，
Cloudflare Pages 返回 **HTTP 200 + `index.html` 内容**，而不是 404。

后果：缺失的图片/视频**不会**在浏览器 Network 面板显示为红色错误，
页面看上去"正常同步了"，实际是坏图。历史上曾因此掩盖了 19 个缺失视频、
12 个过期缩略图，长达多轮同步无人察觉。

应对：
1. 严禁用「HTTP 状态码」判断线上文件是否存在，必须检查 `Content-Type`
   （`verify_sync.py` 已实现此判断）。
2. 仓库根目录的 `404.html` 用于让缺失资源返回真实 404。
   若仍返回 200，需到 Cloudflare Pages 项目设置里把
   *Not found handling* 从 `Single-page application` 改为 `404 page`。

