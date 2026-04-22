/* ═══════════════════════════════════════════════════════════════════
   CS2 Referral Admin — app.js
   Vanilla JS, no framework. Requires D3 v7 + Chart.js v4 from CDN.
═══════════════════════════════════════════════════════════════════ */

'use strict';

const API = '/api/admin';

// ── Toast notifications ───────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const el = document.createElement('div');
  el.textContent = msg;
  el.style.cssText = `
    position:fixed;bottom:24px;right:24px;z-index:9999;
    background:${type === 'success' ? 'var(--green)' : 'var(--red)'};
    color:#fff;padding:12px 20px;border-radius:12px;
    font-size:.85rem;font-family:Inter,sans-serif;font-weight:500;
    box-shadow:0 4px 24px rgba(0,0,0,.4);
    animation:fadeInUp .25s ease;max-width:400px;line-height:1.4;
  `;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

const _style = document.createElement('style');
_style.textContent = `@keyframes fadeInUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}`;
document.head.appendChild(_style);

// ── Auth ─────────────────────────────────────────────────────────────
function getToken() { return localStorage.getItem('admin_token') || ''; }
function setToken(t) { localStorage.setItem('admin_token', t); }
function clearToken() { localStorage.removeItem('admin_token'); }

function authHeaders() {
  return { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' };
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, { ...opts, headers: { ...authHeaders(), ...(opts.headers || {}) } });
  if (res.status === 401) { showLogin('Неверный токен'); return null; }
  if (!res.ok) {
    const txt = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.json();
}

async function doLogin() {
  const t = document.getElementById('token-input').value.trim();
  if (!t) return;
  setToken(t);
  const data = await apiFetch('/review_queue').catch(() => null);
  if (!data) { showLogin('Неверный токен'); return; }
  hideLogin();
  initApp();
}

function showLogin(err = '') {
  document.getElementById('login-overlay').classList.remove('hidden');
  document.getElementById('app').classList.remove('visible');
  document.getElementById('login-err').textContent = err;
}

function hideLogin() {
  document.getElementById('login-overlay').classList.add('hidden');
  document.getElementById('app').classList.add('visible');
}

function logout() {
  clearToken();
  location.reload();
}

// Enter key on token input
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('token-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
  });
  if (getToken()) {
    // Try auto-login
    apiFetch('/review_queue').then(data => {
      if (data) { hideLogin(); initApp(); }
    }).catch(() => {});
  }
});

// ── State ─────────────────────────────────────────────────────────────
let state = {
  page: 1, pages: 1, total: 0, limit: 50,
  sortCol: 'referrals', sortDir: 'desc',
  currentTreeId: null,
};

// ── Init ──────────────────────────────────────────────────────────────
function initApp() {
  loadGiftStatus();
  loadReviewQueue();
  loadUsers();
  loadChart(30);
}

// ══════════════════════════════════════════════════════════════════════
//  0 — Gift global toggle
// ══════════════════════════════════════════════════════════════════════
async function loadGiftStatus() {
  const data = await apiFetch('/settings').catch(() => null);
  if (!data) return;
  renderGiftToggle(data.gifts_enabled);
}

function renderGiftToggle(enabled) {
  const btn  = document.getElementById('gift-toggle-btn');
  const text = document.getElementById('gift-status-text');
  const card = document.getElementById('gift-toggle-card');

  if (enabled) {
    btn.textContent  = '⏸ Остановить выдачу';
    btn.className    = 'btn btn-danger btn-sm';
    text.textContent = '✅ Выдача подарков включена — пользователи могут получать скины';
    card.style.borderColor = '';
  } else {
    btn.textContent  = '▶ Запустить выдачу';
    btn.className    = 'btn btn-success btn-sm';
    text.textContent = '⛔ Выдача подарков остановлена — кнопка заблокирована для всех';
    card.style.borderColor = 'var(--red)';
  }
}

async function toggleGifts() {
  const btn = document.getElementById('gift-toggle-btn');
  btn.disabled = true;
  const data = await apiFetch('/settings/gifts_toggle', { method: 'POST' }).catch(e => {
    showToast('Ошибка: ' + e.message, 'error');
    return null;
  });
  btn.disabled = false;
  if (!data) return;
  renderGiftToggle(data.gifts_enabled);
  showToast(data.gifts_enabled ? '✅ Выдача подарков включена' : '⛔ Выдача подарков остановлена',
            data.gifts_enabled ? 'success' : 'error');
}

