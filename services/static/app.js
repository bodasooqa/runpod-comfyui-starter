/* Shared utilities for all service pages. */

let selectedPresets = [];

function pollStatus(baseUrl, taskId, resultEl, progressEl, fillEl, textEl, btn, btnLabel) {
  fetch(baseUrl + '/status/' + taskId)
    .then(r => r.json())
    .then(data => {
      if (data.status === 'completed' || data.status === 'error') {
        resultEl.textContent = data.message;
        if (progressEl) progressEl.style.display = 'none';
        if (btn) { btn.disabled = false; btn.textContent = btnLabel; }
      } else if (data.status === 'running') {
        const pct = data.progress || 0;
        if (fillEl) fillEl.style.width = pct + '%';
        if (textEl) {
          let msg = data.message || 'Downloading...';
          if (data.total_files && data.current_file !== undefined) {
            const short = (data.current_filename || '').length > 50
              ? data.current_filename.substring(0, 47) + '...'
              : (data.current_filename || '');
            msg = 'File ' + data.current_file + '/' + data.total_files;
            if (short) msg += ': ' + short;
            msg += ' (' + Math.round(pct) + '%)';
          }
          textEl.textContent = msg;
        }
        resultEl.textContent = data.message || 'Downloading...';
        setTimeout(() => pollStatus(baseUrl, taskId, resultEl, progressEl, fillEl, textEl, btn, btnLabel), 500);
      } else {
        resultEl.textContent = 'Unknown status: ' + data.message;
        if (progressEl) progressEl.style.display = 'none';
        if (btn) { btn.disabled = false; btn.textContent = btnLabel; }
      }
    })
    .catch(err => {
      resultEl.textContent = 'Status check error: ' + err.message;
      if (progressEl) progressEl.style.display = 'none';
      if (btn) { btn.disabled = false; btn.textContent = btnLabel; }
    });
}

function submitAsync(formEl, resultEl, progressEl, fillEl, textEl, btn, btnLabel, baseUrl) {
  formEl.addEventListener('submit', function(e) {
    e.preventDefault();
    if (progressEl) progressEl.style.display = 'block';
    resultEl.textContent = '';
    btn.disabled = true;
    btn.textContent = 'Downloading...';

    fetch(formEl.action, { method: 'POST', body: new FormData(formEl) })
      .then(r => r.json())
      .then(data => {
        if (data.task_id) {
          resultEl.textContent = data.message;
          pollStatus(baseUrl, data.task_id, resultEl, progressEl, fillEl, textEl, btn, btnLabel);
        } else {
          resultEl.textContent = data.message;
          if (progressEl) progressEl.style.display = 'none';
          btn.disabled = false;
          btn.textContent = btnLabel;
        }
      })
      .catch(err => {
        resultEl.textContent = 'Error: ' + err.message;
        if (progressEl) progressEl.style.display = 'none';
        btn.disabled = false;
        btn.textContent = btnLabel;
      });
  });
}

/* --- Presets page --- */

function togglePreset(pid) {
  const card = document.querySelector('[data-preset="' + pid + '"]');
  if (!card) return;
  const idx = selectedPresets.indexOf(pid);
  if (idx >= 0) {
    selectedPresets.splice(idx, 1);
    card.classList.remove('selected');
  } else {
    selectedPresets.push(pid);
    card.classList.add('selected');
  }
  const btn = document.getElementById('download-presets-btn');
  if (btn) {
    btn.disabled = selectedPresets.length === 0;
    btn.textContent = selectedPresets.length > 0
      ? 'Download selected (' + selectedPresets.length + ')'
      : 'Download selected';
  }
}

function downloadPresets() {
  if (selectedPresets.length === 0) return;
  const resultEl = document.getElementById('preset-result');
  const progressEl = document.getElementById('preset-progress');
  const fillEl = document.getElementById('preset-progress-fill');
  const textEl = document.getElementById('preset-progress-text');
  const btn = document.getElementById('download-presets-btn');

  if (progressEl) progressEl.style.display = 'block';
  resultEl.textContent = '';
  btn.disabled = true;
  btn.textContent = 'Downloading...';

  const fd = new FormData();
  fd.append('presets', selectedPresets.join(','));

  fetch('/presets/download', { method: 'POST', body: fd })
    .then(r => r.json())
    .then(data => {
      if (data.task_id) {
        resultEl.textContent = data.message;
        pollStatus('/presets', data.task_id, resultEl, progressEl, fillEl, textEl, btn, 'Download selected');
      } else {
        resultEl.textContent = data.message;
        if (progressEl) progressEl.style.display = 'none';
        btn.disabled = false;
        btn.textContent = 'Download selected';
      }
    })
    .catch(err => {
      resultEl.textContent = 'Error: ' + err.message;
      if (progressEl) progressEl.style.display = 'none';
      btn.disabled = false;
      btn.textContent = 'Download selected';
    });
}

/* --- Models page: tab switching --- */

function switchHFMethod(method) {
  document.querySelectorAll('.hf-method-tab').forEach(t => t.classList.remove('active'));
  const tab = document.querySelector('[data-hf-method="' + method + '"]');
  if (tab) tab.classList.add('active');
  const urlForm = document.getElementById('hf-url-form');
  const repoForm = document.getElementById('hf-repo-form');
  if (method === 'url') {
    if (urlForm) urlForm.style.display = 'block';
    if (repoForm) repoForm.style.display = 'none';
  } else {
    if (urlForm) urlForm.style.display = 'none';
    if (repoForm) repoForm.style.display = 'block';
  }
}
