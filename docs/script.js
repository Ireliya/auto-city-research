const eventColors = {
  "hurricane-harvey": "#0f4d92",
  "mexico-earthquake": "#7a7a7a",
  "palu-tsunami": "#3b8c88",
  "santa-rosa-wildfire": "#b6435a",
};

const eventNotes = {
  "hurricane-harvey":
    "Provisional disagreement remains visible, but no cell passes every fixed cross-definition gate.",
  "mexico-earthquake":
    "Four cells pass all non-temporal gates; historical OSM does not support their temporal persistence.",
  "palu-tsunami":
    "Only two exact top-20% diagnostic cells appear, and none survives every fixed gate.",
  "santa-rosa-wildfire":
    "Current-map disagreement is visible and the event-level historical map test supports it, but no individual cell passes all cross-definition gates.",
};

const scaleStates = {
  250: {
    retained: false,
    image: "assets/scale_mexico_250m.png",
    alt: "Mexico candidate area rebuilt with a 250 metre grid",
    caption: "250 m reconstruction · common geographic crop",
    explanation:
      "The candidate area does not meet the common two-population-product support gate at 250 m.",
  },
  500: {
    retained: true,
    image: "assets/scale_mexico_500m.png",
    alt: "Mexico candidate area rebuilt with a 500 metre grid",
    caption: "500 m reconstruction · common geographic crop",
    explanation:
      "The focus cell passes the common support gate at the reference 500 m scale.",
  },
  1000: {
    retained: true,
    image: "assets/scale_mexico_1000m.png",
    alt: "Mexico candidate area rebuilt with a 1000 metre grid",
    caption: "1,000 m reconstruction · common geographic crop",
    explanation:
      "The corresponding area remains supported after independent reconstruction at 1,000 m.",
  },
};

const formatNumber = new Intl.NumberFormat("en-US");

function formatCoordinates(latitude, longitude) {
  const latDirection = latitude >= 0 ? "N" : "S";
  const lonDirection = longitude >= 0 ? "E" : "W";
  return `${Math.abs(latitude).toFixed(3)}° ${latDirection} · ${Math.abs(longitude).toFixed(3)}° ${lonDirection}`;
}

function historyLabel(value) {
  return String(value).replaceAll("_", " ");
}

function setEvent(event, allEvents) {
  const setText = (key, value) => {
    const node = document.querySelector(`[data-event="${key}"]`);
    if (node) node.textContent = value;
  };

  setText("hazard", event.hazard);
  setText("name", event.name);
  setText("history", historyLabel(event.historical_osm_evidence));
  setText("coordinates", formatCoordinates(event.latitude, event.longitude));
  setText("buildings", formatNumber.format(event.buildings));
  setText("cells", formatNumber.format(event.cells));
  setText("percentile", formatNumber.format(event.percentile_disagreement));
  setText("exact", formatNumber.format(event.exact_top20_disagreement));
  setText("robust", formatNumber.format(event.robust_non_temporal));
  setText("temporal", formatNumber.format(event.temporal_support));
  setText("note", eventNotes[event.id] || "Inspect the report for the complete event-level evidence.");

  const history = document.querySelector('[data-event="history"]');
  if (history) {
    history.classList.toggle("support", event.historical_osm_evidence === "support");
    history.classList.toggle("not-supported", event.historical_osm_evidence === "does_not_support");
  }

  const maxExact = Math.max(...allEvents.map((item) => item.exact_top20_disagreement));
  const bar = document.querySelector('[data-event="bar"]');
  if (bar) {
    bar.style.width = `${Math.max(2, (event.exact_top20_disagreement / maxExact) * 100)}%`;
    bar.style.backgroundColor = eventColors[event.id];
  }
}

async function initializeStudyData() {
  try {
    const response = await fetch("data/study.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`Study data request failed: ${response.status}`);
    const payload = await response.json();

    Object.entries(payload.study).forEach(([key, value]) => {
      const node = document.querySelector(`[data-global="${key}"]`);
      if (node) node.textContent = formatNumber.format(value);
    });

    const tabs = [...document.querySelectorAll("[data-event-id]")];
    const selectEvent = (id) => {
      const event = payload.events.find((item) => item.id === id);
      if (!event) return;
      tabs.forEach((tab) => tab.setAttribute("aria-selected", String(tab.dataset.eventId === id)));
      setEvent(event, payload.events);
    };

    tabs.forEach((tab) => tab.addEventListener("click", () => selectEvent(tab.dataset.eventId)));
    selectEvent("hurricane-harvey");
  } catch (error) {
    console.warn(error);
  }
}

function initializeScaleExplorer() {
  const tabs = [...document.querySelectorAll("[data-scale]")];
  const image = document.querySelector("[data-scale-image]");
  const caption = document.querySelector("[data-scale-caption]");
  const status = document.querySelector("[data-scale-status]");
  const explanation = document.querySelector("[data-scale-explanation]");

  const selectScale = (scale) => {
    const state = scaleStates[scale];
    if (!state || !image || !caption || !status || !explanation) return;
    tabs.forEach((tab) => tab.setAttribute("aria-selected", String(tab.dataset.scale === String(scale))));
    image.src = state.image;
    image.alt = state.alt;
    caption.textContent = state.caption;
    status.textContent = state.retained ? "Retained" : "Not retained";
    status.classList.toggle("retained", state.retained);
    status.classList.toggle("not-retained", !state.retained);
    explanation.textContent = state.explanation;
  };

  tabs.forEach((tab) => tab.addEventListener("click", () => selectScale(tab.dataset.scale)));
}

function initializeMenu() {
  const button = document.querySelector("[data-menu-button]");
  const navigation = document.querySelector("[data-navigation]");
  if (!button || !navigation) return;

  const closeMenu = () => {
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "Open navigation");
    navigation.classList.remove("open");
    document.body.classList.remove("menu-open");
  };

  button.addEventListener("click", () => {
    const open = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!open));
    button.setAttribute("aria-label", open ? "Open navigation" : "Close navigation");
    navigation.classList.toggle("open", !open);
    document.body.classList.toggle("menu-open", !open);
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
      dialogCaption.textContent = caption?.textContent.trim() || "Research figure";
      dialog.showModal();
    });
  });

  closeButton.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}

initializeStudyData();
initializeScaleExplorer();
initializeMenu();
initializeFigureDialog();
