const DATA_FILES = {
  cityAnalysis: 'assets/data/city_analysis.json',
  regionPriority: 'assets/data/region_priority.json',
  referenceProfiles: 'assets/data/reference_city_profiles.json',
  chargingSummary: 'assets/data/charging_data_summary.json',
  poiSummary: 'assets/data/poi_data_summary.json'
};

const els = {
  citySelect: document.getElementById('citySelect'),
  datasetMeta: document.getElementById('datasetMeta'),
  metricPrototype: document.getElementById('metricPrototype'),
  metricMatch: document.getElementById('metricMatch'),
  metricOverallConfidence: document.getElementById('metricOverallConfidence'),
  metricConfidenceNote: document.getElementById('metricConfidenceNote'),
  metricRegionConfidence: document.getElementById('metricRegionConfidence'),
  metricWeightedAuc: document.getElementById('metricWeightedAuc'),
  citySummary: document.getElementById('citySummary'),
  distanceBars: document.getElementById('distanceBars'),
  poiFactors: document.getElementById('poiFactors'),
  regionScatter: document.getElementById('regionScatter'),
  regionTable: document.getElementById('regionTable'),
  referenceProfiles: document.getElementById('referenceProfiles'),
  limitations: document.getElementById('limitations'),
  expandHeatmapBtn: document.getElementById('expandHeatmapBtn'),
  heatmapModal: document.getElementById('heatmapModal'),
  heatmapModalBody: document.getElementById('heatmapModalBody'),
  closeHeatmapModal: document.getElementById('closeHeatmapModal')
};

let appState = null;
let currentCity = null;

const BIG_CATEGORY_MAP = [
  [/汽车服务POI|汽车相关POI数量|汽车相关POI|汽车相关/, '汽车相关'],
  [/交通设施POI数量|交通设施POI|交通设施/, '交通设施'],
  [/休闲娱乐POI数量|休闲娱乐POI|休闲娱乐/, '休闲娱乐'],
  [/公司企业POI数量|公司企业POI|公司企业/, '公司企业'],
  [/医疗保健POI数量|医疗保健POI|医疗保健|医疗相关/, '医疗保健'],
  [/商务住宅POI数量|商务住宅POI|商务住宅|居住相关/, '商务住宅'],
  [/旅游景点POI数量|旅游景点POI|旅游景点/, '旅游景点'],
  [/生活服务POI数量|生活服务POI|生活服务/, '生活服务'],
  [/科教文化POI数量|科教文化POI|科教文化|教育相关/, '科教文化'],
  [/购物消费POI数量|购物消费POI|购物消费|零售相关/, '购物消费'],
  [/运动健身POI数量|运动健身POI|运动健身/, '运动健身'],
  [/酒店住宿POI数量|酒店住宿POI|酒店住宿/, '酒店住宿'],
  [/金融机构POI数量|金融机构POI|金融机构/, '金融机构'],
  [/餐饮美食POI数量|餐饮美食POI|餐饮美食|餐饮相关/, '餐饮美食']
];

function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function barRow(label, value, maxValue, invert = false) {
  const safeMax = maxValue <= 0 ? 1 : maxValue;
  const ratio = invert ? (1 - value / safeMax) : value / safeMax;
  return `
    <div class="bar-row">
      <div class="bar-label">${label}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(6, ratio * 100)}%"></div></div>
      <div class="bar-value">${value.toFixed(2)}</div>
    </div>
  `;
}

function normalizePoiFactorName(name) {
  for (const [pattern, label] of BIG_CATEGORY_MAP) {
    if (pattern.test(name)) {
      return label;
    }
  }
  return null;
}

