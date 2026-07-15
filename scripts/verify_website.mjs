#!/usr/bin/env node
// Responsive and bilingual browser QA for the static research website.

import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const baseUrl = process.env.WEBSITE_URL || "http://127.0.0.1:4173/";
const outputDir = path.resolve(process.env.WEBSITE_QA_DIR || ".qa/website");
await fs.mkdir(outputDir, { recursive: true });

const failures = [];
const observations = [];
const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || (existsSync(macChrome) ? macChrome : undefined);
const browser = await chromium.launch({ headless: true, executablePath });

const expectedEvents = {
  "hurricane-harvey": {
    name: "Hurricane Harvey",
    map: "assets/event_hurricane-harvey.png",
  },
  "mexico-earthquake": {
    name: "Mexico earthquake",
    map: "assets/event_mexico-earthquake.png",
  },
  "palu-tsunami": {
    name: "Palu tsunami",
    map: "assets/event_palu-tsunami.png",
  },
  "santa-rosa-wildfire": {
    name: "Santa Rosa wildfire",
    map: "assets/event_santa-rosa-wildfire.png",
  },
};

function check(condition, message) {
  if (!condition) failures.push(message);
}

async function decodeImage(locator) {
  await locator.evaluate(async (image) => {
    try {
      await image.decode();
    } catch {
      // Natural dimensions are checked separately with a precise failure message.
    }
  });
}

async function collectLayout(page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const images = [...document.images].filter((image) => image.getAttribute("src")).map((image) => ({
      src: image.getAttribute("src"),
      naturalWidth: image.naturalWidth,
      naturalHeight: image.naturalHeight,
    }));
    const selector = [
      "button",
      ".metric-inner > div",
      ".event-detail",
      ".event-tabs button",
      ".scale-status",
      ".ranking-source",
      ".funnel-row",
      ".boundary-row",
      ".resource-list a",
      ".hero-links a",
      ".language-switch",
    ].join(",");
    const textContainers = [...document.querySelectorAll(selector)]
      .filter((element) => {
        const style = getComputedStyle(element);
        return style.display !== "none" && style.visibility !== "hidden";
      })
      .map((element) => ({
        selector: element.className || element.tagName,
        text: element.textContent.trim().replace(/\s+/g, " ").slice(0, 80),
        overflowX: element.scrollWidth - element.clientWidth,
      }))
      .filter((entry) => entry.overflowX > 2);
    const h1 = document.querySelector("h1")?.getBoundingClientRect();
    const question = document.querySelector(".hero-question")?.getBoundingClientRect();
    const links = document.querySelector(".hero-links")?.getBoundingClientRect();
    return {
      language: root.lang,
      viewportWidth: root.clientWidth,
      documentWidth: root.scrollWidth,
      images,
      textContainers,
      heroBoxes: { h1, question, links },
    };
  });
}

function checkLayout(layout, label) {
  check(layout.documentWidth <= layout.viewportWidth + 1, `${label}: horizontal page overflow (${layout.documentWidth} > ${layout.viewportWidth})`);
  check(layout.images.length >= 12, `${label}: expected website visual assets are missing`);
  for (const image of layout.images) {
    check(image.naturalWidth > 0 && image.naturalHeight > 0, `${label}: broken image ${image.src}`);
  }
  check(layout.textContainers.length === 0, `${label}: text container overflow ${JSON.stringify(layout.textContainers)}`);
  if (layout.heroBoxes.h1 && layout.heroBoxes.question && layout.heroBoxes.links) {
    check(layout.heroBoxes.h1.bottom <= layout.heroBoxes.question.top + 1, `${label}: hero title overlaps the question`);
    check(layout.heroBoxes.question.bottom <= layout.heroBoxes.links.top + 1, `${label}: hero question overlaps resource links`);
  }
}

