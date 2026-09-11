# 3D USD 资产展示与下载平台 (SimReady Asset Portal)

本平台专为展示和下载 `G:\Simreay\output` 中的 SimReady 3D 资产（包含 USD/USDC 网格、Materials 材质库与贴图、360° 旋转视频及高清渲染缩略图）设计开发。

---

## 🌟 核心特性

1. **多媒体沉浸式预览**：
   - **影棚灰色卡片风格**：深度还原 NVIDIA Omniverse / SimReady Asset Explorer 视觉质感。
   - **悬停即播 360° 视频**：鼠标移动到任意资产卡片上，自动平滑切换并循环播放该资产的 `V_*.mp4` 旋转展示视频。
   - **视频墙模式一键切换**：支持顶部一键切换为“视频墙模式”，所有包含 360° 视频的模型直接在主页全景播放。

2. **全方位资产下载**：
   - **📦 一键打包完整资产 (ZIP)**：自动将当前资产目录（含 `.usd`、`.usdc`、`Materials/` 贴图、MDL 核心定义、预览图和视频）打包成 ZIP 高速下载。
   - **📥 USD 网格极速下载**：支持独立下载主网格 `.usd` 或 `.usdc` 文件。
   - **📋 单文件明细清单**：可单独下载材质贴图或展示视频。

3. **物理属性与元数据解析**：
   - 自动解析 `_simready_manifest.json`，展示分类 (Category)、语义类 (Semantic Class)、物理质量 (Mass kg)、静动摩擦系数、体积、SimReady 校验状态等。

4. **本地开发工作流打通 (Isaac Sim / Omniverse / Blender)**：
   - **在 Windows 资源管理器中打开**：点击按钮直接打开资产所在的本地物理路径。
   - **复制绝对路径**：一键复制完整路径，方便在 Isaac Sim 舞台或代码中直接引用。

---

## 🚀 启动方式

### 方式 1：双击运行（推荐）
在 `G:\JSUDS\Asset\` 目录下，直接双击运行 **`run.bat`** 即可。
脚本会自动启动后端服务并在默认浏览器打开：
👉 **http://127.0.0.1:8000**

### 方式 2：命令行启动
打开终端，进入本项目目录并执行：
```bash
cd G:\JSUDS\Asset
python server.py
```
然后在浏览器访问 `http://127.0.0.1:8000` 即可。

---

## ⚙️ 配置文件说明 (`config.py`)

如需调整资产目录或服务端口，可编辑 `config.py`：
- `ASSET_SOURCE_DIR`：资产源文件夹路径（默认为 `G:\Simreay\output`）
- `PORT`：Web 服务端口（默认为 `8000`）
- `NAME_TRANSLATIONS`：模型拼音前缀到中文/英文名称的映射字典