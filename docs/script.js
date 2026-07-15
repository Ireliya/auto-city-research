const eventColors = {
  "hurricane-harvey": "#0f4d92",
  "mexico-earthquake": "#7a7a7a",
  "palu-tsunami": "#3b8c88",
  "santa-rosa-wildfire": "#b6435a",
};

const translations = {
  en: {
    "meta.description":
      "An auditable urban AI study of where satellite damage rankings disagree with multi-source post-disaster priority scenarios.",
    "meta.ogDescription":
      "Four disasters, three spatial scales, two population products, and one fixed-gate ranking audit.",
    skip: "Skip to research content",
    "brand.home": "Auto-City-Research home",
    "nav.label": "Primary navigation",
    "nav.question": "Question",
    "nav.events": "Events",
    "nav.scale": "Scale",
    "nav.audit": "Audit",
    "nav.results": "Results",
    "nav.reproduce": "Reproduce",
    "language.label": "Language",
    "menu.open": "Open navigation",
    "menu.close": "Close navigation",
    "hero.eyebrow": "Urban Cup 2026 · Competition 2",
    "hero.title": "Damage Is Not Need",
    "hero.question":
      "When an urban AI ranks recovery only by satellite-observed building damage, which places disappear from view?",
    "hero.boundary":
      "A reproducible audit of ranking disagreement across four disasters. It does not estimate true unmet need or prescribe dispatch.",
    "hero.resources": "Project resources",
    "hero.events": "Selected study events",
    "resource.code": "Code",
    "resource.data": "Data",
    "resource.paper": "Paper",
    "metrics.label": "Study scope",
    "metrics.events": "disaster events",
    "metrics.buildings": "labeled buildings",
    "metrics.cells": "reference cells",
    "metrics.funnel": "robust → temporal",
    "question.index": "01 · Research question",
    "question.title": "Visible damage is evidence. It is not the whole decision.",
    "question.quote":
      "If a post-disaster AI uses only remote-sensing damage to rank recovery priority, does it systematically omit places selected when population exposure, road access, critical services, and urban form are also inspected?",
    "question.observeLabel": "What we observe",
    "question.observeValue": "Ranking disagreement under transparent scenarios",
    "question.notObserveLabel": "What we do not observe",
    "question.notObserveValue": "True unmet need or a correct rescue allocation",
    "events.index": "02 · Event atlas",
    "events.title": "One audit, four distinct urban contexts",
    "events.intro": "Select an event to inspect its own 500 m footprint, damage pattern, and evidence state.",
    "events.tabsLabel": "Disaster events",
    "events.buildings": "Buildings",
    "events.cells": "500 m cells",
    "events.percentile": "Percentile diagnostic",
    "events.exact": "Exact top-20%",
    "events.robust": "Cross-definition robust",
    "events.temporal": "Temporal support",
    "overview.index": "03 · Study overview",
    "overview.title": "Geography, scale, and evidence in one frame",
    "overview.intro": "The same graphical overview appears in the English paper and Chinese competition report.",
    "overview.alt":
      "Study overview showing four disaster locations, the same Mexico area at three grid scales, and the fixed-gate evidence funnel",
    "overview.caption":
      "Four selected event footprints, independently rebuilt analysis grids, and the fixed audit that reduced diagnostic disagreements to four non-temporal candidates and zero temporally supported candidates.",
    "scale.index": "04 · Cross-scale explorer",
    "scale.title": "Same place. Different analytical support.",
    "scale.bodyBefore": "These are independently reconstructed grids around the same real Mexico candidate,",
    "scale.bodyAfter": "Empty mesh cells contain no xBD building labels; shaded cells entered the analysis.",
    "scale.tabsLabel": "Spatial resolution",
    "scale.legendLabel": "Map legend",
    "scale.buildingKey": "xBD building labels",
    "scale.cellKey": "containing cell",
    "audit.index": "05 · Audit framework",
    "audit.title": "Disagreement must survive fixed evidence gates",
    "audit.intro": "The framework compares rankings; it never converts a scenario score into a ground-truth need label.",
    "audit.rankingLabel": "Compared ranking families",
    "audit.damageSpan": "Observed physical condition",
    "audit.damageStrong": "Damage-only rankings",
    "audit.damageSmall": "4 alternative baselines",
    "audit.versus": "versus",
    "audit.multiSpan": "Transparent policy scenarios",
    "audit.multiStrong": "Multi-source priorities",
    "audit.multiSmall": "Population · access · services",
    "audit.gatesLabel": "Robustness gates",
    "audit.baselines": "damage baselines",
    "audit.draws": "weight draws",
    "audit.populations": "population products",
    "audit.scales": "rebuilt scales",
    "audit.funnelLabel": "Evidence funnel",
    "audit.audited": "audited cells",
    "audit.diagnostics": "percentile / exact diagnostics",
    "audit.robust": "cross-definition robust, all Mexico",
    "audit.temporal": "supported by historical OSM",
    "audit.proxy":
      "NFIP, SVI, and IHP remain outside this funnel. Their results are reported as mixed, construct-specific external evidence.",
    "results.index": "06 · Evidence",
    "results.title": "The strongest result is the narrowing",
    "results.intro": "Open a figure for a larger view. Every chart is generated from frozen derived tables.",
    "results.openTitle": "Open full figure",
    "results.scaleAlt": "Multiscale robustness results",
    "results.scaleOpen": "Open multiscale robustness figure",
    "results.scaleStrong": "Scale changes counts and area shares.",
    "results.scaleCaption":
      "The analysis is rebuilt at 250, 500, and 1,000 m rather than resampled from one grid.",
    "results.consensusAlt": "Fixed consensus audit results",
    "results.consensusOpen": "Open fixed consensus audit figure",
    "results.consensusStrong": "Only four cells pass every non-temporal gate.",
    "results.consensusCaption": "None survives the separate historical OSM support test.",
    "results.proxyAlt": "External proxy divergence results",
    "results.proxyOpen": "Open external proxy divergence figure",
    "results.proxyStrong": "External proxies disagree by construct.",
    "results.proxyCaption":
      "Insured loss, social vulnerability, and household assistance do not define one universal target.",
    "boundary.index": "07 · Validity boundary",
    "boundary.title": "A useful audit is honest about what remains unknown.",
    "boundary.supported": "Supported",
    "boundary.supportedText":
      "Damage-only and multi-source rankings can diverge, and the apparent signal is sensitive to policy weights, population resolution, spatial scale, and map time.",
    "boundary.notEstablished": "Not established",
    "boundary.notEstablishedText":
      "The analysis does not identify actual unmet need, causal urban-form mechanisms, or an ethically correct rescue and recovery allocation.",
    "boundary.use": "Appropriate use",
    "boundary.useText":
      "Use robust disagreements as locations for human review and additional local evidence, not as automatic dispatch instructions.",
    "reproduce.index": "08 · Open reproduction",
    "reproduce.title": "Trace every number back to data, code, config, and log.",
    "reproduce.body":
      "The public repository contains the core analysis, fixed configs, evidence manifests, and one-command reproduction entry point. Raw xBD imagery is not redistributed.",
    "reproduce.source": "Source code",
    "reproduce.sourceSub": "GitHub repository",
    "reproduce.data": "Derived data",
    "reproduce.dataSub": "Fixed Hugging Face revision",
    "reproduce.report": "Chinese report",
    "reproduce.reportSub": "Competition narrative",
    "reproduce.commandsLabel": "Core reproduction commands",
    "reproduce.terminal": "core reproduction",
    "reproduce.expected": "Expected fixed totals:",
    "reproduce.percentile": "percentile",
    "reproduce.exact": "exact top-20%",
    "reproduce.nonTemporal": "non-temporal robust",
    "reproduce.temporal": "temporal support",
    "footer.tagline": "Urban AI as auditable evidence, not automatic truth.",
    "footer.attribution":
      "Countries: Natural Earth, public domain. Building labels: xBD/xView2. See the report for complete attribution and limitations.",
    "dialog.closeFigure": "Close figure",
    "dialog.close": "Close",
  },
  zh: {
    "meta.description": "一项可审计的城市 AI 研究，分析卫星损毁排序与多源灾后优先情景在何处产生分歧。",
    "meta.ogDescription": "四场灾害、三种空间尺度、两种人口产品，以及一套固定门槛的排序审计。",
    skip: "跳转到研究内容",
    "brand.home": "Auto-City-Research 首页",
    "nav.label": "主导航",
    "nav.question": "问题",
    "nav.events": "事件",
    "nav.scale": "尺度",
    "nav.audit": "审计",
    "nav.results": "结果",
    "nav.reproduce": "复现",
    "language.label": "语言",
    "menu.open": "打开导航",
    "menu.close": "关闭导航",
    "hero.eyebrow": "Urban Cup 2026 · 赛题二",
    "hero.title": "损毁不等于需求",
    "hero.question": "当城市 AI 仅依据卫星影像中的建筑损毁程度排列恢复优先级时，哪些地区会从视野中消失？",
    "hero.boundary": "一项覆盖四场灾害、可复现的排序分歧审计。它不估计真实未满足需求，也不直接给出救援调度方案。",
    "hero.resources": "项目资源",
    "hero.events": "研究事件",
    "resource.code": "代码",
    "resource.data": "数据",
    "resource.paper": "英文论文",
    "metrics.label": "研究范围",
    "metrics.events": "场灾害事件",
    "metrics.buildings": "栋标注建筑",
    "metrics.cells": "个基准网格",
    "metrics.funnel": "稳健候选 → 时间支持",
    "question.index": "01 · 研究问题",
    "question.title": "可见的损毁是证据，但不是决策的全部。",
    "question.quote":
      "如果灾后 AI 只使用遥感损毁程度排列恢复优先级，那么在同时考察人口暴露、道路可达性、关键设施与城市形态时，它是否会系统性遗漏部分地区？",
    "question.observeLabel": "本研究观察到",
    "question.observeValue": "透明政策情景下的排序分歧",
    "question.notObserveLabel": "本研究没有观察到",
    "question.notObserveValue": "真实未满足需求或唯一正确的救援配置",
    "events.index": "02 · 事件图集",
    "events.title": "同一套审计，四种不同的城市情境",
    "events.intro": "选择事件，查看其独立的 500 米研究区、损毁分布与证据状态。",
    "events.tabsLabel": "灾害事件",
    "events.buildings": "建筑数量",
    "events.cells": "500 米网格",
    "events.percentile": "百分位诊断分歧",
    "events.exact": "严格前 20% 分歧",
    "events.robust": "跨定义稳健候选",
    "events.temporal": "时间证据支持",
    "overview.index": "03 · 研究总览",
    "overview.title": "在同一幅图中连接地理、尺度与证据",
    "overview.intro": "英文论文和中文竞赛报告使用同一张研究总览图。",
    "overview.alt": "研究总览图，展示四场灾害的位置、墨西哥同一区域的三种网格尺度，以及固定门槛证据漏斗",
    "overview.caption":
      "四个选定事件的研究区、独立重建的分析网格，以及将诊断分歧收窄为 4 个非时间候选和 0 个时间支持候选的固定审计。",
    "scale.index": "04 · 跨尺度查看",
    "scale.title": "同一地点，不同尺度下的证据支持并不相同。",
    "scale.bodyBefore": "下图围绕墨西哥同一个真实候选单元独立重建三种网格：",
    "scale.bodyAfter": "空白网格不含 xBD 建筑标签；着色网格进入了分析。",
    "scale.tabsLabel": "空间分辨率",
    "scale.legendLabel": "地图图例",
    "scale.buildingKey": "xBD 建筑标签",
    "scale.cellKey": "所属分析网格",
    "audit.index": "05 · 审计框架",
    "audit.title": "排序分歧必须通过预先固定的证据门槛",
    "audit.intro": "该框架比较不同排序，但不会把情景得分转换为真实需求标签。",
    "audit.rankingLabel": "对比的排序体系",
    "audit.damageSpan": "观测到的物理状况",
    "audit.damageStrong": "仅损毁排序",
    "audit.damageSmall": "4 种替代基线",
    "audit.versus": "对比",
    "audit.multiSpan": "透明的政策情景",
    "audit.multiStrong": "多源优先情景",
    "audit.multiSmall": "人口 · 可达性 · 服务设施",
    "audit.gatesLabel": "稳健性门槛",
    "audit.baselines": "种损毁基线",
    "audit.draws": "组权重抽样",
    "audit.populations": "种人口产品",
    "audit.scales": "种重建尺度",
    "audit.funnelLabel": "证据漏斗",
    "audit.audited": "个接受审计的网格",
    "audit.diagnostics": "百分位 / 严格前 20% 诊断分歧",
    "audit.robust": "个跨定义稳健候选，全部位于墨西哥",
    "audit.temporal": "个获得历史 OSM 支持的候选",
    "audit.proxy": "NFIP、SVI 与 IHP 不进入该漏斗；其结果作为衡量不同构念、且结论混合的外部证据单独报告。",
    "results.index": "06 · 证据",
    "results.title": "最有力的结果，是证据逐层收窄",
    "results.intro": "点击图表可查看大图。所有图表均由冻结的派生数据表生成。",
    "results.openTitle": "打开完整图表",
    "results.scaleAlt": "多尺度稳健性结果",
    "results.scaleOpen": "打开多尺度稳健性图",
    "results.scaleStrong": "尺度会改变分歧数量与面积占比。",
    "results.scaleCaption": "250、500 与 1,000 米分析均由原始建筑表独立重建，而非从单一网格重采样。",
    "results.consensusAlt": "固定共识审计结果",
    "results.consensusOpen": "打开固定共识审计图",
    "results.consensusStrong": "只有 4 个网格通过全部非时间门槛。",
    "results.consensusCaption": "没有任何网格通过独立的历史 OSM 支持检验。",
    "results.proxyAlt": "外部代理分歧结果",
    "results.proxyOpen": "打开外部代理分歧图",
    "results.proxyStrong": "不同外部代理衡量的构念并不一致。",
    "results.proxyCaption": "参保财产损失、社会脆弱性和家庭援助不能定义一个通用的真实目标。",
    "boundary.index": "07 · 有效性边界",
    "boundary.title": "有用的审计必须诚实面对尚未知道的部分。",
    "boundary.supported": "已有证据支持",
    "boundary.supportedText":
      "仅损毁排序与多源情景排序可能产生分歧，且可见信号会受到政策权重、人口分辨率、空间尺度与地图时间的影响。",
    "boundary.notEstablished": "尚未建立",
    "boundary.notEstablishedText": "本研究不能识别真实未满足需求、城市形态的因果机制，也不能给出伦理上唯一正确的救援与恢复配置。",
    "boundary.use": "适当用途",
    "boundary.useText": "将稳健分歧地点用于人工复核和补充本地证据，而不是直接作为自动调度指令。",
    "reproduce.index": "08 · 公开复现",
    "reproduce.title": "让每个数字都能追溯到数据、代码、配置与日志。",
    "reproduce.body": "公开仓库包含核心分析、固定配置、证据清单和一条命令复现入口。项目不重新分发 xBD 原始影像。",
    "reproduce.source": "源代码",
    "reproduce.sourceSub": "GitHub 仓库",
    "reproduce.data": "派生数据",
    "reproduce.dataSub": "固定 Hugging Face 版本",
    "reproduce.report": "中文报告",
    "reproduce.reportSub": "竞赛研究说明",
    "reproduce.commandsLabel": "核心复现命令",
    "reproduce.terminal": "核心复现",
    "reproduce.expected": "预期固定结果：",
    "reproduce.percentile": "个百分位分歧",
    "reproduce.exact": "个严格前 20% 分歧",
    "reproduce.nonTemporal": "个非时间稳健候选",
    "reproduce.temporal": "个时间支持候选",
    "footer.tagline": "把城市 AI 作为可审计的证据，而非自动生成的真相。",
    "footer.attribution": "国界数据：Natural Earth（公共领域）；建筑标签：xBD/xView2。完整署名与局限见研究报告。",
    "dialog.closeFigure": "关闭图表",
    "dialog.close": "关闭",
  },
};

