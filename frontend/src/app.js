/**
 * CodeReview AI — Single-Page Application
 * Architecture: Module-based vanilla JS SPA with client-side routing
 * API: FastAPI backend at http://localhost:8000
 */

// ============================================================
//  Configuration
// ============================================================
const API_BASE = 'http://localhost:8000';

// ============================================================
//  Auth State
// ============================================================
const auth = {
  token: localStorage.getItem('cr_token'),
  user: JSON.parse(localStorage.getItem('cr_user') || 'null'),

  setAuth(token, user) {
    this.token = token;
    this.user = user;
    localStorage.setItem('cr_token', token);
    localStorage.setItem('cr_user', JSON.stringify(user));
  },

  logout() {
    this.token = null;
    this.user = null;
    localStorage.removeItem('cr_token');
    localStorage.removeItem('cr_user');
  },

  isAuthenticated() {
    return !!this.token;
  },

  headers() {
    return {
      'Content-Type': 'application/json',
      ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
    };
  },
};

function extractErrorMessage(err, defaultMsg = 'Request failed') {
  if (!err) return defaultMsg;
  if (typeof err === 'string') return err;
  if (err.detail) {
    if (typeof err.detail === 'string') return err.detail;
    if (Array.isArray(err.detail)) {
      return err.detail.map(e => e.msg || e.message || JSON.stringify(e)).join('; ');
    }
    if (typeof err.detail === 'object') return JSON.stringify(err.detail);
  }
  if (err.message) return err.message;
  return defaultMsg;
}

async function apiRequest(method, path, body = null, isFormData = false) {
  const opts = {
    method,
    headers: isFormData
      ? (auth.token ? { Authorization: `Bearer ${auth.token}` } : {})
      : auth.headers(),
  };
  if (body) {
    opts.body = isFormData ? body : JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/login') && !path.startsWith('/register')) {
      auth.logout();
      router.navigate('login');
    }
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(extractErrorMessage(err, `HTTP ${res.status}`));
  }
  if (res.status === 204) return null;
  return res.json();
}

const api = {
  register: (data) => apiRequest('POST', '/register', data),
  login: async (email, password) => {
    const form = new URLSearchParams({ username: email.trim(), password });
    const res = await fetch(`${API_BASE}/login`, {
      method: 'POST', body: form,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(extractErrorMessage(err, 'Invalid email or password.'));
    }
    const data = await res.json();
    auth.token = data.access_token;
    localStorage.setItem('cr_token', data.access_token);
    return data;
  },
  me: () => apiRequest('GET', '/me'),
  listReports: () => apiRequest('GET', '/reports'),
  getReport: (id) => apiRequest('GET', `/report/${id}`),
  getFindings: (id, severity = null) => apiRequest('GET', `/report/${id}/findings${severity ? `?severity=${severity}` : ''}`),
  getRisk: (id) => apiRequest('GET', `/report/${id}/risk`),
  uploadRepo: (file) => {
    const fd = new FormData();
    fd.append('uploaded_file', file);
    return apiRequest('POST', '/upload', fd, true);
  },
  deleteReport: (id) => apiRequest('DELETE', `/report/${id}`),
};

// ============================================================
//  Router
// ============================================================
const router = {
  currentPage: 'home',

  navigate(page, params = {}) {
    if (!auth.isAuthenticated() && !['home', 'login', 'register'].includes(page)) {
      this.navigate('login');
      return;
    }
    this.currentPage = page;
    this.params = params;
    this.render();
    updateNav();
  },

  render() {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const target = document.getElementById(`page-${this.currentPage}`);
    if (target) {
      target.classList.add('active');
      // Trigger page-specific init
      if (this.currentPage === 'dashboard') loadDashboard();
      if (this.currentPage === 'report' && this.params.id) loadReport(this.params.id);
    }
  },
};

// ============================================================
//  Toast Notifications
// ============================================================
function showToast(message, type = 'info', duration = 4000) {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const icons = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };
  const toast = el('div', { class: `toast ${type}` }, [
    el('span', {}, [icons[type] || 'ℹ']),
    el('span', {}, [message]),
  ]);
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), duration);
}

// ============================================================
//  DOM Helpers
// ============================================================
function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  });
  children.forEach(c => {
    if (typeof c === 'string') e.appendChild(document.createTextNode(c));
    else if (c instanceof Node) e.appendChild(c);
  });
  return e;
}

function html(str) {
  const t = document.createElement('template');
  t.innerHTML = str.trim();
  return t.content.firstChild;
}

function $(selector, root = document) { return root.querySelector(selector); }
function $$(selector, root = document) { return [...root.querySelectorAll(selector)]; }

