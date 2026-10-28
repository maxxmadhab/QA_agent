/* QA Agent - Live Test Monitor Client */
'use strict';

(function () {
  const container = document.getElementById('run-container');
  if (!container) return;

  const JOB_ID = container.dataset.jobId;
  const terminalContent = document.getElementById('terminal-content');
  const stopBtn = document.getElementById('stop-btn');
  const statPages = document.getElementById('stat-pages');
  const statFindings = document.getElementById('stat-findings');
  const statElapsed = document.getElementById('stat-elapsed');
  const completeBanner = document.getElementById('complete-banner');
  const errorBanner = document.getElementById('error-banner');
  const stoppedBanner = document.getElementById('stopped-banner');
  const monitorHeading = document.getElementById('monitor-heading');
  const monitorSubheading = document.getElementById('monitor-subheading');

  const progressCircleBar = document.getElementById('progress-circle-bar');
  const progressPctText = document.getElementById('progress-pct-text');
  const currentUrlDisplay = document.getElementById('current-url-display');
  const previewImg = document.getElementById('live-screenshot-img');
  const previewPlaceholder = document.getElementById('preview-placeholder');
  const previewTimestamp = document.getElementById('preview-timestamp');

  // Stages
  const stageInit = document.getElementById('stage-init');
  const stageRunning = document.getElementById('stage-running');
  const stageAnalyzing = document.getElementById('stage-analyzing');
  const stageReport = document.getElementById('stage-report');

  let findingCount = 0;
  let pageCount = 0;
  let currentPct = 15;
  const CIRCUMFERENCE = 238.76;

  function setProgress(pct) {
    currentPct = Math.min(100, Math.max(0, pct));
    if (progressCircleBar) {
      const offset = CIRCUMFERENCE * (1 - currentPct / 100);
      progressCircleBar.style.strokeDashoffset = offset;
    }
    if (progressPctText) {
      progressPctText.textContent = `${Math.round(currentPct)}%`;
    }
  }

  function setStage(stage) {
    [stageInit, stageRunning, stageAnalyzing, stageReport].forEach(el => {
      if (el) el.classList.remove('active', 'completed');
    });

    if (stage === 'init') {
      if (stageInit) stageInit.classList.add('active');
    } else if (stage === 'running') {
      if (stageInit) stageInit.classList.add('completed');
      if (stageRunning) stageRunning.classList.add('active');
    } else if (stage === 'analyzing') {
      if (stageInit) stageInit.classList.add('completed');
      if (stageRunning) stageRunning.classList.add('completed');
      if (stageAnalyzing) stageAnalyzing.classList.add('active');
    } else if (stage === 'report' || stage === 'completed') {
      if (stageInit) stageInit.classList.add('completed');
      if (stageRunning) stageRunning.classList.add('completed');
      if (stageAnalyzing) stageAnalyzing.classList.add('completed');
      if (stageReport) {
        if (stage === 'completed') stageReport.classList.add('completed');
        else stageReport.classList.add('active');
      }
    }
  }

  // Set initial state
  setProgress(15);
  setStage('running');

  // ── Stop button ─────────────────────────────────────────────────────────────
  if (stopBtn) {
    stopBtn.addEventListener('click', () => {
      stopBtn.disabled = true;
      stopBtn.textContent = 'Stopping…';
      fetch(`/api/stop/${JOB_ID}`, { method: 'POST' }).catch(() => {});
    });
  }

  // ── Clear logs ──────────────────────────────────────────────────────────────
  document.getElementById('clear-log-btn')?.addEventListener('click', () => {
    if (terminalContent) terminalContent.innerHTML = '';
  });

  // ── Elapsed timer ───────────────────────────────────────────────────────────
  let startTime = null;
  let elapsedInterval = null;

  function startTimer() {
    if (elapsedInterval) return;
    startTime = Date.now();
    elapsedInterval = setInterval(() => {
      const secs = Math.floor((Date.now() - startTime) / 1000);
      const m = Math.floor(secs / 60);
      const s = secs % 60;
      if (statElapsed) {
        statElapsed.textContent = `${m}:${String(s).padStart(2, '0')}`;
      }
    }, 1000);
  }

  function stopTimer() {
    if (elapsedInterval) {
      clearInterval(elapsedInterval);
      elapsedInterval = null;
    }
  }

  // ── Log formatter ───────────────────────────────────────────────────────────
  function formatLogMessage(raw) {
    const timeMatch = raw.match(/^\[([0-9:]{5,8})\]/);
    let timeStr = '';
    let body = raw;

    if (timeMatch) {
      timeStr = timeMatch[1];
      body = raw.slice(timeMatch[0].length).trim();
    } else {
      const now = new Date();
      timeStr = now.toTimeString().split(' ')[0];
    }

    let levelSpan = '';
    const levelMatch = body.match(/^\[(INFO|TEST|PASS|WARN|WARNING|FAIL|ERROR|FINDING)\]/i);
    if (levelMatch) {
      const tag = levelMatch[1].toUpperCase();
      let tagClass = 'log-level-info';
      if (tag === 'TEST') tagClass = 'log-level-test';
      else if (tag === 'PASS') tagClass = 'log-level-pass';
      else if (tag === 'WARN' || tag === 'WARNING') tagClass = 'log-level-warn';
      else if (tag === 'FAIL' || tag === 'ERROR') tagClass = 'log-level-error';
      else if (tag === 'FINDING') tagClass = 'log-level-warn';

      levelSpan = `<span class="${tagClass}">[${tag}]</span> `;
      body = body.slice(levelMatch[0].length).trim();
    }

    return `<span class="log-time">[${timeStr}]</span> ${levelSpan}${escapeHtml(body)}`;
  }

  function appendLog(raw) {
    if (!terminalContent) return;
    const line = document.createElement('div');
    line.className = 'log-line';
    line.innerHTML = formatLogMessage(raw);
    terminalContent.appendChild(line);
    terminalContent.scrollTop = terminalContent.scrollHeight;

    // Intelligent stage advancement based on log message keywords
    const lower = raw.toLowerCase();
    if (lower.includes('generating') || lower.includes('report') || lower.includes('markdown')) {
      setStage('report');
      setProgress(Math.max(currentPct, 92));
    } else if (lower.includes('analyzing') || lower.includes('summary') || lower.includes('ai planner')) {
      setStage('analyzing');
      setProgress(Math.max(currentPct, 80));
    } else if (lower.includes('navigating') || lower.includes('testing') || lower.includes('worker')) {
      setStage('running');
      setProgress(Math.min(75, Math.max(currentPct, 35) + 3));
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── SSE Stream ──────────────────────────────────────────────────────────────
  function startStream() {
    const es = new EventSource(`/api/stream/${JOB_ID}`);
    startTimer();

    es.addEventListener('log', e => {
      try {
        const data = JSON.parse(e.data);
        appendLog(data.message || '');
      } catch (_) {}
    });

    es.addEventListener('progress', e => {
      try {
        const data = JSON.parse(e.data);
        pageCount++;
        if (statPages) statPages.textContent = pageCount;
        if (data.url && currentUrlDisplay) {
          currentUrlDisplay.textContent = data.url;
        }
        appendLog(data.message || `Testing ${data.url}`);
        setProgress(Math.min(85, currentPct + 10));
      } catch (_) {}
    });

    es.addEventListener('finding', e => {
      try {
        const data = JSON.parse(e.data);
        findingCount++;
        if (statFindings) statFindings.textContent = findingCount;
        appendLog(`[${data.severity.toUpperCase()}] ${data.title}`);
      } catch (_) {}
    });

    es.addEventListener('complete', e => {
      try {
        const data = JSON.parse(e.data);
        es.close();
        stopTimer();
        handleCompletion(data);
      } catch (_) {}
    });

    es.addEventListener('error', e => {
      if (e.data) {
        try {
          const data = JSON.parse(e.data);
          es.close();
          stopTimer();
          handleError(data.message || 'Test execution failure');
        } catch (_) {}
      }
    });

    es.onerror = () => {
      es.close();
      stopTimer();
      // Poll fallback
      fetch(`/api/status/${JOB_ID}`)
        .then(r => r.json())
        .then(d => {
          if (['completed', 'stopped'].includes(d.status)) {
            handleCompletion(d);
          } else if (d.status === 'failed') {
            handleError(d.error || 'Execution failed');
          }
        })
        .catch(() => {});
    };
  }

  function handleCompletion(data) {
    const status = data.status || 'completed';
    setProgress(100);
    setStage('completed');

    if (stopBtn) stopBtn.style.display = 'none';

    if (status === 'stopped') {
      if (monitorHeading) monitorHeading.textContent = 'Test Stopped';
      if (monitorSubheading) monitorSubheading.textContent = 'Execution was halted by user.';
      if (stoppedBanner) stoppedBanner.style.display = 'block';

      if (data.session_id && data.domain) {
        const link = document.getElementById('stopped-link');
        if (link) {
          link.href = `/session/${data.domain}/${data.session_id}`;
          link.style.display = 'inline-block';
        }
      }
    } else {
      if (monitorHeading) monitorHeading.textContent = 'Test Completed!';
      if (monitorSubheading) monitorSubheading.textContent = 'All test categories and reports have finished.';
      if (completeBanner) completeBanner.style.display = 'block';

      if (data.session_id && data.domain) {
        const sessionUrl = `/session/${data.domain}/${data.session_id}`;
        const link = document.getElementById('session-link');
        if (link) link.href = sessionUrl;

        // Auto-navigate after a short moment if user is watching
        setTimeout(() => {
          window.location.href = sessionUrl;
        }, 1500);
      }
    }
  }

  function handleError(msg) {
    if (stopBtn) stopBtn.style.display = 'none';
    if (monitorHeading) monitorHeading.textContent = 'Execution Failed';
    if (monitorSubheading) monitorSubheading.textContent = 'An error occurred during test execution.';
    if (errorBanner) {
      errorBanner.textContent = `Error: ${msg}`;
      errorBanner.style.display = 'block';
    }
  }

  // Initial check
  fetch(`/api/status/${JOB_ID}`)
    .then(r => r.json())
    .then(d => {
      if (['completed', 'stopped', 'failed'].includes(d.status)) {
        if (d.status === 'failed') handleError(d.error);
        else handleCompletion(d);
      } else {
        startStream();
      }
    })
    .catch(() => {
      startStream();
    });
})();
