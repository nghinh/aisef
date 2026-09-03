// S7: trích accessibility tree của một trang, xuất JSON danh sách {role,name}.
import { chromium } from 'playwright';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const target = process.argv[2];
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(pathToFileURL(resolve(target)).href);

// ariaSnapshot trả cây YAML-like: '- textbox "Email"' ...
const snap = await page.locator('body').ariaSnapshot();

const nodes = [];
for (const line of snap.split('\n')) {
  const m = line.match(/^\s*-\s+([a-z]+)(?:\s+"([^"]*)")?/);
  if (m) nodes.push({ role: m[1], name: m[2] ?? '' });
}
console.log(JSON.stringify({ source: target, snapshot: snap, nodes }, null, 2));
await browser.close();
