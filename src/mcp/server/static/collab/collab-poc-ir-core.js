(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.CollabIrCore = factory();
  }
}(typeof globalThis === 'object' ? globalThis : this, function () {
  function simpleDiff(before, after) {
    let prefix = 0;
    const limit = Math.min(before.length, after.length);
    while (prefix < limit && before[prefix] === after[prefix]) prefix++;

    let suffix = 0;
    while (
      suffix < before.length - prefix &&
      suffix < after.length - prefix &&
      before[before.length - suffix - 1] === after[after.length - suffix - 1]
    ) suffix++;

    return {
      pos: prefix,
      deleteText: before.slice(prefix, before.length - suffix),
      insertText: after.slice(prefix, after.length - suffix),
    };
  }

  function applyTextPatch(text, patch) {
    if (patch.pos < 0 || patch.pos > text.length) {
      throw new RangeError('patch position out of bounds');
    }
    if (text.slice(patch.pos, patch.pos + patch.deleteText.length) !== patch.deleteText) {
      throw new Error('patch base does not match text');
    }
    return text.slice(0, patch.pos) + patch.insertText +
      text.slice(patch.pos + patch.deleteText.length);
  }

  function transformPosition(position, patch) {
    const start = patch.pos;
    const end = start + patch.deleteText.length;
    const delta = patch.insertText.length - patch.deleteText.length;
    if (position < start) return position;
    if (position > end) return position + delta;
    return start + patch.insertText.length;
  }

  function transformSelection(selection, patch) {
    return {
      anchor: Math.max(0, transformPosition(selection.anchor, patch)),
      head: Math.max(0, transformPosition(selection.head, patch)),
    };
  }

  function mergePatches(patches) {
    if (!patches || patches.length === 0) return null;
    if (patches.length === 1) return patches[0];
    // The browser layer can only safely coalesce patches with a known base.
    // Disjoint remote events are recalculated from the current Loro text there.
    return null;
  }

  return {
    simpleDiff,
    applyTextPatch,
    transformPosition,
    transformSelection,
    mergePatches,
  };
}));
