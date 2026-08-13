const rm = require('./rmd-chunk.js');
const assert = require('assert');

// parseChunkHeader
assert.deepStrictEqual(rm.parseChunkHeader('{r mychunk, echo=FALSE, fig.height=4}'),
  { engine: 'r', name: 'mychunk', opts: 'echo=FALSE, fig.height=4' });
assert.deepStrictEqual(rm.parseChunkHeader('{r, echo=FALSE}'),
  { engine: 'r', name: '', opts: 'echo=FALSE' });
assert.deepStrictEqual(rm.parseChunkHeader('{r}'),
  { engine: 'r', name: '', opts: '' });
assert.deepStrictEqual(rm.parseChunkHeader('{r echo=FALSE}'),
  { engine: 'r', name: '', opts: 'echo=FALSE' });
assert.deepStrictEqual(rm.parseChunkHeader('{python}'),
  { engine: 'python', name: '', opts: '' });
assert.strictEqual(rm.parseChunkHeader('python'), null); // 非块头
assert.strictEqual(rm.parseChunkHeader(''), null);

// parseRmdMeta
assert.deepStrictEqual(rm.parseRmdMeta('# %%RMD<<r|mychunk|echo=FALSE, fig.height=4>>%%'),
  { engine: 'r', name: 'mychunk', opts: 'echo=FALSE, fig.height=4' });
assert.strictEqual(rm.parseRmdMeta('normal code'), null);

// engineToHljs
assert.strictEqual(rm.engineToHljs('r'), 'r');
assert.strictEqual(rm.engineToHljs('python'), 'python');
assert.strictEqual(rm.engineToHljs('bash'), 'bash');
assert.strictEqual(rm.engineToHljs('unknown123'), 'plaintext');
assert.strictEqual(rm.engineToHljs(''), 'plaintext');

console.log('Task1 parse tests passed');

// 往返：正向再逆向应得到规范化后的合法 Rmd
function canonical(x){ return rm.editorSourceToRmd(rm.rmdToEditorSource(x)); }
assert.strictEqual(
  canonical('```{r mychunk, echo=FALSE, fig.height=4}\nx <- 1:10\nplot(x)\n```'),
  '```{r mychunk, echo=FALSE, fig.height=4}\nx <- 1:10\nplot(x)\n```');
assert.strictEqual(canonical('```{r}\na <- 1\n```'), '```{r}\na <- 1\n```');
assert.strictEqual(canonical('```{r, echo=FALSE}\nb\n```'), '```{r, echo=FALSE}\nb\n```');

// 幂等：两轮应稳定（第二次已是规范化）
var once = rm.rmdToEditorSource('```{r mychunk, echo=FALSE}\nx\n```');
var twice = rm.editorSourceToRmd(once);
var thrice = rm.editorSourceToRmd(rm.rmdToEditorSource(twice));
assert.strictEqual(twice, thrice);

// 非块内容不受影响
var md = '# 标题\n\n正文 `行内码` 与 ```python\ndef f(): pass\n``` 正常。';
assert.strictEqual(canonical(md), md);

// 含 } 的选项值（用 <<>> 分隔，必须安全）
assert.strictEqual(
  canonical('```{r, label="a}b"}\nx\n```'),
  '```{r, label="a}b"}\nx\n```');

// 中文块名/选项
assert.strictEqual(
  canonical('```{r 我的块, 选项=1}\nx\n```'),
  '```{r 我的块, 选项=1}\nx\n```');

// 多个块混合
var multi = '```{r a}\n1\n```\n\n文字\n\n```{python b}\n2\n```';
assert.strictEqual(canonical(multi), multi);

// 模糊：随机生成含花括号/反引号/中文的块与正文，断言不抛错且不丢非块内容
function randChunk(){
  var engines = ['r','python','bash','sql'];
  var e = engines[Math.floor(Math.random()*engines.length)];
  var name = Math.random()<0.5 ? '' : 'chunk'+Math.floor(Math.random()*100);
  var opts = Math.random()<0.5 ? '' : 'echo=FALSE, fig.height='+Math.floor(Math.random()*10);
  var info = '{' + e + (name?' '+name:'') + (opts?(name?', ':'')+opts:'') + '}';
  return '```'+info+'\n'+Math.random().toString(36)+'\n```';
}
for (var t=0; t<200; t++){
  var doc = '# '+Math.random().toString(36)+'\n'+randChunk()+'\n正文`code`'+randChunk();
  var out = rm.editorSourceToRmd(rm.rmdToEditorSource(doc));
  assert.ok(out.indexOf('```') !== -1); // 块未丢失
  assert.ok(out.indexOf('正文') !== -1); // 非块内容未丢失
}

console.log('Task2 roundtrip/fuzz tests passed');