function summarizePoiFactors(items) {
  const bucket = new Map();
  BIG_CATEGORY_MAP.forEach(([, label]) => {
    if (!bucket.has(label)) {
      bucket.set(label, 0);
    }
  });
  items.forEach(item => {
    const label = normalizePoiFactorName(item.name || '') || item.name;
    if (!label) return;
    bucket.set(label, Math.max(bucket.get(label) || 0, Number(item.value || 0)));
  });
  return Array.from(bucket.entries())
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

function summarizeReasons(reasons) {
  const labels = [];
  reasons.forEach(reason => {
    const label = normalizePoiFactorName(reason.name || '') || reason.name;
    if (!labels.includes(label)) {
      labels.push(label);
    }
  });
  return labels.slice(0, 3).join('、');
}

function renderSummary(cityRecord) {
  const metrics = cityRecord.city_metrics;
  els.metricPrototype.textContent = `${cityRecord.prototype_city} / ${cityRecord.prototype_label}`;
  els.metricMatch.textContent = cityRecord.match_statement;
  els.metricOverallConfidence.textContent = `${cityRecord.confidence.overall_confidence}/100`;
  els.metricConfidenceNote.textContent = `城市级 ${cityRecord.confidence.city_confidence}/100`;
  els.metricRegionConfidence.textContent = `${cityRecord.confidence.region_confidence}/100`;
  els.metricWeightedAuc.textContent = `参考城市区域区分度均值 AUC: ${cityRecord.confidence.weighted_region_cv_auc}`;

  els.citySummary.innerHTML = [
    `站点记录数：${metrics.station_count}；唯一站点坐标数：${metrics.unique_station_count}`,
    `POI 总量：${metrics.poi_count}；POI 大类数：${metrics.poi_big_cat_count}`,
    `区域网格数：${metrics.region_count}；已有站点网格占比：${formatPercent(metrics.covered_region_ratio)}`,
    `充电站点位密度代理：${metrics.station_density_hull.toFixed(3)}；POI 密度代理：${metrics.poi_density_hull.toFixed(1)}`
  ].map(item => `<div>${item}</div>`).join('');

  const distances = cityRecord.distances;
  const maxDistance = Math.max(...Object.values(distances));
  els.distanceBars.innerHTML = Object.entries(distances)
    .sort((a, b) => a[1] - b[1])
    .map(([key, value]) => barRow(key, value, maxDistance, true))
    .join('');

  const factorItems = summarizePoiFactors(cityRecord.all_poi_category_factors || cityRecord.top_poi_factors || []);
  const maxFactor = Math.max(...factorItems.map(item => item.value), 1);
  els.poiFactors.innerHTML = factorItems
    .map(item => barRow(item.name, item.value, maxFactor))
    .join('');

  els.limitations.innerHTML = cityRecord.limitations.map(item => `<li>${item}</li>`).join('');
}

function computeDisplayBounds(points) {
  const sparseThreshold = 2;
  const gapThreshold = 4;

  function trim(values) {
    const counts = new Map();
    values.forEach(value => counts.set(value, (counts.get(value) || 0) + 1));
    const sorted = Array.from(counts.keys()).sort((a, b) => a - b);
    let start = 0;
    let end = sorted.length - 1;

    while (start < end) {
      const current = sorted[start];
      const next = sorted[start + 1];
      if ((next - current) > gapThreshold && (counts.get(current) || 0) <= sparseThreshold) {
        start += 1;
      } else {
        break;
      }
    }

    while (end > start) {
      const current = sorted[end];
      const prev = sorted[end - 1];
      if ((current - prev) > gapThreshold && (counts.get(current) || 0) <= sparseThreshold) {
        end -= 1;
      } else {
        break;
      }
    }

    return { min: sorted[start], max: sorted[end] };
  }

  const xBounds = trim(points.map(item => item.grid_x));
  const yBounds = trim(points.map(item => item.grid_y));
  return {
    minX: xBounds.min,
    maxX: xBounds.max,
    minY: yBounds.min,
    maxY: yBounds.max,
  };
}
function renderReferenceProfiles(referenceProfiles) {
  els.referenceProfiles.innerHTML = Object.values(referenceProfiles).map(profile => {
    const factorItems = summarizePoiFactors(profile.all_poi_category_factors || profile.top_positive_poi_factors || []);
    const maxFactor = Math.max(...factorItems.map(item => item.value), 1);
    return `
      <div class="reference-item">
        <h3>${profile.city} / ${profile.label}</h3>
        <p class="muted">${profile.rationale}</p>
        <p>参考网格数：${profile.region_count}；有站网格占比：${formatPercent(profile.positive_rate)}；区域区分度 AUC：${profile.region_cv_auc.toFixed(3)}</p>
        <div class="bar-list">
          
        </div>
      </div>
    `;
  }).join('');
}

function renderRegionTable(regionData) {
  const rows = regionData.top_regions.slice(0, 12).map((item, index) => `
    <tr>
      <td>${index + 1}</td>
      <td><span class="pill">${item.priority_band}</span></td>
      <td>${item.has_station ? '已有站点' : '当前无站点'}</td>
      <td>${item.priority_score.toFixed(3)}</td>
      <td>${item.poi_total}</td>
    </tr>
  `).join('');
  els.regionTable.innerHTML = `
    <table class="table">
      <thead>
        <tr><th>#</th><th>关注等级</th><th>现状</th><th>优先分数</th><th>相关POI数量</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function heatColor(score) {
  if (score >= 0.85) return '#0f5c5d';
  if (score >= 0.7) return '#5f8f78';
  if (score >= 0.55) return '#9ab39d';
  if (score >= 0.4) return '#ccb28d';
  return '#eadfce';
}

function buildHeatmapMarkup(regionData, options = {}) {
  const maxStageW = options.width || 720;
  const maxStageH = options.height || 460;
  const padding = options.padding || 10;
  const modalMode = Boolean(options.modalMode);
  const points = regionData.all_regions;
  const bounds = computeDisplayBounds(points);
  const minX = bounds.minX;
  const maxX = bounds.maxX;
  const minY = bounds.minY;
  const maxY = bounds.maxY;
  const cols = maxX - minX + 1;
  const rows = maxY - minY + 1;
  const cellSize = Math.max(modalMode ? 6 : 4, Math.min((maxStageW - padding * 2) / Math.max(cols, 1), (maxStageH - padding * 2) / Math.max(rows, 1)));
  const plotWidth = cellSize * cols;
  const plotHeight = cellSize * rows;
  const viewW = plotWidth + padding * 2;
  const viewH = plotHeight + padding * 2;
  const offsetX = padding;
  const offsetY = padding;
  const rectSize = Math.max(cellSize - 0.6, 2.8);
  const rankMap = new Map(regionData.top_regions.slice(0, 12).map((item, index) => [item.grid_id, index + 1]));
  const fontSize = Math.max(modalMode ? 10 : 8, Math.min(modalMode ? 22 : 18, cellSize * (modalMode ? 0.62 : 0.52)));
  const textDy = fontSize * 0.32;

  const cells = points.map(item => {
    const x = offsetX + (item.grid_x - minX) * cellSize;
    const y = offsetY + (maxY - item.grid_y) * cellSize;
    const rank = rankMap.get(item.grid_id);
    const stroke = 'rgba(255,255,255,0.92)';
    const strokeWidth = modalMode ? 0.7 : 0.5;
    const showRank = Boolean(rank);
    const text = showRank ? `<text x="${(x + rectSize / 2).toFixed(2)}" y="${(y + rectSize / 2 + textDy).toFixed(2)}" text-anchor="middle" class="heatmap-cell-label" style="font-size:${fontSize.toFixed(1)}px">${rank}</text>` : '';
    const title = `${item.grid_id}\n优先分数: ${item.priority_score}\n现状: ${item.has_station ? '已有站点' : '当前无站点'}\n主要依据: ${summarizeReasons(item.top_reasons || [])}\nPOI数: ${item.poi_total}`;
    return `
      <g>
        <rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${rectSize.toFixed(2)}" height="${rectSize.toFixed(2)}" fill="${heatColor(item.priority_score)}" stroke="${stroke}" stroke-width="${strokeWidth}"><title>${title}</title></rect>
        ${text}
      </g>
    `;
  }).join('');

  const wrapClass = modalMode ? 'scatter-wrap scatter-wrap-modal' : 'scatter-wrap';
  const stageClass = modalMode ? 'heatmap-stage heatmap-stage-modal' : 'heatmap-stage';
  const svgClass = modalMode ? 'heatmap-svg heatmap-svg-modal' : 'heatmap-svg';
  const note = modalMode
    ? '放大视图会尽量保留排名数字；白色描边仅用于区分网格边界，不表示已有站点。'
    : '数字标注与右侧排名表对应；当前区域粒度为 2 公里网格。';

  return `
    <div class="${wrapClass}">
      <div class="heatmap-head">
        <div class="legend-row">
          <span>低</span>
          <span class="legend-swatch" style="background:#eadfce"></span>
          <span class="legend-swatch" style="background:#ccb28d"></span>
          <span class="legend-swatch" style="background:#9ab39d"></span>
          <span class="legend-swatch" style="background:#5f8f78"></span>
          <span class="legend-swatch" style="background:#0f5c5d"></span>
          <span>高</span>
        </div>
      </div>
      <div class="${stageClass}">
        <svg class="${svgClass}" viewBox="0 0 ${viewW} ${viewH}" preserveAspectRatio="xMidYMid meet">
          ${cells}
        </svg>
      </div>
      <div class="heatmap-note">${note}</div>
    </div>
  `;
}

function renderHeatmap(regionData) {
  els.regionScatter.innerHTML = buildHeatmapMarkup(regionData, { width: 720, height: 460, padding: 20, modalMode: false });
}

function openHeatmapModal() {
  if (!currentCity || !appState) return;
  const regionData = appState.regionPriority[currentCity];
  els.heatmapModalBody.innerHTML = buildHeatmapMarkup(regionData, { width: 1180, height: 820, padding: 28, modalMode: true });
  els.heatmapModal.hidden = false;
  document.body.classList.add('modal-open');
}

function closeHeatmapModal() {
  els.heatmapModal.hidden = true;
  els.heatmapModalBody.innerHTML = '';
  document.body.classList.remove('modal-open');
}

function renderCity(city) {
  currentCity = city;
  const cityRecord = appState.cityAnalysis.find(item => item.city === city);
  const regionData = appState.regionPriority[city];
  renderSummary(cityRecord);
  renderRegionTable(regionData);
  renderHeatmap(regionData);
  if (!els.heatmapModal.hidden) {
    openHeatmapModal();
  }
}

async function loadData() {
  const embedded = window.__APP_DATA__ || null;
  if (embedded && embedded.city_analysis && embedded.region_priority && embedded.reference_city_profiles) {
    return {
      cityAnalysis: embedded.city_analysis,
      regionPriority: embedded.region_priority,
      referenceProfiles: embedded.reference_city_profiles,
      chargingSummary: embedded.charging_data_summary,
      poiSummary: embedded.poi_data_summary
    };
  }

  const entries = await Promise.all(
    Object.entries(DATA_FILES).map(async ([key, path]) => {
      const response = await fetch(path);
      if (!response.ok) {
        throw new Error(`${path} -> HTTP ${response.status}`);
      }
      return [key, await response.json()];
    })
  );
  return Object.fromEntries(entries);
}

async function init() {
  appState = await loadData();

  els.datasetMeta.innerHTML = `
    <div>充电站记录：${appState.chargingSummary.guangdong_row_count} 条</div>
    <div>POI 记录：${appState.poiSummary.total_poi_rows} 条</div>
    <div>城市数：${appState.poiSummary.city_count}</div>
  `;

  appState.cityAnalysis.forEach(item => {
    const option = document.createElement('option');
    option.value = item.city;
    option.textContent = item.city;
    els.citySelect.appendChild(option);
  });

  els.citySelect.addEventListener('change', event => renderCity(event.target.value));
  els.expandHeatmapBtn.addEventListener('click', openHeatmapModal);
  els.closeHeatmapModal.addEventListener('click', closeHeatmapModal);
  els.heatmapModal.addEventListener('click', event => {
    if (event.target.dataset.close === 'heatmap') {
      closeHeatmapModal();
    }
  });
  window.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !els.heatmapModal.hidden) {
      closeHeatmapModal();
    }
  });

  renderReferenceProfiles(appState.referenceProfiles);
  renderCity(appState.cityAnalysis[0].city);
}

init().catch(error => {
  const hint = location.protocol === 'file:'
    ? '当前可能是直接通过 file:// 打开的。现在页面优先读取内嵌静态数据；如果仍失败，请确认 assets/data/app_data.js 存在，或改用 python -m http.server 打开 web/ 目录。'
    : '请确认 web/assets/data 下的静态资源存在，或重新运行 python scripts/run_pipeline.py。';
  document.body.innerHTML = `<pre style="padding:24px">加载静态资源失败：${error}\n\n${hint}</pre>`;
});



