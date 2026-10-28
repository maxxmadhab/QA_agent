/* QA Agent - Developer Studio Client Logic */
'use strict';

(function () {
  const form = document.getElementById('studio-form');
  if (!form) return;

  const stepper = document.getElementById('studio-stepper');
  const stepItems = stepper.querySelectorAll('.vert-step-item');
  const panels = form.querySelectorAll('.step-panel');
  const stepOrder = ['basic', 'categories', 'browser', 'auth', 'advanced', 'review'];

  let currentStep = 'basic';

  function goToStep(stepName) {
    if (!stepOrder.includes(stepName)) return;
    currentStep = stepName;

    // Update panel visibility
    panels.forEach(p => {
      p.style.display = p.id === `panel-${stepName}` ? 'block' : 'none';
      if (p.id === `panel-${stepName}`) p.classList.add('active');
      else p.classList.remove('active');
    });

    // Update stepper styling
    const curIdx = stepOrder.indexOf(stepName);
    stepItems.forEach(item => {
      const itemStep = item.dataset.step;
      const itemIdx = stepOrder.indexOf(itemStep);
      item.classList.remove('active', 'completed');

      if (itemIdx === curIdx) {
        item.classList.add('active');
      } else if (itemIdx < curIdx) {
        item.classList.add('completed');
      }
    });

    if (stepName === 'review') {
      renderReviewSummary();
    }

    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // Bind step clicks
  stepItems.forEach(item => {
    item.addEventListener('click', () => {
      goToStep(item.dataset.step);
    });
  });

  // Bind Next / Prev buttons
  form.querySelectorAll('.next-step-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      goToStep(btn.dataset.target);
    });
  });

  form.querySelectorAll('.prev-step-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      goToStep(btn.dataset.target);
    });
  });

  // ── URL line counter ──────────────────────────────────────────────────────────
  const urlsTextarea = document.getElementById('studio-urls');
  const urlCounter = document.getElementById('url-counter');

  function updateUrlCounter() {
    if (!urlsTextarea || !urlCounter) return;
    const lines = urlsTextarea.value.split('\n').map(l => l.trim()).filter(Boolean);
    const count = lines.length;
    urlCounter.textContent = `${count} URL${count === 1 ? '' : 's'}`;
  }

  if (urlsTextarea) {
    urlsTextarea.addEventListener('input', updateUrlCounter);
    updateUrlCounter();
  }

  // ── Mode selection radio cards ────────────────────────────────────────────────
  const modeRadios = form.querySelectorAll('input[name="mode"]');
  const exploreOptions = document.getElementById('explore-options');

  modeRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      document.querySelectorAll('.radio-card').forEach(c => c.classList.remove('active'));
      const parentLabel = radio.closest('.radio-card');
      if (parentLabel) parentLabel.classList.add('active');

      if (exploreOptions) {
        exploreOptions.style.display = radio.value === 'explore' ? 'block' : 'none';
      }
    });
  });

  // ── Screenshot dependency logic ──────────────────────────────────────────────
  const ssEnabled = document.getElementById('ss_enabled');
  const ssOnError = document.getElementById('ss_on_error');
  const ssOnInteract = document.getElementById('ss_on_interaction');
  const ssFullPage = document.getElementById('ss_full_page');

  function syncScreenshots() {
    if (!ssEnabled) return;
    const enabled = ssEnabled.checked;
    const onError = ssOnError ? ssOnError.checked : false;

    if (ssOnError) ssOnError.disabled = !enabled;
    if (ssFullPage) ssFullPage.disabled = !enabled;
    if (ssOnInteract) ssOnInteract.disabled = !enabled || !onError;

    if (!enabled) {
      if (ssOnError) ssOnError.checked = false;
      if (ssFullPage) ssFullPage.checked = false;
      if (ssOnInteract) ssOnInteract.checked = false;
    }
    if (!onError && ssOnInteract) {
      ssOnInteract.checked = false;
    }
  }

  if (ssEnabled) {
    ssEnabled.addEventListener('change', syncScreenshots);
    if (ssOnError) ssOnError.addEventListener('change', syncScreenshots);
    syncScreenshots();
  }

  // ── LLM Provider & Models ─────────────────────────────────────────────────────
  const MODELS = {
    anthropic: [
      { value: 'claude-sonnet-4-6', label: 'claude-sonnet-4-6 (Default)' },
      { value: 'claude-opus-4-6', label: 'claude-opus-4-6' },
      { value: 'claude-haiku-4-5-20251001', label: 'claude-haiku-4-5-20251001' },
    ],
    openai: [
      { value: 'gpt-4o', label: 'gpt-4o (Default)' },
      { value: 'gpt-4o-mini', label: 'gpt-4o-mini' },
      { value: 'gpt-4-turbo', label: 'gpt-4-turbo' },
      { value: 'o1', label: 'o1' },
      { value: 'o1-mini', label: 'o1-mini' },
    ],
    omnikey: [
      { value: '', label: 'Auto (from OmniKey /models)' },
      { value: 'gpt-4o', label: 'gpt-4o' },
      { value: 'claude-3-5-sonnet', label: 'claude-3-5-sonnet' },
    ],
  };

  const KEY_HINTS = {
    anthropic: 'Requires <code>ANTHROPIC_API_KEY</code> environment variable',
    openai: 'Requires <code>OPENAI_API_KEY</code> environment variable',
    omnikey: 'Requires <code>OMNIKEY_API_KEY</code> (in .env)',
  };

  const llmProvider = document.getElementById('llm_provider');
  const aiModel = document.getElementById('ai_model');
  const llmHint = document.getElementById('llm_key_hint');

  function updateLLMOptions() {
    if (!llmProvider || !aiModel) return;
    const provider = llmProvider.value;
    const models = MODELS[provider] || [];

    aiModel.innerHTML = models
      .map(m => `<option value="${m.value}">${m.label}</option>`)
      .join('');

    if (llmHint) llmHint.innerHTML = KEY_HINTS[provider] || '';
  }

  if (llmProvider) {
    llmProvider.addEventListener('change', updateLLMOptions);
    updateLLMOptions();
  }

  // ── Auth Section Toggle ───────────────────────────────────────────────────────
  const authSelect = document.getElementById('auth-type-select');
  const authFormFields = document.getElementById('auth-form-fields');
  const authBasicFields = document.getElementById('auth-basic-fields');
  const authCookieFields = document.getElementById('auth-cookie-fields');
  const authHeaderFields = document.getElementById('auth-header-fields');

  function updateAuthPanels() {
    if (!authSelect) return;
    const val = authSelect.value;
    if (authFormFields) authFormFields.style.display = val === 'form' ? 'block' : 'none';
    if (authBasicFields) authBasicFields.style.display = val === 'basic' ? 'block' : 'none';
    if (authCookieFields) authCookieFields.style.display = val === 'cookie' ? 'block' : 'none';
    if (authHeaderFields) authHeaderFields.style.display = val === 'header' ? 'block' : 'none';
  }

  if (authSelect) {
    authSelect.addEventListener('change', updateAuthPanels);
    updateAuthPanels();
  }

  // ── Collect Form Data into payload ────────────────────────────────────────────
  function collectFormData() {
    const fd = new FormData(form);

    const urlsRaw = (fd.get('urls') || '').split('\n').map(u => u.trim()).filter(Boolean);
    const mode = fd.get('mode') || 'focused';

    const outputFormats = fd.getAll('output_formats');

    const browsers = [];
    if (fd.get('browser_chromium')) browsers.push('chromium');
    if (fd.get('browser_firefox')) browsers.push('firefox');
    if (fd.get('browser_webkit')) browsers.push('webkit');

    const authType = fd.get('auth_type') || 'none';
    let authConfig = null;

    if (authType === 'form') {
      authConfig = {
        type: 'form',
        login_url: fd.get('login_url') || '',
        username: fd.get('auth_username') || '',
        password: fd.get('auth_password') || '',
        username_selector: fd.get('username_selector') || 'input[name="user"]',
        password_selector: fd.get('password_selector') || 'input[type="password"]',
        submit_selector: fd.get('submit_selector') || 'button[type="submit"]',
      };
    } else if (authType === 'basic') {
      authConfig = {
        type: 'basic',
        username: fd.get('basic_username') || '',
        password: fd.get('basic_password') || '',
      };
    } else if (authType === 'cookie') {
      authConfig = {
        type: 'cookie',
        name: fd.get('cookie_name') || '',
        value: fd.get('cookie_value') || '',
        domain: fd.get('cookie_domain') || '',
      };
    } else if (authType === 'header') {
      authConfig = {
        type: 'header',
        name: fd.get('header_name') || 'Authorization',
        value: fd.get('header_value') || '',
      };
    }

    const payload = {
      urls: urlsRaw,
      mode,
      browsers: browsers.length ? browsers : ['chromium'],
      output_formats: outputFormats.length ? outputFormats : ['console', 'markdown', 'json'],
      output_dir: fd.get('output_dir') || './qa-agent-output',
      headless: !!fd.get('headless'),
      workers: parseInt(fd.get('workers') || '1', 10),
      viewport_width: parseInt(fd.get('viewport_width') || '1280', 10),
      viewport_height: parseInt(fd.get('viewport_height') || '720', 10),
      timeout: parseInt(fd.get('timeout') || '30000', 10),
      max_depth: parseInt(fd.get('max_depth') || '3', 10),
      max_pages: parseInt(fd.get('max_pages') || '50', 10),
      max_interactions_per_page: parseInt(fd.get('max_interactions_per_page') || '50', 10),
      test_keyboard: !!fd.get('test_keyboard'),
      test_mouse: !!fd.get('test_mouse'),
      test_forms: !!fd.get('test_forms'),
      test_accessibility: !!fd.get('test_accessibility'),
      test_console_errors: !!fd.get('test_console_errors'),
      test_network_errors: !!fd.get('test_network_errors'),
      test_wcag_compliance: !!fd.get('test_wcag_compliance'),
      same_domain_only: !!fd.get('same_domain_only'),
      ignore_patterns: (fd.get('ignore_patterns') || '').split('\n').map(s => s.trim()).filter(Boolean),
      instructions: fd.get('instructions') || null,
      ai_model: fd.get('ai_model') || 'claude-sonnet-4-6',
      use_plan_cache: !!fd.get('use_plan_cache'),
      screenshots: {
        enabled: !!fd.get('screenshots_enabled'),
        on_error: !!fd.get('screenshots_on_error'),
        on_interaction: !!fd.get('screenshots_on_interaction'),
        full_page: !!fd.get('screenshots_full_page'),
      },
      recording: {
        enabled: !!fd.get('recording_enabled'),
      },
    };

    if (authConfig) {
      payload.auth = authConfig;
    }

    return payload;
  }

  // ── Render Review Summary ─────────────────────────────────────────────────────
  function renderReviewSummary() {
    const summaryEl = document.getElementById('review-summary');
    if (!summaryEl) return;

    const data = collectFormData();
    const categories = [];
    if (data.test_keyboard) categories.push('Keyboard');
    if (data.test_mouse) categories.push('Mouse');
    if (data.test_forms) categories.push('Forms');
    if (data.test_accessibility) categories.push('Accessibility');
    if (data.test_wcag_compliance) categories.push('WCAG Compliance');
    if (data.test_console_errors) categories.push('Console Errors');
    if (data.test_network_errors) categories.push('Network Errors');

    summaryEl.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.25rem;">
        <div>
          <div class="text-muted" style="font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem;">Target URLs (${data.urls.length})</div>
          <div class="text-mono" style="font-size: 0.85rem; max-height: 80px; overflow-y: auto; background: var(--surface); padding: 0.5rem; border-radius: 4px; border: 1px solid var(--border);">
            ${data.urls.length ? data.urls.map(u => `<div>${escapeHtml(u)}</div>`).join('') : '<span class="text-orange">No URLs entered!</span>'}
          </div>
        </div>
        <div>
          <div class="text-muted" style="font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem;">Execution Mode</div>
          <div style="font-weight: 600; font-size: 0.95rem;">${data.mode === 'explore' ? 'Explore (Crawl & Discover)' : 'Focused (Exact URLs)'}</div>
          <div class="text-muted" style="font-size: 0.82rem; margin-top: 0.25rem;">Browsers: ${data.browsers.join(', ')} &bull; Concurrency: ${data.workers} worker(s)</div>
        </div>
      </div>

      <div style="margin-top: 1.25rem; padding-top: 1.25rem; border-top: 1px solid var(--border); display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.25rem;">
        <div>
          <div class="text-muted" style="font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem;">Active Test Categories (${categories.length})</div>
          <div style="font-size: 0.88rem; display: flex; flex-wrap: wrap; gap: 0.35rem;">
            ${categories.map(c => `<span class="badge" style="background: var(--surface-active); color: var(--text); font-weight: 500;">${c}</span>`).join('')}
          </div>
        </div>
        <div>
          <div class="text-muted" style="font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem;">Outputs &amp; Artifacts</div>
          <div style="font-size: 0.85rem;">Formats: <strong>${data.output_formats.join(', ')}</strong></div>
          <div class="text-muted" style="font-size: 0.82rem; margin-top: 0.2rem;">Screenshots: ${data.screenshots.enabled ? 'Enabled' : 'Disabled'} &bull; Output: <code>${escapeHtml(data.output_dir)}</code></div>
        </div>
      </div>

      ${data.instructions ? `
        <div style="margin-top: 1.25rem; padding-top: 1.25rem; border-top: 1px solid var(--border);">
          <div class="text-muted" style="font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.35rem;">Agentic Instructions (${data.ai_model})</div>
          <div style="font-size: 0.85rem; font-style: italic; background: var(--surface); padding: 0.5rem 0.75rem; border-radius: 4px; border: 1px solid var(--border);">
            "${escapeHtml(data.instructions)}"
          </div>
        </div>
      ` : ''}
    `;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Form Submission ───────────────────────────────────────────────────────────
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const submitBtn = document.getElementById('studio-submit-btn');
    const errBox = document.getElementById('form-error');

    if (errBox) errBox.style.display = 'none';

    const payload = collectFormData();
    if (!payload.urls.length) {
      if (errBox) {
        errBox.textContent = 'Please enter at least one URL in the Basic Configuration tab.';
        errBox.style.display = 'block';
      }
      goToStep('basic');
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Starting Test…';

    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to start test job');
      }

      window.location.href = `/run/${data.job_id}`;
    } catch (err) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Run Test →';
      if (errBox) {
        errBox.textContent = err.message;
        errBox.style.display = 'block';
      }
    }
  });

  // ── Presets & Config Import/Export ────────────────────────────────────────────
  const PRESET_KEY = 'qa_studio_presets_v1';

  function getPresets() {
    try {
      return JSON.parse(localStorage.getItem(PRESET_KEY)) || {};
    } catch (_) {
      return {};
    }
  }

  function savePresets(obj) {
    localStorage.setItem(PRESET_KEY, JSON.stringify(obj));
  }

  function populatePresets() {
    const select = document.getElementById('preset-select');
    if (!select) return;
    const presets = getPresets();
    select.innerHTML = '<option value="">Load saved preset...</option>';
    for (const name of Object.keys(presets)) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    }
  }

  populatePresets();

  document.getElementById('save-preset-btn')?.addEventListener('click', () => {
    const name = prompt('Preset name:');
    if (!name) return;
    const presets = getPresets();
    presets[name] = collectFormData();
    savePresets(presets);
    populatePresets();
    alert(`Preset "${name}" saved.`);
  });

  document.getElementById('export-config-btn')?.addEventListener('click', () => {
    const cfg = collectFormData();
    const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'qa-agent-studio-config.json';
    a.click();
    URL.revokeObjectURL(a.href);
  });
})();
