# Design

## Context

站点为纯静态外网架构：`build_static_showcase.py` 将资产索引与媒体固化到 `static/`（含 448MB `media/`、`data/assets.json` 约 350KB），`push_to_git.py` 按"媒体先行、元数据最后"策略分批 git 推送，Cloudflare Pages 自动构建发布（构建输出目录为仓库内 `static/`，故站点根路径对应 `static/`）。前端 `static/js/app.js` 在外网模式下给每个媒体 URL 附加 `?_b=${state.forceBuster}`（每次页面加载取 `Date.now()`），并以 `cache:"no-store"` 拉取 assets.json——这使 Cloudflare 边缘缓存与浏览器缓存全部失效，是"给别人很卡"的首要根因。mp4 视频未经任何转码（261 个共 444MB，最大 9MB），视频墙模式同时播放全部视频，悬停播放无并发限制。本机已装 ffmpeg（`C:\ffmpeg\bin`，LGPL 构建，无 libx264，但 `h264_nvenc` 硬件编码可用）。

## Goals / Non-Goals

**Goals:**
- 重复访问近乎零媒体回源（稳定 URL + 长缓存 + immutable）
- 媒体总体积降至约 150MB 以内（ffmpeg 转码，360° 预览质量可接受）
- 任意时刻实际播放视频 ≤3 路；视频墙只播视口内视频
- 保持"一键同步更新"与现有 git 发布链路行为不变

**Non-Goals:**
- 不引入 HLS/DASH 自适应流（对几秒的循环旋转视频过度设计）
- 不改动本地 8000/8088 服务端 API 行为
- 不改 CDN 厂商或部署方式
- 不压缩 webp 缩略图（总共仅 2.4MB，收益可忽略）

## Decisions

1. **稳定版本参数：文件 mtime 而非内容哈希 —— 构建脚本已具备，只需前端停止破坏**
   - 实测确认：`build_static_showcase.py` 第 89-94 行**已经**把稳定版本参数写进 assets.json —— 视频为 `?v=<源文件 mtime>`，缩略图为 `?v=<webp mtime>`，语义完全正确（内容变化才变）。
   - 破坏发生在 `app.js` 外网分支：`rawThumb.includes("?") ? `${rawThumb}&_b=${state.forceBuster}`` 在已正确的稳定参数后追加了每次会话变化的 `_b`，使 URL 每次访问都不同。
   - 因此本项的改动面比初版方案更小：**仅需在 `app.js` 外网分支停止追加 `_b`（含 `openModal` 中的同类逻辑），无需改动构建脚本**。
   - 备选（SHA-256 内容哈希）更精确但需全量扫描 448MB 媒体并改导出数据结构，收益不成比例。

2. **缓存头用 Cloudflare Pages 原生 `_headers` 文件**
   - 在 `static/_headers` 配置：`/media/*` → `Cache-Control: public, max-age=31536000, immutable`；`/data/assets.json`、`/*.html` → `Cache-Control: public, max-age=0, must-revalidate`。
   - 备选（Cloudflare Workers/页面规则）引入额外配置面，Pages 原生支持零成本。

3. **视频转码档位：实测四档对比后确定（本机 ffmpeg n6.1.2 + h264_nvenc）**
   - 实测源视频：243 个为 2048×2048、18 个为 1024×1024，共 261 个 / 444MB / 总时长 34.4 分钟 / 平均码率 1.81 Mbps。2048×2048 即 419 万像素，而实际显示位置仅为网格卡片（约 200-400px 宽）与详情弹窗（约 700px 宽）。
   - 样片实测（最大 `SM_GuiZi08` 8.98MB 与中等 `SM_BiJiBenDianNao` 1.50MB，NVENC `-preset p5 -an +faststart`）：

     | 档位 | 平均降幅 | 全量推算 | SSIM（对齐源分辨率）| SSIM（缩到 700px 显示尺寸后比对）|
     |---|---|---|---|---|
     | 2048 / cq30 | 6.5% | 416MB | 0.9916 | 0.9962 |
     | **2048 / cq36** | **59.4%** | **180MB** | 0.9823 | **0.9912** |
     | 1440 / cq28 | 34.2% | 292MB | 0.9860 | 0.9951 |
     | 960 / cq28 | 66.8% | 148MB | 0.9728 | 0.9919 |

   - **实测结论（含对初版判断的修正）**：初版担心"保持分辨率 + 提高 CRF 会产生可见伪影"，实测不支持该担忧——按访客实际看到的 700px 尺寸比对时，**四档全部 ≥0.991 SSIM，肉眼无法区分**。真正的风险是 `cq30` **降幅仅 6.5%（个别文件反而变大 6.8%）＝无效压缩**，即"档位选低了"比"分辨率"更关键。
   - **决策**：默认档位取 **2048 / cq36**（保留源分辨率、体积降 59% → 约 180MB、显示尺寸 SSIM 0.9912），既尊重"不缩分辨率"的诉求又拿到实际收益；备选 **960 / cq28**（148MB，体积再降 18%，显示尺寸画质 0.9919 与前者持平）——若后续更看重加载速度可切换。参数集中配置，便于单文件调整。
   - `-movflags +faststart` 让元数据前置、首帧更快；去音轨（视频本身无声）可再省体积并规避自动播放策略问题。
   - 编码器优先级（可移植）：`libx264` → `h264_nvenc` → `h264_qsv` → `h264_amf` → `libopenh264`。本机实测 NVENC 可用且快（2048² 约 77fps），无需安装额外组件。
   - **关键前提**：转码只作用于发布产物 `static/media/`，本地 `server.py` 的 `/api/media/*` 直接串流 `G:\Simreay\output` 源文件，本地审阅与 Isaac Sim 取用的仍是原始 2048×2048 视频，画质不受任何影响；源文件亦不做任何修改，可随时重建。
   - 转码集成进 `build_static_showcase.py` 导出流程（实现在独立模块 `transcode_media.py`），幂等策略：记录文件（`static/cache/transcode_manifest.json`，已被 `.gitignore` 覆盖）保存"源 mtime+size、输出 size、参数签名"，三者全部一致才跳过；参数（档位/编码器）变化也会触发重转，避免 immutable 长缓存下取到旧档位产物。
   - 版本参数在源 mtime 之外附加**参数签名**（`?v=<src_mtime>_<params_sig>`）：档位变化时 URL 随之变化，规避"一年 immutable 缓存 + 内容已变但 URL 未变"的错配。
   - ffmpeg 通过**自动探测**获得（见 Decision 6），不安装到仓库、不硬编码本机路径；探测不到时退化为"直接复制源文件"，站点功能不受影响，仅失去体积收益。
   - 备选（H.265/AV1）压缩率更高但 Safari/旧浏览器兼容差；实测已表明"缩到 960px/CRF 28"与本档位在访客显示尺寸下画质持平（SSIM 0.9919 vs 0.9912）且体积再小 18%，如后续更看重加载速度可一行参数切换。

