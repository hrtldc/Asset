# Tasks

## 1. 构建期依赖与转码管线（video-delivery-optimization）

- [x] 1.1 【已完成·实测】样片基准测试：3 个代表样片 × 4 档位（2048/cq30、2048/cq36、1440/cq28、960/cq28）实测体积与 SSIM，产出 `G:\JSUDS\_perf_test\result_full.json`；实测结论：2048/cq30 仅降 6.5%（无效，个别文件反而变大 6.8%），2048/cq36 降 59.4%→180MB（显示尺寸 SSIM 0.9912，保持分辨率的最优解），1440/cq28 降 34.2%→292MB，960/cq28 降 66.8%→148MB（显示尺寸 SSIM 0.9919）
- [x] 1.2 【已完成】档位定稿 **2048/cq36**（用户确认"保持源分辨率"），已同步写入 design.md / proposal.md / video-delivery-optimization spec；验证：三份产物档位表述一致（cq36、目标 ≤200MB），无"待定"残留
- [x] 1.3 【已完成·已验证】新增 `transcode_media.py`：ffmpeg 自动探测（`FFMPEG_BIN` → PATH → 常见安装位置 → 项目内被 gitignore 的 `tools/ffmpeg/bin`），不安装、不硬编码、不进仓库；验证：`python transcode_media.py --detect` 定位到 `C:\ffmpeg\bin\ffmpeg.exe` 并选出 `h264_nvenc -preset p5 -cq 36`；`--no-ffmpeg` 模拟屏蔽后返回 `available=False`、`process()` 返回 `copied`，全程无异常
- [x] 1.4 【已完成·已验证】转码接入 `build_static_showcase.py`（幂等：manifest 记录源 mtime+size、输出 size、参数签名，任一变化才重转；失败自动退化为复制，绝不中断发布）；验证：首次全量运行 9m09s，258/258 个可转码视频全部成功、manifest 258 条生成；二次运行 6.3s 全部跳过（转码 0 | 跳过 258）
- [x] 1.5 【已完成·已验证】全量统计与抽样：视频总体积 **442MB → 132MB（降 70.2%）**，`static/media` 整体 448MB → 138MB；转码产物 box 顺序 `ftyp→moov→mdat`（+faststart 生效，首帧快）；样片已交付用户肉眼比对（`SM_GuiZi08` 原片 8.98MB → 2.74MB）。已知边界：`wq_11/SM-PINGBANMEN-10_B` 源文件本身 NAL 流损坏无法解码，按设计退化为保留原样（与改版前线上状态一致，建议重导出该资产）；另有 2 个未被 assets.json 引用的历史遗留视频（`V_ZHEDIEMEN_fold.mp4`、`SM-ZHUANGSHIGUI-2/V_ZHUANGSHIGUI-2.mp4`，共 4.1MB）未被处理也不被访客下载
- [x] 1.6 【已完成·已验证】`.gitignore` 增补 `tools/`、`*.tmp.mp4`、`*.mp4.tmp`、`.transcode_probe_tmp*`；验证：`git status --porcelain --ignored` 中转码临时文件显示为 `!!`（已忽略），ffmpeg 及其下载包不在仓库中

## 2. 缓存策略（public-site-caching）

- [x] 2.1 【已完成】新建 `static/_headers`：`/media/*` → `public, max-age=31536000, immutable`；`/`、`/*.html`、`/data/*` → `max-age=0, must-revalidate`；`/css/*`、`/js/*` → `max-age=86400, must-revalidate`；验证：本地 `_headers` 模拟服务实测响应头正确（线上验证在 5.3 发布后复核）
- [x] 2.2 【已完成·已验证】`app.js` 外网模式（`renderGrid` 与 `openModal` 两处）停止追加 `&_b=${forceBuster}`，改用构建脚本写入的稳定 `?v=<源mtime>_<转码参数签名>`；验证：CDP 实测两次访问媒体 URL 完全一致（`mediaUrlsStableAcrossReload: true`）、全部媒体 URL 中 `_b=` 出现 0 次
- [x] 2.3 【已完成·已验证】`loadAssets()` 外网模式改为正常缓存语义（去掉 `no-store` 与时间戳），"一键同步更新"仍以 `no-store + 时间戳` 绕过缓存；验证：二次访问 4/4 媒体请求 `fromDiskCache`，assets.json 正常加载、强刷路径保留

## 3. 播放带宽控制（video-delivery-optimization）

- [x] 3.1 【已完成·已验证】`app.js` 实现播放并发上限（`PLAY_LIMIT=3`）+ IntersectionObserver 视口管理；验证（CDP 实测）：同时请求 6 个卡片播放仅 3 个被接受（`acceptedCount: 3, concurrent: 3`）；滚动离开视口后并发降为 0
- [x] 3.2 【已完成·已验证】视频墙模式接入同一 Observer（rootMargin 200px）：验证：视口内 8 个视频播放、其余 251 个不加载（`concurrent: 8 / inViewport: 8 / total: 259`），改版前为全部同时播放
- [x] 3.3 【已完成·已验证】`index.html` 资源引用版本号更新为 `?v=20260922_perf1`；验证：CDP 实测页面加载的是新版 JS

## 4. 外网产物隔离（public-site-isolation）

- [x] 4.1 【已完成·已验证】外网模式隐藏本地专属入口：`applyEnvironmentVisibility()` 在静态模式隐藏"排除文件夹设置"按钮与弹窗内"本地开发集成"区块；验证：外网模拟模式下 `filterBtnVisible: false`、`localSectionDisplay: "none"`；本地 8088 模式两者照常可见可用
- [x] 4.2 【已完成·已验证】清理本地文案：`index.html` 的"本地 8088 页面"、`updateAllBtn` 的 `G:\Simreay\output` 提示、`app.js` 的 `127.0.0.1:8088` 与"本地 8088 端口"提示均改为中性文案；验证：外网模拟模式下页面与 HTML 中 `127.0.0.1|localhost|:8088` 命中 0 次
- [x] 4.3 【已完成·已验证】发布产物无本地路径与构建工具：`static/data/assets.json` 中 `abs_path` 出现 0 次、`G:\` 出现 0 次；`git status` 无 tools/transcode 临时产物（已被 gitignore 覆盖）

## 5. 本地验证与发布

- [x] 5.1 【已完成·已验证】本地 8088 回归（headless Chrome + CDP 实测）：网格 260 卡/259 视频渲染正常、首屏视频请求数 0、搜索"GuiZi" 260→23、USD 筛选正常、详情弹窗打开且视频加载、"排除文件夹设置"弹窗正常读取本地接口、悬停播放/离开暂停均正常、并发上限 3 生效
- [x] 5.2 【已完成·已验证】外网静态模式模拟（`_headers` 语义的本地静态服务 + CDP）：媒体 URL 稳定、二次访问 4/4 命中磁盘缓存（`Cache-Control: public, max-age=31536000, immutable`）、无本地专属入口与文案、悬停并发 ≤3、视频墙只播视口内视频
- [ ] 5.3 运行发布链路（`push_to_git.py` 分批推送），确认 Cloudflare Pages 构建成功后线上 https://asset-9n2.pages.dev/ 行为符合本 change 三份 spec 的全部 Scenario，验证：线上抽查 `_headers` 生效、媒体 URL 稳定、二次访问基本零媒体回源
