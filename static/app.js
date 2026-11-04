/* global fetch */

const W = 900;
const H = 1800;
const CELL = 10;
const ROWS = 180;
const COLS = 90;

const TYPE_LABEL = {
  building: "建筑",
  dorm: "宿舍",
  sports: "运动场",
  gate: "校门",
  park: "园区",
  water: "水域",
  landmark: "广场",
};

const TYPE_COLOR = {
  building: "#0f766e",
  dorm: "#b45309",
  sports: "#2563eb",
  gate: "#64748b",
  park: "#15803d",
  water: "#0284c7",
  landmark: "#7c3aed",
};

const canvas = document.getElementById("map");
const ctx = canvas.getContext("2d");
const mapScroll = document.getElementById("mapScroll");
const canvasWrap = document.getElementById("canvasWrap");
const mapPanel = document.querySelector(".map-panel");
const tooltip = document.getElementById("tooltip");
const toastEl = document.getElementById("toast");

const S = {
  grid: Array.from({ length: ROWS }, () => Array(COLS).fill(1)),
  places: [],
  history: [],
  stats: { walkable: 0, blocked: 0, places: 0, queries: 0, components: [] },
  mapName: "",
  updatedAt: "",
  hash: "",
  start: null,
  goal: null,
  route: null,
  searchStep: 0,
  playTimer: null,
  mode: "view",
  brush: 1,
  showGrid: true,
  showLabels: false,
  showWalk: true,
  hover: null,
  painting: false,
  pending: new Map(),
  undo: [],
  zoom: "full",
  editPromise: Promise.resolve(),
  placeFilter: "",
  selectedPlaceId: null,
};

let mapImage = null;
let mapImageReady = false;
let walkCanvas = null;
let walkDirty = true;
let popup = null;
let toastTimer = null;

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function typeLabel(type) {
  return TYPE_LABEL[type] || type;
}

function formatTime(value) {
  if (!value) return "—";
  return value.replace("T", " ").slice(5, 19);
}

async function api(url, body) {
  const options = { method: body === undefined ? "GET" : "POST", headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`服务器返回异常（HTTP ${response.status}）`);
  }
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `请求失败（HTTP ${response.status}）`);
  }
  return data;
}

function toast(message, isError = false) {
  toastEl.textContent = message;
  toastEl.hidden = false;
  toastEl.classList.toggle("error", Boolean(isError));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toastEl.hidden = true;
  }, isError ? 5200 : 3000);
}

function setSaveState(text) {
  $("saveState").textContent = text;
}

/* ------------------------------------------------------------------ data */

async function loadState() {
  try {
    const data = await api("/api/state");
    applyState(data);
    setSaveState("已加载");
  } catch (error) {
    toast(`加载地图失败：${error.message}`, true);
  }
}

function applyState(data) {
  S.grid = data.map.grid.map((row) => row.slice());
  S.places = data.places;
  S.history = data.history;
  S.stats = data.stats;
  S.mapName = data.map.name;
  S.updatedAt = data.map.updated_at;
  S.hash = data.map.snapshot_hash;
  S.hover = null;
  S.pending.clear();
  S.undo = [];
  walkDirty = true;
  if (S.start?.placeId && !S.places.some((place) => place.id === S.start.placeId)) {
    S.start = null;
  }
  if (S.goal?.placeId && !S.places.some((place) => place.id === S.goal.placeId)) {
    S.goal = null;
  }
  rebuildSelects();
  renderTopStats();
  renderManagePanel();
  renderPlaceList();
  renderHistory();
  updateEndpointUI();
  draw();
  applyZoom();
}

function renderTopStats() {
  const stats = S.stats;
  $("topStats").innerHTML = [
    ["可走", stats.walkable],
    ["障碍", stats.blocked],
    ["地点", stats.places],
    ["查询", stats.queries],
  ]
    .map(
      ([label, value]) =>
        `<span class="top-stat"><strong>${Number(value ?? 0).toLocaleString()}</strong>${label}</span>`,
    )
    .join("");
}

function renderManagePanel() {
  const stats = S.stats;
  const components = stats.components || [];
  $("manageStats").innerHTML = [
    ["可走格", stats.walkable],
    ["障碍格", stats.blocked],
    ["地点数", stats.places],
    ["历史查询", stats.queries],
    ["连通块", components.length],
    ["最大连通块", components[0] || 0],
  ]
    .map(
      ([label, value]) =>
        `<div class="stat-box"><span>${label}</span><strong>${Number(value || 0).toLocaleString()}</strong></div>`,
    )
    .join("");
  $("mapUpdated").textContent = `最近保存：${formatTime(S.updatedAt)} · 指纹 ${S.hash}`;
}

/* --------------------------------------------------------------- selects */

function rebuildSelects() {
  const options = S.places
    .map(
      (place) =>
        `<option value="${place.id}">${escapeHtml(place.name)}</option>`,
    )
    .join("");
  $("startSelect").innerHTML = `<option value="">选择地点…</option>${options}`;
  $("endSelect").innerHTML = `<option value="">选择地点…</option>${options}`;
  syncSelects();
}