// ---- 最小 DOM mock 冒烟测试（验证增强流程不抛错且产出块头）----
function makeMockDoc(){
  var nodes = [];
  function El(tag){
    this.tag = tag; this.children = []; this.attrs = {}; this.classes = {};
    this.style = {}; this._text = ''; this.parent = null; this.listeners = {};
    var self = this;
    this.classList = {
      add: function(c){ self.classes[c]=true; },
      contains: function(c){ return !!self.classes[c]; }
    };
  }
  El.prototype.appendChild = function(c){ c.parent = this; this.children.push(c); return c; };
  El.prototype.insertBefore = function(n, ref){ n.parent = this; this.children.unshift(n); return n; };
  Object.defineProperty(El.prototype, 'parentElement', { get: function(){ return this.parent; } });
  El.prototype.setAttribute = function(k,v){ this.attrs[k]=v; };
  El.prototype.addEventListener = function(t,fn){ (this.listeners[t]=this.listeners[t]||[]).push(fn); };
  Object.defineProperty(El.prototype, 'textContent', {
    get: function(){ return this._text; },
    set: function(v){ this._text = v; this.children = []; }
  });
  Object.defineProperty(El.prototype, 'innerHTML', {
    get: function(){ return this._text; },
    set: function(v){ this._text = v; this.children = []; }
  });
  El.prototype.querySelectorAll = function(sel){
    var res = [];
    function walk(n){
      n.children.forEach(function(ch){
        if ((sel === 'pre > code.language-rm-chunk' || sel === 'pre > code') && ch.tag === 'code' && n.tag === 'pre') {
          res.push(ch);
        }
        walk(ch);
      });
    }
    walk(this);
    return res;
  };
  var code = new El('code');
  code.textContent = '# %%RMD<<r|mychunk|echo=FALSE>>%%\nx <- 1:10';
  var pre = new El('pre'); pre.appendChild(code);
  var doc = { querySelectorAll: function(){ return []; }, createElement: function(t){ return new El(t); },
    getElementById: function(){ return null; }, body: new El('body') };
  doc.__root = pre;
  return { code: code, pre: pre, doc: doc };
}
var mock = makeMockDoc();
// 增强函数使用裸 document，需在 node 下让全局 document 可用（复用顶部已 require 的 rm）
global.document = mock.doc;
global.window = mock.doc;
rm.enhanceRmdChunks(mock.doc.__root);
assert.ok(mock.pre.classes['rmd-chunk'], 'pre 应被加上 rmd-chunk 类');
assert.ok(mock.pre.attrs['data-rmd-meta'] && mock.pre.attrs['data-rmd-meta'].indexOf('mychunk') !== -1, 'data-rmd-meta 应含块名');
console.log('Task3 DOM smoke test passed');

// ---- Task4: 实例感知（增强/回写作用于正确的 Vditor 实例）----
(function(){
  var m = makeMockDoc();
  var encoded = '```r\n' + m.code.textContent + '\n```';
  var fakeVditor = {
    _val: encoded,
    getValue: function(){ return this._val; },
    setValue: function(s){ this._val = s; }
  };
  var otherCalled = false;
  var otherVditor = { setValue: function(){ otherCalled = true; } };
  // 强化防护：确保 rm.state.vditor 未泄漏到本测试
  delete rm.state;
  rm.enhanceRmdChunks(m.doc.__root, fakeVditor);
  assert.strictEqual(m.code.__rmdVditor, fakeVditor, 'enhanceRmdChunks 应把 vditor 绑到 code 元素');

  // 双击改表头：回写须作用于绑定的 fakeVditor，而非其它实例
  var newMeta = { engine: 'r', name: 'renamed', opts: 'echo=FALSE' };
  rm.applyMetaToEditor(newMeta, m.code);
  assert.ok(fakeVditor._val.indexOf('renamed') !== -1, 'applyMetaToEditor 应回写到绑定的 vditor');
  assert.ok(/# %%RMD<<r\|renamed\|echo=FALSE>>%%/.test(fakeVditor._val), '回写后 meta 行应更新');
  assert.strictEqual(otherCalled, false, '其它实例的 setValue 不应被调用');
})();
console.log('Task4 instance-awareness test passed');

// ---- Task5: contenteditable 中 dblclick 目标为文本节点时仍能打开块编辑弹窗 ----
(function(){
  var docById = {};
  function El(tag){
    this.tag = tag; this.nodeType = 1; this.children = []; this.attrs = {}; this.classes = {}; this._text = ''; this.parent = null; this.listeners = {}; this.id = '';
    var self = this;
    this.classList = { add: function(c){ self.classes[c] = true; }, contains: function(c){ return !!self.classes[c]; } };
  }
  Object.defineProperty(El.prototype, 'parentElement', { get: function(){ return this.parent; } });
  El.prototype.appendChild = function(c){ c.parent = this; this.children.push(c); var _id = c.id || (c.attrs && c.attrs.id); if (_id) docById[_id] = c; return c; };
  El.prototype.removeChild = function(c){ var i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); };
  El.prototype.addEventListener = function(t, fn){ (this.listeners[t] = this.listeners[t] || []).push(fn); };
  El.prototype._find = function(pred){ for (var i=0;i<this.children.length;i++){ var ch=this.children[i]; if (pred(ch)) return ch; var r = ch._find ? ch._find(pred) : null; if (r) return r; } return null; };
  El.prototype.querySelector = function(sel){ return sel === 'code' ? this._find(function(n){ return n.tag === 'code'; }) : null; };
  El.prototype.closest = function(sel){
    var self = this;
    var parts = String(sel).split(',').map(function(s){ return s.trim(); });
    function match(el, p){
      if (p.charAt(0) === '['){
        var mm = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(p);
        if (!mm) return false;
        var v = el.attrs[mm[1]];
        if (mm[2] === undefined) return v !== undefined;
        return v === mm[2];
      }
      var tm = /^([a-z0-9]*)\.([\w-]+)$/.exec(p);
      if (tm){ if (tm[1] && el.tag !== tm[1]) return false; return !!el.classes[tm[2]]; }
      if (/^[a-z0-9]+$/.test(p)) return el.tag === p;
      return false;
    }
    var cur = self;
    while (cur){ for (var i=0;i<parts.length;i++){ if (match(cur, parts[i])) return cur; } cur = cur.parent; }
    return null;
  };
  Object.defineProperty(El.prototype, 'textContent', { get: function(){ return this._text; }, set: function(v){ this._text = v; this.children = []; } });

  var mockDoc = {
    _handlers: {},
    addEventListener: function(t, fn){ (this._handlers[t] = this._handlers[t] || []).push(fn); },
    getElementById: function(id){ return docById[id] || null; },
    createElement: function(t){ return new El(t); },
    body: new El('body')
  };
  global.document = mockDoc;  // openChunkEditor 用裸 document（Node global.document）
  rm.document = mockDoc;     // 注册用模块内 global（=== rm）

  var code = new El('code');
  code.textContent = '# %%RMD<<r|mychunk|echo=FALSE>>%%\nx';
  var pre = new El('pre');
  pre.classList.add('rmd-chunk');
  pre.appendChild(code);
  var textNode = { nodeType: 3, parentElement: code };  // dblclick 落在文本节点

  rm.initChunkEditTrigger();
  var handlers = mockDoc._handlers['dblclick'] || [];
  assert.ok(handlers.length >= 1, '应注册 document 级 dblclick 监听');
  handlers[handlers.length - 1]({ target: textNode });
  assert.ok(docById['rmdChunkEditor'], '文本节点的 dblclick 应创建块编辑弹窗（#rmdChunkEditor）');
})();
console.log('Task5 text-node dblclick test passed');

