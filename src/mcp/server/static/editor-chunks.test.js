const assert = require('assert');
global.window = global; // editor-chunks.js 以 `(window)` 结尾挂载
require('./editor-chunks.js');
const ec = global.EditorChunks;

// ---- extractYamlFrontmatter ----
const yaml = '---\r\ntitle: "Lecture Notes"\r\noutput:\r\n  pdf_document: default\r\n---\r\n# 第一章\n正文';
const y = ec.extractYamlFrontmatter(yaml);
assert.strictEqual(y.prefix, '---\r\ntitle: "Lecture Notes"\r\noutput:\r\n  pdf_document: default\r\n---\r\n');
assert.strictEqual(y.body, '# 第一章\n正文');

// 无 YAML
assert.deepStrictEqual(ec.extractYamlFrontmatter('# 标题\n正文'), { prefix: '', body: '# 标题\n正文' });
assert.deepStrictEqual(ec.extractYamlFrontmatter(''), { prefix: '', body: '' });
assert.deepStrictEqual(ec.extractYamlFrontmatter(null), { prefix: '', body: null });

// YAML 结束无末尾换行
const yamlNoNl = '---\n title: x\n---';
const yn = ec.extractYamlFrontmatter(yamlNoNl);
assert.strictEqual(yn.prefix, yamlNoNl);
assert.strictEqual(yn.body, '');

// 正文开头的 ``` 围栏不被误判为 YAML
const fenceFirst = '```r\nx <- 1\n```';
assert.strictEqual(ec.extractYamlFrontmatter(fenceFirst).prefix, '');

// ---- YAML 中的 # 注释行不进入分块树（enable 时已剥离 YAML）----
const yamlWithHash = '---\n# 注释行\n---\n# 真标题\n正文';
const yh = ec.extractYamlFrontmatter(yamlWithHash);
assert.strictEqual(yh.prefix, '---\n# 注释行\n---\n');
assert.strictEqual(ec.scanTitles(yh.body).length, 1, '剥离 YAML 后仅剩真实标题');

console.log('editor-chunks YAML tests passed');