async function loadEveryImage(page) {
  await page.evaluate(async () => {
    const step = Math.max(window.innerHeight * 0.8, 500);
    for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((resolve) => setTimeout(resolve, 35));
    }
    window.scrollTo(0, 0);
  });
  const lazyImages = page.locator('img[loading="lazy"]');
  const lazyImageCount = await lazyImages.count();
  for (let index = 0; index < lazyImageCount; index += 1) {
    const image = lazyImages.nth(index);
    await image.scrollIntoViewIfNeeded();
    await decodeImage(image);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForLoadState("networkidle");
}

async function inspectPage(page, label) {
  const consoleErrors = [];
  const failedResponses = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`);
  });

  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.locator('[data-language="en"]').click();
  check((await page.title()).includes("Damage Is Not Need"), `${label}: English document title is missing`);
  check(await page.locator("h1").isVisible(), `${label}: hero title is not visible`);
  await loadEveryImage(page);

  const mapSources = [];
  for (const [id, expected] of Object.entries(expectedEvents)) {
    await page.locator(`[data-event-id="${id}"]`).click();
    const eventMap = page.locator("[data-event-map]");
    await page.waitForFunction(
      ({ selector, source }) => document.querySelector(selector)?.getAttribute("src") === source,
      { selector: "[data-event-map]", source: expected.map },
    );
    await decodeImage(eventMap);
    const source = await eventMap.getAttribute("src");
    mapSources.push(source);
    check((await page.locator('[data-event="name"]').textContent())?.trim() === expected.name, `${label}: ${id} name did not update`);
    check(source === expected.map, `${label}: ${id} map did not update to ${expected.map}`);
    const size = await eventMap.evaluate((image) => ({ width: image.naturalWidth, height: image.naturalHeight }));
    check(size.width > 0 && size.height > 0, `${label}: ${id} map did not decode`);
  }
  check(new Set(mapSources).size === 4, `${label}: event selector does not expose four distinct maps`);
  check((await page.locator('[data-event="robust"]').textContent())?.trim() === "0", `${label}: selected Santa Rosa robust count should be zero`);

  await page.locator('[data-event-id="mexico-earthquake"]').click();
  check((await page.locator('[data-event="robust"]').textContent())?.trim() === "4", `${label}: Mexico robust count did not update to four`);

  await page.locator('[data-scale="500"]').click();
  await decodeImage(page.locator("[data-scale-image]"));
  check((await page.locator("[data-scale-status]").textContent())?.trim() === "Retained", `${label}: English 500 m status is not retained`);
  check((await page.locator("[data-scale-image]").getAttribute("src")) === "assets/scale_mexico_500m.png", `${label}: 500 m image did not load`);

  const englishLayout = await collectLayout(page);
  check(englishLayout.language === "en", `${label}: English language state was not applied`);
  checkLayout(englishLayout, `${label}-en`);

  await page.locator('[data-language="zh"]').click();
  check((await page.locator("html").getAttribute("lang")) === "zh-CN", `${label}: Chinese html language was not applied`);
  check((await page.locator("h1").textContent())?.trim() === "损毁不等于需求", `${label}: Chinese hero title did not update`);
  check((await page.locator('[data-event="name"]').textContent())?.trim() === "墨西哥地震", `${label}: Chinese event content did not update`);
  check((await page.locator("[data-event-map]").getAttribute("src")) === expectedEvents["mexico-earthquake"].map, `${label}: map state changed during translation`);
  check((await page.locator("[data-scale-status]").textContent())?.trim() === "保留", `${label}: Chinese 500 m status did not update`);
  const chineseLayout = await collectLayout(page);
  checkLayout(chineseLayout, `${label}-zh`);

  const zoomButtons = page.locator("[data-figure-open]");
  const zoomButtonCount = await zoomButtons.count();
  check(zoomButtonCount >= 1, `${label}: no figure zoom control is available`);
  await zoomButtons.nth(0).click();
  check(await page.locator("[data-figure-dialog]").evaluate((dialog) => dialog.open), `${label}: figure dialog did not open`);
  check((await page.locator("[data-dialog-close]").getAttribute("aria-label")) === "关闭图表", `${label}: dialog accessibility label was not translated`);
  await page.locator("[data-dialog-close]").click();

  await page.locator('[data-language="en"]').click();
  check((await page.locator("h1").textContent())?.trim() === "Damage Is Not Need", `${label}: English state was not restored`);

  check(consoleErrors.length === 0, `${label}: browser console errors ${JSON.stringify(consoleErrors)}`);
  check(failedResponses.length === 0, `${label}: failed asset responses ${JSON.stringify(failedResponses)}`);
  observations.push({ label, englishLayout, chineseLayout, mapSources, consoleErrors, failedResponses });
}

try {
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await inspectPage(desktop, "desktop-1440x1000");
  await desktop.goto(baseUrl, { waitUntil: "networkidle" });
  await desktop.locator('[data-language="en"]').click();
  await desktop.screenshot({ path: path.join(outputDir, "desktop-home.png"), fullPage: false });
  await desktop.locator('[data-event-id="mexico-earthquake"]').click();
  await desktop.locator("#events").scrollIntoViewIfNeeded();
  await desktop.screenshot({ path: path.join(outputDir, "desktop-events.png"), fullPage: false });
  await desktop.locator('[data-language="zh"]').click();
  await desktop.screenshot({ path: path.join(outputDir, "desktop-zh-events.png"), fullPage: false });
  await desktop.locator("#scale").scrollIntoViewIfNeeded();
  await desktop.screenshot({ path: path.join(outputDir, "desktop-zh-scale.png"), fullPage: false });
  await desktop.screenshot({ path: path.join(outputDir, "desktop-zh-full.png"), fullPage: true });
  await desktop.close();

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  await inspectPage(mobile, "mobile-390x844");
  await mobile.goto(baseUrl, { waitUntil: "networkidle" });
  await mobile.locator('[data-language="zh"]').click();
  await mobile.screenshot({ path: path.join(outputDir, "mobile-zh-home.png"), fullPage: false });

  const menuButton = mobile.locator("[data-menu-button]");
  await menuButton.click();
  check((await menuButton.getAttribute("aria-expanded")) === "true", "mobile-390x844: menu did not open");
  check((await menuButton.getAttribute("aria-label")) === "关闭导航", "mobile-390x844: open-menu label is not Chinese");
  check(await mobile.locator("[data-navigation]").isVisible(), "mobile-390x844: navigation is not visible after opening");
  await mobile.locator('[data-navigation] a[href="#events"]').click();
  check((await menuButton.getAttribute("aria-expanded")) === "false", "mobile-390x844: menu did not close after navigation");
  await mobile.locator('[data-event-id="palu-tsunami"]').click();
  await mobile.locator("#events").scrollIntoViewIfNeeded();
  await mobile.screenshot({ path: path.join(outputDir, "mobile-zh-events.png"), fullPage: false });
  await mobile.locator("#scale").scrollIntoViewIfNeeded();
  await mobile.screenshot({ path: path.join(outputDir, "mobile-zh-scale.png"), fullPage: false });
  await mobile.screenshot({ path: path.join(outputDir, "mobile-zh-full.png"), fullPage: true });
  await mobile.close();
} finally {
  await browser.close();
}

const report = {
  baseUrl,
  failures,
  observations,
  screenshots: [
    "desktop-home.png",
    "desktop-events.png",
    "desktop-zh-events.png",
    "desktop-zh-scale.png",
    "desktop-zh-full.png",
    "mobile-zh-home.png",
    "mobile-zh-events.png",
    "mobile-zh-scale.png",
    "mobile-zh-full.png",
  ],
};
await fs.writeFile(path.join(outputDir, "report.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");

if (failures.length) {
  console.error(`website_qa=FAIL (${failures.length})`);
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("website_qa=PASS");
console.log(`viewports=${observations.map((item) => item.label).join(",")}`);
console.log(`screenshots=${outputDir}`);
