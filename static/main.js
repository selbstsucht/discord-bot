/* ── Tab switching ───────────────────────────────────────────── */
function switchTab(name, btn) {
  document.querySelectorAll('.tab-section').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.sidebar-btn').forEach(el => el.classList.remove('active'));
  const section = document.getElementById('tab-' + name);
  if (section) section.classList.add('active');
  if (btn) btn.classList.add('active');
}

/* ── Toast ───────────────────────────────────────────────────── */
let _toastTimer;
function showToast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast ${type} show`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.classList.remove('show'); }, 3000);
}

/* ── API helper ──────────────────────────────────────────────── */
async function api(method, url, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || 'Fehler');
  return data;
}

/* ── Welcome ─────────────────────────────────────────────────── */
async function saveWelcome(gid) {
  try {
    await api('POST', `/api/server/${gid}/welcome`, {
      enabled:    document.getElementById('welcome-enabled').checked,
      channel_id: document.getElementById('welcome-channel').value,
      message:    document.getElementById('welcome-message').value,
    });
    showToast('Willkommen-Einstellungen gespeichert!');
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Goodbye ─────────────────────────────────────────────────── */
async function saveGoodbye(gid) {
  try {
    await api('POST', `/api/server/${gid}/goodbye`, {
      enabled:    document.getElementById('goodbye-enabled').checked,
      channel_id: document.getElementById('goodbye-channel').value,
      message:    document.getElementById('goodbye-message').value,
    });
    showToast('Verabschiedungs-Einstellungen gespeichert!');
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Auto-Roles ──────────────────────────────────────────────── */
function addAutorole(sel) {
  const id   = sel.value;
  const name = sel.options[sel.selectedIndex]?.dataset?.name;
  if (!id) return;
  sel.value = '';

  const container = document.getElementById('autorole-selected');
  if (container.querySelector(`[data-id="${id}"]`)) return;

  const chip = document.createElement('span');
  chip.className = 'role-chip';
  chip.dataset.id = id;
  chip.innerHTML = `${name}<button class="chip-remove" onclick="removeAutorole('${id}')">×</button>`;
  container.appendChild(chip);
}

function removeAutorole(id) {
  const chip = document.querySelector(`#autorole-selected [data-id="${id}"]`);
  if (chip) chip.remove();
}

