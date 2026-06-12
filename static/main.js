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
function _srTypeHints() {
  return {
    buttons:    'Nutzer klicken auf einen Button um eine Rolle zu erhalten/abzugeben.',
    reactions:  'Nutzer reagieren mit einem Emoji um eine Rolle zu erhalten. Emoji muss bei jeder Rolle eingetragen sein.',
    select_menu:'Nutzer wählen Rollen aus einem scrollbaren Dropdown-Menü.',
  };
}

function updateTypeHint() {
  const val  = document.getElementById('m-type')?.value;
  const hint = document.getElementById('m-type-hint');
  if (hint) hint.textContent = (_srTypeHints()[val] || '');
}

function _buildSrModal({ title, gid, submitLabel, defaults = {} }) {
  const channelOptions = (window.ALL_CHANNELS || [])
    .map(c => `<option value="${c.id}" ${c.id === (defaults.channel_id || '') ? 'selected' : ''}># ${c.name}</option>`).join('');
  const itype  = defaults.interaction_type || 'buttons';
  const single = defaults.single_select    || false;
  const color  = defaults.embed_color      || '#5865f2';

  return `
    <div class="modal-title">${title}</div>
    <div class="modal-form">
      <label>Titel
        <input class="input" id="m-title" value="${_esc(defaults.embed_title || 'Self Roles')}" maxlength="256">
      </label>
      <label>Beschreibung
        <textarea class="textarea" id="m-desc" rows="3">${_esc(defaults.embed_description || 'Klicke auf einen Button um eine Rolle zu erhalten!')}</textarea>
      </label>
      <label>Farbe
        <div class="color-row">
          <input type="color" id="m-color-picker" value="${color}"
                 oninput="document.getElementById('m-color').value=this.value">
          <input class="input" id="m-color" value="${color}" placeholder="#5865f2" maxlength="7"
                 oninput="syncColor(this.value)">
        </div>
      </label>
      <label>Bild-URL (optional)
        <input class="input" id="m-img" value="${_esc(defaults.embed_image_url || '')}" placeholder="https://…">
      </label>
      <label>Channel
        <select class="select" id="m-channel">
          <option value="">— Channel wählen —</option>
          ${channelOptions}
        </select>
      </label>
      <label>Interaktionstyp
        <select class="select" id="m-type" onchange="updateTypeHint()">
          <option value="buttons"    ${itype === 'buttons'     ? 'selected' : ''}>🔘 Buttons</option>
          <option value="reactions"  ${itype === 'reactions'   ? 'selected' : ''}>⚡ Reaction Roles</option>
          <option value="select_menu"${itype === 'select_menu' ? 'selected' : ''}>📋 Dropdown-Menü</option>
        </select>
      </label>
      <p class="hint" id="m-type-hint">${_esc(_srTypeHints()[itype] || '')}</p>
      <label class="toggle-label" style="margin-top:4px">
        <span>Nur eine Rolle wählbar (Einzelwahl)</span>
        <label class="toggle">
          <input type="checkbox" id="m-single" ${single ? 'checked' : ''}>
          <span class="toggle-slider"></span>
        </label>
      </label>
      <p class="hint">An = Nutzer kann immer nur eine Rolle aus dieser Nachricht haben.</p>
      <div class="modal-actions">
        <button class="btn btn-ghost" onclick="closeModal()">Abbrechen</button>
        <button class="btn btn-primary" onclick="submitSrForm('${gid}')">${submitLabel}</button>
      </div>
    </div>
  `;
}

