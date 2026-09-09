// Dựng mockup trong trình duyệt thật rồi trích hợp đồng thị giác.
//
// Vì sao phải mở trình duyệt thay vì đọc HTML bằng regex: hợp đồng phải là
// thứ người dùng **thấy được**. Nút bị CSS ẩn, nhãn gắn sai `for`, vai trò
// ARIA bị ghi đè — regex đều không thấy, còn accessibility tree thì thấy.
// Đây cũng đúng cách bước 6.7b đối chiếu ứng dụng thật, nên hai bên so
// bằng cùng một thước đo.
//
// Đầu vào: JSON qua stdin — { jobs: [{ id, html, png }], viewport }
// Đầu ra:  JSON qua stdout — { screens: [...] } hoặc { error }
import { pathToFileURL } from 'node:url';
import { resolve, join } from 'node:path';
import { readFileSync } from 'node:fs';

const input = JSON.parse(readFileSync(0, 'utf8'));
const viewport = input.viewport ?? { width: 1280, height: 900 };

// ESM không đọc NODE_PATH, nên đường dẫn playwright phải truyền vào tường
// minh: script này nằm trong repo framework, còn playwright cài ở dự án.
const entry = input.playwright
  ? pathToFileURL(join(input.playwright, 'playwright', 'index.js')).href
  : 'playwright';
// playwright là gói CommonJS: nạp qua ESM thì API nằm trong `default`.
const mod = await import(entry);
const { chromium } = mod.chromium ? mod : mod.default;

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log(JSON.stringify({ error: `không mở được chromium: ${e.message}` }));
  process.exit(3);
}

const screens = [];
for (const job of input.jobs ?? []) {
  const page = await browser.newPage({ viewport });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  try {
    // Mockup mở bằng file://, ứng dụng thật mở bằng http:// — cùng một
    // đường trích, để hai bên so bằng cùng thước đo.
    const target = job.url ?? pathToFileURL(resolve(job.html)).href;
    const resp = await page.goto(target, { waitUntil: job.url ? 'networkidle' : 'load' });

    // Trang lỗi của máy chủ **cũng là** một trang: nó có tiêu đề, có phần tử,
    // và bộ so sánh chấm nó như thể ứng dụng dựng thiếu mọi thứ. Đo trên
    // `todo` 2026-09-09: route trong hợp đồng là một câu tiếng Anh, máy chủ
    // trả 404, cổng báo "thiếu heading/form/control" và story đốt hết 3 lượt
    // để sửa thứ không hỏng. Trạng thái ≥ 400 nghĩa là **chưa so được**.
    if (job.url && resp && resp.status() >= 400) {
      screens.push({ id: job.id, html: '', url: job.url, console_errors: errors,
                     error: `route không mở được: HTTP ${resp.status()} tại ${target}` });
      continue;
    }
    const snapshot = await page.locator('body').ariaSnapshot();

    // Vùng dữ liệu mẫu: hàng danh sách, thẻ, kết quả tìm kiếm. Tên gọi ở
    // đây đến từ nội dung ví dụ, không phải cam kết giao diện — ứng dụng
    // thật sẽ hiển thị dữ liệu khác. So theo tên sẽ đỏ mãi mãi, và một cổng
    // đỏ mãi mãi thì bị tắt.
    const samples = [];
    for (const region of await page.locator('[data-sample]').all()) {
      samples.push(await region.ariaSnapshot());
    }

    // Chú thích của chính tài liệu mockup: tiêu đề trạng thái, ghi chú cho
    // người đọc. Ứng dụng thật không bao giờ dựng chúng, nên chúng không
    // phải cam kết.
    const annotations = [];
    for (const region of await page.locator('[data-annotation]').all()) {
      annotations.push(await region.ariaSnapshot());
    }

    // Một file mockup thường dựng nhiều trạng thái cạnh nhau, nhưng ứng
    // dụng thật ở một thời điểm chỉ ở **một** trạng thái. Gộp hết vào hợp
    // đồng thì không có màn hình thật nào khớp nổi. Lấy trạng thái chính.
    const primaryLocator = (await page.locator('[data-state="primary"]').count())
      ? page.locator('[data-state="primary"]').first()
      : ((await page.locator('[data-state]').count())
          ? page.locator('[data-state]').first()
          : null);
    const primary = primaryLocator ? await primaryLocator.ariaSnapshot() : '';
    const states = await page.evaluate(() =>
      [...document.querySelectorAll('[data-state]')].map((el) => el.getAttribute('data-state')),
    );

    // Trường nhập lấy trong phạm vi trạng thái chính. Lấy cả trang thì một
    // ô tìm kiếm dựng lại ở 11 trạng thái sẽ thành 11 ràng buộc giống nhau.
    const meta = await page.evaluate(() => {
      // Tên thẻ đổi ở 0.2.0 (`aisdlc-` → `aisef-`). Mockup do bản cũ dựng vẫn
      // nằm trong dự án thật, nên đọc tên mới trước, tên cũ sau — không thì
      // cổng map mockup báo "không khai route" cho thứ đã khai đúng.
      const metaOf = (n) => (
        document.querySelector(`meta[name="${n}"]`)?.content
        ?? document.querySelector(`meta[name="${n.replace(/^aisef-/, 'aisdlc-')}"]`)?.content
        ?? ''
      );
      const scope =
        document.querySelector('[data-state="primary"]') ??
        document.querySelector('[data-state]') ??
        document;
      const fields = [...scope.querySelectorAll('input, textarea, select')].map((el) => ({
        name: el.name || el.id || '',
        type: (el.getAttribute('type') || el.tagName).toLowerCase(),
        label: (el.labels?.[0]?.textContent || el.getAttribute('aria-label') || el.placeholder || '').trim(),
        required: el.hasAttribute('required'),
        pattern: el.getAttribute('pattern') || '',
        min: el.getAttribute('min') || '',
        max: el.getAttribute('max') || '',
        maxlength: el.getAttribute('maxlength') || '',
      }));
      return {
        route: metaOf('aisef-route'),
        screenId: metaOf('aisef-screen'),
        title: document.title || '',
        fields,
        // Chỗ mockup tự khai là chưa chốt — cổng máy chặn nếu còn sót.
        unresolved: [...document.querySelectorAll('[data-unresolved]')].map(
          (el) => el.getAttribute('data-unresolved') || el.textContent.trim().slice(0, 120),
        ),
      };
    });

    if (job.png) {
      await page.screenshot({ path: job.png, fullPage: true });
    }
    screens.push({ id: job.id, html: job.html ?? '', url: job.url ?? '', png: job.png ?? '',
                   snapshot, sample_snapshots: samples, annotation_snapshots: annotations,
                   primary_snapshot: primary, declared_states: states,
                   ...meta, console_errors: errors });
  } catch (e) {
    screens.push({ id: job.id, html: job.html ?? '', url: job.url ?? '', error: String(e), console_errors: errors });
  } finally {
    await page.close();
  }
}

await browser.close();
console.log(JSON.stringify({ screens }, null, 2));