const eventContent = {
  en: {
    "hurricane-harvey": {
      name: "Hurricane Harvey",
      shortName: "Harvey",
      hazard: "Flooding",
      note: "Provisional disagreement remains visible, but no cell passes every fixed cross-definition gate.",
      mapAlt: "Hurricane Harvey xBD footprint with independently rebuilt 500 metre damage cells",
      mapCaption: "Hurricane Harvey · independently rebuilt 500 m analysis cells",
    },
    "mexico-earthquake": {
      name: "Mexico earthquake",
      shortName: "Mexico",
      hazard: "Earthquake",
      note: "Four cells pass all non-temporal gates; historical OSM does not support their temporal persistence.",
      mapAlt: "Mexico earthquake xBD footprint with 500 metre damage cells and four robust candidates",
      mapCaption: "Mexico earthquake · four non-temporal candidates outlined in gold",
    },
    "palu-tsunami": {
      name: "Palu tsunami",
      shortName: "Palu",
      hazard: "Tsunami",
      note: "Only two exact top-20% diagnostic cells appear, and none survives every fixed gate.",
      mapAlt: "Palu tsunami xBD footprint with independently rebuilt 500 metre damage cells",
      mapCaption: "Palu tsunami · independently rebuilt 500 m analysis cells",
    },
    "santa-rosa-wildfire": {
      name: "Santa Rosa wildfire",
      shortName: "Santa Rosa",
      hazard: "Wildfire",
      note: "Current-map disagreement is visible and the event-level historical map test supports it, but no individual cell passes all cross-definition gates.",
      mapAlt: "Santa Rosa wildfire xBD footprint with independently rebuilt 500 metre damage cells",
      mapCaption: "Santa Rosa wildfire · independently rebuilt 500 m analysis cells",
    },
  },
  zh: {
    "hurricane-harvey": {
      name: "哈维飓风",
      shortName: "哈维",
      hazard: "洪水",
      note: "初步排序分歧依然可见，但没有网格通过全部固定的跨定义门槛。",
      mapAlt: "哈维飓风 xBD 研究区及独立重建的 500 米损毁网格",
      mapCaption: "哈维飓风 · 独立重建的 500 米分析网格",
    },
    "mexico-earthquake": {
      name: "墨西哥地震",
      shortName: "墨西哥",
      hazard: "地震",
      note: "4 个网格通过全部非时间门槛，但历史 OSM 证据不支持其时间一致性。",
      mapAlt: "墨西哥地震 xBD 研究区、500 米损毁网格及 4 个稳健候选",
      mapCaption: "墨西哥地震 · 金色边框标出 4 个非时间稳健候选",
    },
    "palu-tsunami": {
      name: "帕卢海啸",
      shortName: "帕卢",
      hazard: "海啸",
      note: "仅出现 2 个严格前 20% 诊断分歧网格，且没有网格通过全部固定门槛。",
      mapAlt: "帕卢海啸 xBD 研究区及独立重建的 500 米损毁网格",
      mapCaption: "帕卢海啸 · 独立重建的 500 米分析网格",
    },
    "santa-rosa-wildfire": {
      name: "圣罗莎野火",
      shortName: "圣罗莎",
      hazard: "野火",
      note: "当前地图中的排序分歧可见，事件级历史地图检验也支持该信号，但没有单个网格通过全部跨定义门槛。",
      mapAlt: "圣罗莎野火 xBD 研究区及独立重建的 500 米损毁网格",
      mapCaption: "圣罗莎野火 · 独立重建的 500 米分析网格",
    },
  },
};