function severityClass(sev) {
  const m = { CRITICAL: 'critical', HIGH: 'high', MEDIUM: 'medium', LOW: 'low', INFO: 'info' };
  return m[(sev || '').toUpperCase()] || 'info';
}

function scoreClass(score) {
  if (score >= 80) return 'score-great';
  if (score >= 65) return 'score-good';
  if (score >= 45) return 'score-warn';
  return 'score-bad';
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function initials(name) {
  if (!name) return '?';
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

// ============================================================
//  Score Ring Component
// ============================================================
function buildScoreRing(score, size = 140, strokeW = 12) {
  const r = (size / 2) - (strokeW / 2);
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = score >= 80 ? '#22c55e' : score >= 65 ? '#06b6d4' : score >= 45 ? '#eab308' : '#ef4444';

  return html(`
    <div class="score-ring-wrapper" style="width:${size}px;height:${size}px">
      <svg class="score-ring-svg" viewBox="0 0 ${size} ${size}">
        <circle class="score-ring-bg" cx="${size/2}" cy="${size/2}" r="${r}" />
        <circle class="score-ring-fg" cx="${size/2}" cy="${size/2}" r="${r}"
          stroke="${color}"
          stroke-dasharray="${circ}"
          stroke-dashoffset="${circ}"
          data-offset="${offset}" />
      </svg>
      <div class="score-ring-text">
        <span class="score-ring-num" style="color:${color}">${Math.round(score)}</span>
        <span class="score-ring-label">/ 100</span>
      </div>
    </div>
  `);
}

function animateRings() {
  $$('.score-ring-fg').forEach(circle => {
    const target = parseFloat(circle.dataset.offset);
    setTimeout(() => { circle.style.strokeDashoffset = target; }, 100);
  });
  $$('.score-bar-fill').forEach(bar => {
    const w = bar.dataset.width;
    setTimeout(() => { bar.style.width = w; }, 100);
  });
}

// ============================================================
//  Nav
// ============================================================
function updateNav() {
  const nav = document.getElementById('app-nav');
  if (!nav) return;
  const linksEl = nav.querySelector('.nav-links');
  const authEl = nav.querySelector('.nav-auth');

  if (auth.isAuthenticated()) {
    linksEl.innerHTML = '';
    [
      ['dashboard', '📊 Dashboard'],
      ['upload', '⬆ Upload'],
    ].forEach(([page, label]) => {
      const a = el('span', {
        class: `nav-link${router.currentPage === page ? ' active' : ''}`,
        onclick: () => router.navigate(page),
      }, [label]);
      linksEl.appendChild(a);
    });

    authEl.innerHTML = '';
    const avatar = el('div', { class: 'nav-avatar' }, [initials(auth.user?.name || auth.user?.email)]);
    const name = el('span', { class: 'nav-user' }, [auth.user?.name || auth.user?.email?.split('@')[0] || 'User']);
    const logoutBtn = el('button', {
      class: 'btn-ghost', onclick: () => {
        auth.logout();
        router.navigate('home');
        showToast('Signed out successfully', 'success');
      },
    }, ['Sign Out']);
    authEl.append(avatar, name, logoutBtn);
  } else {
    linksEl.innerHTML = '';
    authEl.innerHTML = '';
    authEl.append(
      el('button', { class: 'btn-ghost', onclick: () => router.navigate('login') }, ['Sign In']),
      el('button', { class: 'nav-cta', onclick: () => router.navigate('register') }, ['Get Started']),
    );
  }
}

// ============================================================
//  Pages — Home
// ============================================================
function renderHome() {
  return html(`
    <div>
      <!-- Hero -->
      <section class="hero">
        <div class="hero-grid"></div>
        <div class="hero-content">
          <div class="hero-badge">🟢 AI-Powered Code Analysis Platform</div>
          <h1 class="hero-title">
            Review Code Like a<br/>
            <span class="gradient-text">Senior Engineer</span>
          </h1>
          <p class="hero-subtitle">
            7 specialized AI agents analyze your codebase for bugs, security vulnerabilities,
            performance issues, and maintainability—backed by static analysis and ML risk prediction.
          </p>
          <div class="hero-actions">
            <button class="btn-primary" id="hero-cta">
              ⬆ Upload Your Code
            </button>
            <button class="btn-secondary" id="hero-secondary">
              📊 View Demo Report
            </button>
          </div>
          <div class="hero-stats">
            <div class="hero-stat"><div class="hero-stat-num">7</div><div class="hero-stat-label">Specialized AI Agents</div></div>
            <div class="hero-stat"><div class="hero-stat-num">5+</div><div class="hero-stat-label">Analysis Dimensions</div></div>
            <div class="hero-stat"><div class="hero-stat-num">ML</div><div class="hero-stat-label">Risk Prediction</div></div>
            <div class="hero-stat"><div class="hero-stat-num">∞</div><div class="hero-stat-label">Code Languages</div></div>
          </div>
        </div>
      </section>

      <!-- Features -->
      <section class="features-section">
        <div class="container">
          <div class="section-header">
            <h2 class="section-title">Everything You Need for <span class="gradient-text">Complete Code Review</span></h2>
            <p class="section-subtitle">A professional-grade platform that goes beyond syntax checking</p>
          </div>
          <div class="features-grid">
            <div class="feature-card">
              <div class="feature-icon">🐛</div>
              <div class="feature-title">Bug Detection</div>
              <div class="feature-desc">Identifies logic errors, null pointer risks, unhandled edge cases, and common programming mistakes before they reach production.</div>
            </div>
            <div class="feature-card">
              <div class="feature-icon">🔐</div>
              <div class="feature-title">Security Analysis</div>
              <div class="feature-desc">Scans for injection attacks, hardcoded secrets, insecure dependencies, path traversal, and OWASP Top-10 vulnerabilities.</div>
            </div>
            <div class="feature-card">
              <div class="feature-icon">⚡</div>
              <div class="feature-title">Performance Review</div>
              <div class="feature-desc">Detects O(n²) algorithms, memory leaks, inefficient database queries, and unnecessary compute inside hot loops.</div>
            </div>
            <div class="feature-card">
              <div class="feature-icon">🔬</div>
              <div class="feature-title">Static Analysis</div>
              <div class="feature-desc">Cross-language Semgrep scanning (Python, JS, TS, Java, C++), AST structural metrics, Radon cyclomatic complexity, and Bandit security scanning.</div>
            </div>
            <div class="feature-card">
              <div class="feature-icon">🤖</div>
              <div class="feature-title">ML Risk Prediction</div>
              <div class="feature-desc">XGBoost model trained on NASA's KC1 defect dataset predicts defect probability and maintenance risk using 12 code metrics.</div>
            </div>
            <div class="feature-card">
              <div class="feature-icon">📋</div>
              <div class="feature-title">Structured Findings</div>
              <div class="feature-desc">Every issue is a typed, filterable finding with severity, confidence, file location, impact assessment, and actionable recommendations.</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  `);
}

// ============================================================
//  Pages — Auth
// ============================================================
function renderLogin() {
  const card = html(`
    <div class="auth-page">
      <div class="auth-card">
        <div class="auth-card-header">
          <div class="auth-logo">⬡</div>
          <h2 class="auth-title">Welcome Back</h2>
          <p class="auth-subtitle">Sign in to your CodeReview AI account</p>
        </div>
        <form id="login-form">
          <div class="form-group">
            <label class="form-label">Email Address</label>
            <input type="email" id="login-email" class="form-input" placeholder="you@example.com" required />
          </div>
          <div class="form-group">
            <label class="form-label">Password</label>
            <input type="password" id="login-password" class="form-input" placeholder="••••••••" required />
          </div>
          <div class="form-error" id="login-error"></div>
          <button type="submit" class="btn-primary btn-full" id="login-btn">Sign In</button>
        </form>
        <div class="auth-footer">Don't have an account? <a id="go-register">Create one →</a></div>
      </div>
    </div>
  `);

  card.querySelector('#go-register').addEventListener('click', () => router.navigate('register'));
  card.querySelector('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = card.querySelector('#login-email').value.trim();
    const password = card.querySelector('#login-password').value;
    const btn = card.querySelector('#login-btn');
    const errEl = card.querySelector('#login-error');
    errEl.textContent = '';
    btn.textContent = 'Signing in…'; btn.disabled = true;
    try {
      const data = await api.login(email, password);
      // auth.token has been saved, now load the user profile
      const user = await api.me();
      auth.setAuth(data.access_token, user);
      showToast(`Welcome back, ${user.name || user.email}!`, 'success');
      router.navigate('dashboard');
    } catch (err) {
      errEl.textContent = err.message || 'Invalid credentials. Please try again.';
      btn.textContent = 'Sign In'; btn.disabled = false;
    }
  });

  return card;
}

function renderRegister() {
  const card = html(`
    <div class="auth-page">
      <div class="auth-card">
        <div class="auth-card-header">
          <div class="auth-logo">⬡</div>
          <h2 class="auth-title">Create Your Account</h2>
          <p class="auth-subtitle">Start reviewing code with AI in minutes</p>
        </div>
        <form id="register-form">
          <div class="form-group">
            <label class="form-label">Full Name</label>
            <input type="text" id="reg-name" class="form-input" placeholder="Ada Lovelace" required />
          </div>
          <div class="form-group">
            <label class="form-label">Email Address</label>
            <input type="email" id="reg-email" class="form-input" placeholder="ada@example.com" required />
          </div>
          <div class="form-group">
            <label class="form-label">Password</label>
            <input type="password" id="reg-password" class="form-input" placeholder="At least 8 characters" required minlength="8" />
          </div>
          <div class="form-error" id="reg-error"></div>
          <button type="submit" class="btn-primary btn-full" id="reg-btn">Create Account</button>
        </form>
        <div class="auth-footer">Already have an account? <a id="go-login">Sign in →</a></div>
      </div>
    </div>
  `);

  card.querySelector('#go-login').addEventListener('click', () => router.navigate('login'));
  card.querySelector('#register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = card.querySelector('#reg-name').value.trim();
    const email = card.querySelector('#reg-email').value.trim();
    const password = card.querySelector('#reg-password').value;
    const btn = card.querySelector('#reg-btn');
    const errEl = card.querySelector('#reg-error');
    errEl.textContent = '';
    btn.textContent = 'Creating account…'; btn.disabled = true;
    try {
      await api.register({ name, email, password });
      // Automatically log in newly created user and navigate to dashboard
      const data = await api.login(email, password);
      const user = await api.me();
      auth.setAuth(data.access_token, user);
      showToast(`Account created! Welcome, ${user.name || user.email}!`, 'success');
      router.navigate('dashboard');
    } catch (err) {
      errEl.textContent = err.message || 'Registration failed.';
      btn.textContent = 'Create Account'; btn.disabled = false;
    }
  });

  return card;
}

