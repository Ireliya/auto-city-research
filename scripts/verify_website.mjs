#!/usr/bin/env node
// Responsive browser QA for the static research website.

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

function check(condition, message) {
  if (!condition) failures.push(message);
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
  check((await page.title()).includes("Damage Is Not Need"), `${label}: document title is missing`);
  check(await page.locator("h1").isVisible(), `${label}: hero title is not visible`);

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
    await image.evaluate(async (element) => {
      try {
        await element.decode();
      } catch {
        // The natural-size check below reports the specific image on failure.
      }
    });
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForLoadState("networkidle");

  const layout = await page.evaluate(() => {
    const root = document.documentElement;
    const images = [...document.images].filter((image) => image.getAttribute("src")).map((image) => ({
      src: image.getAttribute("src"),
      naturalWidth: image.naturalWidth,
      naturalHeight: image.naturalHeight,
    }));
    const textContainers = [...document.querySelectorAll("button, .metric-inner > div, .event-detail, .ranking-source")]
      .map((element) => ({
        selector: element.className || element.tagName,
        overflowX: element.scrollWidth - element.clientWidth,
        overflowY: element.scrollHeight - element.clientHeight,
      }))
      .filter((entry) => entry.overflowX > 2);
    const h1 = document.querySelector("h1")?.getBoundingClientRect();
    const question = document.querySelector(".hero-question")?.getBoundingClientRect();
    const links = document.querySelector(".hero-links")?.getBoundingClientRect();
    return {
      viewportWidth: root.clientWidth,
      documentWidth: root.scrollWidth,
      images,
      textContainers,
      heroBoxes: { h1, question, links },
    };
  });

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

  const mexicoTab = page.locator('[data-event-id="mexico-earthquake"]');
  await mexicoTab.click();
  check((await page.locator('[data-event="name"]').textContent())?.trim() === "Mexico earthquake", `${label}: event selector did not update the event name`);
  check((await page.locator('[data-event="robust"]').textContent())?.trim() === "4", `${label}: Mexico robust count did not update to four`);

  const scale500 = page.locator('[data-scale="500"]');
  await scale500.click();
  check((await page.locator("[data-scale-status]").textContent())?.trim() === "Retained", `${label}: 500 m status is not retained`);
  check((await page.locator("[data-scale-image]").getAttribute("src")) === "assets/scale_mexico_500m.png", `${label}: 500 m image did not load`);

  const scale1000 = page.locator('[data-scale="1000"]');
  await scale1000.click();
  check((await page.locator("[data-scale-status]").textContent())?.trim() === "Retained", `${label}: 1,000 m status is not retained`);

  const zoomButtons = page.locator("[data-figure-open]");
  const zoomButtonCount = await zoomButtons.count();
  check(zoomButtonCount >= 1, `${label}: no figure zoom control is available`);
  await zoomButtons.nth(0).click();
  check(await page.locator("[data-figure-dialog]").evaluate((dialog) => dialog.open), `${label}: figure dialog did not open`);
  await page.locator("[data-dialog-close]").click();

  check(consoleErrors.length === 0, `${label}: browser console errors ${JSON.stringify(consoleErrors)}`);
  check(failedResponses.length === 0, `${label}: failed asset responses ${JSON.stringify(failedResponses)}`);
  observations.push({ label, layout, consoleErrors, failedResponses });
}

try {
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await inspectPage(desktop, "desktop-1440x1000");
  await desktop.goto(baseUrl, { waitUntil: "networkidle" });
  await desktop.screenshot({ path: path.join(outputDir, "desktop-home.png"), fullPage: false });
  await desktop.locator("#scale").scrollIntoViewIfNeeded();
  await desktop.screenshot({ path: path.join(outputDir, "desktop-scale.png"), fullPage: false });
  await desktop.screenshot({ path: path.join(outputDir, "desktop-full.png"), fullPage: true });
  await desktop.close();

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  await inspectPage(mobile, "mobile-390x844");
  await mobile.goto(baseUrl, { waitUntil: "networkidle" });
  await mobile.screenshot({ path: path.join(outputDir, "mobile-home.png"), fullPage: false });

  const menuButton = mobile.locator("[data-menu-button]");
  await menuButton.click();
  check((await menuButton.getAttribute("aria-expanded")) === "true", "mobile-390x844: menu did not open");
  check(await mobile.locator("[data-navigation]").isVisible(), "mobile-390x844: navigation is not visible after opening");
  await mobile.locator('[data-navigation] a[href="#scale"]').click();
  check((await menuButton.getAttribute("aria-expanded")) === "false", "mobile-390x844: menu did not close after navigation");
  await mobile.locator("#scale").scrollIntoViewIfNeeded();
  await mobile.screenshot({ path: path.join(outputDir, "mobile-scale.png"), fullPage: false });
  await mobile.screenshot({ path: path.join(outputDir, "mobile-full.png"), fullPage: true });
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
    "desktop-scale.png",
    "desktop-full.png",
    "mobile-home.png",
    "mobile-scale.png",
    "mobile-full.png",
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
