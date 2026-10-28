/* QA Agent - Session Report & Gallery Client */
'use strict';

(function () {
  // ── Tab Navigation ────────────────────────────────────────────────────────────
  const tabBtns = document.querySelectorAll('.report-tab-btn');
  const panels = document.querySelectorAll('.report-tab-panel');

  function switchTab(tabName) {
    tabBtns.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    panels.forEach(panel => {
      if (panel.id === `tab-panel-${tabName}`) {
        panel.style.display = 'block';
        panel.classList.add('active');
      } else {
        panel.style.display = 'none';
        panel.classList.remove('active');
      }
    });
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.dataset.tab);
    });
  });

  // "View Details ->" scroll/switch
  document.getElementById('view-details-btn')?.addEventListener('click', (e) => {
    e.preventDefault();
    switchTab('issues');
    document.getElementById('report-details')?.scrollIntoView({ behavior: 'smooth' });
  });

  // ── Issues Severity Filter ───────────────────────────────────────────────────
  const filterBtns = document.querySelectorAll('.issue-filter-btn');
  const findingRows = document.querySelectorAll('.finding-row');

  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const sev = btn.dataset.filter;

      findingRows.forEach(row => {
        if (sev === 'all' || row.dataset.severity === sev) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
      });
    });
  });

  // Expand / collapse finding detail
  findingRows.forEach(row => {
    const titleEl = row.querySelector('.finding-title');
    const detailEl = row.querySelector('.finding-detail');
    if (titleEl && detailEl) {
      titleEl.addEventListener('click', (e) => {
        e.stopPropagation();
        detailEl.style.display = detailEl.style.display === 'none' ? 'block' : 'none';
      });
    }
  });

  // ── Screenshot Lightbox Modal ─────────────────────────────────────────────────
  const lightbox = document.getElementById('lightbox-modal');
  const lightboxImg = document.getElementById('lightbox-img');
  const lightboxClose = document.getElementById('lightbox-close');

  function openLightbox(src) {
    if (!lightbox || !lightboxImg) return;
    lightboxImg.src = src;
    lightbox.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  function closeLightbox() {
    if (!lightbox) return;
    lightbox.classList.remove('active');
    if (lightboxImg) lightboxImg.src = '';
    document.body.style.overflow = '';
  }

  document.querySelectorAll('.gallery-item').forEach(item => {
    item.addEventListener('click', () => {
      const src = item.dataset.src;
      if (src) openLightbox(src);
    });
  });

  if (lightboxClose) {
    lightboxClose.addEventListener('click', closeLightbox);
  }

  if (lightbox) {
    lightbox.addEventListener('click', (e) => {
      if (e.target === lightbox) closeLightbox();
    });
  }

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && lightbox && lightbox.classList.contains('active')) {
      closeLightbox();
    }
  });

  // ── PDF Export Button ─────────────────────────────────────────────────────────
  document.getElementById('export-pdf-btn')?.addEventListener('click', () => {
    window.print();
  });

  // ── AI Analysis Trigger ───────────────────────────────────────────────────────
  const aiBtn = document.getElementById('run-analysis-btn');
  if (aiBtn) {
    aiBtn.addEventListener('click', async () => {
      const domain = aiBtn.dataset.domain;
      const sessionId = aiBtn.dataset.sessionId;
      if (!domain || !sessionId) return;

      aiBtn.disabled = true;
      aiBtn.textContent = '⏳ Analyzing with AI...';

      try {
        const res = await fetch(`/api/session/${encodeURIComponent(domain)}/${encodeURIComponent(sessionId)}/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider: 'anthropic' }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'AI analysis request failed');
        window.location.reload();
      } catch (err) {
        alert(`AI Analysis: ${err.message}`);
        aiBtn.disabled = false;
        aiBtn.textContent = '⚡ Deep Analysis';
      }
    });
  }
})();