function syncSelects() {
  $("startSelect").value = S.start?.placeId ? String(S.start.placeId) : "";
  $("endSelect").value = S.goal?.placeId ? String(S.goal.placeId) : "";
}

function endpointFromPlace(place) {
  return {
    row: place.access_row,
    col: place.access_col,
    markerRow: place.row,
    markerCol: place.col,
    name: place.name,
    placeId: place.id,
  };
}

function endpointFromCell(row, col) {
  return {
    row,
    col,
    markerRow: row,
    markerCol: col,
    name: `自定义 (${row}, ${col})`,
    placeId: null,
  };
}

function focusPlace(place) {
  const rect = canvas.getBoundingClientRect();
  const scale = rect.height / H;
  const target = (place.row + 0.5) * CELL * scale;
  mapScroll.scrollTo({
    top: Math.max(0, target - mapScroll.clientHeight / 2),
    behavior: "smooth",
  });
}

function setEndpoint(which, endpoint) {
  S[which] = endpoint;
  clearRoute(false);
  syncSelects();
  updateEndpointUI();
  draw();
}

function updateEndpointUI() {
  const start = S.start;
  const goal = S.goal;
  $("startName").textContent = start?.name || "从地图或列表选择起点";
  $("endName").textContent = goal?.name || "从地图或列表选择终点";
  $("startCoord").textContent = start ? `入口 (${start.row}, ${start.col})` : "未选择";
  $("endCoord").textContent = goal ? `入口 (${goal.row}, ${goal.col})` : "未选择";
}

function pairEndpoint(payload) {
  if (!payload) return null;
  if (payload.placeId) return { place_id: payload.placeId };
  return { row: payload.row, col: payload.col };
}

/* ----------------------------------------------------------------- canvas */

function cellCenter(row, col) {
  return [(col + 0.5) * CELL, (row + 0.5) * CELL];
}

function draw() {
  ctx.clearRect(0, 0, W, H);
  if (mapImageReady) {
    ctx.drawImage(mapImage, 0, 0, W, H);
  } else {
    ctx.fillStyle = "#f7f4e9";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#8a918d";
    ctx.font = '16px "Microsoft YaHei", sans-serif';
    ctx.textAlign = "center";
    ctx.fillText("正在加载校园底图…", W / 2, H / 2);
    ctx.textAlign = "left";
  }
  if (S.showWalk) drawWalkLayer();
  if (S.showGrid) drawGrid();
  drawExpanded();
  drawPath();
  drawPlaces();
  drawEndpoints();
  drawHover();
}

function drawGrid() {
  ctx.save();
  ctx.lineWidth = 0.5;
  ctx.strokeStyle = "rgba(20, 31, 27, 0.12)";
  ctx.beginPath();
  for (let col = 1; col < COLS; col += 1) {
    ctx.moveTo(col * CELL, 0);
    ctx.lineTo(col * CELL, H);
  }
  for (let row = 1; row < ROWS; row += 1) {
    ctx.moveTo(0, row * CELL);
    ctx.lineTo(W, row * CELL);
  }
  ctx.stroke();
  ctx.lineWidth = 0.9;
  ctx.strokeStyle = "rgba(20, 31, 27, 0.22)";
  ctx.beginPath();
  for (let col = 10; col < COLS; col += 10) {
    ctx.moveTo(col * CELL, 0);
    ctx.lineTo(col * CELL, H);
  }
  for (let row = 10; row < ROWS; row += 10) {
    ctx.moveTo(0, row * CELL);
    ctx.lineTo(W, row * CELL);
  }
  ctx.stroke();
  ctx.restore();
}

function rebuildWalkLayer() {
  if (!walkCanvas) {
    walkCanvas = document.createElement("canvas");
    walkCanvas.width = W;
    walkCanvas.height = H;
  }
  const layer = walkCanvas.getContext("2d");
  layer.clearRect(0, 0, W, H);
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      if (S.grid[row][col] === 0) {
        layer.fillStyle = "rgba(21, 128, 61, 0.22)";
        layer.fillRect(col * CELL, row * CELL, CELL, CELL);
      }
    }
  }
  walkDirty = false;
}

function drawWalkLayer() {
  if (walkDirty) rebuildWalkLayer();
  ctx.drawImage(walkCanvas, 0, 0);
}

