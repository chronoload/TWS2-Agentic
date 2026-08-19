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

// ================= 脚注防覆写丢失 =================

// ---- splitFootnotes：把脚注定义从正文剥离为保留域 ----
const fnDoc = '# 第一章\n这里有一个引用[^1]和另一个[^2]。\n\n## 小节\n正文内容。\n\n[^1]: 第一个脚注。\n[^2]: 第二个脚注。\n';
const sf = ec.splitFootnotes(fnDoc);
assert.strictEqual(sf.footnotes, '[^1]: 第一个脚注。\n[^2]: 第二个脚注。', '脚注定义被剥离到 footnotes 域');
assert.ok(sf.body.indexOf('[^1]:') === -1, '正文不再包含脚注定义');
assert.ok(sf.body.indexOf('[^1]') !== -1, '正文保留行内引用');

// 脚注带续行（缩进 4 空格）应整体保留
const fnMulti = '段落[^a]。\n\n[^a]: 第一行。\n    续行内容。\n';
const sf2 = ec.splitFootnotes(fnMulti);
assert.strictEqual(sf2.footnotes, '[^a]: 第一行。\n    续行内容。', '脚注续行一并保留');
assert.strictEqual(sf2.body, '段落[^a]。\n\n', '正文剥离脚注后保持干净');

// 脚注出现在代码围栏内不剥离
const fnFence = '```\n[^x]: 代码里的假脚注\n```\n正文[^x]。\n\n[^x]: 真脚注。\n';
const sf3 = ec.splitFootnotes(fnFence);
assert.strictEqual(sf3.footnotes, '[^x]: 真脚注。', '围栏内脚注不剥离');
assert.ok(sf3.body.indexOf('[^x]: 代码里的假脚注') !== -1, '围栏内容保留在正文');

// 无脚注
const sfEmpty = ec.splitFootnotes('# 无脚注\n正文\n');
assert.strictEqual(sfEmpty.footnotes, '');
assert.strictEqual(sfEmpty.body, '# 无脚注\n正文\n');

// ---- 完整往返：load → 编辑含脚注块 → read 不丢脚注 ----
// 构造足够长且含 ≥3 个 H2 的文档以触发分块
function makeLongDoc() {
  const sec = (i) => '## 小节' + i + '\n' + '段落正文[^f' + i + ']。\n' + '补充段落内容。'.repeat(1500) + '\n';
  let body = '# 总标题\n引言段落。\n';
  for (let i = 1; i <= 4; i++) body += '\n' + sec(i);
  let fns = '';
  for (let i = 1; i <= 4; i++) fns += '[^f' + i + ']: 脚注内容' + i + '。\n';
  return body + '\n' + fns;
}
const longDoc = makeLongDoc();
const fullDoc = '---\ntitle: t\n---\n' + longDoc;

// mock Vditor：chunk 模式下 setValue 收到"当前块切片 + 注入脚注"，getValue 返回它
const fakeElement = {
  querySelectorAll: () => [],
  addEventListener: () => {},
  removeEventListener: () => {},
  scrollTop: 0,
  clientHeight: 100,
  scrollHeight: 100,
};
const fakeVditor = {
  _v: '',
  vditor: { currentMode: 'ir', ir: { element: fakeElement }, sv: { element: fakeElement } },
  setValue(v) { this._v = v; },
  getValue() { return this._v; }
};

// 临时 adapter：直接暴露 fakeVditor
const savedAdapter = ec._testAdapter; // 不存在则为 undefined
// attach 一个 adapter：getVditor 返回 fakeVditor，其余最小实现
ec.attach({
  getVditor: () => fakeVditor,
  getActivePath: () => '/tmp/t.md',
  getEditorSource: () => longDoc,
  setValue: (src) => fakeVditor.setValue(src),
  promptTitle: async () => null,
  onStateChange: () => {}
});

const loaded = ec.load(longDoc);
assert.ok(loaded, '长文档应启用分块');
// load → enable → renderActive 已把首块切片+脚注喂给 fakeVditor
const rendered = fakeVditor._v;
assert.ok(rendered.indexOf('[^f1]: 脚注内容1。') !== -1, '渲染首块时脚注定义被注入以解析引用');
// 编辑该块（保持内容不变，仅触发提交路径）
const out = ec.read();
assert.strictEqual(out.indexOf('[^f1]: 脚注内容1。') !== -1, true, 'read 后脚注定义仍保留');
assert.strictEqual(out.indexOf('[^f4]: 脚注内容4。') !== -1, true, 'read 后所有脚注定义仍保留');
assert.ok(out.indexOf('[^f1]') !== -1, '行内引用保留');
// 取全文应与原始（无 YAML）等价
assert.strictEqual(out.replace(/[ \t]+/g, ' '), longDoc.replace(/[ \t]+/g, ' '), 'round-trip 后正文+脚注与原始一致');

// 编辑脚注本身（改定义文本）后提交，应被捕获
fakeVditor._v = fakeVditor._v.replace('[^f1]: 脚注内容1。', '[^f1]: 修改后的脚注1。');
const out2 = ec.read();
assert.ok(out2.indexOf('[^f1]: 修改后的脚注1。') !== -1, '脚注编辑被捕获保留');

// 清理：禁用分块，恢复 adapter
ec.toggle();
ec.attach(savedAdapter || null);

console.log('editor-chunks footnote tests passed');