// ============================================================
//  Pages — Dashboard
// ============================================================
function renderDashboard() {
  return html(`
    <div>
      <div class="dashboard-header" style="padding: 2rem 2rem 1.5rem">
        <h1 class="dashboard-title">Your Code Reviews</h1>
        <p class="dashboard-subtitle">Upload a repository ZIP to start an AI-powered review</p>
      </div>
      <div class="container">
        <div class="dashboard-grid" id="stats-grid">
          <div class="stat-card"><div class="stat-label">Total Reviews</div><div class="stat-value skeleton" style="width:60px;height:36px;margin-top:8px"></div></div>
          <div class="stat-card"><div class="stat-label">Avg Score</div><div class="stat-value skeleton" style="width:60px;height:36px;margin-top:8px"></div></div>
          <div class="stat-card"><div class="stat-label">Critical Issues</div><div class="stat-value skeleton" style="width:60px;height:36px;margin-top:8px"></div></div>
          <div class="stat-card"><div class="stat-label">High Issues</div><div class="stat-value skeleton" style="width:60px;height:36px;margin-top:8px"></div></div>
        </div>
        <div id="reports-list"></div>
      </div>
    </div>
  `);
}

async function loadDashboard() {
  try {
    const reports = await api.listReports();
    renderReportsList(reports);
    renderStats(reports);
  } catch (err) {
    showToast('Failed to load reports: ' + err.message, 'error');
    const list = document.getElementById('reports-list');
    if (list) list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠</div><div class="empty-state-title">Could not load reports</div><div class="empty-state-desc">Make sure the API server is running at localhost:8000</div></div>';
  }
}

