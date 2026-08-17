const assert = require('assert');
const core = require('./collab-poc-ir-core.js');

assert.deepStrictEqual(core.simpleDiff('abc', 'aXbc'), {
  pos: 1, deleteText: '', insertText: 'X',
});
assert.deepStrictEqual(core.simpleDiff('abc', 'ac'), {
  pos: 1, deleteText: 'b', insertText: '',
});
assert.strictEqual(core.applyTextPatch('abcdef', {
  pos: 2, deleteText: 'cd', insertText: 'XY',
}), 'abXYef');
assert.deepStrictEqual(core.transformSelection({anchor: 6, head: 6}, {
  pos: 2, deleteText: 'cd', insertText: 'XYZ',
}), {anchor: 7, head: 7});
assert.deepStrictEqual(core.transformSelection({anchor: 3, head: 3}, {
  pos: 3, deleteText: '', insertText: 'X',
}), {anchor: 4, head: 4});
assert.strictEqual(core.mergePatches([
  {pos: 1, deleteText: '', insertText: 'X'},
  {pos: 2, deleteText: '', insertText: 'Y'},
]), null);

console.log('IR core tests passed');
