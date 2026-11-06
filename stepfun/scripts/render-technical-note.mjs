#!/usr/bin/env node
/** Render docs/技术说明.html to the one-page A4 PDF with headless Edge. */
import { chromium } from "playwright";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage();
const file = "file:///" + path.join(root, "docs", "技术说明.html").replace(/\\/g, "/");
await page.goto(file, { waitUntil: "networkidle" });
await page.emulateMedia({ media: "print" });
const pdf = await page.pdf({
  path: path.join(root, "docs", "技术说明.pdf"),
  format: "A4",
  printBackground: true,
  preferCSSPageSize: true,
  margin: { top: "0", right: "0", bottom: "0", left: "0" },
});
const pages = (pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
console.log(`docs/技术说明.pdf · ${(pdf.length / 1024).toFixed(1)} KiB · ${pages} page(s)`);
await browser.close();
if (pages !== 1) process.exit(2);
