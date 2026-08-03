(function (global) {
  'use strict';

  var ENGINE_HLJS = {
    r: 'r', R: 'r', rs: 'rust',
    python: 'python', py: 'python',
    bash: 'bash', sh: 'bash', shell: 'bash',
    sql: 'sql',
    js: 'javascript', javascript: 'javascript',
    ts: 'typescript', typescript: 'typescript',
    tex: 'latex', latex: 'latex',
    c: 'c', cpp: 'cpp', 'c++': 'cpp',
    java: 'java', go: 'go', rs: 'rust',
    json: 'json', yaml: 'yaml', yml: 'yaml',
    html: 'xml', xml: 'xml', md: 'markdown'
  };

  function engineToHljs(engine) {
    if (!engine) return 'plaintext';
    return ENGINE_HLJS[String(engine).toLowerCase()] || 'plaintext';
  }

  function parseChunkHeader(info) {
    if (!info) return null;
    var s = String(info).trim();
    if (s.charAt(0) !== '{' || s.charAt(s.length - 1) !== '}') return null;
    s = s.slice(1, -1).trim();
    if (!s) return null;
    var m = /^(\S+)\s*([\s\S]*)$/.exec(s);
    var engine = m ? m[1] : s;
    var rest = m ? m[2] : '';
    rest = rest.trim();
    var name = '';
    var opts = '';
    if (engine.charAt(engine.length - 1) === ',') {
      engine = engine.slice(0, -1);
      name = '';
      opts = rest;
    } else if (rest) {
      var c = rest.indexOf(',');
      if (c === -1) {
        if (rest.indexOf('=') !== -1) { opts = rest; }
        else { name = rest; }
      } else {
        name = rest.slice(0, c).trim();
        opts = rest.slice(c + 1).trim();
      }
    }
    return { engine: engine, name: name, opts: opts };
  }

  function parseRmdMeta(line) {
    var m = /^# %%RMD<<(.+)>>%%$/.exec(String(line).trim());
    if (!m) return null;
    var parts = m[1].split('|');
    return {
      engine: (parts[0] || '').trim(),
      name: (parts[1] || '').trim(),
      opts: (parts[2] || '').trim()
    };
  }

  function buildMetaLine(meta) {
    return '# %%RMD<<' + meta.engine + '|' + meta.name + '|' + meta.opts + '>>%%';
  }

  function buildHeaderInfo(meta) {
    var h = '{' + meta.engine;
    if (meta.name) {
      h += ' ' + meta.name;
      if (meta.opts) h += ', ' + meta.opts;
    } else if (meta.opts) {
      h += ', ' + meta.opts;
    }
    h += '}';
    return h;
  }

  var FENCE_RE = /^(\s*)(`{3,})(.*)$/;

  function rmToEditorSource(md) {
    if (md == null) return '';
    var lines = String(md).split('\n');
    var out = [];
    var i = 0, n = lines.length;
    while (i < n) {
      var line = lines[i];
      var fm = FENCE_RE.exec(line);
      if (fm) {
        var ticks = fm[2];
        var info = fm[3].trim();
        var header = parseChunkHeader(info);
        if (header) {
          out.push(fm[1] + ticks + header.engine);
          out.push(fm[1] + buildMetaLine(header));
          i++;
          while (i < n) {
            var bl = lines[i];
            var bfm = FENCE_RE.exec(bl);
            if (bfm && bfm[2].length === ticks.length && bfm[3].trim() === '') {
              out.push(bl);
              i++;
              break;
            }
            out.push(bl);
            i++;
          }
          continue;
        }
      }
      out.push(line);
      i++;
    }
    return out.join('\n');
  }

  function editorSourceToRmd(text) {
    if (text == null) return '';
    var lines = String(text).split('\n');
    var out = [];
    var i = 0, n = lines.length;
    while (i < n) {
      var line = lines[i];
      var fm = FENCE_RE.exec(line);
      if (fm) {
        var ticks = fm[2];
        var info = fm[3].trim();
        // scan the WHOLE code-block body for the meta line (it is not
        // necessarily the line right after the fence: vditor may insert
        // a blank line or reorder on a wysiwyg<->IR<->md switch)
        var meta = null, metaIdx = -1;
        for (var j = i + 1; j < n; j++) {
          var cj = FENCE_RE.exec(lines[j]);
          if (cj && cj[2].length === ticks.length && cj[3].trim() === '') break;
          var m = parseRmdMeta(lines[j]);
          if (m && m.engine === info) { meta = m; metaIdx = j; break; }
        }
        if (meta) {
          out.push(fm[1] + ticks + buildHeaderInfo(meta));
          for (var k = i + 1; k < n; k++) {
            var bk = lines[k];
            var bkf = FENCE_RE.exec(bk);
            if (bkf && bkf[2].length === ticks.length && bkf[3].trim() === '') {
              out.push(bk);
              i = k + 1;
              break;
            }
            if (k === metaIdx) continue; // drop the machine-readable meta line
            out.push(bk);
          }
          continue;
        }
      }
      out.push(line);
      i++;
    }
    return out.join('\n');
  }

  // NOTE: no DOM header bar is injected into vditor's editable area (that
  // corrupted content and broke editing on wysiwyg<->IR mode switch).
  // The chunk header is shown via CSS `pre.rmd-chunk::before` (read from
  // data-rmd-meta) and edited via a double-click handler whose popup
  // lives on document.body (outside vditor, so it is never serialized).

  function openChunkEditor(meta, code) {
    var existing = document.getElementById('rmdChunkEditor');
    if (existing) existing.parentNode.removeChild(existing);
    var overlay = document.createElement('div');
    overlay.className = 'rmd-chunk-editor-overlay';
    overlay.id = 'rmdChunkEditor';
    var box = document.createElement('div');
    box.className = 'rmd-chunk-editor-box';
    var h = document.createElement('h4'); h.textContent = '编辑 Rmd 代码块';
    box.appendChild(h);
    var nameLabel = document.createElement('label'); nameLabel.textContent = '块名';
    var nameInput = document.createElement('input'); nameInput.type = 'text'; nameInput.value = meta.name || '';
    box.appendChild(nameLabel); box.appendChild(nameInput);
    var optsLabel = document.createElement('label'); optsLabel.textContent = '选项 (如 echo=FALSE, fig.height=4)';
    var optsInput = document.createElement('textarea'); optsInput.value = meta.opts || '';
    box.appendChild(optsLabel); box.appendChild(optsInput);
    var saveBtn = document.createElement('button'); saveBtn.type = 'button'; saveBtn.textContent = '保存';
    var cancelBtn = document.createElement('button'); cancelBtn.type = 'button'; cancelBtn.textContent = '取消';
    box.appendChild(saveBtn); box.appendChild(cancelBtn);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    function close() { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); }
    cancelBtn.addEventListener('click', close);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    saveBtn.addEventListener('click', function () {
      var newMeta = { engine: meta.engine, name: nameInput.value.trim(), opts: optsInput.value.trim() };
      applyMetaToEditor(newMeta, code);
      close();
    });
  }

  function rewriteMetaInLines(lines, newMeta, code) {
    var target = code.__rmdMetaText;
    for (var i = 0; i < lines.length; i++) {
      var fm = FENCE_RE.exec(lines[i]);
      if (fm && fm[3].trim() !== '') {
        // scan the whole block for the meta line (may not be i+1 after a re-render)
        for (var j = i + 1; j < lines.length; j++) {
          var bfm = FENCE_RE.exec(lines[j]);
          if (bfm && bfm[2].length === fm[2].length && bfm[3].trim() === '') break;
          if (target && lines[j].trim() === target.trim()) {
            lines[j] = buildMetaLine(newMeta);
            return lines.join('\n');
          }
        }
      }
    }
    return lines.join('\n');
  }

  function applyMetaToEditor(newMeta, code) {
    var vd = (code && code.__rmdVditor) || (global.state && global.state.vditor);
    if (!vd) return;
    var full = vd.getValue();
    var updated = rewriteMetaInLines(full.split('\n'), newMeta, code);
    vd.setValue(updated);
    setTimeout(function () { enhanceRmdChunks(global.document); }, 60);
  }

  function enhanceRmdChunks(root, vditor) {
    if (!root || !root.querySelectorAll) return;
    var blocks = root.querySelectorAll('pre > code');
    for (var b = 0; b < blocks.length; b++) {
      var code = blocks[b];
      var pre = code.parentElement;
      if (!pre) continue;
      if (vditor) code.__rmdVditor = vditor;
      var text = code.textContent || '';
      // scan the WHOLE code text for the meta line (may not be the
      // first line after vditor re-flows / inserts a blank line)
      var meta = null, firstLine = '';
      var tlines = text.split('\n');
      for (var ti = 0; ti < tlines.length; ti++) {
        var m = parseRmdMeta(tlines[ti]);
        if (m) { meta = m; firstLine = tlines[ti]; break; }
      }
      if (!meta) continue;
      code.__rmdMetaText = firstLine;
      if (pre.classList.contains('rmd-chunk')) {
        pre.setAttribute('data-engine', meta.engine);
        pre.setAttribute('data-name', meta.name);
        pre.setAttribute('data-opts', meta.opts);
        pre.setAttribute('data-rmd-meta',
          meta.engine + (meta.name ? ' · ' + meta.name : '') + (meta.opts ? ' · ' + meta.opts : ''));
        continue;
      }
      pre.classList.add('rmd-chunk');
      pre.setAttribute('data-engine', meta.engine);
      pre.setAttribute('data-name', meta.name);
      pre.setAttribute('data-opts', meta.opts);
      pre.setAttribute('data-rmd-meta',
        meta.engine + (meta.name ? ' · ' + meta.name : '') + (meta.opts ? ' · ' + meta.opts : ''));
    }
  }

  var _editTriggerInited = false;
  function initChunkEditTrigger() {
    if (_editTriggerInited) return;
    if (!global.document || !global.document.addEventListener) return;
    _editTriggerInited = true;
    global.document.addEventListener('dblclick', function (e) {
      // contenteditable 中 dblclick 的目标常是文本节点，需上溯到元素
      var node = e.target;
      if (node && node.nodeType === 3) node = node.parentElement;
      if (!node || !node.closest) return;
      // 双击目标可能在 pre.rmd-chunk 内，也可能在 vditor 的
      // 兄弟预览节点（vditor-wysiwyg__preview）内 —— 两种都处理。
      var hit = node.closest('pre.rmd-chunk, [data-type="code-block"]');
      var pre = null;
      if (hit) {
        pre = (hit.classList && hit.classList.contains('rmd-chunk'))
          ? hit
          : (hit.querySelector ? hit.querySelector('pre.rmd-chunk') : null);
      }
      if (!pre) return;
      var code = pre.querySelector('code');
      if (!code) return;
      var firstLine = (code.textContent || '').split('\n')[0] || '';
      var meta = parseRmdMeta(firstLine);
      if (meta) openChunkEditor(meta, code);
    });
  }

  var _enhancing = false;
  function initRmdChunksWatcher(container, vditor) {
    if (!global.MutationObserver || !container) return;
    if (container.__rmdWatcherInited) return;
    container.__rmdWatcherInited = true;
    if (vditor) container.__rmdVditor = vditor;
    var observer = new MutationObserver(function () {
      if (_enhancing) return;
      _enhancing = true;
      try { enhanceRmdChunks(container, container.__rmdVditor); }
      finally { setTimeout(function () { _enhancing = false; }, 0); }
    });
    observer.observe(container, { childList: true, subtree: true });
    initChunkEditTrigger();
  }

  global.enhanceRmdChunks = enhanceRmdChunks;
  global.initRmdChunksWatcher = initRmdChunksWatcher;
  global.initChunkEditTrigger = initChunkEditTrigger;
  global.openChunkEditor = openChunkEditor;
  global.applyMetaToEditor = applyMetaToEditor;

  global.engineToHljs = engineToHljs;
  global.parseChunkHeader = parseChunkHeader;
  global.parseRmdMeta = parseRmdMeta;
  global.rmdToEditorSource = rmToEditorSource;
  global.editorSourceToRmd = editorSourceToRmd;

})(typeof window !== 'undefined' ? window : this);
