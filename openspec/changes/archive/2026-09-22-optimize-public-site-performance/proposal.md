# Proposal: 优化外网静态展示站性能（Cloudflare Pages）

## Why

外网站点 https://asset-9n2.pages.dev/ 给访客使用时非常卡顿、视频播放缓慢。根因已确诊：前端为每个媒体 URL 附加了每次页面加载都会变化的 `?_b=<timestamp>` 缓存击穿参数，导致 448MB 媒体资产（261 个 mp4 共约 444MB + 267 个 webp 缩略图）完全无法命中浏览器缓存与 Cloudflare 边缘缓存，每位访客每次访问都近乎全量回源拉取；同时 assets.json（约 350KB）以 `cache:"no-store"` 强制重拉、站点没有 `_headers` 缓存策略、mp4 未做任何压缩转码（最大单文件 9MB）、视频墙模式会同时无限制地播放所有视频。

## What Changes

- 移除前端媒体 URL 上破坏缓存的动态查询参数（`&_b=` / forceBuster），沿用构建脚本**已经写好**的基于文件 mtime 的稳定版本参数 `?v=`，使浏览器与 Cloudflare 边缘缓存可长期命中（此为本次收益最大、改动最小的修复点）
- 新增 Cloudflare Pages `_headers` 文件：媒体资源设置长周期 `Cache-Control`（immutable），HTML/JSON 设置短周期或协商缓存
- assets.json 改为可缓存加载（去掉 `cache:"no-store"` 与时间戳击穿参数），并在此基础上提供"一键同步更新"时的强制刷新路径
- 新增视频转码管线：发布导出时用 ffmpeg 将 mp4 统一转码为低码率 H.264（去音轨、保持源分辨率不缩放、`cq 36` 恒定质量压缩，实测目标总体积 444MB → 200MB 以内）。**本地服务播放的仍是 `G:\Simreay\output` 原始视频，画质不受影响**；档位由四档样片实测 + SSIM 客观评分确认（访客显示尺寸下 SSIM 0.9912，肉眼不可区分）
- 网格卡片悬停播放与视频墙模式增加并发上限（同时播放视频数限制 + IntersectionObserver 只播放视口内视频），避免带宽被几十路视频挤占
- 悬停预加载策略优化：仅预加载悬停卡片的视频，离开视口即暂停并释放
- 外网产物与本地环境隔离：外网模式下不再显示仅本地可用的功能入口（"排除文件夹设置"等）与 `127.0.0.1` 文案；构建期工具（ffmpeg）只作为本机依赖自动探测，不进入仓库与发布产物

## Capabilities

### New Capabilities

- `public-site-caching`: 外网静态站的缓存与资源版本策略（稳定 URL 版本参数、_headers 缓存头、assets.json 缓存与强制刷新行为）
- `video-delivery-optimization`: 视频转码压缩管线与前端播放带宽控制（ffmpeg 转码规范、悬停/视频墙并发上限、视口内播放）
- `public-site-isolation`: 外网产物与本地环境隔离（本地专属入口与文案不外显、发布产物不含本地路径与构建工具、构建期依赖可移植自动探测）

### Modified Capabilities

（无——项目此前没有已归档的 specs，全部为新增能力）

## Impact

- **前端代码**：`static/js/app.js`（URL 构造、loadAssets、renderGrid 悬停/视频墙逻辑）、`static/index.html`（资源引用版本）
- **构建/发布管线**：`build_static_showcase.py`（接入新增转码步骤）、新增模块 `transcode_media.py`、新增 `static/_headers`、`.gitignore`（屏蔽构建期工具与中转产物）
- **发布链路**：`push_to_git.py` 无需大改，但转码后媒体体积大幅下降，git 推送与 Cloudflare Pages 构建都会显著加快
- **风险**：老访客浏览器缓存的旧媒体 URL 将一次性失效（可接受，一次性成本）；ffmpeg 为新增构建期依赖，通过自动探测获取（本机已有 `C:\ffmpeg\bin`），探测失败时自动跳过转码、发布流程不受影响