const historyLabels = {
  en: {
    not_assessable: "not assessable",
    does_not_support: "does not support",
    support: "supports",
  },
  zh: {
    not_assessable: "无法判定",
    does_not_support: "不支持",
    support: "支持",
  },
};

const scaleStates = {
  250: {
    retained: false,
    image: "assets/scale_mexico_250m.png",
    en: {
      alt: "Mexico candidate area rebuilt with a 250 metre grid",
      caption: "250 m reconstruction · common geographic crop",
      explanation: "The candidate area does not meet the common two-population-product support gate at 250 m.",
      status: "Not retained",
    },
    zh: {
      alt: "以 250 米网格独立重建的墨西哥候选区域",
      caption: "250 米独立重建 · 相同地理范围",
      explanation: "候选区域在 250 米尺度下未通过两种人口产品共同支持门槛。",
      status: "未保留",
    },
  },
  500: {
    retained: true,
    image: "assets/scale_mexico_500m.png",
    en: {
      alt: "Mexico candidate area rebuilt with a 500 metre grid",
      caption: "500 m reconstruction · common geographic crop",
      explanation: "The focus cell passes the common support gate at the reference 500 m scale.",
      status: "Retained",
    },
    zh: {
      alt: "以 500 米网格独立重建的墨西哥候选区域",
      caption: "500 米独立重建 · 相同地理范围",
      explanation: "焦点网格在基准 500 米尺度下通过共同支持门槛。",
      status: "保留",
    },
  },
  1000: {
    retained: true,
    image: "assets/scale_mexico_1000m.png",
    en: {
      alt: "Mexico candidate area rebuilt with a 1000 metre grid",
      caption: "1,000 m reconstruction · common geographic crop",
      explanation: "The corresponding area remains supported after independent reconstruction at 1,000 m.",
      status: "Retained",
    },
    zh: {
      alt: "以 1,000 米网格独立重建的墨西哥候选区域",
      caption: "1,000 米独立重建 · 相同地理范围",
      explanation: "对应区域在 1,000 米尺度独立重建后仍获得支持。",
      status: "保留",
    },
  },
};