function drawPlaces() {
  ctx.save();
  for (const place of S.places) {
    const x = (place.col + 0.5) * CELL;
    const y = (place.row + 0.5) * CELL;
    const color = TYPE_COLOR[place.type] || TYPE_COLOR.building;
    const selected = S.selectedPlaceId === place.id;
    ctx.beginPath();
    ctx.arc(x, y, selected ? 6.5 : 4.2, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.lineWidth = selected ? 2 : 1.4;
    ctx.strokeStyle = selected ? "#fff7d6" : "#ffffff";
    ctx.stroke();
    if (selected) {
      ctx.beginPath();
      ctx.arc(x, y, 10, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255, 247, 214, 0.9)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    if (S.showLabels) {
      ctx.font = '10px "Microsoft YaHei", sans-serif';
      ctx.textBaseline = "middle";
      ctx.lineWidth = 3;
      ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
      ctx.strokeText(place.name, x + 7, y - 1);
      ctx.fillStyle = "#1b2b26";
      ctx.fillText(place.name, x + 7, y - 1);
    }
  }
  ctx.restore();
}

function drawExpanded() {
  if (!S.route || !S.route.expanded_order?.length) return;
  const limit = Math.min(S.searchStep, S.route.expanded_order.length);
  ctx.save();
  for (let index = 0; index < limit; index += 1) {
    const [row, col] = S.route.expanded_order[index];
    ctx.fillStyle = "rgba(194, 65, 12, 0.42)";
    ctx.fillRect(col * CELL + 1, row * CELL + 1, CELL - 2, CELL - 2);
  }
  ctx.restore();
}

function drawPath() {
  if (!S.route?.found || !S.route.path?.length) return;
  const path = S.route.path;
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  path.forEach(([row, col], index) => {
    const [x, y] = cellCenter(row, col);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "rgba(29, 78, 216, 0.26)";
  ctx.lineWidth = 7;
  ctx.stroke();
  ctx.strokeStyle = "#1d4ed8";
  ctx.lineWidth = 3.2;
  ctx.stroke();
  ctx.restore();
}

function drawEndpoints() {
  if (S.start) drawEndpoint(S.start, "#15803d", "起");
  if (S.goal) drawEndpoint(S.goal, "#b91c1c", "终");
}

function drawEndpoint(endpoint, color, label) {
  const markerX = (endpoint.markerCol + 0.5) * CELL;
  const markerY = (endpoint.markerRow + 0.5) * CELL;
  const accessX = (endpoint.col + 0.5) * CELL;
  const accessY = (endpoint.row + 0.5) * CELL;
  ctx.save();
  if (markerX !== accessX || markerY !== accessY) {
    ctx.beginPath();
    ctx.setLineDash([3, 3]);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.moveTo(markerX, markerY);
    ctx.lineTo(accessX, accessY);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(accessX, accessY, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = "#fff";
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.8;
    ctx.stroke();
  }
  ctx.beginPath();
  ctx.arc(markerX, markerY, 8, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#fffef5";
  ctx.stroke();
  ctx.fillStyle = "#fff";
  ctx.font = 'bold 9px "Microsoft YaHei", sans-serif';
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, markerX, markerY + 0.5);
  ctx.restore();
}

function drawHover() {
  if (!S.hover) return;
  const { row, col } = S.hover;
  ctx.save();
  ctx.strokeStyle = "rgba(15, 118, 110, 0.9)";
  ctx.lineWidth = 2;
  ctx.strokeRect(col * CELL + 1, row * CELL + 1, CELL - 2, CELL - 2);
  ctx.restore();
}

/* --------------------------------------------------------------- geometry */

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  const x = ((event.clientX - rect.left) * W) / rect.width;
  const y = ((event.clientY - rect.top) * H) / rect.height;
  return {
    x,
    y,
    row: Math.max(0, Math.min(ROWS - 1, Math.floor(y / CELL))),
    col: Math.max(0, Math.min(COLS - 1, Math.floor(x / CELL))),
  };
}

function placeAt(x, y) {
  let best = null;
  let bestDistance = 14;
  for (const place of S.places) {
    const px = (place.col + 0.5) * CELL;
    const py = (place.row + 0.5) * CELL;
    const distance = Math.hypot(px - x, py - y);
    if (distance < bestDistance) {
      best = place;
      bestDistance = distance;
    }
  }
  return best;
}

function nearestWalkable(row, col, maxRadius = 12) {
  if (S.grid[row]?.[col] === 0) return { row, col, distance: 0 };
  const queue = [[row, col, 0]];
  const seen = new Set([`${row},${col}`]);
  const moves = [
    [-1, 0],
    [0, 1],
    [1, 0],
    [0, -1],
  ];
  while (queue.length) {
    const [currentRow, currentCol, distance] = queue.shift();
    if (distance >= maxRadius) continue;
    for (const [dRow, dCol] of moves) {
      const nextRow = currentRow + dRow;
      const nextCol = currentCol + dCol;
      const key = `${nextRow},${nextCol}`;
      if (
        nextRow < 0 ||
        nextRow >= ROWS ||
        nextCol < 0 ||
        nextCol >= COLS ||
        seen.has(key)
      ) {
        continue;
      }
      seen.add(key);
      if (S.grid[nextRow][nextCol] === 0) {
        return { row: nextRow, col: nextCol, distance: distance + 1 };
      }
      queue.push([nextRow, nextCol, distance + 1]);
    }
  }
  return null;
}

/* ------------------------------------------------------------------ modes */

const MODE_HINTS = {
  view: "点击建筑圆点选择地点；滚轮可滚动地图",
  start: "点击地图或地点圆点设置起点",
  end: "点击地图或地点圆点设置终点",
  walk: "按住并拖动，把网格改为可走（0）",
  block: "按住并拖动，把网格改为障碍（1）",
  place: "点击地图选择新地点的标记位置",
};

function setMode(mode) {
  S.mode = mode;
  mapPanel.dataset.mode = mode;
  document.querySelectorAll(".mode").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  $("modeHint").textContent = MODE_HINTS[mode] || "";
  hidePopup();
}

document.querySelectorAll(".mode").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

/* --------------------------------------------------------------- painting */

function paintAt(row, col) {
  const value = S.mode === "walk" ? 0 : 1;
  const radius = Math.floor(S.brush / 2);
  for (let dRow = -radius; dRow <= radius; dRow += 1) {
    for (let dCol = -radius; dCol <= radius; dCol += 1) {
      const nextRow = row + dRow;
      const nextCol = col + dCol;
      if (nextRow < 0 || nextRow >= ROWS || nextCol < 0 || nextCol >= COLS) {
        continue;
      }
      const oldValue = S.grid[nextRow][nextCol];
      if (oldValue === value) continue;
      S.grid[nextRow][nextCol] = value;
      S.pending.set(`${nextRow},${nextCol}`, {
        row: nextRow,
        col: nextCol,
        value,
        old: oldValue,
      });
    }
  }
  walkDirty = true;
  if (S.route) clearRoute(false);
  draw();
}

function flushEdits() {
  if (!S.pending.size) return;
  const items = [...S.pending.values()];
  S.pending.clear();
  const changes = items.map((item) => [item.row, item.col, item.value]);
  const reverse = items.map((item) => [item.row, item.col, item.old]);
  S.undo.push(reverse);
  if (S.undo.length > 50) S.undo.shift();
  setSaveState("正在保存…");
  S.editPromise = S.editPromise
    .then(() => api("/api/edit", { changes }))
    .then((result) => {
      S.updatedAt = result.updated_at;
      S.hash = result.snapshot_hash;
      S.stats = { ...S.stats, ...result.stats };
      renderTopStats();
      renderManagePanel();
      setSaveState(`已保存 ${formatTime(result.updated_at)}`);
    })
    .catch((error) => {
      toast(`保存失败：${error.message}`, true);
      setSaveState("保存失败");
      return loadState();
    });
}

canvas.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  hidePopup();
  const point = canvasPoint(event);
  if (S.mode === "walk" || S.mode === "block") {
    event.preventDefault();
    S.painting = true;
    S.pending.clear();
    canvas.setPointerCapture(event.pointerId);
    tooltip.hidden = true;
    paintAt(point.row, point.col);
    return;
  }
  handleMapClick(point, event);
});

canvas.addEventListener("pointermove", (event) => {
  const point = canvasPoint(event);
  S.hover = { row: point.row, col: point.col };
  $("cursorInfo").textContent = `行 ${point.row}, 列 ${point.col} · ${
    S.grid[point.row][point.col] === 0 ? "可走" : "障碍"
  }`;
  if (S.painting) {
    paintAt(point.row, point.col);
    return;
  }
  draw();
  showTooltip(event, point);
});

canvas.addEventListener("pointerup", (event) => {
  if (!S.painting) return;
  S.painting = false;
  try {
    canvas.releasePointerCapture(event.pointerId);
  } catch {
    /* ignore */
  }
  flushEdits();
});

canvas.addEventListener("pointerleave", () => {
  S.hover = null;
  tooltip.hidden = true;
  if (!S.painting) draw();
});

function handleMapClick(point, event) {
  const place = placeAt(point.x, point.y);
  if (S.mode === "start") {
    setEndpoint("start", place ? endpointFromPlace(place) : endpointFromCell(point.row, point.col));
    if (!place && S.grid[point.row][point.col] !== 0) {
      toast("该格不可走，已按坐标选择；查询时会自动吸附", true);
    }
    setMode("view");
    return;
  }
  if (S.mode === "end") {
    setEndpoint("goal", place ? endpointFromPlace(place) : endpointFromCell(point.row, point.col));
    if (!place && S.grid[point.row][point.col] !== 0) {
      toast("该格不可走，已按坐标选择；查询时会自动吸附", true);
    }
    setMode("view");
    return;
  }
  if (S.mode === "place") {
    const nearest = nearestWalkable(point.row, point.col);
    $("placeRow").value = point.row;
    $("placeCol").value = point.col;
    $("accessRow").value = nearest ? nearest.row : point.row;
    $("accessCol").value = nearest ? nearest.col : point.col;
    switchTab("places");
    setMode("view");
    $("placeName").focus();
    toast("已填入坐标，请补充地点名称");
    return;
  }
  if (place) {
    S.selectedPlaceId = place.id;
    draw();
    showPlacePopup(place, event);
  } else {
    S.selectedPlaceId = null;
    draw();
  }
}

/* --------------------------------------------------------------- tooltip */

function showTooltip(event, point) {
  if (S.painting) {
    tooltip.hidden = true;
    return;
  }
  const place = placeAt(point.x, point.y);
  if (place) {
    tooltip.innerHTML = `<strong>${escapeHtml(place.name)}</strong>${
      typeLabel(place.type)
    } · 标记 (${place.row}, ${place.col})<br/>入口 (${place.access_row}, ${place.access_col})`;
  } else {
    tooltip.innerHTML = `<strong>(${point.row}, ${point.col})</strong>${
      S.grid[point.row][point.col] === 0 ? "可走 0" : "障碍 1"
    }`;
  }
  const wrapRect = canvasWrap.getBoundingClientRect();
  tooltip.hidden = false;
  tooltip.style.left = `${event.clientX - wrapRect.left}px`;
  tooltip.style.top = `${event.clientY - wrapRect.top}px`;
}

/* ----------------------------------------------------------------- popup */

function showPlacePopup(place, event) {
  hidePopup();
  popup = document.createElement("div");
  popup.className = "place-popup";
  popup.innerHTML = `
    <strong>${escapeHtml(place.name)}</strong>
    <span>${typeLabel(place.type)} · 入口 (${place.access_row}, ${place.access_col})</span>
    <div class="popup-actions">
      <button data-act="start">设为起点</button>
      <button data-act="end">设为终点</button>
      <button data-act="edit">编辑</button>
    </div>`;
  canvasWrap.appendChild(popup);
  const wrapRect = canvasWrap.getBoundingClientRect();
  const left = Math.min(event.clientX - wrapRect.left + 8, wrapRect.width - 176);
  const top = Math.min(event.clientY - wrapRect.top + 8, wrapRect.height - 96);
  popup.style.left = `${Math.max(6, left)}px`;
  popup.style.top = `${Math.max(6, top)}px`;
  popup.addEventListener("pointerdown", (event_) => event_.stopPropagation());
  popup.querySelector('[data-act="start"]').addEventListener("click", () => {
    setEndpoint("start", endpointFromPlace(place));
    focusPlace(place);
    hidePopup();
  });
  popup.querySelector('[data-act="end"]').addEventListener("click", () => {
    setEndpoint("goal", endpointFromPlace(place));
    focusPlace(place);
    hidePopup();
  });
  popup.querySelector('[data-act="edit"]').addEventListener("click", () => {
    editPlace(place.id);
    hidePopup();
  });
}

function hidePopup() {
  if (popup) {
    popup.remove();
    popup = null;
  }
}

/* ----------------------------------------------------------------- route */

async function runRoute() {
  if (!S.start || !S.goal) {
    toast("请先选择起点和终点", true);
    return;
  }
  const button = $("routeBtn");
  button.disabled = true;
  button.textContent = "搜索中…";
  try {
    const result = await api("/api/route", {
      start: pairEndpoint(S.start),
      goal: pairEndpoint(S.goal),
    });
    S.start = {
      row: result.start.row,
      col: result.start.col,
      markerRow: S.start.markerRow ?? result.start.row,
      markerCol: S.start.markerCol ?? result.start.col,
      name: result.start.name,
      placeId: S.start.placeId,
    };
    S.goal = {
      row: result.goal.row,
      col: result.goal.col,
      markerRow: S.goal.markerRow ?? result.goal.row,
      markerCol: S.goal.markerCol ?? result.goal.col,
      name: result.goal.name,
      placeId: S.goal.placeId,
    };
    S.route = result;
    S.searchStep = result.expanded;
    S.stats = { ...S.stats, queries: (S.stats.queries || 0) + 1 };
    updateEndpointUI();
    renderTopStats();
    renderResult();
    await refreshHistory();
    draw();
    if (result.notes?.length) toast(result.notes.join("；"));
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "开始 A* 查询";
  }
}

function clearRoute(redraw = true) {
  stopPlayback();
  S.route = null;
  S.searchStep = 0;
  $("resultCard").hidden = true;
  $("routeEmpty").hidden = false;
  if (redraw) draw();
}

function renderResult() {
  const route = S.route;
  const card = $("resultCard");
  if (!route) {
    card.hidden = true;
    $("routeEmpty").hidden = false;
    return;
  }
  $("routeEmpty").hidden = true;
  card.hidden = false;
  card.classList.toggle("found", Boolean(route.found));
  card.classList.toggle("unreachable", !route.found);
  $("resultKicker").textContent = route.history ? "历史记录" : "实时查询";
  const badge = $("resultBadge");
  badge.textContent = route.found ? "成功" : "不可达";
  badge.classList.toggle("bad", !route.found);
  $("resultTitle").textContent = route.found
    ? `最短路 ${route.cost} 步`
    : "终点不可达";
  $("resultMessage").textContent = route.message || "";
  $("metricCost").textContent = route.found ? `${route.cost} 步` : "—";
  $("metricExpanded").textContent = Number(route.expanded || 0).toLocaleString();
  $("metricTime").textContent = `${Number(route.elapsed_ms || 0).toFixed(1)} ms`;
  const traceLength = route.expanded_order?.length || 0;
  $("traceSlider").max = String(traceLength);
  $("traceSlider").value = String(Math.min(S.searchStep, traceLength));
  $("traceSlider").disabled = traceLength === 0;
  $("traceInfo").textContent =
    traceLength > 0
      ? `扩展 ${Math.min(S.searchStep, traceLength)} / ${traceLength}`
      : route.history
        ? "历史记录只保留路径"
        : "没有扩展记录";
}

function stopPlayback() {
  if (S.playTimer) {
    clearInterval(S.playTimer);
    S.playTimer = null;
  }
  $("playBtn").textContent = "播放";
}

function togglePlayback() {
  if (S.playTimer) {
    stopPlayback();
    return;
  }
  const length = S.route?.expanded_order?.length || 0;
  if (!length) return;
  if (S.searchStep >= length) S.searchStep = 0;
  $("playBtn").textContent = "暂停";
  const step = Math.max(1, Math.ceil(length / 90));
  S.playTimer = setInterval(() => {
    S.searchStep = Math.min(length, S.searchStep + step);
    $("traceSlider").value = String(S.searchStep);
    $("traceInfo").textContent = `扩展 ${S.searchStep} / ${length}`;
    draw();
    if (S.searchStep >= length) stopPlayback();
  }, 55);
}

$("routeBtn").addEventListener("click", runRoute);
$("swapBtn").addEventListener("click", () => {
  [S.start, S.goal] = [S.goal, S.start];
  syncSelects();
  updateEndpointUI();
  clearRoute(false);
  draw();
});
$("playBtn").addEventListener("click", togglePlayback);
$("traceSlider").addEventListener("input", (event) => {
  stopPlayback();
  S.searchStep = Number(event.target.value);
  const length = S.route?.expanded_order?.length || 0;
  $("traceInfo").textContent = `扩展 ${S.searchStep} / ${length}`;
  draw();
});

$("startSelect").addEventListener("change", (event) => {
  const place = S.places.find((item) => String(item.id) === event.target.value);
  if (place) {
    setEndpoint("start", endpointFromPlace(place));
    focusPlace(place);
  }
});
$("endSelect").addEventListener("change", (event) => {
  const place = S.places.find((item) => String(item.id) === event.target.value);
  if (place) {
    setEndpoint("goal", endpointFromPlace(place));
    focusPlace(place);
  }
});

/* ----------------------------------------------------------------- tabs */

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${name}`);
  });
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

/* ---------------------------------------------------------------- places */

function renderPlaceList() {
  const filter = S.placeFilter.trim().toLowerCase();
  const places = S.places.filter((place) => {
    if (!filter) return true;
    return `${place.name} ${place.aliases || ""} ${typeLabel(place.type)}`
      .toLowerCase()
      .includes(filter);
  });
  $("placeCount").textContent = `共 ${S.places.length} 个地点${
    filter ? `，匹配 ${places.length} 个` : ""
  }`;
  $("placeList").innerHTML = places
    .map(
      (place) => `
      <div class="place-item" data-id="${place.id}">
        <div>
          <div class="place-title">
            <span class="type-dot ${place.type}"></span>
            <strong>${escapeHtml(place.name)}</strong>
          </div>
          <div class="place-meta">${typeLabel(place.type)} · 入口 (${place.access_row}, ${place.access_col})</div>
        </div>
        <div class="place-actions">
          <button data-act="start">起</button>
          <button data-act="end">终</button>
          <button data-act="edit">编辑</button>
        </div>
      </div>`,
    )
    .join("");
}

$("placeList").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const item = event.target.closest(".place-item");
  const place = S.places.find((entry) => String(entry.id) === item.dataset.id);
  if (!place) return;
  if (button.dataset.act === "start") {
    setEndpoint("start", endpointFromPlace(place));
    focusPlace(place);
    switchTab("route");
    toast(`起点：${place.name}`);
  } else if (button.dataset.act === "end") {
    setEndpoint("goal", endpointFromPlace(place));
    focusPlace(place);
    switchTab("route");
    toast(`终点：${place.name}`);
  } else if (button.dataset.act === "edit") {
    editPlace(place.id);
  }
});

$("placeSearch").addEventListener("input", (event) => {
  S.placeFilter = event.target.value;
  renderPlaceList();
});

function resetPlaceForm() {
  $("placeForm").reset();
  $("placeId").value = "";
  $("placeFormTitle").textContent = "新增地点";
  $("deletePlace").hidden = true;
  $("placeRow").value = "";
  $("placeCol").value = "";
  $("accessRow").value = "";
  $("accessCol").value = "";
}

function editPlace(id) {
  const place = S.places.find((item) => item.id === id);
  if (!place) return;
  $("placeId").value = String(place.id);
  $("placeFormTitle").textContent = "编辑地点";
  $("placeName").value = place.name;
  $("placeType").value = place.type;
  $("placeRow").value = place.row;
  $("placeCol").value = place.col;
  $("accessRow").value = place.access_row;
  $("accessCol").value = place.access_col;
  $("placeAliases").value = place.aliases || "";
  $("deletePlace").hidden = false;
  switchTab("places");
  $("placeName").focus();
}

$("newPlaceBtn").addEventListener("click", () => {
  resetPlaceForm();
  setMode("place");
  switchTab("places");
  toast("请在地图上点击新地点的位置");
});

$("pickPlaceBtn").addEventListener("click", () => {
  setMode("place");
  toast("请在地图上点击新地点的位置");
});

$("cancelPlace").addEventListener("click", () => {
  resetPlaceForm();
  setMode("view");
});

$("placeForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = $("placeId").value;
  const row = Number($("placeRow").value);
  const col = Number($("placeCol").value);
  let accessRow = $("accessRow").value === "" ? null : Number($("accessRow").value);
  let accessCol = $("accessCol").value === "" ? null : Number($("accessCol").value);
  if (accessRow === null || accessCol === null) {
    const nearest = nearestWalkable(row, col);
    if (nearest) {
      accessRow = nearest.row;
      accessCol = nearest.col;
    }
  }
  const payload = {
    action: id ? "update" : "add",
    id: id ? Number(id) : undefined,
    name: $("placeName").value.trim(),
    type: $("placeType").value,
    row,
    col,
    access_row: accessRow,
    access_col: accessCol,
    aliases: $("placeAliases").value.trim(),
  };
  try {
    await api("/api/places", payload);
    toast(id ? "地点已更新" : "地点已添加");
    resetPlaceForm();
    await loadState();
    switchTab("places");
  } catch (error) {
    toast(error.message, true);
  }
});

$("deletePlace").addEventListener("click", async () => {
  const id = Number($("placeId").value);
  const place = S.places.find((item) => item.id === id);
  if (!id || !place) return;
  if (!confirm(`确定删除“${place.name}”吗？历史记录不会删除。`)) return;
  try {
    await api("/api/places", { action: "delete", id });
    toast("地点已删除");
    resetPlaceForm();
    await loadState();
  } catch (error) {
    toast(error.message, true);
  }
});

/* ---------------------------------------------------------------- history */

async function refreshHistory() {
  try {
    const data = await api("/api/history");
    S.history = data.history;
    renderHistory();
  } catch {
    /* non-critical */
  }
}

function renderHistory() {
  if (!S.history.length) {
    $("historyList").innerHTML =
      '<div class="empty"><p>还没有查询记录。</p><p class="muted">运行一次 A* 查询后会自动保存。</p></div>';
    return;
  }
  $("historyList").innerHTML = S.history
    .map(
      (item) => `
      <div class="history-item">
        <div class="history-top">
          <span class="history-route">${escapeHtml(item.start_name)} <span>→</span> ${escapeHtml(item.end_name)}</span>
          <span class="badge ${item.found ? "" : "bad"}">${item.found ? "成功" : "不可达"}</span>
        </div>
        <div class="history-meta">
          <span>${formatTime(item.created_at)}</span>
          <span>${item.found ? `${item.cost} 步` : "无路径"}</span>
          <span>扩展 ${item.expanded}</span>
        </div>
        <div class="history-actions">
          <button class="btn btn-small" data-act="view" data-id="${item.id}">查看路线</button>
          <button class="btn btn-small" data-act="snapshot" data-id="${item.id}">载入当时地图</button>
        </div>
      </div>`,
    )
    .join("");
}

$("historyList").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const id = Number(button.dataset.id);
  if (button.dataset.act === "view") viewHistory(id);
  if (button.dataset.act === "snapshot") loadHistorySnapshot(id);
});

async function viewHistory(id) {
  try {
    const item = await api(`/api/history/${id}`);
    S.start = {
      row: item.start_row,
      col: item.start_col,
      markerRow: item.start_row,
      markerCol: item.start_col,
      name: item.start_name,
      placeId: null,
    };
    S.goal = {
      row: item.end_row,
      col: item.end_col,
      markerRow: item.end_row,
      markerCol: item.end_col,
      name: item.end_name,
      placeId: null,
    };
    S.route = {
      found: item.found,
      path: item.path,
      cost: item.cost,
      expanded: item.expanded,
      expanded_order: [],
      message: item.message,
      elapsed_ms: item.elapsed_ms,
      history: true,
      snapshot_hash: item.snapshot_hash,
    };
    S.searchStep = 0;
    syncSelects();
    updateEndpointUI();
    renderResult();
    switchTab("route");
    draw();
    if (item.snapshot_hash !== S.hash) {
      toast("这是旧地图上的记录；如需完全复现，请点“载入当时地图”", true);
    }
  } catch (error) {
    toast(error.message, true);
  }
}

async function loadHistorySnapshot(id) {
  if (!confirm("载入历史地图会覆盖当前网格（地点列表不变），确定继续吗？")) return;
  try {
    const item = await api(`/api/history/${id}`);
    const data = await api("/api/map/snapshot", { snapshot: item.snapshot });
    clearRoute(false);
    applyState(data);
    toast("已载入该次查询时的地图");
    switchTab("manage");
  } catch (error) {
    toast(error.message, true);
  }
}

$("clearHistory").addEventListener("click", async () => {
  if (!confirm("确定清空全部查询记录吗？")) return;
  try {
    await api("/api/history/clear", {});
    S.history = [];
    S.stats = { ...S.stats, queries: 0 };
    renderHistory();
    renderTopStats();
    toast("查询记录已清空");
  } catch (error) {
    toast(error.message, true);
  }
});

/* ------------------------------------------------------------------ map */

async function saveMap() {
  try {
    const result = await api("/api/map/save", {});
    S.updatedAt = result.updated_at;
    setSaveState(`已保存 ${formatTime(result.updated_at)}`);
    renderManagePanel();
    toast("地图已保存到 SQLite");
  } catch (error) {
    toast(error.message, true);
  }
}

$("saveBtn").addEventListener("click", saveMap);
$("saveMapBtn").addEventListener("click", saveMap);

$("resetMapBtn").addEventListener("click", async () => {
  if (!confirm("恢复基准地图会覆盖当前所有涂格修改，确定继续吗？")) return;
  try {
    const data = await api("/api/map/reset", {});
    clearRoute(false);
    applyState(data);
    setSaveState("已恢复基准地图");
    toast("已恢复基准地图");
  } catch (error) {
    toast(error.message, true);
  }
});

$("exportBtn").addEventListener("click", () => {
  window.location.href = "/api/map/export";
});

$("importFile").addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    const bundle = JSON.parse(text);
    if (!confirm("导入会替换当前地图和地点列表，确定继续吗？")) return;
    const data = await api("/api/map/import", bundle);
    S.start = null;
    S.goal = null;
    clearRoute(false);
    applyState(data);
    toast("地图导入成功");
  } catch (error) {
    toast(`导入失败：${error.message}`, true);
  } finally {
    event.target.value = "";
  }
});

/* ----------------------------------------------------------------- misc */

$("undoBtn").addEventListener("click", async () => {
  const batch = S.undo.pop();
  if (!batch) {
    toast("没有可撤销的修改");
    return;
  }
  try {
    for (const [row, col, value] of batch) {
      S.grid[row][col] = value;
    }
    walkDirty = true;
    draw();
    const result = await api("/api/edit", { changes: batch });
    S.updatedAt = result.updated_at;
    S.hash = result.snapshot_hash;
    S.stats = { ...S.stats, ...result.stats };
    renderTopStats();
    renderManagePanel();
    setSaveState(`已撤销 · ${formatTime(result.updated_at)}`);
  } catch (error) {
    toast(`撤销失败：${error.message}`, true);
    await loadState();
  }
});

$("brush").addEventListener("change", (event) => {
  S.brush = Number(event.target.value);
});
$("showGrid").addEventListener("change", (event) => {
  S.showGrid = event.target.checked;
  draw();
});
$("showLabels").addEventListener("change", (event) => {
  S.showLabels = event.target.checked;
  draw();
});
$("showWalk").addEventListener("change", (event) => {
  S.showWalk = event.target.checked;
  draw();
});

function applyZoom() {
  if (S.zoom === "fit") {
    const availableHeight = Math.max(320, mapScroll.clientHeight - 36);
    const availableWidth = Math.max(260, mapScroll.clientWidth - 36);
    const width = Math.min(availableWidth, availableHeight * 0.5);
    canvasWrap.style.width = `${Math.floor(width)}px`;
  } else {
    canvasWrap.style.width = `${W}px`;
  }
}

$("fitBtn").addEventListener("click", () => {
  S.zoom = "fit";
  applyZoom();
});
$("fullBtn").addEventListener("click", () => {
  S.zoom = "full";
  applyZoom();
});

window.addEventListener("resize", applyZoom);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    hidePopup();
    setMode("view");
  }
  if (
    event.target instanceof HTMLInputElement ||
    event.target instanceof HTMLSelectElement
  ) {
    return;
  }
  if (event.key === "1" || event.key === "3" || event.key === "5") {
    S.brush = Number(event.key);
    $("brush").value = event.key;
  }
});

/* --------------------------------------------------------------- startup */

mapImage = new Image();
mapImage.onload = () => {
  mapImageReady = true;
  draw();
};
mapImage.src = "/static/campus_map.jpg";

applyZoom();
loadState();
