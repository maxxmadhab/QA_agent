// Toggle finding detail rows
document.querySelectorAll('.finding-row').forEach(row => {
  row.addEventListener('click', () => {
    const detail = row.querySelector('.finding-detail');
    if (detail) detail.style.display = detail.style.display === 'none' ? '' : 'none';
  });
});

// Re-run with same config: pre-fill form on index page
(function () {
  const configEl = document.getElementById('session-config-data');
  if (!configEl) return;
  const config = JSON.parse(configEl.textContent);
  document.getElementById('rerun-btn').addEventListener('click', e => {
    e.preventDefault();
    if (config.urls && config.urls.length) {
      sessionStorage.setItem('qa_rerun_config', JSON.stringify(config));
      window.location.href = '/';
    }
  });
}());

// Trigger AI Narrative Analysis for the current session
(function () {
  const btn = document.getElementById('run-analysis-btn');
  if (!btn) return;

  btn.addEventListener('click', async function () {
    const domain = btn.getAttribute('data-domain') || '';
    const sessionId = btn.getAttribute('data-session-id') || '';
    if (!domain || !sessionId) {
      alert('Missing domain or session ID for AI analysis.');
      return;
    }

    btn.disabled = true;
    btn.textContent = '⏳ Analyzing report with OmniKey AI...';

    try {
      const res = await fetch(`/api/session/${encodeURIComponent(domain)}/${encodeURIComponent(sessionId)}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: 'omnikey' })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to analyze session report');
      }
      // Reload page to display generated analysis
      window.location.reload();
    } catch (err) {
      alert(`AI Analysis Error: ${err.message}`);
      btn.disabled = false;
      btn.textContent = '⚡ Generate AI Analysis with OmniKey';
    }
  });
}());

// Export / Print report to PDF
(function () {
  const exportBtn = document.getElementById('export-pdf-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', function () {
      window.print();
    });
  }
}());


