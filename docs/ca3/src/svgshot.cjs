const { chromium } = require('/opt/npm-tools/node_modules/playwright');
(async () => { const [src,out,w,h]=process.argv.slice(2); const b=await chromium.launch(); const p=await b.newPage({viewport:{width:+w,height:+h},deviceScaleFactor:1.5});
await p.goto('file://'+require('path').resolve(src)); await p.screenshot({path:out}); await b.close(); })();