function renderStats(reports) {
  const grid = document.getElementById('stats-grid');
  if (!grid) return;
  const total = reports.length;
  const avgScore = total ? (reports.reduce((s, r) => s + r.overall_score, 0) / total).toFixed(1) : 0;
  const critTotal = reports.reduce((s, r) => s + (r.critical_count || 0), 0);
  const highTotal = reports.reduce((s, r) => s + (r.high_count || 0), 0);

  grid.innerHTML = `
    <div class="stat-card"><div class="stat-label">Total Reviews</div><div class="stat-value">${total}</div></div>
    <div class="stat-card"><div class="stat-label">Avg Score</div><div class="stat-value">${avgScore}</div><div class="stat-sub">out of 100</div></div>
    <div class="stat-card"><div class="stat-label">Critical Issues</div><div class="stat-value" style="color:var(--sev-critical)">${critTotal}</div></div>
    <div class="stat-card"><div class="stat-label">High Issues</div><div class="stat-value" style="color:var(--sev-high)">${highTotal}</div></div>
  `;
}

function renderReportsList(reports) {
  const container = document.getElementById('reports-list');
  if (!container) return;

  if (!reports.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📂</div>
        <div class="empty-state-title">No reviews yet</div>
        <div class="empty-state-desc">Upload a repository ZIP to start your first AI code review</div>
        <button class="btn-primary" style="margin-top:1.5rem" onclick="window.crNavigate('upload')">Upload Repository</button>
      </div>`;
    return;
  }

  const table = el('div', { class: 'reports-table' });
  table.innerHTML = `
    <div class="table-header">
      <span>Repository</span>
      <span>Date</span>
      <span>Score</span>
      <span>Findings</span>
      <span>Action</span>
    </div>`;

  reports.forEach(r => {
    const total = (r.critical_count || 0) + (r.high_count || 0) + (r.medium_count || 0) + (r.low_count || 0);
    const row = html(`
      <div class="report-row">
        <span class="report-name">📁 Report #${r.id}</span>
        <span class="report-date">${formatDate(r.created_at)}</span>
        <span class="score-chip ${scoreClass(r.overall_score)}">${Math.round(r.overall_score)}</span>
        <span class="report-date">${total} issues</span>
        <button class="btn-ghost" style="padding:6px 12px;font-size:0.8rem">View →</button>
      </div>`);
    row.addEventListener('click', () => router.navigate('report', { id: r.id }));
    table.appendChild(row);
  });
  container.innerHTML = '';
  container.appendChild(table);
}

// ============================================================
//  Pages — Upload
// ============================================================
function renderUpload() {
  const page = html(`
    <div class="upload-section">
      <div class="container" style="max-width:800px">
        <h1 style="font-size:1.75rem;font-weight:700;letter-spacing:-0.03em;margin-bottom:0.5rem">Upload Repository</h1>
        <p style="color:var(--color-text-secondary);margin-bottom:2rem">Upload a ZIP file containing your source code for a comprehensive AI review</p>
        
        <div class="upload-card" id="upload-drop-zone">
          <div class="upload-icon">📦</div>
          <h3 class="upload-title">Drop your ZIP here</h3>
          <p class="upload-desc">or click to select a file from your computer</p>
          <div class="upload-formats">
            <span class="format-badge">.zip</span>
            <span class="format-badge">Python</span>
            <span class="format-badge">JavaScript</span>
            <span class="format-badge">TypeScript</span>
            <span class="format-badge">Java</span>
            <span class="format-badge">C++</span>
          </div>
          <button class="btn-primary" id="upload-btn">Choose File</button>
          <input type="file" id="file-input" class="file-input" accept=".zip" />
        </div>
        
        <div id="upload-info" style="display:none;margin-top:1.5rem">
          <div class="finding-card" style="cursor:default">
            <div style="display:flex;align-items:center;gap:1rem">
              <span style="font-size:1.5rem">📄</span>
              <div style="flex:1">
                <div id="file-name" style="font-weight:600"></div>
                <div id="file-size" style="font-size:0.8rem;color:var(--color-text-muted)"></div>
              </div>
              <button class="btn-primary" id="start-analysis">Analyze Code →</button>
            </div>
          </div>
        </div>

        <div style="margin-top:2rem;padding:1.5rem;background:var(--color-bg-card);border:1px solid var(--color-border);border-radius:var(--radius-lg)">
          <h3 style="font-size:0.9rem;font-weight:600;margin-bottom:1rem">What happens during analysis?</h3>
          <div style="display:flex;flex-direction:column;gap:0.75rem">
            ${[
              ['🔬', 'Static Analysis', 'Semgrep cross-language rules (Python, JS, TS, Java, C++), Radon & Bandit'],
              ['🤖', 'ML Risk Prediction', 'XGBoost defect probability and maintenance risk score'],
              ['🐛', 'Bug & Quality Review', '7 specialized AI agents run sequentially'],
              ['🔐', 'Security Audit', 'OWASP vulnerabilities, hardcoded secrets, injection risks'],
              ['📋', 'Structured Report', 'Deduplicated, prioritized findings with actionable fixes'],
            ].map(([icon, title, desc]) => `
              <div style="display:flex;gap:0.75rem;align-items:flex-start">
                <span style="font-size:1.1rem;flex-shrink:0">${icon}</span>
                <div>
                  <div style="font-size:0.85rem;font-weight:600">${title}</div>
                  <div style="font-size:0.8rem;color:var(--color-text-muted)">${desc}</div>
                </div>
              </div>`).join('')}
          </div>
        </div>
      </div>
    </div>
  `);

  let selectedFile = null;
  const dropZone = page.querySelector('#upload-drop-zone');
  const fileInput = page.querySelector('#file-input');
  const uploadBtn = page.querySelector('#upload-btn');
  const uploadInfo = page.querySelector('#upload-info');
  const startBtn = page.querySelector('#start-analysis');

  const setFile = (file) => {
    if (!file || !file.name.endsWith('.zip')) {
      showToast('Please upload a ZIP file', 'error'); return;
    }
    selectedFile = file;
    page.querySelector('#file-name').textContent = file.name;
    page.querySelector('#file-size').textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
    uploadInfo.style.display = 'block';
  };

  uploadBtn.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => setFile(e.target.files[0]));
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragging'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragging'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault(); dropZone.classList.remove('dragging');
    setFile(e.dataTransfer.files[0]);
  });

  startBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    showAnalyzingOverlay();
    try {
      const result = await api.uploadRepo(selectedFile);
      hideAnalyzingOverlay();
      showToast(`Analysis complete! Score: ${Math.round(result.overall_score)}/100`, 'success');
      router.navigate('report', { id: result.report_id });
    } catch (err) {
      hideAnalyzingOverlay();
      showToast('Analysis failed: ' + err.message, 'error');
    }
  });

  return page;
}

function showAnalyzingOverlay() {
  const agents = [
    { name: 'Static Analysis', badge: 'Semgrep + Bandit + Radon' },
    { name: 'ML Risk Prediction', badge: 'XGBoost · KC1' },
    { name: 'Quality Agent', badge: 'Gemini AI' },
    { name: 'Bug Detection Agent', badge: 'Gemini AI' },
    { name: 'Security Agent', badge: 'Gemini AI' },
    { name: 'Performance Agent', badge: 'Gemini AI' },
    { name: 'Refactoring Agent', badge: 'Gemini AI' },
    { name: 'Documentation Agent', badge: 'Gemini AI' },
    { name: 'Final Report Agent', badge: 'Synthesis' },
  ];

  const overlay = html(`
    <div class="analyzing-overlay" id="analyzing-overlay">
      <div class="analyzing-card">
        <div class="analyzing-title">🔍 Analyzing Your Code</div>
        <div class="analyzing-subtitle">Our 7 AI agents + static analysis are working through your repository</div>
        <div class="agent-list" id="agent-list"></div>
      </div>
    </div>`);

  const list = overlay.querySelector('#agent-list');
  agents.forEach((a, i) => {
    const item = el('div', { class: 'agent-item', id: `agent-${i}` }, [
      el('div', { class: 'agent-status' }, []),
      el('div', { class: 'agent-name' }, [a.name]),
      el('div', { class: 'agent-badge' }, [a.badge]),
    ]);
    list.appendChild(item);
  });

  document.body.appendChild(overlay);

  // Animate agents sequentially
  let current = 0;
  const advanceAgent = () => {
    const items = list.querySelectorAll('.agent-item');
    if (current < items.length) {
      items[current].classList.add('active');
      if (current > 0) {
        items[current - 1].classList.remove('active');
        items[current - 1].classList.add('done');
        items[current - 1].querySelector('.agent-status').textContent = '✓';
        items[current - 1].querySelector('.agent-badge').textContent = 'Done';
      }
      current++;
      // Estimate time per step (rough approximation for animation)
      const delay = current <= 2 ? 3000 : 15000; // static analysis fast, LLM agents slower
      setTimeout(advanceAgent, delay);
    }
  };
  setTimeout(advanceAgent, 500);
}

function hideAnalyzingOverlay() {
  const overlay = document.getElementById('analyzing-overlay');
  if (overlay) overlay.remove();
}

// ============================================================
//  Pages — Report
// ============================================================
function renderReport() {
  return html(`
    <div id="report-content">
      <div class="analyzing-card" style="max-width:600px;margin:4rem auto;text-align:center">
        <div class="splash-spinner" style="margin:0 auto 1rem"></div>
        <div>Loading report…</div>
      </div>
    </div>
  `);
}

async function loadReport(reportId) {
  const container = document.getElementById('report-content');
  if (!container) return;

  try {
    const [report, findingsData, risk] = await Promise.allSettled([
      api.getReport(reportId),
      api.getFindings(reportId),
      api.getRisk(reportId),
    ]);

    const r = report.value;
    const findings = findingsData.value?.findings || [];
    const riskData = risk.value || null;

    if (!r) { container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠</div><div class="empty-state-title">Report not found</div></div>'; return; }

    const scores = [
      { name: 'Quality', val: r.quality_score || 0 },
      { name: 'Security', val: r.security_score || 0 },
      { name: 'Performance', val: r.performance_score || 0 },
      { name: 'Maintainability', val: r.maintainability_score || 0 },
      { name: 'Testing', val: r.testing_score || 0 },
    ];

    const ring = buildScoreRing(r.overall_score || 0);

    container.innerHTML = '';

    // Header
    const header = html(`
      <div class="report-header">
        <h1 class="report-title">📋 Report #${r.id}</h1>
        <div class="report-meta">Analyzed on ${formatDate(r.created_at)} · Repository ID: ${r.repository_id}</div>
        <div class="report-actions">
          <a href="${API_BASE}/report/${r.id}/export?format=json" class="btn-ghost" style="display:inline-flex;align-items:center;gap:6px;padding:8px 16px;font-size:0.875rem;border-radius:6px;border:1px solid var(--color-border);color:var(--color-text-secondary)">⬇ Export JSON</a>
          <a href="${API_BASE}/report/${r.id}/export?format=markdown" class="btn-ghost" style="display:inline-flex;align-items:center;gap:6px;padding:8px 16px;font-size:0.875rem;border-radius:6px;border:1px solid var(--color-border);color:var(--color-text-secondary)">📄 Export Markdown</a>
        </div>
      </div>`);
    container.appendChild(header);

    const body = el('div', { class: 'container' });

    // Score section
    const scoreSection = el('div', { class: 'score-section', style: 'margin-top:2rem' });
    scoreSection.appendChild(ring);
    const scoreBars = el('div', { class: 'score-bars' });
    scores.forEach(s => {
      scoreBars.innerHTML += `
        <div class="score-bar-item">
          <div class="score-bar-header">
            <span class="score-bar-name">${s.name}</span>
            <span class="score-bar-val">${Math.round(s.val)}</span>
          </div>
          <div class="score-bar-track">
            <div class="score-bar-fill" style="width:0%" data-width="${s.val}%"></div>
          </div>
        </div>`;
    });
    scoreSection.appendChild(scoreBars);
    body.appendChild(scoreSection);

    // Severity summary chips
    const sevRow = html(`
      <div style="display:flex;gap:0.75rem;flex-wrap:wrap;margin:1.5rem 0">
        <span class="finding-sev-badge sev-critical">🔴 ${r.critical_count || 0} Critical</span>
        <span class="finding-sev-badge sev-high">🟠 ${r.high_count || 0} High</span>
        <span class="finding-sev-badge sev-medium">🟡 ${r.medium_count || 0} Medium</span>
        <span class="finding-sev-badge sev-low">🟢 ${r.low_count || 0} Low</span>
        <span class="finding-sev-badge sev-info">ℹ ${r.info_count || 0} Info</span>
      </div>`);
    body.appendChild(sevRow);

    // ML Risk panel
    if (riskData) {
      const riskPriorityClass = { HIGH: 'risk-high', MEDIUM: 'risk-medium', LOW: 'risk-low' }[riskData.review_priority] || 'risk-low';
      const panel = html(`
        <div class="risk-panel">
          <div class="risk-panel-header">
            <span class="risk-panel-icon">🤖</span>
            <span class="risk-panel-title">ML Code Risk Prediction</span>
            <span class="risk-panel-badge ${riskPriorityClass}">${riskData.review_priority} Priority</span>
          </div>
          <div class="risk-meters">
            <div class="risk-meter">
              <div class="risk-meter-label">Defect Probability</div>
              <div class="risk-meter-value" style="color:${riskData.defect_probability > 0.5 ? 'var(--sev-critical)' : riskData.defect_probability > 0.3 ? 'var(--sev-medium)' : 'var(--sev-low)'}">
                ${(riskData.defect_probability * 100).toFixed(1)}%
              </div>
              <div class="risk-meter-sub">probability of defects</div>
            </div>
            <div class="risk-meter">
              <div class="risk-meter-label">Maintenance Risk</div>
              <div class="risk-meter-value" style="color:${riskData.maintenance_risk > 0.6 ? 'var(--sev-high)' : riskData.maintenance_risk > 0.3 ? 'var(--sev-medium)' : 'var(--sev-low)'}">
                ${(riskData.maintenance_risk * 100).toFixed(1)}%
              </div>
              <div class="risk-meter-sub">maintenance burden</div>
            </div>
          </div>
          <div class="risk-factors">
            <div class="risk-factors-title">Top Risk Factors</div>
            ${(riskData.top_risk_factors || []).map(f => `<div class="risk-factor">${f}</div>`).join('') || '<div class="risk-factor">No significant risk factors detected</div>'}
          </div>
          <div class="disclaimer">${riskData.disclaimer || ''}</div>
        </div>`);
      body.appendChild(panel);
    }

    // Findings section
    const findingsSection = el('div', { class: '' });
    const findingsHeader = el('div', { class: 'findings-header' });
    findingsHeader.innerHTML = `<h2 class="findings-title">📍 Findings (${findings.length})</h2>`;
    const filters = el('div', { class: 'findings-filters' });

    let activeFilter = 'ALL';
    const filterBtns = [
      { label: 'All', val: 'ALL' },
      { label: '🔴 Critical', val: 'CRITICAL' },
      { label: '🟠 High', val: 'HIGH' },
      { label: '🟡 Medium', val: 'MEDIUM' },
      { label: '🟢 Low', val: 'LOW' },
      { label: '🔬 Semgrep Static', val: 'STATIC' },
    ];

    const findingsList = el('div', { id: 'findings-list' });

    const renderFindings = (filter) => {
      const filtered = filter === 'ALL'
        ? findings
        : filter === 'STATIC'
          ? findings.filter(f => f.source === 'static_analysis' || (f.agent && f.agent.toLowerCase().includes('semgrep')))
          : findings.filter(f => f.severity === filter);
      findingsList.innerHTML = '';
      if (!filtered.length) {
        findingsList.innerHTML = '<div class="empty-state" style="padding:2rem"><div class="empty-state-icon">✅</div><div class="empty-state-title">No findings for this filter</div></div>';
        return;
      }
      filtered.forEach(f => {
        const sc = severityClass(f.severity);
        const isSemgrep = f.source === 'static_analysis' || (f.agent && f.agent.toLowerCase().includes('semgrep'));
        const card = html(`
          <div class="finding-card">
            <div class="finding-card-header">
              <span class="finding-sev-badge sev-${sc}">${f.severity}</span>
              <span class="finding-title">${f.title}</span>
              <span class="confidence-pill">${f.confidence}% conf.</span>
            </div>
            <div class="finding-meta">
              <span class="finding-tag">🤖 ${f.agent}</span>
              <span class="finding-tag">📁 ${f.category}</span>
              ${f.file ? `<span class="finding-tag" style="font-family:var(--font-mono)">📄 ${f.file}${f.line_start ? ':' + f.line_start : ''}</span>` : ''}
              <span class="finding-tag">${isSemgrep ? '🔬 Semgrep Static' : '🤖 AI Agent'}</span>
            </div>
            <div class="finding-body">
              <p class="finding-desc">${f.description}</p>
              <div class="finding-rec">💡 ${f.recommendation}</div>
              ${f.code_snippet ? `<pre class="finding-code">${f.code_snippet}</pre>` : ''}
              ${f.suggested_fix ? `<div style="margin-top:0.75rem;font-size:0.8rem;color:var(--color-text-muted)">Suggested fix:</div><pre class="finding-code" style="color:var(--color-success)">${f.suggested_fix}</pre>` : ''}
            </div>
          </div>`);
        card.addEventListener('click', () => card.classList.toggle('expanded'));
        findingsList.appendChild(card);
      });
    };

    filterBtns.forEach(({ label, val }) => {
      const btn = el('button', { class: `filter-btn${activeFilter === val ? ' active' : ''}` }, [label]);
      btn.addEventListener('click', () => {
        activeFilter = val;
        $$('.filter-btn', filters).forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderFindings(val);
      });
      filters.appendChild(btn);
    });

    findingsHeader.appendChild(filters);
    findingsSection.appendChild(findingsHeader);
    renderFindings('ALL');
    findingsSection.appendChild(findingsList);
    body.appendChild(findingsSection);

    container.appendChild(body);

    // Animate score rings and bars after DOM insertion
    requestAnimationFrame(animateRings);

  } catch (err) {
    showToast('Failed to load report: ' + err.message, 'error');
    container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠</div><div class="empty-state-title">Error loading report</div><div class="empty-state-desc">${err.message}</div></div>`;
  }
}