4. **播放并发控制：播放计数信号量 + IntersectionObserver**
   - 模块级 `activePlays` 计数（上限 3），悬停时超过上限则不播放（缩略图闪烁代价可接受）；用 IntersectionObserver 统一管理：卡片离开视口立即 pause 并释放计数。
   - 视频墙模式复用同一 Observer：进入视口（rootMargin 200px 缓冲）才 `play()`，离开即暂停。
   - 备选（队列等待自动补播）交互复杂度高，且用户鼠标早已离开，无意义。

5. **assets.json 改为正常缓存 + 手动强刷**
   - 普通加载：`fetch("data/assets.json")` 默认缓存语义（配合 must-revalidate 得到 304）；"一键同步更新"时才附加时间戳绕缓存。外网"一键同步更新"语义改为"拉取最新数据"（数据新鲜度由发布链路保证，与现状一致）。

6. **构建期工具与本地环境严格隔离（不进入公网产物）**
   - 事实确认：`push_to_git.py` 使用 `git add -A`（第 485/552 行），会暂存仓库内所有文件。因此把 ffmpeg 放在仓库内（如 `Asset\tools\`）会被提交并推到公网仓库——必须避免。
   - 决策：转码工具**只作为构建期依赖存在于本机**，通过自动探测获得，不进入仓库、不进入发布产物；探测顺序为 `FFMPEG_BIN` 环境变量 → `PATH` → 常见安装位置（`C:\ffmpeg\bin`、`Program Files\ffmpeg\bin`、winget Links、choco bin）→ 项目内被 gitignore 的 `tools/ffmpeg/bin`。找不到则跳过转码并给出安装指引，绝不让发布流程失败。
   - 决策：`.gitignore` 增补 `tools/`、`*.mp4.tmp` 等中转产物，作为对 `git add -A` 的兜底防护。
   - 事实确认：当前发布产物**未泄漏本地路径** —— 构建脚本已 `pop("abs_path")`，线上 `assets.json` 中 `abs_path` 字段数为 0；但前端仍在外网模式显示本地专属入口与文案（"排除文件夹设置"依赖 `/api/ignore-rules`、提示"在本地 http://127.0.0.1:8088/ 编辑"），对外部访客无意义且易误导，本次一并隔离。
   - 关键澄清：ffmpeg 是**构建期工具**，外部访客永远不会接触它——访客从 Cloudflare 下载的只有已转码的 mp4 与 HTML/CSS/JS/assets.json。产物中不含任何对本地目录或本地工具的引用。

## Risks / Trade-offs

- [老访客首次回访时旧 URL 缓存一次性失效，需重新下载] → 一次性成本；转码后总体积已降 2/3，可接受
- [cq36 个别高细节模型有可见压缩伪影] → 质量参数集中配置（`transcode_media.TARGET_QUALITY`）；如反馈不佳可单文件调低 cq 重转
- [ffmpeg 转码 261 个文件首次耗时较长（实测 NVENC 下预计 10-20 分钟）] → 幂等跳过 + 逐文件落盘 manifest，中断可续
- [mtime 精度问题导致误跳过] → manifest 同时比对源 size、输出 size 与参数签名，任一不一致即重转
- [编码器差异导致跨机器反复重转] → 参数签名含编码器名；同一台机器上稳定，跨机器切换编码器时会整体重转一次（可接受，换取产物一致）
- [转码覆盖原文件不可逆] → 源文件在 `G:\Simreay\output` 不受影响；`static/media` 可随时由导出管线重建

## Migration Plan

1. 探测/确认 ffmpeg 可用（本机已有 `C:\ffmpeg\bin`，NVENC 可用；无需安装）→ 2. 实现并运行转码管线生成压缩媒体 → 3. 前端 URL 与缓存策略改造 + `_headers` → 4. 本地 `python server.py` 验证两种模式行为 → 5. `push_to_git.py` 正常发布（媒体先行、元数据最后，天然保证切换期外网完整性）→ 回滚：git revert 前端改动即可，转码产物无副作用（源文件在 `G:\Simreay\output`，`static/media` 可由导出管线随时重建）。

## Open Questions

（无——转码质量参数等均已在 Decisions 中给出默认值，可在实施中按效果微调）
