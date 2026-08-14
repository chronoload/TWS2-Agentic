(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();
  } else {
    root.discoverUtils = factory();
    root.fuzzyMatch = factory().fuzzyMatch;
    root.highlightHtml = factory().highlightHtml;
    root.rankAndGroup = factory().rankAndGroup;
    root.createMRU = factory().createMRU;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  /**
   * discover-utils —— 指令面板（发现面板）纯函数工具箱
   *
   * langdriven 设计：搜索/排序/分组/最近使用 均为纯函数或可注入副作用的封装，
   * node 可单测；app.js 仅做 UI 组装。
   *
   * - fuzzyMatch(query, text)   → {score, ranges} | null（子串 / 跨词顺序，词长≥2）
   * - highlightHtml(text, ranges) → 命中子串 <mark> 高亮（HTML 转义安全）
   * - rankAndGroup(items, query) → [{group, items:[{item, score, ranges}]}]
   * - createMRU({storage,key,max}) → {add, list, clear}（LRU 去重置顶）
   */

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /**
   * 模糊匹配：仅"连续子串"命中（与原来的 includes 语义一致，附带 ranges）。
   * 返回 {score, ranges} 或 null。词长 < 2 直接返回 null（单字符过宽）。
   * 注意：不做跨词顺序匹配——会过宽把不相干结果带进来（用户否决）。
   */
  function fuzzyMatch(query, text) {
    const q = String(query == null ? '' : query).toLowerCase().trim();
    const t = String(text == null ? '' : text).toLowerCase();
    if (!q || q.length < 2) return null;
    const idx = t.indexOf(q);
    if (idx >= 0) {
      return { score: 100 - idx, ranges: [{ start: idx, end: idx + q.length }] };
    }
    return null;
  }

  /**
   * 高亮：ranges 排序合并后 <mark> 包裹；非命中区转义，命中区原文（保留语义）。
   */
  function highlightHtml(text, ranges) {
    const src = String(text == null ? '' : text);
    if (!ranges || !ranges.length) return escapeHtml(src);
    const rs = ranges.slice().sort((a, b) => a.start - b.start);
    const merged = [];
    for (const r of rs) {
      const lastM = merged[merged.length - 1];
      if (lastM && r.start <= lastM.end) lastM.end = Math.max(lastM.end, r.end);
      else merged.push({ start: r.start, end: r.end });
    }
    let out = '';
    let pos = 0;
    for (const r of merged) {
      const s = Math.max(0, Math.min(r.start, src.length));
      const e = Math.max(s, Math.min(r.end, src.length));
      out += escapeHtml(src.slice(pos, s));
      out += '<mark>' + escapeHtml(src.slice(s, e)) + '</mark>';
      pos = e;
    }
    out += escapeHtml(src.slice(pos));
    return out;
  }

  /**
   * 搜索 + 排序 + 分组。
   * items: [{name, description, group}]；query 空 → 原序分组（不丢项）。
   * 非空 query → 名字命中优先（+50），描述命中次之；无命中丢弃。
   */
  function rankAndGroup(items, query) {
    const q = String(query == null ? '' : query).trim();
    const scored = [];
    if (!q) {
      for (const it of items) scored.push({ item: it, score: 0, ranges: null });
    } else {
      for (const it of items) {
        const mName = fuzzyMatch(q, it.name);
        if (mName) { scored.push({ item: it, score: mName.score + 50, ranges: mName.ranges }); continue; }
        const mDesc = fuzzyMatch(q, it.description);
        if (mDesc) scored.push({ item: it, score: mDesc.score, ranges: mDesc.ranges });
      }
      scored.sort((a, b) => b.score - a.score);
    }
    const map = new Map();
    for (const s of scored) {
      const g = s.item.group || '其他';
      if (!map.has(g)) map.set(g, []);
      map.get(g).push(s);
    }
    return Array.from(map.entries()).map(([group, items2]) => ({ group: group, items: items2 }));
  }

  /**
   * 最近使用（LRU）：storage 可注入（localStorage / 内存对象），add 去重置顶 + 上限截断。
   */
  function createMRU(opts) {
    opts = opts || {};
    const storage = opts.storage || null;
    const key = opts.key || 'discover-mru';
    const max = opts.max || 20;
    let cache = [];
    if (storage) {
      try {
        const raw = storage.getItem(key);
        cache = raw ? JSON.parse(raw) : [];
        if (!Array.isArray(cache)) cache = [];
      } catch (e) { cache = []; }
    }
    function persist() {
      if (!storage) return;
      try { storage.setItem(key, JSON.stringify(cache)); } catch (e) { /* 隐私模式降级 */ }
    }
    function add(entry) {
      cache = [entry].concat(cache.filter((x) => x !== entry)).slice(0, max);
      persist();
    }
    function list() { return cache.slice(); }
    function clear() { cache = []; persist(); }
    return { add: add, list: list, clear: clear };
  }

  return { fuzzyMatch, highlightHtml, rankAndGroup, createMRU };
});