// ============================================================
//  App Bootstrap
// ============================================================
function buildNav() {
  const nav = html(`
    <nav class="nav" id="app-nav">
      <div class="nav-brand" id="nav-brand">
        <div class="brand-icon">⬡</div>
        <span>CodeReview AI</span>
      </div>
      <div class="nav-links" id="nav-links"></div>
      <div class="nav-auth" id="nav-auth"></div>
    </nav>`);
  nav.querySelector('#nav-brand').addEventListener('click', () => router.navigate('home'));
  return nav;
}

function buildPages() {
  const pages = {
    home: renderHome(),
    login: renderLogin(),
    register: renderRegister(),
    dashboard: renderDashboard(),
    upload: renderUpload(),
    report: renderReport(),
  };

  const container = el('div', { class: 'main-content' });
  Object.entries(pages).forEach(([id, content]) => {
    const wrapper = el('div', { class: 'page', id: `page-${id}` });
    wrapper.appendChild(content);
    container.appendChild(wrapper);
  });

  return container;
}

function init() {
  const app = document.getElementById('app');
  app.innerHTML = '';
  app.appendChild(buildNav());
  app.appendChild(buildPages());

  // Setup hero buttons after DOM is ready
  setTimeout(() => {
    const heroCta = document.getElementById('hero-cta');
    const heroSec = document.getElementById('hero-secondary');
    if (heroCta) heroCta.addEventListener('click', () => {
      if (auth.isAuthenticated()) router.navigate('upload');
      else router.navigate('register');
    });
    if (heroSec) heroSec.addEventListener('click', () => {
      showToast('Demo: Please upload your own repository to see a live report', 'info');
    });
  }, 100);

  // Expose for inline event handlers
  window.crNavigate = (page) => router.navigate(page);

  // Navigate to initial page
  if (auth.isAuthenticated()) {
    router.navigate('dashboard');
  } else {
    router.navigate('home');
  }
}

init();