let currentLanguage = "en";
let studyPayload = null;
let selectedEventId = "hurricane-harvey";
let selectedScale = "250";

function t(key) {
  return translations[currentLanguage][key] ?? translations.en[key] ?? key;
}

function numberFormatter() {
  return new Intl.NumberFormat(currentLanguage === "zh" ? "zh-CN" : "en-US");
}

function formatCoordinates(latitude, longitude) {
  const latDirection = latitude >= 0 ? "N" : "S";
  const lonDirection = longitude >= 0 ? "E" : "W";
  const separator = currentLanguage === "zh" ? "，" : " · ";
  return `${Math.abs(latitude).toFixed(3)}° ${latDirection}${separator}${Math.abs(longitude).toFixed(3)}° ${lonDirection}`;
}

function setEventText(key, value) {
  const node = document.querySelector(`[data-event="${key}"]`);
  if (node) node.textContent = value;
}

function renderEvent() {
  if (!studyPayload) return;
  const event = studyPayload.events.find((item) => item.id === selectedEventId);
  if (!event) return;
  const content = eventContent[currentLanguage][event.id] ?? eventContent.en[event.id];
  const formatter = numberFormatter();

  setEventText("hazard", content.hazard);
  setEventText("name", content.name);
  setEventText("history", historyLabels[currentLanguage][event.historical_osm_evidence]);
  setEventText("coordinates", formatCoordinates(event.latitude, event.longitude));
  setEventText("buildings", formatter.format(event.buildings));
  setEventText("cells", formatter.format(event.cells));
  setEventText("percentile", formatter.format(event.percentile_disagreement));
  setEventText("exact", formatter.format(event.exact_top20_disagreement));
  setEventText("robust", formatter.format(event.robust_non_temporal));
  setEventText("temporal", formatter.format(event.temporal_support));
  setEventText("note", content.note);

  const tabs = [...document.querySelectorAll("[data-event-id]")];
  tabs.forEach((tab) => tab.setAttribute("aria-selected", String(tab.dataset.eventId === event.id)));

  const history = document.querySelector('[data-event="history"]');
  if (history) {
    history.classList.toggle("support", event.historical_osm_evidence === "support");
    history.classList.toggle("not-supported", event.historical_osm_evidence === "does_not_support");
  }

  const maxExact = Math.max(...studyPayload.events.map((item) => item.exact_top20_disagreement));
  const bar = document.querySelector('[data-event="bar"]');
  if (bar) {
    bar.style.width = `${Math.max(2, (event.exact_top20_disagreement / maxExact) * 100)}%`;
    bar.style.backgroundColor = eventColors[event.id];
  }

  const map = document.querySelector("[data-event-map]");
  const caption = document.querySelector("[data-event-map-caption]");
  if (map) {
    const nextSource = event.map_image;
    const finishSwap = () => map.classList.remove("is-changing");
    if (map.getAttribute("src") !== nextSource) {
      map.classList.add("is-changing");
      map.addEventListener("load", finishSwap, { once: true });
      map.src = nextSource;
      if (map.complete) finishSwap();
    }
    map.alt = content.mapAlt;
  }
  if (caption) caption.textContent = content.mapCaption;
}