// ══════════════════════════════════════════════════════════════════════
//  A — Review queue
// ══════════════════════════════════════════════════════════════════════
async function loadReviewQueue() {
  const data = await apiFetch('/review_queue').catch(() => null);
  if (!data) return;

  const badge = document.getElementById('review-badge');
  const list  = document.getElementById('review-list');

  if (data.count === 0) {
    badge.classList.add('hidden');
    list.innerHTML = '<span id="review-empty" class="text-muted">✅ Нет пользователей на проверке</span>';
    return;
  }

  badge.textContent = `${data.count} на проверке`;
  badge.classList.remove('hidden');

  list.innerHTML = data.users.map(u => `
    <div class="review-row" id="rrow-${u.telegram_id}">
      <span class="review-id" onclick="openTree(${u.telegram_id})">${u.telegram_id}</span>
      <span class="review-count">📨 ${u.referrals} реф.</span>
      <span class="tag ${u.is_frozen ? 'tag-frozen' : 'tag-review'}">${u.is_frozen ? '🔴 заморожен' : '🟡 активен'}</span>
      <button class="btn btn-success btn-sm" onclick="approveUser(${u.telegram_id})">✓ Одобрить</button>
      <button class="btn btn-danger btn-sm"  onclick="dismissUser(${u.telegram_id})">✗ Отклонить</button>
    </div>
  `).join('');
}

async function approveUser(id) {
  const res = await apiFetch(`/approve/${id}`, { method: 'POST' }).catch(e => { alert(e.message); return null; });
  if (!res) return;
  if (res.restored > 0) {
    showToast(`✅ Одобрен ${id}. Восстановлено рефералов: +${res.restored} (${res.referrals_before} → ${res.referrals_after})`, 'success');
  } else {
    showToast(`✅ Одобрен ${id}`, 'success');
  }
  document.getElementById(`rrow-${id}`)?.remove();
  await loadReviewQueue();
  await loadUsers();
}

async function dismissUser(id) {
  await apiFetch(`/dismiss/${id}`, { method: 'POST' }).catch(e => alert(e.message));
  document.getElementById(`rrow-${id}`)?.remove();
  await loadReviewQueue();
  await loadUsers();
}

// ══════════════════════════════════════════════════════════════════════
//  C — Manual add referral
// ══════════════════════════════════════════════════════════════════════
function switchTab(tab) {
  document.getElementById('tab-real-content').style.display = tab === 'real' ? '' : 'none';
  document.getElementById('tab-fake-content').style.display = tab === 'fake' ? '' : 'none';
  document.getElementById('tab-real').className = `btn btn-sm ${tab === 'real' ? 'btn-primary' : 'btn-ghost'}`;
  document.getElementById('tab-real').style.borderRadius = '8px 0 0 8px';
  document.getElementById('tab-fake').className = `btn btn-sm ${tab === 'fake' ? 'btn-primary' : 'btn-ghost'}`;
  document.getElementById('tab-fake').style.borderRadius = '0 8px 8px 0';
  document.getElementById('add-ref-result').innerHTML = '';
}

async function incrementReferrals() {
  const userId  = document.getElementById('inc-ref-id').value.trim();
  const count   = parseInt(document.getElementById('inc-ref-count').value) || 1;
  const resultEl = document.getElementById('add-ref-result');

  if (!userId) { resultEl.innerHTML = '<span class="text-red">Введите ID пользователя</span>'; return; }

  resultEl.innerHTML = '<span class="loader"></span>';

  const res = await apiFetch(`/increment_referrals/${userId}`, {
    method: 'POST',
    body: JSON.stringify({ count }),
  }).catch(e => { resultEl.innerHTML = `<span class="text-red">Ошибка: ${e.message}</span>`; return null; });

  if (!res) return;

  resultEl.innerHTML = `<span class="text-green">
    ✅ Добавлено <b>${res.added}</b> реф. Пользователь <b>${userId}</b> теперь имеет <b>${res.referrals_count}</b> рефералов.
    Отправлено уведомлений о подарках: ${res.gifts_sent}.
  </span>`;

  document.getElementById('inc-ref-id').value = '';
  document.getElementById('inc-ref-count').value = '1';
  await loadUsers();
}