function openCreateModal(gid) {
  _currentEditId = null;
  openModal(_buildSrModal({ title: 'Neue Self-Role Nachricht', gid, submitLabel: 'Erstellen' }));
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
    interaction_type:  document.getElementById('m-type').value,
    single_select:     document.getElementById('m-single').checked,
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
  // Inject channels into ALL_CHANNELS temporarily so _buildSrModal can use them
  const _prev = window.ALL_CHANNELS;
  window.ALL_CHANNELS = channels;
  openModal(_buildSrModal({ title: 'Nachricht bearbeiten', gid, submitLabel: 'Speichern', defaults: sr }));
  window.ALL_CHANNELS = _prev;
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

async function saveLvVoice(gid) {
  const min = parseInt(document.getElementById('lv-voice-xp-min').value);
  const max = parseInt(document.getElementById('lv-voice-xp-max').value);
  if (min > max) { showToast('XP Min darf nicht größer als Max sein.', 'error'); return; }
  try {
    await api('POST', `/api/server/${gid}/leveling/voice`, {
      voice_enabled:         document.getElementById('lv-voice-enabled').checked,
      voice_xp_min:          min,
      voice_xp_max:          max,
      voice_interval:        parseInt(document.getElementById('lv-voice-interval').value),
      voice_ignore_muted:    document.getElementById('lv-voice-ignore-muted').checked,
      voice_ignore_deafened: document.getElementById('lv-voice-ignore-deafened').checked,
    });
    showToast('Voice XP Einstellungen gespeichert!');
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

async function addCmdCh(gid, sel) {
  const channel_id = sel.value; if (!channel_id) return; sel.value = '';
  try {
    await api('POST', `/api/server/${gid}/leveling/cmd-channels`, { channel_id });
    const name = document.querySelector(`#cmdch-add option[value="${channel_id}"]`)?.textContent || `#${channel_id}`;
    const chip = document.createElement('span');
    chip.className = 'role-chip'; chip.id = `cmdch-${channel_id}`;
    chip.style.cssText = 'background:var(--bg4);color:var(--text1)';
    chip.innerHTML = `${name}<button class="chip-remove" onclick="deleteCmdCh('${gid}','${channel_id}')">×</button>`;
    document.getElementById('cmd-ch-list').appendChild(chip);
    showToast('Command-Channel hinzugefügt.');
  } catch(e) { showToast(e.message, 'error'); }
}

async function deleteCmdCh(gid, channel_id) {
  try {
    await api('DELETE', `/api/server/${gid}/leveling/cmd-channels/${channel_id}`);
    document.getElementById(`cmdch-${channel_id}`)?.remove();
    showToast('Command-Channel entfernt.');
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Bot-Admins ──────────────────────────────────────────────── */
async function addBotAdmin(gid) {
  const input = document.getElementById('admin-uid-input');
  const user_id = input.value.trim();
  if (!user_id) { showToast('Bitte eine User-ID eingeben.', 'error'); return; }
  if (!/^\d+$/.test(user_id)) { showToast('Ungültige User-ID.', 'error'); return; }
  try {
    const res = await api('POST', `/api/server/${gid}/bot-admins`, { user_id });
    document.getElementById('admin-empty')?.remove();
    const chip = document.createElement('span');
    chip.className = 'role-chip';
    chip.id = `admin-entry-${res.id}`;
    chip.innerHTML = `${user_id}<button class="chip-remove" onclick="removeBotAdmin('${gid}',${res.id})">×</button>`;
    document.getElementById('admin-list').appendChild(chip);
    input.value = '';
    showToast('Admin hinzugefügt!');
  } catch(e) { showToast(e.message, 'error'); }
}

async function removeBotAdmin(gid, id) {
  try {
    await api('DELETE', `/api/server/${gid}/bot-admins/${id}`);
    document.getElementById(`admin-entry-${id}`)?.remove();
    if (!document.querySelectorAll('#admin-list .role-chip').length) {
      const empty = document.createElement('span');
      empty.id = 'admin-empty';
      empty.className = 'text-muted';
      empty.style.fontSize = '13px';
      empty.textContent = 'Noch keine Admins hinzugefügt.';
      document.getElementById('admin-list').appendChild(empty);
    }
    showToast('Admin entfernt.');
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Moderation: Bad-Words ───────────────────────────────────── */

async function addBadWord(gid) {
  const input = document.getElementById('bw-input');
  const word = input.value.trim().toLowerCase();
  if (!word) { showToast('Bitte ein Wort eingeben.', 'error'); return; }
  try {
    const res = await api('POST', `/api/server/${gid}/moderation/badwords`, { word });
    document.getElementById('bw-empty')?.remove();
    const chip = document.createElement('span');
    chip.className = 'role-chip';
    chip.id = `bw-entry-${res.id}`;
    chip.title = 'Klicken zum Deaktivieren';
    chip.style.cursor = 'pointer';
    chip.innerHTML = `<span onclick="toggleBadWord('${gid}',${res.id})">${_esc(word)}</span><button class="chip-remove" onclick="removeBadWord('${gid}',${res.id})">×</button>`;
    document.getElementById('bw-list').appendChild(chip);
    input.value = '';
    showToast('Bad-Word hinzugefügt!');
  } catch(e) { showToast(e.message, 'error'); }
}

async function removeBadWord(gid, id) {
  try {
    await api('DELETE', `/api/server/${gid}/moderation/badwords/${id}`);
    document.getElementById(`bw-entry-${id}`)?.remove();
    if (!document.querySelectorAll('#bw-list .role-chip').length) {
      const empty = document.createElement('span');
      empty.id = 'bw-empty';
      empty.className = 'text-muted';
      empty.style.fontSize = '13px';
      empty.textContent = 'Noch keine Bad-Words eingetragen.';
      document.getElementById('bw-list').appendChild(empty);
    }
    showToast('Bad-Word entfernt.');
  } catch(e) { showToast(e.message, 'error'); }
}

async function toggleBadWord(gid, id) {
  try {
    const res = await api('POST', `/api/server/${gid}/moderation/badwords/${id}/toggle`);
    const chip = document.getElementById(`bw-entry-${id}`);
    if (!chip) return;
    if (res.enabled) {
      chip.classList.remove('chip-disabled');
      chip.title = 'Klicken zum Deaktivieren';
    } else {
      chip.classList.add('chip-disabled');
      chip.title = 'Klicken zum Aktivieren';
    }
    showToast(res.enabled ? 'Bad-Word aktiviert.' : 'Bad-Word deaktiviert.');
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Moderation: Warn-Punishments ────────────────────────────── */

function toggleWpDuration() {
  const action = document.getElementById('wp-action').value;
  document.getElementById('wp-duration-wrap').style.display = action === 'timeout' ? '' : 'none';
}

async function addWarnPunishment(gid) {
  const count    = parseInt(document.getElementById('wp-count').value);
  const action   = document.getElementById('wp-action').value;
  const duration = document.getElementById('wp-duration').value.trim();
  if (!count || count < 1) { showToast('Bitte eine gültige Warn-Anzahl eingeben.', 'error'); return; }
  if (action === 'timeout' && !duration) { showToast('Bitte eine Dauer für den Timeout angeben.', 'error'); return; }
  try {
    const res = await api('POST', `/api/server/${gid}/moderation/warn-punishments`, {
      warn_count: count, action, timeout_duration: action === 'timeout' ? duration : null
    });
    document.getElementById('wp-empty')?.remove();
    const actionLabel = action === 'timeout'
      ? `⏱ Timeout${duration ? ` (${duration})` : ''}`
      : action === 'kick' ? '👢 Kick' : '🔨 Ban';
    const row = document.createElement('div');
    row.className = 'wp-row';
    row.id = `wp-entry-${res.id}`;
    row.style.cssText = 'display:flex;align-items:center;gap:10px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:8px 14px';
    row.innerHTML = `<span class="badge badge-level" style="min-width:70px;text-align:center">Warn ${count}</span><span class="wp-action-badge wp-action-${action}">${actionLabel}</span><button class="btn btn-sm btn-danger" style="margin-left:auto" onclick="removeWarnPunishment('${gid}',${res.id})">Entfernen</button>`;
    const list = document.getElementById('wp-list');
    const rows = Array.from(list.querySelectorAll('.wp-row'));
    const after = rows.find(r => {
      const n = parseInt(r.querySelector('.badge-level')?.textContent?.replace('Warn ', '') || '0');
      return n > count;
    });
    after ? list.insertBefore(row, after) : list.appendChild(row);
    document.getElementById('wp-count').value = '';
    document.getElementById('wp-duration').value = '';
    showToast('Warn-Stufe hinzugefügt!');
  } catch(e) { showToast(e.message, 'error'); }
}

async function removeWarnPunishment(gid, id) {
  try {
    await api('DELETE', `/api/server/${gid}/moderation/warn-punishments/${id}`);
    document.getElementById(`wp-entry-${id}`)?.remove();
    if (!document.querySelectorAll('#wp-list .wp-row').length) {
      const empty = document.createElement('span');
      empty.id = 'wp-empty';
      empty.className = 'text-muted';
      empty.style.fontSize = '13px';
      empty.textContent = 'Noch keine Stufen konfiguriert.';
      document.getElementById('wp-list').appendChild(empty);
    }
    showToast('Warn-Stufe entfernt.');
  } catch(e) { showToast(e.message, 'error'); }
}

/* ── Self-Roles: Drag & Drop Sortierung ──────────────────────── */
function initSrDragDrop() {
  const list = document.getElementById('selfroles-list');
  if (!list) return;
  let dragging = null;

  list.querySelectorAll('.sr-card').forEach(card => {
    card.addEventListener('dragstart', e => {
      dragging = card;
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });
    card.addEventListener('dragend', () => {
      card.classList.remove('dragging');
      list.querySelectorAll('.sr-card').forEach(c => c.classList.remove('drag-over'));
      dragging = null;
    });
    card.addEventListener('dragover', e => {
      e.preventDefault();
      if (!dragging || card === dragging) return;
      list.querySelectorAll('.sr-card').forEach(c => c.classList.remove('drag-over'));
      card.classList.add('drag-over');
      const mid = card.getBoundingClientRect().top + card.getBoundingClientRect().height / 2;
      list.insertBefore(dragging, e.clientY < mid ? card : card.nextSibling);
    });
    card.addEventListener('drop', e => e.preventDefault());
  });
}

async function applySrOrder(gid) {
  const order = Array.from(document.querySelectorAll('#selfroles-list .sr-card'))
    .map(c => c.id.replace('sr-card-', ''));
  try {
    showToast('Reihenfolge wird angewendet…', 'info');
    await api('POST', `/api/server/${gid}/selfroles/reorder`, { order });
    showToast('Reihenfolge gespeichert und in Discord aktualisiert!');
    setTimeout(() => location.reload(), 1000);
  } catch(e) { showToast(e.message, 'error'); }
}

document.addEventListener('DOMContentLoaded', initSrDragDrop);

/* ── Util ────────────────────────────────────────────────────── */
function _esc(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