// ---- Task6: 图片路径双向转换（相对路径 ↔ 下载 URL）----
(function(){
  function rel(md){ return rm.rmdToEditorSource(md); }
  function save(md){ return rm.editorSourceToRmd(md); }

  // 加载：相对路径 → 下载 URL
  assert.strictEqual(rel('![](Notes/foo.png)'), '![](/api/file/download/Notes/foo.png)');
  assert.strictEqual(rel('![](assets/img/图 1.png)'), '![](/api/file/download/assets/img/%E5%9B%BE%201.png)');
  // 已是 URL / 绝对链接 / data URI 不动
  assert.strictEqual(rel('![](/api/file/download/Notes/foo.png)'), '![](/api/file/download/Notes/foo.png)');
  assert.strictEqual(rel('![](https://example.com/a.png)'), '![](https://example.com/a.png)');
  assert.strictEqual(rel('![](http://cdn.com/b.png)'), '![](http://cdn.com/b.png)');
  assert.strictEqual(rel('![](data:image/png;base64,abc)'), '![](data:image/png;base64,abc)');
  assert.strictEqual(rel('![](//cdn.com/a.png)'), '![](//cdn.com/a.png)');
  assert.strictEqual(rel('![](/absolute/root.png)'), '![](/absolute/root.png)');
  // 带 title 保留
  assert.strictEqual(rel('![alt](Notes/foo.png "title")'), '![alt](/api/file/download/Notes/foo.png "title")');

  // 保存：下载 URL → 相对路径（含 query、带 origin）
  assert.strictEqual(save('![](/api/file/download/Notes/foo.png?preview=true)'), '![](Notes/foo.png)');
  assert.strictEqual(save('![](http://localhost:8000/api/file/download/assets/img/%E5%9B%BE%201.png)'), '![](assets/img/图 1.png)');
  // 相对路径保存不动
  assert.strictEqual(save('![](Notes/rel.png)'), '![](Notes/rel.png)');
  assert.strictEqual(save('![](https://example.com/a.png)'), '![](https://example.com/a.png)');

  // 往返
  assert.strictEqual(save(rel('![](Notes/图.png)')), '![](Notes/图.png)');

  // 混合行只转图片
  assert.strictEqual(
    rel('文本 ![](a.png) 和 [链接](b.png)'),
    '文本 ![](/api/file/download/a.png) 和 [链接](b.png)');

  // 代码块内部图片不转换
  var code = '```{r}\n# ![](Notes/foo.png)\n1+1\n```';
  assert.strictEqual(rel(code), '```r\n# %%RMD<<r||>>%%\n# ![](Notes/foo.png)\n1+1\n```');
})();
console.log('Task6 image path transform tests passed');

