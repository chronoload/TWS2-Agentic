// ─── Office 文档预览模块 ───────────────────────────
// 使用 vue-office (@js-preview) 在 iframe 中渲染 docx/xlsx/pptx

var _officeCurrentPath = null;

function showOfficeEditor(path) {
  document.getElementById('officeEditorView').style.display = 'flex';
  _officeCurrentPath = path;
  var encoded = path.split('/').map(function(s) { return encodeURIComponent(s); }).join('/');
  var parts = path.split('.');
  var ext = parts.length > 1 ? parts[parts.length - 1].toLowerCase() : '';
  var fname = path.split('/').pop();
  var url = API_BASE + '/static/vue-office/preview.html?url=' + encodeURIComponent(API_BASE + '/api/file/download/' + encoded) + '&ext=' + ext + '&name=' + encodeURIComponent(fname);
  document.getElementById('officeViewerFrame').src = url;
  document.getElementById('officeFileInfo').textContent = path.split('/').pop();
}

function hideOfficeEditor() {
  document.getElementById('officeEditorView').style.display = 'none';
  var frame = document.getElementById('officeViewerFrame');
  if (frame) { frame.src = 'about:blank'; }
  _officeCurrentPath = null;
}

function officeDownload() {
  if (!_officeCurrentPath) return;
  var encoded = _officeCurrentPath.split('/').map(function(s) { return encodeURIComponent(s); }).join('/');
  window.open(API_BASE + '/api/file/download/' + encoded, '_blank');
}

async function officeConvertPdf() {
  if (!_officeCurrentPath) return;
  showToast('正在转换为 PDF...', 'info');
  try {
    var resp = await fetch(API_BASE + '/api/file/convert-to-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: _officeCurrentPath })
    });
    if (resp.ok && resp.headers.get('content-type') && resp.headers.get('content-type').includes('pdf')) {
      var blob = await resp.blob();
      var url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      setTimeout(function() { URL.revokeObjectURL(url); }, 60000);
      showToast('转换完成', 'success');
    } else {
      var text = await resp.text();
      showToast('转换失败: ' + text, 'error');
    }
  } catch (e) {
    showToast('转换失败: ' + e.message, 'error');
  }
}