async function manualAddReferral() {
  const referrerId = document.getElementById('add-ref-referrer').value.trim();
  const invitedId  = document.getElementById('add-ref-invited').value.trim();
  const resultEl   = document.getElementById('add-ref-result');

  if (!referrerId || !invitedId) {
    resultEl.innerHTML = '<span class="text-red">Заполните оба поля</span>';
    return;
  }

  resultEl.innerHTML = '<span class="loader"></span>';

  const res = await apiFetch('/add_referral', {
    method: 'POST',
    body: JSON.stringify({ referrer_id: parseInt(referrerId), invited_id: parseInt(invitedId) }),
  }).catch(e => { resultEl.innerHTML = `<span class="text-red">Ошибка: ${e.message}</span>`; return null; });

  if (!res) return;

  resultEl.innerHTML = `<span class="text-green">
    ✅ Готово! Пригласивший <b>${referrerId}</b> теперь имеет <b>${res.referrals_count}</b> рефералов.
    Уведомление о подарке отправлено.
  </span>`;

  document.getElementById('add-ref-referrer').value = '';
  document.getElementById('add-ref-invited').value  = '';

  await loadUsers();
}

// ══════════════════════════════════════════════════════════════════════
//  B — Users table
// ══════════════════════════════════════════════════════════════════════
async function loadUsers() {
  const { page, limit, sortCol, sortDir } = state;
  const params = new URLSearchParams({ page, limit, sort_by: sortCol, sort_dir: sortDir });
  const data = await apiFetch(`/users?${params}`).catch(() => null);
  if (!data) return;

  state.pages = data.pages;
  state.total  = data.total;

  document.getElementById('users-total').textContent =
    `Всего: ${data.total} пользователей (стр. ${data.page} из ${data.pages})`;

  renderUsersTable(data.users);
  renderPagination();
}

function renderUsersTable(users) {
  const tbody = document.getElementById('users-tbody');
  if (!users.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--muted)">Нет данных</td></tr>';
    return;
  }
  tbody.innerHTML = users.map(u => {
    const statusTag = u.is_frozen
      ? `<span class="tag tag-frozen">🔴 заморожен</span>`
      : u.needs_review
        ? `<span class="tag tag-review">🟠 проверка</span>`
        : `<span class="tag tag-ok">🟢 норм</span>`;

    const joinedAt = u.joined_at
      ? new Date(u.joined_at).toLocaleDateString('ru-RU')
      : '—';

    const steamLink = u.steam_profile
      ? `<a href="${u.steam_profile}" target="_blank" style="color:var(--blue);font-size:.75rem">Steam ↗</a>`
      : '<span class="text-muted">—</span>';

    // Разморозить → approve (восстанавливает рефералы + шлёт подарки)
    // Заморозить  → freeze
    const freezeBtn = u.is_frozen
      ? `<button class="btn btn-success btn-sm" onclick="approveUser(${u.telegram_id})">Разморозить</button>`
      : `<button class="btn btn-danger btn-sm"  onclick="toggleFreeze(${u.telegram_id}, true)">Заморозить</button>`;

    const frozenWaiting = u.frozen_referrals > 0
      ? `<span style="color:var(--blue)">${u.frozen_referrals}</span>`
      : `<span class="text-muted">—</span>`;

    return `
      <tr id="urow-${u.telegram_id}">
        <td class="mono" style="color:var(--blue);cursor:pointer" onclick="showSidebar(${u.telegram_id})">${u.telegram_id}</td>
        <td><b>${u.referrals}</b></td>
        <td>${frozenWaiting}</td>
        <td>${statusTag}</td>
        <td>${joinedAt}</td>
        <td>${steamLink}</td>
        <td>
          <div class="flex-row">
            ${freezeBtn}
            <button class="btn btn-ghost btn-sm" onclick="openTree(${u.telegram_id})">🌐 Дерево</button>
          </div>
        </td>
      </tr>`;
  }).join('');
}

async function toggleFreeze(id, freeze) {
  await apiFetch(`/freeze/${id}`, {
    method: 'POST',
    body: JSON.stringify({ freeze }),
  }).catch(e => alert(e.message));
  await loadUsers();
  await loadReviewQueue();
}

// Sort
function sortBy(col) {
  if (state.sortCol === col) {
    state.sortDir = state.sortDir === 'desc' ? 'asc' : 'desc';
  } else {
    state.sortCol = col;
    state.sortDir = 'desc';
  }
  state.page = 1;
  updateSortHeaders();
  loadUsers();
}

function updateSortHeaders() {
  document.querySelectorAll('th[data-col]').forEach(th => {
    const col = th.dataset.col;
    th.classList.toggle('active-sort', col === state.sortCol);
    const arrow = th.querySelector('.sort-arrow');
    if (arrow) arrow.textContent = col === state.sortCol ? (state.sortDir === 'desc' ? '↓' : '↑') : '↕';
  });
}

// Pagination
function renderPagination() {
  const el = document.getElementById('pagination');
  const { page, pages } = state;
  if (pages <= 1) { el.innerHTML = ''; return; }
  el.innerHTML = `
    <button class="btn btn-ghost btn-sm" ${page <= 1 ? 'disabled' : ''} onclick="goPage(${page-1})">← Пред</button>
    <span>стр. ${page} / ${pages}</span>
    <button class="btn btn-ghost btn-sm" ${page >= pages ? 'disabled' : ''} onclick="goPage(${page+1})">След →</button>
  `;
}