function renderScale() {
  const state = scaleStates[selectedScale];
  const localized = state?.[currentLanguage] ?? state?.en;
  const image = document.querySelector("[data-scale-image]");
  const caption = document.querySelector("[data-scale-caption]");
  const status = document.querySelector("[data-scale-status]");
  const explanation = document.querySelector("[data-scale-explanation]");
  if (!state || !localized || !image || !caption || !status || !explanation) return;

  document.querySelectorAll("[data-scale]").forEach((tab) => {
    tab.setAttribute("aria-selected", String(tab.dataset.scale === String(selectedScale)));
  });
  image.src = state.image;
  image.alt = localized.alt;
  caption.textContent = localized.caption;
  status.textContent = localized.status;
  status.classList.toggle("retained", state.retained);
  status.classList.toggle("not-retained", !state.retained);
  explanation.textContent = localized.explanation;
}

function updateMenuLabel() {
  const button = document.querySelector("[data-menu-button]");
  if (!button) return;
  const open = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-label", t(open ? "menu.close" : "menu.open"));
}

function applyLanguage(language) {
  currentLanguage = language === "zh" ? "zh" : "en";
  document.documentElement.lang = currentLanguage === "zh" ? "zh-CN" : "en";
  document.title = currentLanguage === "zh" ? "损毁不等于需求 | Auto-City-Research" : "Damage Is Not Need | Auto-City-Research";

  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  });
  document.querySelectorAll("[data-i18n-alt]").forEach((node) => {
    node.setAttribute("alt", t(node.dataset.i18nAlt));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((node) => {
    node.setAttribute("title", t(node.dataset.i18nTitle));
  });
  document.querySelectorAll("[data-i18n-content]").forEach((node) => {
    node.setAttribute("content", t(node.dataset.i18nContent));
  });

  Object.entries(eventContent[currentLanguage]).forEach(([id, content]) => {
    document.querySelectorAll(`[data-event-label="${id}"], [data-event-tab="${id}"]`).forEach((node) => {
      node.textContent = content.shortName;
    });
  });
  document.querySelectorAll("[data-language]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.language === currentLanguage));
  });

  updateMenuLabel();
  renderEvent();
  renderScale();

  try {
    window.localStorage.setItem("auto-city-language", currentLanguage);
  } catch {
    // Language selection remains available even when storage is blocked.
  }
}

