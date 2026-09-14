/**
 * 3D USD Asset Portal Frontend Application - One-Click Force Update Edition
 */

const isLocalServer = (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") && (window.location.port === "8088" || window.location.port === "8000");

const state = {
  assets: [],
  filteredAssets: [],
  batches: [],
  categories: [],
  categoryCounts: {},
  batchCounts: {},
  stats: {},
  stripMode: "category", // 'category' | 'batch'
  currentCategory: "all",
  currentBatch: "all",
  mediaFilter: "all", // 'all' | 'video' | 'usd'
  searchQuery: "",
  sortBy: "name", // 'name' | 'category' | 'batch' | 'size'
  viewMode: "thumb", // 'thumb' (hover play) | 'videowall' (always play)
  selectedAsset: null,
  activeMediaTab: "video", // 'video' | 'image'
  forceBuster: Date.now()
};

// DOM elements
const elements = {
  assetGrid: document.getElementById("assetGrid"),
  searchInput: document.getElementById("searchInput"),
  filterChips: document.getElementById("filterChips"),
  stripModeCategory: document.getElementById("stripModeCategory"),
  stripModeBatch: document.getElementById("stripModeBatch"),
  mediaFilterSelect: document.getElementById("mediaFilterSelect"),
  sortSelect: document.getElementById("sortSelect"),
  modeThumbBtn: document.getElementById("modeThumbBtn"),
  modeVideoBtn: document.getElementById("modeVideoBtn"),
  totalAssetsCount: document.getElementById("totalAssetsCount"),
  filteredCount: document.getElementById("filteredCount"),
  videosCount: document.getElementById("videosCount"),
  usdCount: document.getElementById("usdCount"),
  totalSize: document.getElementById("totalSize"),
  updateAllBtn: document.getElementById("updateAllBtn"),
  // Modal
  modalBackdrop: document.getElementById("assetModal"),
  modalCloseBtn: document.getElementById("modalCloseBtn"),
  modalTitle: document.getElementById("modalTitle"),
  modalSubtitle: document.getElementById("modalSubtitle"),
  modalVideoPlayer: document.getElementById("modalVideoPlayer"),
  modalImagePreview: document.getElementById("modalImagePreview"),
  modalVideoTabBtn: document.getElementById("modalVideoTabBtn"),
  modalImageTabBtn: document.getElementById("modalImageTabBtn"),
  modalDownloadZip: document.getElementById("modalDownloadZip"),
  modalQuickUsdRow: document.getElementById("modalQuickUsdRow"),
  modalMassVal: document.getElementById("modalMassVal"),
  modalSemanticClassVal: document.getElementById("modalSemanticClassVal"),
  modalQCodeVal: document.getElementById("modalQCodeVal"),
  modalStaticFrictionVal: document.getElementById("modalStaticFrictionVal"),
  modalDynamicFrictionVal: document.getElementById("modalDynamicFrictionVal"),
  modalRestitutionVal: document.getElementById("modalRestitutionVal"),
  modalOpenFolderBtn: document.getElementById("modalOpenFolderBtn"),
  modalCopyPathBtn: document.getElementById("modalCopyPathBtn"),
  toast: document.getElementById("toastNotice")
};

// Initialize
async function initApp() {
  bindEvents();
  await loadAssets();
}

function showToast(msg) {
  if (!elements.toast) return;
  elements.toast.textContent = msg;
  elements.toast.classList.add("show");
  setTimeout(() => {
    elements.toast.classList.remove("show");
  }, 2800);
}

// Event Listeners
function bindEvents() {
  elements.searchInput.addEventListener("input", (e) => {
    state.searchQuery = e.target.value.trim().toLowerCase();
    applyFilters();
  });

  elements.mediaFilterSelect.addEventListener("change", (e) => {
    state.mediaFilter = e.target.value;
    applyFilters();
  });

  elements.sortSelect.addEventListener("change", (e) => {
    state.sortBy = e.target.value;
    applyFilters();
  });

  elements.modeThumbBtn.addEventListener("click", () => {
    setViewMode("thumb");
  });

  elements.modeVideoBtn.addEventListener("click", () => {
    setViewMode("videowall");
  });

  if (elements.stripModeCategory) {
    elements.stripModeCategory.addEventListener("click", () => {
      state.stripMode = "category";
      elements.stripModeCategory.classList.add("active");
      if (elements.stripModeBatch) elements.stripModeBatch.classList.remove("active");
      state.currentBatch = "all";
      renderFilterChips();
      applyFilters();
    });
  }

  if (elements.stripModeBatch) {
    elements.stripModeBatch.addEventListener("click", () => {
      state.stripMode = "batch";
      elements.stripModeBatch.classList.add("active");
      if (elements.stripModeCategory) elements.stripModeCategory.classList.remove("active");
      state.currentCategory = "all";
      renderFilterChips();
      applyFilters();
    });
  }

  if (!isLocalServer && elements.updateAllBtn) {
    elements.updateAllBtn.style.display = "none";
  }

  // One-Click Force Update & Cache Busting
  if (elements.updateAllBtn) {
    elements.updateAllBtn.addEventListener("click", async () => {
      elements.updateAllBtn.classList.add("spinning");
      state.forceBuster = Date.now();
      await loadAssets(true);
      elements.updateAllBtn.classList.remove("spinning");
      showToast(`⚡ 资产与图片已全部强制同步完成！共 ${state.assets.length} 套模型最新就绪`);
    });
  }

  // Modal events
  elements.modalCloseBtn.addEventListener("click", closeModal);
  elements.modalBackdrop.addEventListener("click", (e) => {
    if (e.target === elements.modalBackdrop) closeModal();
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });

  elements.modalVideoTabBtn.addEventListener("click", () => {
    switchMediaTab("video");
  });

  elements.modalImageTabBtn.addEventListener("click", () => {
    switchMediaTab("image");
  });

  elements.modalOpenFolderBtn.addEventListener("click", async () => {
    if (!state.selectedAsset) return;
    try {
      const res = await fetch("/api/open-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          batch: state.selectedAsset.batch,
          asset: state.selectedAsset.name
        })
      });
      const data = await res.json();
      if (data.success) {
        showToast("📂 已在 Windows 资源管理器中打开该资产文件夹");
      } else {
        showToast("打开失败: " + (data.error || "未知错误"));
      }
    } catch (err) {
      showToast("请求失败: " + err.message);
    }
  });

  elements.modalCopyPathBtn.addEventListener("click", () => {
    if (!state.selectedAsset) return;
    navigator.clipboard.writeText(state.selectedAsset.abs_path).then(() => {
      showToast("📋 本地绝对路径已成功复制到剪贴板");
    });
  });
}