async function saveAutorole(gid) {
  const chips = document.querySelectorAll('#autorole-selected .role-chip');
  const role_ids = Array.from(chips).map(c => c.dataset.id);
  try {
    await api('POST', `/api/server/${gid}/autorole`, {
      enabled:  document.getElementById('autorole-enabled').checked,
      role_ids,
    });
    showToast('Auto-Rollen gespeichert!');
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Modal ───────────────────────────────────────────────────── */
let _currentEditId = null;

function openModal(html) {
  document.getElementById('modal-content').innerHTML = html;
  document.getElementById('modal-overlay').classList.add('open');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
  _currentEditId = null;
}

/* ── Self-Roles: Create ──────────────────────────────────────── */
function openCreateModal(gid) {
  _currentEditId = null;
  const channelOptions = (window.ALL_CHANNELS || [])
    .map(c => `<option value="${c.id}"># ${c.name}</option>`).join('');

  openModal(`
    <div class="modal-title">Neue Self-Role Nachricht</div>
    <div class="modal-form">
      <label>Titel
        <input class="input" id="m-title" value="Self Roles" maxlength="256">
      </label>
      <label>Beschreibung
        <textarea class="textarea" id="m-desc" rows="3">Klicke auf einen Button um eine Rolle zu erhalten!</textarea>
      </label>
      <label>Farbe
        <div class="color-row">
          <input type="color" id="m-color-picker" value="#5865f2"
                 oninput="document.getElementById('m-color').value=this.value">
          <input class="input" id="m-color" value="#5865f2" placeholder="#5865f2" maxlength="7"
                 oninput="syncColor(this.value)">
        </div>
      </label>
      <label>Bild-URL (optional)
        <input class="input" id="m-img" placeholder="https://…">
      </label>
      <label>Channel
        <select class="select" id="m-channel">
          <option value="">— Channel wählen —</option>
          ${channelOptions}
        </select>
      </label>
      <div class="modal-actions">
        <button class="btn btn-ghost" onclick="closeModal()">Abbrechen</button>
        <button class="btn btn-primary" onclick="submitSrForm('${gid}')">Erstellen</button>
      </div>
    </div>
  `);
}

function syncColor(val) {
  const picker = document.getElementById('m-color-picker');
  if (/^#[0-9a-fA-F]{6}$/.test(val) && picker) picker.value = val;
}

async function submitSrForm(gid) {
  const body = {
    embed_title:       document.getElementById('m-title').value.trim(),
    embed_description: document.getElementById('m-desc').value.trim(),
    embed_color:       document.getElementById('m-color').value,
    embed_image_url:   document.getElementById('m-img').value.trim(),
    channel_id:        document.getElementById('m-channel').value,
  };
  try {
    if (_currentEditId) {
      await api('PUT', `/api/server/${gid}/selfroles/${_currentEditId}`, body);
      showToast('Nachricht aktualisiert!');
    } else {
      await api('POST', `/api/server/${gid}/selfroles`, body);
      showToast('Nachricht erstellt!');
    }
    closeModal();
    location.reload();
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Self-Roles: Edit ────────────────────────────────────────── */
function openEditModal(gid, id, sr, channels) {
  _currentEditId = id;
  const channelOptions = channels
    .map(c => `<option value="${c.id}" ${c.id === sr.channel_id ? 'selected' : ''}># ${c.name}</option>`)
    .join('');

  openModal(`
    <div class="modal-title">Nachricht bearbeiten</div>
    <div class="modal-form">
      <label>Titel
        <input class="input" id="m-title" value="${_esc(sr.embed_title)}" maxlength="256">
      </label>
      <label>Beschreibung
        <textarea class="textarea" id="m-desc" rows="3">${_esc(sr.embed_description)}</textarea>
      </label>
      <label>Farbe
        <div class="color-row">
          <input type="color" id="m-color-picker" value="${sr.embed_color}"
                 oninput="document.getElementById('m-color').value=this.value">
          <input class="input" id="m-color" value="${sr.embed_color}" placeholder="#5865f2" maxlength="7"
                 oninput="syncColor(this.value)">
        </div>
      </label>
      <label>Bild-URL (optional)
        <input class="input" id="m-img" value="${_esc(sr.embed_image_url)}" placeholder="https://…">
      </label>
      <label>Channel
        <select class="select" id="m-channel">
          <option value="">— Channel wählen —</option>
          ${channelOptions}
        </select>
      </label>
      <div class="modal-actions">
        <button class="btn btn-ghost" onclick="closeModal()">Abbrechen</button>
        <button class="btn btn-primary" onclick="submitSrForm('${gid}')">Speichern</button>
      </div>
    </div>
  `);
}

/* ── Self-Roles: Delete ──────────────────────────────────────── */
async function deleteSrMessage(gid, id) {
  if (!confirm('Nachricht wirklich löschen? (Wird auch aus Discord entfernt)')) return;
  try {
    await api('DELETE', `/api/server/${gid}/selfroles/${id}`);
    document.getElementById(`sr-card-${id}`)?.remove();
    showToast('Nachricht gelöscht.');
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Self-Roles: Post ────────────────────────────────────────── */
async function postSrMessage(gid, id) {
  try {
    showToast('Wird gepostet…', 'info');
    await api('POST', `/api/server/${gid}/selfroles/${id}/post`);
    showToast('Nachricht erfolgreich gepostet!');
    setTimeout(() => location.reload(), 800);
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Self-Roles: Buttons ─────────────────────────────────────── */
function toggleAddBtnForm(mid) {
  const form = document.getElementById(`add-btn-form-${mid}`);
  if (form) form.style.display = form.style.display === 'none' ? 'flex' : 'none';
}

async function addSrButton(gid, mid) {
  const role_id = document.getElementById(`ab-role-${mid}`).value;
  const label   = document.getElementById(`ab-label-${mid}`).value.trim();
  const emoji   = document.getElementById(`ab-emoji-${mid}`).value.trim();
  const style   = document.getElementById(`ab-style-${mid}`).value;

  if (!role_id) { showToast('Bitte eine Rolle auswählen.', 'error'); return; }
  if (!label)   { showToast('Bitte einen Button-Text eingeben.', 'error'); return; }

  try {
    await api('POST', `/api/server/${gid}/selfroles/${mid}/buttons`, { role_id, label, emoji, style });
    showToast('Button hinzugefügt!');
    location.reload();
  } catch(e) { showToast(e.message, 'error'); }
}

async function deleteSrButton(gid, mid, bid) {
  try {
    await api('DELETE', `/api/server/${gid}/selfroles/${mid}/buttons/${bid}`);
    showToast('Button entfernt.');
    location.reload();
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Leveling ────────────────────────────────────────────────── */

function toggleLvChannel() {
  const mode = document.getElementById('lv-mode').value;
  document.getElementById('lv-channel-row').style.display = mode === 'custom' ? '' : 'none';
}

async function saveLvGeneral(gid) {
  const min = parseInt(document.getElementById('lv-xp-min').value);
  const max = parseInt(document.getElementById('lv-xp-max').value);
  if (min > max) { showToast('XP Min darf nicht größer als Max sein.', 'error'); return; }
  try {
    await api('POST', `/api/server/${gid}/leveling/general`, {
      enabled:  document.getElementById('lv-enabled').checked,
      xp_min:   min,
      xp_max:   max,
      cooldown: parseInt(document.getElementById('lv-cooldown').value),
    });
    showToast('Leveling-Einstellungen gespeichert!');
  } catch(e) { showToast(e.message, 'error'); }
}

async function saveLvLevelup(gid) {
  try {
    await api('POST', `/api/server/${gid}/leveling/levelup`, {
      levelup_mode:       document.getElementById('lv-mode').value,
      levelup_channel_id: document.getElementById('lv-channel')?.value || null,
      levelup_message:    document.getElementById('lv-msg').value,
      role_stack:         document.getElementById('lv-stack').checked,
    });
    showToast('Level-Up Einstellungen gespeichert!');
  } catch(e) { showToast(e.message, 'error'); }
}

async function addLvRole(gid) {
  const level   = document.getElementById('lv-role-level').value;
  const role_id = document.getElementById('lv-role-select').value;
  if (!level || !role_id) { showToast('Level und Rolle auswählen.', 'error'); return; }
  try {
    const res = await api('POST', `/api/server/${gid}/leveling/level-roles`, { level: parseInt(level), role_id });
    const roleName = document.querySelector(`#lv-role-select option[value="${role_id}"]`)?.textContent || role_id;
    const row = document.createElement('div');
    row.className = 'lv-role-row'; row.id = `lvr-${res.id}`;
    row.innerHTML = `<span class="badge badge-level">Level ${level}</span><span class="role-chip">${roleName}</span><button class="btn btn-sm btn-danger" onclick="deleteLvRole('${gid}',${res.id})">×</button>`;
    document.getElementById('lv-roles-list').appendChild(row);
    document.getElementById('lv-role-level').value = '';
    document.getElementById('lv-role-select').value = '';
    showToast('Level-Rolle hinzugefügt!');
  } catch(e) { showToast(e.message, 'error'); }
}

async function deleteLvRole(gid, id) {
  try {
    await api('DELETE', `/api/server/${gid}/leveling/level-roles/${id}`);
    document.getElementById(`lvr-${id}`)?.remove();
    showToast('Level-Rolle entfernt.');
  } catch(e) { showToast(e.message, 'error'); }
}

async function addXpMr(gid) {
  const role_id    = document.getElementById('xpmr-role').value;
  const multiplier = document.getElementById('xpmr-mult').value;
  if (!role_id) { showToast('Bitte eine Rolle wählen.', 'error'); return; }
  try {
    const res = await api('POST', `/api/server/${gid}/leveling/xp-mult-roles`, { role_id, multiplier: parseFloat(multiplier) });
    const name = document.querySelector(`#xpmr-role option[value="${role_id}"]`)?.textContent || role_id;
    const row = document.createElement('div');
    row.className = 'lv-role-row'; row.id = `xpmr-${res.id}`;
    row.innerHTML = `<span class="role-chip">${name}</span><span class="multiplier-badge">×${multiplier}</span><button class="btn btn-sm btn-danger" onclick="deleteXpMr('${gid}',${res.id})">×</button>`;
    document.getElementById('xp-mr-list').appendChild(row);
    showToast('Multiplikator hinzugefügt!');
  } catch(e) { showToast(e.message, 'error'); }
}

async function deleteXpMr(gid, id) {
  try {
    await api('DELETE', `/api/server/${gid}/leveling/xp-mult-roles/${id}`);
    document.getElementById(`xpmr-${id}`)?.remove();
    showToast('Multiplikator entfernt.');
  } catch(e) { showToast(e.message, 'error'); }
}

async function addXpMc(gid) {
  const channel_id = document.getElementById('xpmc-ch').value;
  const multiplier = document.getElementById('xpmc-mult').value;
  if (!channel_id) { showToast('Bitte einen Channel wählen.', 'error'); return; }
  try {
    const res = await api('POST', `/api/server/${gid}/leveling/xp-mult-channels`, { channel_id, multiplier: parseFloat(multiplier) });
    const name = document.querySelector(`#xpmc-ch option[value="${channel_id}"]`)?.textContent || channel_id;
    const row = document.createElement('div');
    row.className = 'lv-role-row'; row.id = `xpmc-${res.id}`;
    row.innerHTML = `<span class="badge badge-channel">${name}</span><span class="multiplier-badge">×${multiplier}</span><button class="btn btn-sm btn-danger" onclick="deleteXpMc('${gid}',${res.id})">×</button>`;
    document.getElementById('xp-mc-list').appendChild(row);
    showToast('Channel-Multiplikator hinzugefügt!');
  } catch(e) { showToast(e.message, 'error'); }
}

async function deleteXpMc(gid, id) {
  try {
    await api('DELETE', `/api/server/${gid}/leveling/xp-mult-channels/${id}`);
    document.getElementById(`xpmc-${id}`)?.remove();
    showToast('Multiplikator entfernt.');
  } catch(e) { showToast(e.message, 'error'); }
}

async function addNoXpCh(gid, sel) {
  const channel_id = sel.value; if (!channel_id) return; sel.value = '';
  try {
    const res = await api('POST', `/api/server/${gid}/leveling/no-xp-channels`, { channel_id });
    const name = document.querySelector(`#noxpch-add option[value="${channel_id}"]`)?.textContent || channel_id;
    const chip = document.createElement('span');
    chip.className = 'role-chip'; chip.id = `noxpch-${res.id}`;
    chip.style.cssText = 'background:var(--bg4);color:var(--text1)';
    chip.innerHTML = `${name}<button class="chip-remove" onclick="deleteNoXpCh('${gid}',${res.id})">×</button>`;
    document.getElementById('no-xp-ch-list').appendChild(chip);
    showToast('No-XP Channel hinzugefügt.');
  } catch(e) { showToast(e.message, 'error'); }
}

async function deleteNoXpCh(gid, id) {
  try {
    await api('DELETE', `/api/server/${gid}/leveling/no-xp-channels/${id}`);
    document.getElementById(`noxpch-${id}`)?.remove();
  } catch(e) { showToast(e.message, 'error'); }
}

async function addNoXpRo(gid, sel) {
  const role_id = sel.value; if (!role_id) return; sel.value = '';
  try {
    const res = await api('POST', `/api/server/${gid}/leveling/no-xp-roles`, { role_id });
    const name = document.querySelector(`#noxpro-add option[value="${role_id}"]`)?.textContent || role_id;
    const chip = document.createElement('span');
    chip.className = 'role-chip'; chip.id = `noxpro-${res.id}`;
    chip.innerHTML = `${name}<button class="chip-remove" onclick="deleteNoXpRo('${gid}',${res.id})">×</button>`;
    document.getElementById('no-xp-ro-list').appendChild(chip);
    showToast('No-XP Rolle hinzugefügt.');
  } catch(e) { showToast(e.message, 'error'); }
}

async function deleteNoXpRo(gid, id) {
  try {
    await api('DELETE', `/api/server/${gid}/leveling/no-xp-roles/${id}`);
    document.getElementById(`noxpro-${id}`)?.remove();
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Util ────────────────────────────────────────────────────── */
function _esc(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