function initializeLanguage() {
  let initialLanguage = "en";
  try {
    const stored = window.localStorage.getItem("auto-city-language");
    if (stored === "zh" || stored === "en") initialLanguage = stored;
  } catch {
    // English remains the deterministic default.
  }
  document.querySelectorAll("[data-language]").forEach((button) => {
    button.addEventListener("click", () => applyLanguage(button.dataset.language));
  });
  applyLanguage(initialLanguage);
}

function initializeTabKeyboard(selector, onSelect) {
  const tabs = [...document.querySelectorAll(selector)];
  tabs.forEach((tab, index) => {
    tab.addEventListener("keydown", (event) => {
      let nextIndex = null;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = tabs.length - 1;
      if (nextIndex === null) return;
      event.preventDefault();
      tabs[nextIndex].focus();
      onSelect(tabs[nextIndex]);
    });
  });
}

async function initializeStudyData() {
  try {
    const response = await fetch("data/study.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`Study data request failed: ${response.status}`);
    studyPayload = await response.json();

    const formatter = numberFormatter();
    Object.entries(studyPayload.study).forEach(([key, value]) => {
      const node = document.querySelector(`[data-global="${key}"]`);
      if (node) node.textContent = formatter.format(value);
    });

    const selectEvent = (tab) => {
      selectedEventId = tab.dataset.eventId;
      renderEvent();
    };
    document.querySelectorAll("[data-event-id]").forEach((tab) => {
      tab.addEventListener("click", () => selectEvent(tab));
    });
    initializeTabKeyboard("[data-event-id]", selectEvent);
    renderEvent();
  } catch (error) {
    console.warn(error);
  }
}

function initializeScaleExplorer() {
  const selectScale = (tab) => {
    selectedScale = tab.dataset.scale;
    renderScale();
  };
  document.querySelectorAll("[data-scale]").forEach((tab) => {
    tab.addEventListener("click", () => selectScale(tab));
  });
  initializeTabKeyboard("[data-scale]", selectScale);
  renderScale();
}

function initializeMenu() {
  const button = document.querySelector("[data-menu-button]");
  const navigation = document.querySelector("[data-navigation]");
  if (!button || !navigation) return;

  const closeMenu = () => {
    button.setAttribute("aria-expanded", "false");
    navigation.classList.remove("open");
    document.body.classList.remove("menu-open");
    updateMenuLabel();
  };

  button.addEventListener("click", () => {
    const open = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!open));
    navigation.classList.toggle("open", !open);
    document.body.classList.toggle("menu-open", !open);
    updateMenuLabel();
  });

  navigation.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
  window.addEventListener("resize", () => {
    if (window.innerWidth > 760) closeMenu();
  });
}

function initializeFigureDialog() {
  const dialog = document.querySelector("[data-figure-dialog]");
  const dialogImage = document.querySelector("[data-dialog-image]");
  const dialogCaption = document.querySelector("[data-dialog-caption]");
  const closeButton = document.querySelector("[data-dialog-close]");
  if (!dialog || !dialogImage || !dialogCaption || !closeButton) return;

  document.querySelectorAll("[data-figure-open]").forEach((button) => {
    button.addEventListener("click", () => {
      const figure = button.closest("figure");
      const image = figure?.querySelector("img");
      const caption = figure?.querySelector("figcaption");
      if (!image) return;
      dialogImage.src = image.src;
      dialogImage.alt = image.alt;
      dialogCaption.textContent = caption?.textContent.trim() || (currentLanguage === "zh" ? "研究图表" : "Research figure");
      dialog.showModal();
    });
  });

  closeButton.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}

initializeLanguage();
initializeStudyData();
initializeScaleExplorer();
initializeMenu();
initializeFigureDialog();
