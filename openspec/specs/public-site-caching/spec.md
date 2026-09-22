# public-site-caching Specification

# Spec Delta: public-site-caching（外网站点缓存与资源版本策略）

## Purpose

定义外网静态展示站在浏览器与 CDN（Cloudflare Pages）上的资源缓存行为，确保 448MB 级媒体资产可被长期缓存命中、重复访问接近零回源，同时保留资产数据更新后强制刷新的能力。

## Requirements

### Requirement: 媒体资源 URL 必须使用稳定版本参数

外网（静态）模式下，缩略图与视频的 URL MUST NOT 附带随页面加载会话变化的查询参数（如每次刷新都变化的 `Date.now()` 值）。版本参数只能来源于该文件的内容版本（如文件的 mtime/哈希），使同一文件在多次访问之间 URL 保持不变。

#### Scenario: 同一访客二次访问站点
- **WHEN** 访客在媒体文件未变更的情况下再次打开外网站点
- **THEN** 所有缩略图与视频请求的 URL 与上次访问完全一致，命中浏览器缓存（from cache / 304），不产生对媒体文件的完整重新下载

#### Scenario: 单个资产媒体更新
- **WHEN** 某资产的视频文件被重新导出（mtime 变化）并发布
- **THEN** 仅该资产的媒体 URL 版本参数变化并重新下载，其余资产媒体 URL 保持不变且继续命中缓存

### Requirement: 静态缓存头配置

站点 MUST 包含 Cloudflare Pages 的 `_headers` 规则：媒体文件（webp/mp4 等）设置不低于 30 天的 `public, max-age` 并标记 `immutable`；HTML 与 assets.json 使用短缓存或协商缓存（如 `max-age=0, must-revalidate` 或不超过 5 分钟的 `max-age`）。

#### Scenario: 媒体响应缓存头
- **WHEN** 浏览器或 Cloudflare 边缘节点请求任一 webp/mp4 媒体文件
- **THEN** 响应包含长周期 `Cache-Control: public, max-age>=2592000, immutable`

#### Scenario: 数据文件缓存头
- **WHEN** 浏览器请求 index.html 或 assets.json
- **THEN** 响应的 Cache-Control 允许及时感知更新（max-age 为 0 或极小值，配合 must-revalidate / ETag）

### Requirement: assets.json 可缓存且保留强制刷新

外网模式下加载 assets.json SHALL 使用浏览器正常缓存语义（MUST NOT 使用 `cache:"no-store"` 及时间戳击穿参数）；"一键同步更新"操作 MUST 仍能绕过缓存获取最新数据。

#### Scenario: 普通加载
- **WHEN** 访客正常打开外网站点
- **THEN** assets.json 请求使用默认缓存策略，可命中缓存或以 304 协商返回

#### Scenario: 一键同步更新
- **WHEN** 访客点击"一键同步更新"按钮
- **THEN** 前端以绕过缓存的方式重新拉取 assets.json 并重新渲染资产列表
