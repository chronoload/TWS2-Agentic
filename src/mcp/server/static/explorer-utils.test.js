// explorer-utils TDD 测试
// 运行: node mcp/server/static/explorer-utils.test.js
const assert = require('assert');
const { sortEntries, matchTypeFilter } = require('./explorer-utils.js');

// ── matchTypeFilter ──
const fileMd = { name: 'a.md', is_dir: false, ext: '.md' };
const filePy = { name: 'b.py', is_dir: false, ext: '.py' };
const dir = { name: 'd', is_dir: true, ext: '' };

assert.strictEqual(matchTypeFilter(fileMd, ''), true, '空筛选全部通过');
assert.strictEqual(matchTypeFilter(fileMd, 'all'), true, 'all 全部通过');
assert.strictEqual(matchTypeFilter(dir, 'dir'), true, 'dir 匹配文件夹');
assert.strictEqual(matchTypeFilter(fileMd, 'dir'), false, 'dir 不匹配文件');
assert.strictEqual(matchTypeFilter(fileMd, 'file'), true, 'file 匹配文件');
assert.strictEqual(matchTypeFilter(dir, 'file'), false, 'file 不匹配文件夹');
assert.strictEqual(matchTypeFilter(fileMd, '.md'), true, '.md 匹配 md 文件');
assert.strictEqual(matchTypeFilter(filePy, '.md'), false, '.md 不匹配 py 文件');
assert.strictEqual(matchTypeFilter(fileMd, 'md'), true, '无点扩展名同 .md');
assert.strictEqual(matchTypeFilter(dir, '.md'), false, '目录不匹配扩展名');
assert.strictEqual(matchTypeFilter(fileMd, '.PY'), false, '.PY 不匹配 .md 文件');
assert.strictEqual(matchTypeFilter(filePy, '.PY'), true, '过滤器大小写不敏感：.PY 匹配 .py 文件');

// ── sortEntries 默认 mtime desc ──
const oldFile = { name: 'old.txt', is_dir: false, modified: 100, size: 1 };
const newFile = { name: 'new.txt', is_dir: false, modified: 300, size: 2 };
const dirA = { name: 'aaa', is_dir: true, modified: 50 };
const dirB = { name: 'bbb', is_dir: true, modified: 400 };

let sorted = sortEntries([oldFile, newFile, dirA, dirB]);
assert.strictEqual(sorted[0], dirB, '目录优先，组内 mtime 降序');
assert.strictEqual(sorted[1], dirA, '目录组内第二个为较早目录');
assert.strictEqual(sorted[2], newFile, '文件组内最新在前');
assert.strictEqual(sorted[3], oldFile, '文件组内最旧在后');

// 显式 mtime asc
sorted = sortEntries([newFile, oldFile], 'mtime', 'asc');
assert.strictEqual(sorted[0], oldFile, 'mtime asc 旧文件在前');
assert.strictEqual(sorted[1], newFile, 'mtime asc 新文件在后');

// name 排序行为不变
sorted = sortEntries([{ name: 'z.md', is_dir: false, modified: 1 }, { name: 'a.md', is_dir: false, modified: 2 }], 'name', 'asc');
assert.strictEqual(sorted[0].name, 'a.md', 'name asc 按名称');

// 目录始终排最前（即使 name 反序）
sorted = sortEntries([{ name: 'b.txt', is_dir: false, modified: 1 }, { name: 'a', is_dir: true, modified: 1 }], 'name', 'desc');
assert.strictEqual(sorted[0].is_dir, true, '目录仍在前');
assert.strictEqual(sorted[1].name, 'b.txt', '文件组内 name desc');

console.log('explorer-utils tests passed');