function setViewMode(mode) {
  state.viewMode = mode;
  if (mode === "videowall") {
    document.body.classList.add("mode-videowall");
    elements.modeVideoBtn.classList.add("active");
    elements.modeThumbBtn.classList.remove("active");
    document.querySelectorAll(".card-preview video.has-video").forEach((v) => {
      if (!v.src && v.dataset.src) v.src = v.dataset.src;
      v.play().catch(() => {});
    });
  } else {
    document.body.classList.remove("mode-videowall");
    elements.modeThumbBtn.classList.add("active");
    elements.modeVideoBtn.classList.remove("active");
    document.querySelectorAll(".card-preview video").forEach((v) => {
      v.pause();
    });
  }
}

// Fetch Assets from API with Cache Buster
async function loadAssets(forceRefresh = false) {
  try {
    let data;
    if (isLocalServer) {
      const endpoint = forceRefresh ? "/api/update" : "/api/assets";
      const url = `${endpoint}?refresh=${forceRefresh ? "true" : "false"}&_t=${Date.now()}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } else {
      // Public Static Mode (Cloudflare / GitHub Pages)
      let staticRes = await fetch("data/assets.json");
      if (!staticRes.ok) staticRes = await fetch("/data/assets.json");
      if (!staticRes.ok) staticRes = await fetch("/static/data/assets.json");
      if (!staticRes.ok) throw new Error(`Static data load failed: ${staticRes.status}`);
      data = await staticRes.json();
    }

    state.assets = data.assets || [];
    state.batches = data.batches || [];
    state.categories = data.categories || [];
    state.categoryCounts = data.category_counts || {};
    state.batchCounts = data.batch_counts || {};
    state.stats = data.stats || {};

    updateStatsBar();
    renderFilterChips();
    applyFilters();
  } catch (err) {
    console.warn("API request failed, attempting static data fallback:", err);
    try {
      let staticRes = await fetch("/data/assets.json");
      if (!staticRes.ok) staticRes = await fetch("data/assets.json");
      if (!staticRes.ok) staticRes = await fetch("/static/data/assets.json");
      if (staticRes.ok) {
        const data = await staticRes.json();
        state.assets = data.assets || [];
        state.batches = data.batches || [];
        state.categories = data.categories || [];
        state.categoryCounts = data.category_counts || {};
        state.batchCounts = data.batch_counts || {};
        state.stats = data.stats || {};
        updateStatsBar();
        renderFilterChips();
        applyFilters();
        showToast("ℹ️ 当前处于离线静态模式，已加载缓存资产数据");
        return;
      }
    } catch (staticErr) {
      console.error("Static data fallback failed:", staticErr);
    }
    elements.assetGrid.innerHTML = `
      <div class="empty-state" style="grid-column: 1/-1;">
        <h3>无法连接至资产服务</h3>
        <p>${err.message}</p>
      </div>`;
  }
}

function updateStatsBar() {
  if (elements.totalAssetsCount) elements.totalAssetsCount.textContent = state.stats.total_assets || state.assets.length;
  if (elements.videosCount) elements.videosCount.textContent = state.stats.total_videos || 0;
  if (elements.usdCount) elements.usdCount.textContent = state.stats.total_usds || 0;
  if (elements.totalSize) elements.totalSize.textContent = `${state.stats.total_size_gb || 0} GB`;
}

// Render Filter Chips (Categories or Batches)
function renderFilterChips() {
  const container = elements.filterChips;
  container.innerHTML = "";

  if (state.stripMode === "category") {
    const allChip = document.createElement("button");
    allChip.className = `batch-chip ${state.currentCategory === "all" ? "active" : ""}`;
    allChip.textContent = `全部类别 (${state.assets.length})`;
    allChip.addEventListener("click", () => {
      state.currentCategory = "all";
      container.querySelectorAll(".batch-chip").forEach((c) => c.classList.remove("active"));
      allChip.classList.add("active");
      applyFilters();
    });
    container.appendChild(allChip);

    state.categories.forEach((cat) => {
      const count = state.categoryCounts[cat] || 0;
      const chip = document.createElement("button");
      chip.className = `batch-chip ${state.currentCategory === cat ? "active" : ""}`;
      chip.textContent = `${cat} (${count})`;
      chip.addEventListener("click", () => {
        state.currentCategory = cat;
        container.querySelectorAll(".batch-chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        applyFilters();
      });
      container.appendChild(chip);
    });
  } else {
    const allChip = document.createElement("button");
    allChip.className = `batch-chip ${state.currentBatch === "all" ? "active" : ""}`;
    allChip.textContent = `全部批次 (${state.assets.length})`;
    allChip.addEventListener("click", () => {
      state.currentBatch = "all";
      container.querySelectorAll(".batch-chip").forEach((c) => c.classList.remove("active"));
      allChip.classList.add("active");
      applyFilters();
    });
    container.appendChild(allChip);

    state.batches.forEach((batch) => {
      const count = state.batchCounts[batch] || 0;
      const chip = document.createElement("button");
      chip.className = `batch-chip ${state.currentBatch === batch ? "active" : ""}`;
      chip.textContent = `${batch} (${count})`;
      chip.addEventListener("click", () => {
        state.currentBatch = batch;
        container.querySelectorAll(".batch-chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        applyFilters();
      });
      container.appendChild(chip);
    });
  }
}

// Filtering and Sorting
function applyFilters() {
  let list = [...state.assets];

  // Category filter
  if (state.currentCategory !== "all") {
    list = list.filter((a) => a.category === state.currentCategory);
  }

  // Batch filter
  if (state.currentBatch !== "all") {
    list = list.filter((a) => a.batch === state.currentBatch);
  }

  // Media filter
  if (state.mediaFilter === "video") {
    list = list.filter((a) => a.has_video);
  } else if (state.mediaFilter === "usd") {
    list = list.filter((a) => a.has_usd);
  }

  // Search query
  if (state.searchQuery) {
    const q = state.searchQuery;
    list = list.filter((a) => {
      return (
        a.name.toLowerCase().includes(q) ||
        a.displayName.toLowerCase().includes(q) ||
        a.category.toLowerCase().includes(q) ||
        a.category_en.toLowerCase().includes(q) ||
        a.batch.toLowerCase().includes(q)
      );
    });
  }

  // Sort
  if (state.sortBy === "name") {
    list.sort((a, b) => a.displayName.localeCompare(b.displayName));
  } else if (state.sortBy === "category") {
    list.sort((a, b) => a.category.localeCompare(b.category) || a.displayName.localeCompare(b.displayName));
  } else if (state.sortBy === "batch") {
    list.sort((a, b) => a.batch.localeCompare(b.batch) || a.name.localeCompare(b.name));
  } else if (state.sortBy === "size") {
    list.sort((a, b) => b.total_size_bytes - a.total_size_bytes);
  }

  state.filteredAssets = list;
  if (elements.filteredCount) elements.filteredCount.textContent = list.length;
  renderGrid();
}

// Render Asset Cards
function renderGrid() {
  const container = elements.assetGrid;
  container.innerHTML = "";

  if (state.filteredAssets.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1/-1;">
        <h3>未找到匹配的模型资产</h3>
        <p>请尝试选择其他类别或更改检索关键词</p>
      </div>`;
    return;
  }

  const fragment = document.createDocumentFragment();

  state.filteredAssets.forEach((asset) => {
    const card = document.createElement("div");
    card.className = "asset-card";
    card.setAttribute("data-id", asset.id);

    // Media path resolution (Local server vs Static CDN)
    let thumbUrl = null;
    let fallbackThumbUrl = "";
    let videoUrl = null;

    if (isLocalServer) {
      const vStamp = `${asset.thumbnail_mtime || 0}_${state.forceBuster}`;
      thumbUrl = asset.thumbnail_rel_path
        ? `/api/thumbnail/${asset.batch}/${asset.name}/${asset.thumbnail_rel_path}?v=${vStamp}`
        : null;
      fallbackThumbUrl = asset.thumbnail_rel_path
        ? `/api/media/${asset.batch}/${asset.name}/${asset.thumbnail_rel_path}?v=${vStamp}`
        : "";
      videoUrl = asset.video_rel_path
        ? `/api/media/${asset.batch}/${asset.name}/${asset.video_rel_path}?v=${asset.video_mtime || 0}_${state.forceBuster}`
        : null;
    } else {
      thumbUrl = asset.static_thumb_path || (asset.thumbnail_rel_path ? `media/${asset.batch}/${asset.name}/thumb.webp` : null);
      videoUrl = asset.static_video_path || (asset.video_rel_path ? `media/${asset.batch}/${asset.name}/${asset.video_rel_path.split("/").pop()}` : null);
    }

    let mediaHtml = "";
    if (thumbUrl) {
      mediaHtml += `<img src="${thumbUrl}" alt="${asset.displayName}" loading="lazy" class="${videoUrl ? "has-video-sibling" : ""}" onerror="if('${fallbackThumbUrl}' && this.src!=='${fallbackThumbUrl}'){this.src='${fallbackThumbUrl}';}">`;
    }
    if (videoUrl) {
      mediaHtml += `<video data-src="${videoUrl}" loop muted playsinline preload="none" class="has-video"></video>`;
    }
    if (!thumbUrl && !videoUrl) {
      mediaHtml = `
        <div class="no-preview" style="color:#64748b; font-size:0.9rem; font-weight:600; display:flex; flex-direction:column; align-items:center; gap:8px;">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
            <line x1="12" y1="22.08" x2="12" y2="12"/>
          </svg>
          <span>USD 3D Mesh</span>
        </div>`;
    }

    card.innerHTML = `
      <div class="card-preview">
        ${
          asset.has_video
            ? `<span class="badge-video"><span class="video-playing-indicator"></span> 关节视频</span>`
            : ""
        }
        ${mediaHtml}
        <div class="card-hover-actions">
          <button class="btn-card-action" type="button">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
            </svg>
            详情与下载
          </button>
        </div>
      </div>
      <div class="card-info">
        <div class="card-title" title="${asset.displayName} (${asset.name})">${asset.displayName}</div>
        <div class="card-meta">
          <span class="card-tag">${asset.category}</span>
          <span>·</span>
          <span>${asset.total_size_mb} MB</span>
          ${asset.has_usd ? `<span>·</span><span class="card-tag-usd">USD</span>` : ""}
        </div>
      </div>
    `;

    // Video hover interaction with on-demand zero-lag loading
    const videoElem = card.querySelector("video.has-video");
    if (videoElem) {
      videoElem.addEventListener("playing", () => {
        videoElem.classList.add("is-playing");
      });
      card.addEventListener("mouseenter", () => {
        if (!videoElem.src && videoElem.dataset.src) {
          videoElem.src = videoElem.dataset.src;
          videoElem.preload = "auto";
        }
        if (state.viewMode === "thumb") {
          const playPromise = videoElem.play();
          if (playPromise !== undefined) {
            playPromise.catch(() => {});
          }
        }
      });
      card.addEventListener("mouseleave", () => {
        if (state.viewMode === "thumb") {
          videoElem.pause();
          videoElem.classList.remove("is-playing");
          videoElem.currentTime = 0;
        }
      });
    }

    // Card click opens modal
    card.addEventListener("click", () => {
      openModal(asset);
    });

    fragment.appendChild(card);
  });

  container.appendChild(fragment);

  // If in video-wall mode, play newly rendered videos
  if (state.viewMode === "videowall") {
    container.querySelectorAll("video.has-video").forEach((v) => {
      v.play().catch(() => {});
    });
  }
}

// Modal Detail and Download Logic
function openModal(asset) {
  state.selectedAsset = asset;
  elements.modalTitle.textContent = asset.displayName;
  elements.modalSubtitle.textContent = `类别: ${asset.category_display} · 标识名: ${asset.name} · 批次: ${asset.batch} · 完整大小: ${asset.total_size_mb} MB`;

  // Populate Physics & Simulation specs
  if (elements.modalMassVal) {
    elements.modalMassVal.textContent = (asset.mass_kg !== undefined && asset.mass_kg !== null) ? `${asset.mass_kg} kg` : "-- kg";
  }
  if (elements.modalSemanticClassVal) {
    elements.modalSemanticClassVal.textContent = asset.semantic_class || "--";
  }
  if (elements.modalQCodeVal) {
    elements.modalQCodeVal.textContent = asset.wikidata_qcode || "--";
  }
  if (elements.modalStaticFrictionVal) {
    elements.modalStaticFrictionVal.textContent = (asset.static_friction !== undefined && asset.static_friction !== null) ? `${asset.static_friction}` : "0.50";
  }
  if (elements.modalDynamicFrictionVal) {
    elements.modalDynamicFrictionVal.textContent = (asset.dynamic_friction !== undefined && asset.dynamic_friction !== null) ? `${asset.dynamic_friction}` : "0.35";
  }
  if (elements.modalRestitutionVal) {
    elements.modalRestitutionVal.textContent = (asset.restitution !== undefined && asset.restitution !== null) ? `${asset.restitution}` : "0.05";
  }

  let thumbUrl = null;
  let videoUrl = null;

  if (isLocalServer) {
    const vStamp = `${asset.thumbnail_mtime || 0}_${state.forceBuster}`;
    thumbUrl = asset.thumbnail_rel_path
      ? `/api/media/${asset.batch}/${asset.name}/${asset.thumbnail_rel_path}?v=${vStamp}`
      : null;
    videoUrl = asset.video_rel_path
      ? `/api/media/${asset.batch}/${asset.name}/${asset.video_rel_path}?v=${asset.video_mtime || 0}_${state.forceBuster}`
      : null;
  } else {
    thumbUrl = asset.static_thumb_path || (asset.thumbnail_rel_path ? `media/${asset.batch}/${asset.name}/thumb.webp` : null);
    videoUrl = asset.static_video_path || (asset.video_rel_path ? `media/${asset.batch}/${asset.name}/${asset.video_rel_path.split("/").pop()}` : null);
  }

  if (videoUrl) {
    elements.modalVideoTabBtn.style.display = "block";
    elements.modalVideoPlayer.src = videoUrl;
    elements.modalVideoPlayer.style.display = "block";
    elements.modalImagePreview.style.display = "none";
    elements.modalVideoPlayer.play().catch(() => {});
    switchMediaTab("video");
  } else {
    elements.modalVideoTabBtn.style.display = "none";
    elements.modalVideoPlayer.pause();
    elements.modalVideoPlayer.removeAttribute("src");
    elements.modalVideoPlayer.style.display = "none";
    switchMediaTab("image");
  }

  if (thumbUrl) {
    elements.modalImageTabBtn.style.display = "block";
    elements.modalImagePreview.src = thumbUrl;
    elements.modalImagePreview.alt = asset.displayName;
  } else {
    elements.modalImageTabBtn.style.display = "none";
  }

  // Branch action buttons based on environment
  if (isLocalServer) {
    if (elements.modalOpenFolderBtn) elements.modalOpenFolderBtn.style.display = "inline-flex";
    if (elements.modalCopyPathBtn) elements.modalCopyPathBtn.style.display = "inline-flex";

    elements.modalDownloadZip.href = `/api/download/zip/${asset.batch}/${asset.name}`;
    elements.modalDownloadZip.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> 一键打包下载完整资产 (ZIP)`;
    elements.modalDownloadZip.style.background = "";
    elements.modalDownloadZip.style.cursor = "pointer";
    elements.modalDownloadZip.onclick = null;

    elements.modalQuickUsdRow.innerHTML = "";
    if (asset.usd_files && asset.usd_files.length > 0) {
      asset.usd_files.forEach((usdFile) => {
        const dlBtn = document.createElement("a");
        dlBtn.className = "btn-secondary";
        dlBtn.href = `/api/download/file/${asset.batch}/${asset.name}/${usdFile.rel_path}`;
        dlBtn.download = usdFile.name;
        dlBtn.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          下载 ${usdFile.name} (${usdFile.size_str})
        `;
        elements.modalQuickUsdRow.appendChild(dlBtn);
      });
    }
  } else {
    // Public Static CDN Mode
    if (elements.modalOpenFolderBtn) elements.modalOpenFolderBtn.style.display = "none";
    if (elements.modalCopyPathBtn) elements.modalCopyPathBtn.style.display = "none";

    elements.modalDownloadZip.href = "javascript:void(0);";
    elements.modalDownloadZip.innerHTML = `<span>🔒 完整 3D 资产受控 · 请联系工程师调取</span>`;
    elements.modalDownloadZip.style.background = "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)";
    elements.modalDownloadZip.style.border = "1px solid rgba(255, 255, 255, 0.15)";
    elements.modalDownloadZip.style.cursor = "default";
    elements.modalDownloadZip.onclick = () => {
      showToast("ℹ️ 完整工程 USD/USDC 资产受保护，仅供企业局域网/内网调取");
    };

    elements.modalQuickUsdRow.innerHTML = `
      <div style="font-size:0.82rem; color:#94a3b8; background:rgba(255,255,255,0.03); padding:12px 16px; border-radius:10px; border:1px solid rgba(255,255,255,0.06); width:100%; line-height:1.6;">
        💡 <b>工程模型规格说明：</b>该套资产包含高精 USD 网格、物理碰撞属性、MDL 真实物理材质库及 4K 贴图。公网仅供 360° 视频在线交互审阅，完整文件仅供内网调取。
      </div>
    `;
  }

  // Open backdrop
  elements.modalBackdrop.classList.add("open");
  document.body.style.overflow = "hidden";
}

function switchMediaTab(tab) {
  state.activeMediaTab = tab;
  if (tab === "video") {
    elements.modalVideoTabBtn.classList.add("active");
    elements.modalImageTabBtn.classList.remove("active");
    elements.modalVideoPlayer.style.display = "block";
    elements.modalImagePreview.style.display = "none";
    elements.modalVideoPlayer.play().catch(() => {});
  } else {
    elements.modalImageTabBtn.classList.add("active");
    elements.modalVideoTabBtn.classList.remove("active");
    elements.modalVideoPlayer.style.display = "none";
    elements.modalVideoPlayer.pause();
    elements.modalImagePreview.style.display = "block";
  }
}

function closeModal() {
  elements.modalBackdrop.classList.remove("open");
  elements.modalVideoPlayer.pause();
  document.body.style.overflow = "";
  state.selectedAsset = null;
}

// Start application (Handles DOMContentLoaded race condition)
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}