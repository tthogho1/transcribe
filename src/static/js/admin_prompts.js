// Prompt editor (/admin/prompts). Talks to /api/admin/* with the ADMIN_TOKEN.
// All prompt data is inserted with textContent, never as HTML.

const $ = id => document.getElementById(id);

const state = {
  token: '',
  prompts: [],
  defaultId: '',
  selectedId: null, // null while creating a new prompt
};

// --- token storage (per tab; sessionStorage can be unavailable) -------------

function loadToken() {
  try {
    return window.sessionStorage.getItem('admin.token') || '';
  } catch {
    return '';
  }
}

function saveToken(token) {
  try {
    window.sessionStorage.setItem('admin.token', token);
  } catch {
    /* only kept in memory */
  }
}

// --- API --------------------------------------------------------------------

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: {
      Authorization: `Bearer ${state.token}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try {
    data = await response.json();
  } catch {
    /* non-JSON error page */
  }
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

// --- UI ---------------------------------------------------------------------

function setStatus(message, kind = '') {
  const status = $('status');
  status.textContent = message;
  status.className = kind;
}

function renderList() {
  const list = $('prompt-list');
  list.replaceChildren(
    ...state.prompts.map(p => {
      const li = document.createElement('li');
      li.className = p.id === state.selectedId ? 'selected' : '';
      const title = document.createElement('div');
      title.textContent = p.title;
      if (p.id === state.defaultId) title.append(badge('既定', 'default'));
      if (p.builtin) title.append(badge('標準・編集不可'));
      const id = document.createElement('div');
      id.className = 'pid';
      id.textContent = p.id;
      li.append(title, id);
      li.addEventListener('click', () => selectPrompt(p.id));
      return li;
    })
  );
}

function badge(text, extra = '') {
  const span = document.createElement('span');
  span.className = `badge ${extra}`;
  span.textContent = text;
  return span;
}

function fillEditor({ id, title, text }, { idEditable, readOnly }) {
  $('prompt-id').value = id;
  $('prompt-id').readOnly = !idEditable;
  $('prompt-title').value = title;
  $('prompt-text').value = text;
  $('prompt-title').readOnly = readOnly;
  $('prompt-text').readOnly = readOnly;
  $('builtin-note').hidden = !readOnly;
}

function selectPrompt(id) {
  const prompt = state.prompts.find(p => p.id === id);
  if (!prompt) return;
  state.selectedId = id;
  // Built-in prompts are read-only: they change only with the code.
  fillEditor(prompt, { idEditable: false, readOnly: prompt.builtin });
  updateButtons();
  renderList();
  setStatus('');
}

function startNewPrompt(from = { id: '', title: '', text: '' }) {
  state.selectedId = null;
  fillEditor(from, { idEditable: true, readOnly: false });
  updateButtons();
  renderList();
  setStatus('ID・名前・本文を入力して保存してください。');
  $('prompt-id').focus();
}

// A free id like "full-copy", "full-copy-2", ... (max 40 characters)
function copyId(id) {
  const base = `${id}-copy`.slice(0, 33);
  const taken = new Set(state.prompts.map(p => p.id));
  if (!taken.has(base)) return base;
  for (let n = 2; ; n++) {
    if (!taken.has(`${base}-${n}`)) return `${base}-${n}`;
  }
}

function copyPrompt() {
  const prompt = state.prompts.find(p => p.id === state.selectedId);
  if (!prompt) return;
  startNewPrompt({
    id: copyId(prompt.id),
    title: `${prompt.title}（コピー）`.slice(0, 60),
    text: prompt.text,
  });
  setStatus('コピーを作りました。編集して保存してください。');
}

function updateButtons() {
  const prompt = state.prompts.find(p => p.id === state.selectedId);
  const creating = state.selectedId === null;
  const editable = creating || (prompt && !prompt.builtin);
  $('save').disabled = !editable;
  $('copy').disabled = !prompt;
  $('make-default').disabled = !prompt || prompt.id === state.defaultId;
  $('delete').disabled = !prompt || prompt.builtin;
}

async function reload(selectId) {
  const data = await api('GET', '/api/admin/prompts');
  state.prompts = data.prompts;
  state.defaultId = data.default;
  $('store-path').textContent = `保存先: ${data.store}`;
  if (selectId && state.prompts.some(p => p.id === selectId)) {
    selectPrompt(selectId);
  } else if (state.prompts.length) {
    selectPrompt(state.prompts[0].id);
  }
}

// --- actions ----------------------------------------------------------------

async function connect() {
  state.token = $('token').value.trim();
  if (!state.token) {
    setStatus('');
    return;
  }
  try {
    await reload(state.selectedId);
    saveToken(state.token);
    $('editor-area').hidden = false;
    $('login').hidden = true;
  } catch (error) {
    $('editor-area').hidden = true;
    alert(`接続できません: ${error.message}`);
  }
}

async function save() {
  const id = $('prompt-id').value.trim();
  const body = { title: $('prompt-title').value, text: $('prompt-text').value };
  if (state.selectedId === null && state.prompts.some(p => p.id === id)) {
    setStatus(`ID「${id}」は既にあります。別の ID にしてください。`, 'error');
    return;
  }
  try {
    await api('PUT', `/api/admin/prompts/${encodeURIComponent(id)}`, body);
    await reload(id);
    setStatus('保存しました。チャットにすぐ反映されます。', 'ok');
  } catch (error) {
    setStatus(`保存できません: ${error.message}`, 'error');
  }
}

async function makeDefault() {
  try {
    await api('PUT', '/api/admin/default-prompt', { id: state.selectedId });
    await reload(state.selectedId);
    setStatus('既定のプロンプトにしました。', 'ok');
  } catch (error) {
    setStatus(`変更できません: ${error.message}`, 'error');
  }
}

async function remove() {
  const prompt = state.prompts.find(p => p.id === state.selectedId);
  if (!prompt || prompt.builtin) return;
  if (!confirm(`「${prompt.title}」を削除しますか？元に戻せません。`)) return;
  try {
    await api('DELETE', `/api/admin/prompts/${encodeURIComponent(prompt.id)}`);
    await reload(null);
    setStatus('削除しました。', 'ok');
  } catch (error) {
    setStatus(`削除できません: ${error.message}`, 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  $('connect').addEventListener('click', connect);
  $('token').addEventListener('keydown', e => {
    if (e.key === 'Enter') connect();
  });
  $('new-prompt').addEventListener('click', () => startNewPrompt());
  $('copy').addEventListener('click', copyPrompt);
  $('save').addEventListener('click', save);
  $('make-default').addEventListener('click', makeDefault);
  $('delete').addEventListener('click', remove);

  const saved = loadToken();
  if (saved) {
    $('token').value = saved;
    connect();
  }
});
