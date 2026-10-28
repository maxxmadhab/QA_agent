/* QA Agent – Non-Developer Quick Test Wizard */
'use strict';

document.addEventListener('DOMContentLoaded', () => {
  const urlInput = document.getElementById('quick_url');
  const instrInput = document.getElementById('quick_instructions');
  const charCountEl = document.getElementById('char-count');
  const errorEl = document.getElementById('quick-error');
  const authCheckbox = document.getElementById('auth_enabled');
  const authFields = document.getElementById('auth-fields');
  const togglePassBtn = document.getElementById('toggle-pass-visibility');
  const passInput = document.getElementById('quick_auth_pass');

  const stepDescribe = document.getElementById('quick-step-describe');
  const stepReview = document.getElementById('quick-step-review');
  const stepNode1 = document.getElementById('step-node-1');
  const stepNode2 = document.getElementById('step-node-2');
  const stepNode3 = document.getElementById('step-node-3');

  const btnToReview = document.getElementById('btn-to-review');
  const btnBackToDescribe = document.getElementById('btn-back-to-describe');
  const btnRun = document.getElementById('btn-run-quick-test');

  // Character counter
  instrInput.addEventListener('input', () => {
    charCountEl.textContent = instrInput.value.length;
  });

  // Example pills
  document.querySelectorAll('.example-pill-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      instrInput.value = btn.getAttribute('data-text');
      charCountEl.textContent = instrInput.value.length;
      instrInput.focus();
    });
  });

  // Auth toggle
  authCheckbox.addEventListener('change', () => {
    authFields.style.display = authCheckbox.checked ? 'block' : 'none';
  });

  // Password visibility toggle
  togglePassBtn.addEventListener('click', () => {
    if (passInput.type === 'password') {
      passInput.type = 'text';
      togglePassBtn.textContent = 'Hide';
    } else {
      passInput.type = 'password';
      togglePassBtn.textContent = 'Show';
    }
  });

  // Step 1 -> Step 2 (Review)
  btnToReview.addEventListener('click', () => {
    errorEl.style.display = 'none';
    let url = urlInput.value.trim();

    if (!url) {
      errorEl.textContent = 'Please enter a website URL to test.';
      errorEl.style.display = 'block';
      urlInput.focus();
      return;
    }

    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'https://' + url;
      urlInput.value = url;
    }

    try {
      new URL(url);
    } catch (_) {
      errorEl.textContent = 'Please enter a valid website URL (e.g. https://example.com).';
      errorEl.style.display = 'block';
      urlInput.focus();
      return;
    }

    // Populate Review Step
    document.getElementById('review-url').textContent = url;
    const instructions = instrInput.value.trim();
    document.getElementById('review-instructions').textContent =
      instructions || 'Standard comprehensive quality, user flow, and accessibility audit.';

    const authActive = authCheckbox.checked;
    if (authActive) {
      const authUrl = document.getElementById('quick_auth_url').value.trim() || url;
      const user = document.getElementById('quick_auth_user').value.trim() || 'Specified in form';
      document.getElementById('review-auth').innerHTML =
        `Enabled for <strong>${escapeHtml(authUrl)}</strong> &bull; User: <code>${escapeHtml(user)}</code> &bull; Password: <code>••••••••</code> (redacted)`;
    } else {
      document.getElementById('review-auth').textContent = 'None (Public pages only)';
    }

    // Transition view
    stepDescribe.style.display = 'none';
    stepReview.style.display = 'block';
    stepNode1.classList.remove('active');
    stepNode1.classList.add('completed');
    stepNode2.classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // Step 2 -> Step 1 (Back)
  btnBackToDescribe.addEventListener('click', () => {
    stepReview.style.display = 'none';
    stepDescribe.style.display = 'block';
    stepNode2.classList.remove('active');
    stepNode1.classList.remove('completed');
    stepNode1.classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  // Run Test
  btnRun.addEventListener('click', async () => {
    btnRun.disabled = true;
    btnRun.textContent = 'Starting Test Run…';

    const url = urlInput.value.trim();
    const instructions = instrInput.value.trim();
    const payload = {
      urls: [url],
      mode: 'focused',
      instructions: instructions || undefined,
      output_formats: ['console', 'markdown', 'json', 'pdf'],
      test_keyboard: true,
      test_mouse: true,
      test_forms: true,
      test_accessibility: true,
      test_console_errors: true,
      test_network_errors: true,
      test_wcag_compliance: false,
      screenshots: {
        enabled: true,
        on_error: true,
        full_page: true
      }
    };

    if (authCheckbox.checked) {
      payload.auth = {
        auth_url: document.getElementById('quick_auth_url').value.trim() || url,
        username: document.getElementById('quick_auth_user').value.trim() || undefined,
        password: passInput.value || undefined
      };
    }

    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to start quick test');

      stepNode2.classList.remove('active');
      stepNode2.classList.add('completed');
      stepNode3.classList.add('active');
      window.location.href = `/run/${data.job_id}`;
    } catch (err) {
      alert(`Error starting test: ${err.message}`);
      btnRun.disabled = false;
      btnRun.textContent = 'Run Test →';
    }
  });

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