function goPage(p) { state.page = p; loadUsers(); }

// ══════════════════════════════════════════════════════════════════════
//  C — Referral tree (D3 v7)
// ══════════════════════════════════════════════════════════════════════
let treeZoom = null;
let treeSvg  = null;

function openTree(id) {
  id = parseInt(id);
  if (!id) return;
  state.currentTreeId = id;
  document.getElementById('tree-title').textContent = `Дерево: ${id}`;
  document.getElementById('tree-panel').classList.add('open');
  document.getElementById('inline-tree-msg').textContent = `Открыто дерево для ${id}`;
  document.getElementById('tree-id-input').value = id;
  fetchAndRenderTree(id, parseInt(document.getElementById('depth-slider').value));
}

function closeTree() {
  document.getElementById('tree-panel').classList.remove('open');
  state.currentTreeId = null;
}

function reloadTree() {
  if (!state.currentTreeId) return;
  const depth = parseInt(document.getElementById('depth-slider').value);
  fetchAndRenderTree(state.currentTreeId, depth);
}

async function fetchAndRenderTree(id, depth) {
  const statusEl = document.getElementById('tree-status');
  statusEl.textContent = 'Загрузка...';

  const data = await apiFetch(`/tree/${id}?depth=${depth}`).catch(e => {
    statusEl.textContent = 'Ошибка: ' + e.message;
    return null;
  });
  if (!data) return;

  const nodeCount = countNodes(data);
  statusEl.textContent = `${nodeCount} узлов`;
  renderD3Tree(data);
}

function countNodes(node) {
  if (!node) return 0;
  return 1 + (node.children || []).reduce((s, c) => s + countNodes(c), 0);
}

function renderD3Tree(rootData) {
  const wrap = document.getElementById('tree-svg-wrap');
  wrap.innerHTML = '';   // clear

  const W = wrap.clientWidth  || 560;
  const H = wrap.clientHeight || 500;

  const svg = d3.select(wrap)
    .append('svg')
    .attr('width', W).attr('height', H)
    .style('background', 'var(--bg)');

  const g = svg.append('g');

  // Zoom
  treeZoom = d3.zoom().scaleExtent([.1, 4]).on('zoom', e => g.attr('transform', e.transform));
  svg.call(treeZoom);

  const root = d3.hierarchy(rootData);

  // Determine layout: use tree layout
  const treeLayout = d3.tree().nodeSize([48, 240]);
  treeLayout(root);

  // Shift so root is visible
  const xs = root.descendants().map(d => d.x);
  const minX = Math.min(...xs);
  const offsetX = -minX + 20;
  const initTransform = d3.zoomIdentity.translate(80, H / 2 + offsetX);
  svg.call(treeZoom.transform, initTransform);

  // Links
  g.selectAll('.link')
    .data(root.links())
    .enter().append('path')
    .attr('class', 'link')
    .attr('fill', 'none')
    .attr('stroke', 'var(--border)')
    .attr('stroke-width', 1.5)
    .attr('d', d3.linkHorizontal()
      .x(d => d.y)
      .y(d => d.x)
    );

  // Nodes
  const node = g.selectAll('.node')
    .data(root.descendants())
    .enter().append('g')
    .attr('class', 'node')
    .attr('transform', d => `translate(${d.y},${d.x})`)
    .style('cursor', 'pointer')
    .on('click', (event, d) => showSidebar(d.data.id))
    .on('mouseover', (event, d) => showTreeTip(event, d, wrap))
    .on('mouseout', () => document.getElementById('tree-tip').style.display = 'none');

  // Circle
  node.append('circle')
    .attr('r', 10)
    .attr('fill', d => {
      if (d.data.frozen)       return 'var(--red)';
      if (d.data.needs_review) return 'var(--orange)';
      return d.depth === 0 ? 'var(--blue)' : 'var(--green)';
    })
    .attr('stroke', 'var(--surface)')
    .attr('stroke-width', 2);

  // Label: referral count
  node.append('text')
    .attr('dy', '.35em')
    .attr('text-anchor', 'middle')
    .attr('fill', '#fff')
    .attr('font-size', '9px')
    .attr('font-weight', '700')
    .text(d => d.data.referrals > 0 ? d.data.referrals : '');

  // ID label below
  node.append('text')
    .attr('dy', '26px')
    .attr('text-anchor', 'middle')
    .attr('fill', 'var(--muted)')
    .attr('font-size', '10px')
    .attr('font-family', 'monospace')
    .text(d => d.data.id);

  // Truncation indicator
  node.filter(d => d.data.truncated_count > 0)
    .append('text')
    .attr('dy', '42px')
    .attr('text-anchor', 'middle')
    .attr('fill', 'var(--orange)')
    .attr('font-size', '8px')
    .text(d => `+${d.data.truncated_count} ещё`);
}

