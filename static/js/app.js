/**
 * 3D USD Asset Portal Frontend Application - One-Click Force Update Edition
 */

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

  // Category vs Batch Strip Switchers
  elements.stripModeCategory.addEventListener("click", () => {
    state.stripMode = "category";
    elements.stripModeCategory.classList.add("active");
    elements.stripModeBatch.classList.remove("active");
    state.currentBatch = "all";
    renderFilterChips();
    applyFilters();
  });

  elements.stripModeBatch.addEventListener("click", () => {
    state.stripMode = "batch";
    elements.stripModeBatch.classList.add("active");
    elements.stripModeCategory.classList.remove("active");
    state.currentCategory = "all";
    renderFilterChips();
    applyFilters();
  });

  // One-Click Force Update & Cache Busting
  elements.updateAllBtn.addEventListener("click", async () => {
    elements.updateAllBtn.classList.add("spinning");
    state.forceBuster = Date.now();
    await loadAssets(true);
    elements.updateAllBtn.classList.remove("spinning");
    showToast(`⚡ 资产与图片已全部强制同步完成！共 ${state.assets.length} 套模型最新就绪`);
  });

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
    const url = `/api/update?refresh=${forceRefresh ? "true" : "false"}&_t=${Date.now()}`;
    const res = await fetch(url);
    const data = await res.json();
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
    console.error("Failed to load assets:", err);
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

    // Dynamic cache buster with file modification time + forceBuster
    const vStamp = `${asset.thumbnail_mtime || 0}_${state.forceBuster}`;
    const thumbUrl = asset.thumbnail_rel_path
      ? `/api/media/${asset.batch}/${asset.name}/${asset.thumbnail_rel_path}?v=${vStamp}`
      : null;
    const videoUrl = asset.video_rel_path
      ? `/api/media/${asset.batch}/${asset.name}/${asset.video_rel_path}?v=${asset.video_mtime || 0}_${state.forceBuster}`
      : null;

    let mediaHtml = "";
    if (thumbUrl) {
      mediaHtml += `<img src="${thumbUrl}" alt="${asset.displayName}" loading="lazy" class="${videoUrl ? "has-video-sibling" : ""}">`;
    }
    if (videoUrl) {
      mediaHtml += `<video src="${videoUrl}" loop muted playsinline preload="none" class="has-video"></video>`;
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
        <span class="badge-batch">${asset.batch}</span>
        ${
          asset.has_video
            ? `<span class="badge-video"><span class="video-playing-indicator"></span> 360° 视频</span>`
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

    // Video hover interaction
    const videoElem = card.querySelector("video.has-video");
    if (videoElem) {
      card.addEventListener("mouseenter", () => {
        if (state.viewMode === "thumb") {
          videoElem.play().catch(() => {});
        }
      });
      card.addEventListener("mouseleave", () => {
        if (state.viewMode === "thumb") {
          videoElem.pause();
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

  const vStamp = `${asset.thumbnail_mtime || 0}_${state.forceBuster}`;
  const thumbUrl = asset.thumbnail_rel_path
    ? `/api/media/${asset.batch}/${asset.name}/${asset.thumbnail_rel_path}?v=${vStamp}`
    : null;
  const videoUrl = asset.video_rel_path
    ? `/api/media/${asset.batch}/${asset.name}/${asset.video_rel_path}?v=${asset.video_mtime || 0}_${state.forceBuster}`
    : null;

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

  // Download ZIP Button
  elements.modalDownloadZip.href = `/api/download/zip/${asset.batch}/${asset.name}`;

  // Quick USD Download Buttons
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

// Start application
document.addEventListener("DOMContentLoaded", initApp);