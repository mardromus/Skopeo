const { chromium } = require('/opt/npm-tools/node_modules/playwright');
(async () => {
  const [src, out, title] = process.argv.slice(2);
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
  const p = await b.newPage();
  await p.goto('file://' + require('path').resolve(src), { waitUntil: 'networkidle' });
  await p.pdf({ path: out, format: 'A4', printBackground: true, preferCSSPageSize: true,
    displayHeaderFooter: true, headerTemplate: '<span></span>',
    footerTemplate: `<div style="width:100%;font:7.5pt Inter,sans-serif;color:#6f7785;padding:0 17mm;display:flex;justify-content:space-between"><span>${title}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>` });
  await b.close();
})();