function showTreeTip(event, d, container) {
  const tip = document.getElementById('tree-tip');
  const rect = container.getBoundingClientRect();
  tip.style.display = 'block';
  tip.style.left = (event.clientX - rect.left + 12) + 'px';
  tip.style.top  = (event.clientY - rect.top  + 12) + 'px';
  tip.innerHTML = `
    <b>${d.data.id}</b><br>
    Рефералов: <b>${d.data.referrals}</b><br>
    ${d.data.frozen ? '🔴 Заморожен' : d.data.needs_review ? '🟠 На проверке' : '🟢 Норм'}
  `;
}

// ══════════════════════════════════════════════════════════════════════
//  User sidebar
// ══════════════════════════════════════════════════════════════════════
async function showSidebar(id) {
  const data = await apiFetch(`/user/${id}`).catch(() => null);
  if (!data) return;

  document.getElementById('sb-title').textContent = `ID: ${data.telegram_id}`;
  document.getElementById('sidebar').classList.add('open');

  const rows = [
    ['Рефералов', data.referrals],
    ['❄️ Ждут разморозки', data.frozen_referrals > 0 ? `<b style="color:var(--blue)">${data.frozen_referrals}</b>` : '—'],
    ['Статус', data.is_frozen ? '🔴 Заморожен' : (data.needs_review ? '🟠 На проверке' : '🟢 Норм')],
    ['Дата входа', data.joined_at ? new Date(data.joined_at).toLocaleString('ru-RU') : '—'],
    ['Приглашён от', data.referred_by || '—'],
    ['Подарок', data.has_gift ? '✅ активен' : '—'],
    ['Trade link', data.trade_link ? `<a href="${data.trade_link}" target="_blank" style="color:var(--blue)">ссылка</a>` : '—'],
  ];

  document.getElementById('sb-body').innerHTML = rows.map(([l, v]) =>
    `<div class="sb-row"><span class="sb-label">${l}</span><span>${v}</span></div>`
  ).join('');

  // Разморозить → approve (восстанавливает рефералы + шлёт подарки)
  const freezeBtn = data.is_frozen
    ? `<button class="btn btn-success btn-sm" onclick="approveUser(${id});closeSidebar()">Разморозить</button>`
    : `<button class="btn btn-danger btn-sm" onclick="toggleFreeze(${id}, true);closeSidebar()">Заморозить</button>`;

  const approveBtn = data.needs_review && !data.is_frozen
    ? `<button class="btn btn-primary btn-sm" onclick="approveUser(${id});closeSidebar()">Одобрить</button>`
    : '';

  document.getElementById('sb-actions').innerHTML = `
    ${freezeBtn}
    ${approveBtn}
    <button class="btn btn-ghost btn-sm" onclick="openTree(${id})">🌐 Дерево</button>
    <button class="btn btn-ghost btn-sm" onclick="closeSidebar()">✕</button>
  `;
}

function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
}

// ══════════════════════════════════════════════════════════════════════
//  D — Chart (Chart.js v4)
// ══════════════════════════════════════════════════════════════════════
let chartInstance = null;

async function loadChart(days) {
  const data = await apiFetch(`/stats/referrals_per_day?days=${days}`).catch(() => null);
  if (!data) return;

  const labels = data.data.map(d => d.date);
  const values = data.data.map(d => d.count);

  const ctx = document.getElementById('chart-canvas').getContext('2d');
  if (chartInstance) chartInstance.destroy();

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Новые рефералы',
        data: values,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,.12)',
        borderWidth: 2,
        fill: true,
        tension: 0.35,
        pointRadius: 3,
        pointHoverRadius: 6,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { family: 'Inter' } } },
        tooltip: { mode: 'index', intersect: false },
      },
      scales: {
        x: {
          ticks: { color: '#64748b', font: { family: 'Inter', size: 11 } },
          grid:  { color: 'rgba(255,255,255,.05)' },
        },
        y: {
          beginAtZero: true,
          ticks: { color: '#64748b', font: { family: 'Inter', size: 11 }, precision: 0 },
          grid:  { color: 'rgba(255,255,255,.05)' },
        },
      },
    },
  });
}
