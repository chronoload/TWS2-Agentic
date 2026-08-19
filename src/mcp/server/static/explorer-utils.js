/* explorer-utils.js —— 文件树/源码浏览器纯函数工具箱（排序 + 类型过滤）
 *
 * 双端模块：浏览器挂 window 全局（sortEntries / matchTypeFilter），
 * node 端 module.exports。风格与 discover-utils.js 一致。
 */
(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();
  } else {
    root.sortEntries = factory().sortEntries;
    root.matchTypeFilter = factory().matchTypeFilter;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // 类型过滤谓词：""|all=全部 / dir=只文件夹 / file=只文件 / .ext|ext=匹配扩展名的文件
  function matchTypeFilter(entry, typeFilter) {
    const tf = (typeFilter || '').toLowerCase();
    if (!tf || tf === 'all') return true;
    if (tf === 'dir') return entry.is_dir;
    if (tf === 'file') return !entry.is_dir;
    const ext = tf.startsWith('.') ? tf : '.' + tf;
    return !entry.is_dir && (entry.ext || '') === ext;
  }

  // 排序（对标 Windows Explorer：目录优先，再按 key + 方向）；默认 mtime
  function sortEntries(entries, sortBy, order) {
    sortBy = sortBy || 'mtime';
    const reverse = (order || 'desc') === 'desc';
    const cmp = (a, b) => {
      let r = 0;
      if (sortBy === 'size') {
        r = (a.size || 0) - (b.size || 0);
      } else if (sortBy === 'mtime' || sortBy === 'modified') {
        r = (a.modified || 0) - (b.modified || 0);
      } else if (sortBy === 'type' || sortBy === 'ext') {
        r = (a.ext || '').localeCompare(b.ext || '');
        if (r === 0) r = a.name.localeCompare(b.name);
      } else {
        r = a.name.localeCompare(b.name);
      }
      return reverse ? -r : r;
    };
    const dirs = entries.filter(e => e.is_dir).sort(cmp);
    const files = entries.filter(e => !e.is_dir).sort(cmp);
    return [...dirs, ...files];
  }

  return { sortEntries: sortEntries, matchTypeFilter: matchTypeFilter };
});
