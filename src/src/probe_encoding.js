const fs = require('fs');
const os = require('os');
const path = require('path');
const ROOT = 'C:\\Users\\qu\\Desktop\\物理科学与技术论题\\TS2_dev';
function probe(p, label) {
  const b = fs.readFileSync(p);
  let u = 'OK', g = 'OK';
  try { new TextDecoder('utf-8', { fatal: true }).decode(b); } catch (e) { u = 'FAIL'; }
  try { new TextDecoder('gbk', { fatal: true }).decode(b); } catch (e) { g = 'FAIL'; }
  console.log(label, b.length + 'B', 'utf8:' + u, 'gbk:' + g);
}
probe(path.join(ROOT, 'src/mcp/server/static/app.js'), 'work/app.js    ');
probe(path.join(os.tmpdir(), 'app_head.js'), 'HEAD/app.js    ');
