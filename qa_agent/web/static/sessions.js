/* QA Agent - Sessions Archive Client */
'use strict';

(function () {
  const container = document.getElementById('sessions-container');
  const activeJobsContainer = document.getElementById('active-jobs-container');
  const domainFiltersContainer = document.getElementById('domain-filters');
  const searchInput = document.getElementById('search');

  let allSessions = [];
  let selectedDomain = 'all';

  const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info'];

  function formatDuration(secs) {
    if (!secs && secs !== 0) return '—';
    const s = Math.round(secs);
    if (s < 60) return `${s}s`;
    const mins = Math.floor(s / 60);
    const rem = s % 60;
    return `${mins}m ${rem}s`;
  }

  function formatDate(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (_) {
      return iso;
    }
  }

  function renderSeverityBadges(s) {
    const total = s.total_findings || 0;
    if (total === 0) {
      return `
        <span class="badge" style="background: #E8F5E9; color: #2E7D32;">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
          Clean Test (0 Issues)
        </span>
      `;
    }

    const pills = [];
    const counts = s.findings_by_severity || {};

    for (const sev of SEVERITY_ORDER) {
      const count = counts[sev] || 0;
      if (count > 0) {
        const label = sev.charAt(0).toUpperCase() + sev.slice(1);
        pills.push(`<span class="badge badge-${sev}">${count} ${label}</span>`);
      }
    }

    if (!pills.length) {
      pills.push(`<span class="badge badge-medium">${total} Issue${total !== 1 ? 's' : ''}</span>`);
    }

    return pills.join(' ');
  }

  function renderStatusBadge(s) {
    const total = s.total_findings || 0;
    const critical = (s.findings_by_severity && s.findings_by_severity.critical) || 0;
    const high = (s.findings_by_severity && s.findings_by_severity.high) || 0;

    if (total === 0) {
      return `<span class="badge" style="background: #E8F5E9; color: #2E7D32;">Passed</span>`;
    } else if (critical > 0 || high > 0) {
      return `<span class="badge badge-critical">${critical + high} Blocker${critical + high !== 1 ? 's' : ''}</span>`;
    } else {
      return `<span class="badge badge-medium">${total} Issue${total !== 1 ? 's' : ''}</span>`;
    }
  }

  function renderDomainFilters() {
    if (!domainFiltersContainer || !allSessions.length) {
      if (domainFiltersContainer) domainFiltersContainer.style.display = 'none';
      return;
    }

    const domainCounts = {};
    allSessions.forEach(s => {
      const d = s.domain || 'unknown';
      domainCounts[d] = (domainCounts[d] || 0) + 1;
    });

    const domains = Object.keys(domainCounts).sort();
    if (domains.length <= 1) {
      domainFiltersContainer.style.display = 'none';
      return;
    }

    domainFiltersContainer.style.display = 'flex';
    let html = `
      <button type="button" class="domain-pill-btn ${selectedDomain === 'all' ? 'active' : ''}" data-domain="all">
        All Domains <span class="domain-pill-count">${allSessions.length}</span>
      </button>
    `;

    domains.forEach(d => {
      html += `
        <button type="button" class="domain-pill-btn ${selectedDomain === d ? 'active' : ''}" data-domain="${escapeHtml(d)}">
          ${escapeHtml(d)} <span class="domain-pill-count">${domainCounts[d]}</span>
        </button>
      `;
    });

    domainFiltersContainer.innerHTML = html;

    domainFiltersContainer.querySelectorAll('.domain-pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        selectedDomain = btn.dataset.domain;
        domainFiltersContainer.querySelectorAll('.domain-pill-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        applyFilters();
      });
    });
  }

  function renderSessionsList(sessions) {
    if (!sessions.length) {
      container.innerHTML = `
        <div class="card p-5 text-center" style="background: var(--surface);">
          <div style="font-family: var(--font-serif); font-size: 1.5rem; color: var(--ink); margin-bottom: 0.5rem;">
            No test sessions found
          </div>
          <p class="text-muted" style="margin-bottom: 1.5rem;">No past test records match your filter criteria.</p>
          <a href="/quick-test" class="btn btn-primary" style="border-radius: var(--radius-pill); padding: 0.6rem 1.5rem;">
            Run a New Test
          </a>
        </div>
      `;
      return;
    }

    let html = '';
    sessions.forEach(s => {
      const targetUrl = (s.urls && s.urls.length) ? s.urls[0] : `https://${s.domain}`;
      const urlCountText = (s.urls && s.urls.length > 1) ? ` +${s.urls.length - 1} more` : '';
      const pages = s.pages_tested || (s.urls ? s.urls.length : 1);

      html += `
        <article class="session-card-clean" data-domain="${escapeHtml(s.domain)}" data-id="${escapeHtml(s.session_id)}">
          <div class="session-card-top">
            <div class="session-target-info">
              <div class="session-domain-badge-wrap">
                <span class="session-domain-heading">${escapeHtml(s.domain)}</span>
                <span class="session-id-pill">#${escapeHtml(s.session_id)}</span>
              </div>
              <div class="session-url-preview" title="${escapeHtml(targetUrl)}">
                ${escapeHtml(targetUrl)}${urlCountText}
              </div>
            </div>

            <div class="session-card-actions">
              ${renderStatusBadge(s)}
              <a href="/session/${encodeURIComponent(s.domain)}/${encodeURIComponent(s.session_id)}" class="session-view-report-btn">
                View Report &rarr;
              </a>
            </div>
          </div>

          <div class="session-card-divider"></div>

          <div class="session-card-bottom">
            <div class="session-meta-chips">
              <span class="session-chip" title="Start Time">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                  <line x1="16" y1="2" x2="16" y2="6"></line>
                  <line x1="8" y1="2" x2="8" y2="6"></line>
                  <line x1="3" y1="10" x2="21" y2="10"></line>
                </svg>
                ${formatDate(s.start_time)}
              </span>

              <span class="session-chip" title="Execution Duration">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <polyline points="12 6 12 12 16 14"></polyline>
                </svg>
                ${formatDuration(s.duration_seconds)}
              </span>

              <span class="session-chip" title="Pages Audited">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                </svg>
                ${pages} page${pages !== 1 ? 's' : ''}
              </span>
            </div>

            <div class="session-findings-summary">
              ${renderSeverityBadges(s)}
            </div>
          </div>
        </article>
      `;
    });

    container.innerHTML = html;
  }

  function applyFilters() {
    const q = (searchInput ? searchInput.value.trim().toLowerCase() : '');

    let filtered = allSessions.slice();

    if (selectedDomain !== 'all') {
      filtered = filtered.filter(s => s.domain === selectedDomain);
    }

    if (q) {
      filtered = filtered.filter(s => {
        const domainMatch = s.domain && s.domain.toLowerCase().includes(q);
        const idMatch = s.session_id && s.session_id.toLowerCase().includes(q);
        const urlMatch = s.urls && s.urls.some(u => u.toLowerCase().includes(q));
        return domainMatch || idMatch || urlMatch;
      });
    }

    renderSessionsList(filtered);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Active Live Jobs ─────────────────────────────────────────────────────────
  function renderActiveJobs(jobs) {
    if (!activeJobsContainer) return;
    const active = (jobs || []).filter(j => !['completed', 'stopped', 'failed'].includes(j.status));

    if (!active.length) {
      activeJobsContainer.innerHTML = '';
      return;
    }

    let html = '';
    active.forEach(j => {
      const domain = j.domain || 'In progress';
      html += `
        <div class="active-job-card">
          <div class="flex items-center">
            <span class="active-job-pulse"></span>
            <div>
              <strong>Test Run #${escapeHtml(j.job_id)}</strong> on <code>${escapeHtml(domain)}</code>
              <span class="text-muted" style="margin-left: 0.5rem; font-size: 0.85rem;">
                (${j.pages_tested || 0} page(s) tested, ${j.total_findings || 0} finding(s))
              </span>
            </div>
          </div>
          <a href="/run/${encodeURIComponent(j.job_id)}" class="btn btn-primary btn-sm" style="border-radius: var(--radius-pill); padding: 0.35rem 1rem;">
            View Live Run &rarr;
          </a>
        </div>
      `;
    });

    activeJobsContainer.innerHTML = html;
  }

  function loadActiveJobs() {
    fetch('/api/jobs')
      .then(r => r.json())
      .then(data => renderActiveJobs(data.jobs || []))
      .catch(() => {});
  }

  // ── Load Sessions from API ───────────────────────────────────────────────────
  function loadSessions() {
    fetch('/api/sessions?limit=200')
      .then(r => r.json())
      .then(data => {
        allSessions = data.sessions || [];
        renderDomainFilters();
        applyFilters();
      })
      .catch(() => {
        container.innerHTML = `
          <div class="alert alert-error">
            Failed to load test sessions from server.
          </div>
        `;
      });
  }

  loadSessions();
  loadActiveJobs();

  const jobsPoll = setInterval(loadActiveJobs, 4000);
  window.addEventListener('beforeunload', () => clearInterval(jobsPoll));

  // ── Search Input ────────────────────────────────────────────────────────────
  if (searchInput) {
    let debounceTimer;
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(applyFilters, 200);
    });
  }
})();
