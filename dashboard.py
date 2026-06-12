import os
import requests
from urllib.parse import quote
from flask import Flask, session, redirect, request, url_for, render_template, jsonify
from dotenv import load_dotenv
from database import (init_db, get_session,
                      WelcomeConfig, GoodbyeConfig, AutoRoleConfig,
                      SelfRoleMessage, SelfRoleButton,
                      LevelConfig, UserLevel, LevelRole,
                      XpMultiplierRole, XpMultiplierChannel, NoXpChannel, NoXpRole,
                      BotAdminConfig, WarnEntry, BadWordConfig, WarnPunishment)

load_dotenv()
init_db()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'changeme-dev-key')

CLIENT_ID     = os.getenv('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
REDIRECT_URI  = os.getenv('DISCORD_REDIRECT_URI', 'http://localhost:5000/auth')
BOT_TOKEN     = os.getenv('BOT_TOKEN')
API           = 'https://discord.com/api/v10'

STYLE_MAP = {'primary': 1, 'secondary': 2, 'success': 3, 'danger': 4}


def _build_sr_payload(sm):
    embed = {
        'title':       sm.embed_title,
        'description': sm.embed_description,
        'color':       sm.embed_color or 0x5865F2,
    }
    if sm.embed_image_url:
        embed['image'] = {'url': sm.embed_image_url}

    itype = sm.interaction_type or 'buttons'

    if itype == 'reactions':
        return {'embeds': [embed], 'components': []}
    elif itype == 'select_menu':
        options = []
        for btn in sm.buttons[:25]:
            opt = {'label': btn.label[:100], 'value': btn.role_id}
            if btn.emoji:
                opt['emoji'] = {'name': btn.emoji}
            options.append(opt)
        if not options:
            return None
        max_vals = 1 if sm.single_select else min(len(options), 25)
        return {'embeds': [embed], 'components': [{
            'type': 1,
            'components': [{
                'type':        3,
                'custom_id':   f'selfrole_menu_{sm.id}',
                'options':     options,
                'min_values':  0,
                'max_values':  max_vals,
                'placeholder': 'Rolle wählen…' if sm.single_select else 'Rollen wählen…',
            }]
        }]}
    else:
        components, row = [], {'type': 1, 'components': []}
        for i, btn in enumerate(sm.buttons[:25]):
            if i > 0 and i % 5 == 0:
                components.append(row)
                row = {'type': 1, 'components': []}
            b = {'type': 2, 'label': btn.label,
                 'custom_id': f'selfrole_{sm.id}_{btn.role_id}',
                 'style': STYLE_MAP.get(btn.style, 1)}
            if btn.emoji:
                b['emoji'] = {'name': btn.emoji}
            row['components'].append(b)
        if row['components']:
            components.append(row)
        return {'embeds': [embed], 'components': components}


def _post_sr_message(sm, db):
    if not sm.channel_id:
        return False, 'Kein Channel ausgewählt'
    payload = _build_sr_payload(sm)
    if payload is None:
        return False, 'Mindestens eine Option/Rolle erforderlich'
    itype = sm.interaction_type or 'buttons'
    if itype == 'reactions' and sm.message_id:
        requests.delete(f'{API}/channels/{sm.channel_id}/messages/{sm.message_id}/reactions',
                        headers={'Authorization': f'Bot {BOT_TOKEN}'})
    if sm.message_id:
        r = requests.patch(f'{API}/channels/{sm.channel_id}/messages/{sm.message_id}',
                           json=payload, headers=_bot())
    else:
        r = requests.post(f'{API}/channels/{sm.channel_id}/messages',
                          json=payload, headers=_bot())
    if not r.ok:
        return False, r.text
    sm.message_id = r.json()['id']
    db.commit()
    if itype == 'reactions':
        for btn in sm.buttons:
            if btn.emoji:
                requests.put(
                    f'{API}/channels/{sm.channel_id}/messages/{sm.message_id}'
                    f'/reactions/{quote(btn.emoji.strip(), safe="")}/@me',
                    headers={'Authorization': f'Bot {BOT_TOKEN}'})
    return True, None


def _bearer(token):
    return {'Authorization': f'Bearer {token}'}


def _bot():
    return {'Authorization': f'Bot {BOT_TOKEN}', 'Content-Type': 'application/json'}


def _text_channels(guild_id):
    r = requests.get(f'{API}/guilds/{guild_id}/channels', headers=_bot())
    if not r.ok:
        return []
    return sorted([c for c in r.json() if c['type'] == 0], key=lambda c: c['position'])


def _roles(guild_id):
    r = requests.get(f'{API}/guilds/{guild_id}/roles', headers=_bot())
    if not r.ok:
        return []
    return [ro for ro in r.json() if ro['name'] != '@everyone']


def _guild(guild_id):
    r = requests.get(f'{API}/guilds/{guild_id}', headers=_bot())
    return r.json() if r.ok else {}


def _user_guilds(token):
    r = requests.get(f'{API}/users/@me/guilds', headers=_bearer(token))
    return r.json() if r.ok else []


def _bot_guild_ids():
    r = requests.get(f'{API}/users/@me/guilds', headers={'Authorization': f'Bot {BOT_TOKEN}'})
    if not r.ok:
        return set()
    return {g['id'] for g in r.json()}


def _require_login():
    return 'user' not in session


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('servers') if 'user' in session else url_for('login'))


@app.route('/login')
def login():
    if 'user' in session:
        return redirect(url_for('servers'))
    return render_template('login.html')


@app.route('/oauth')
def oauth():
    return redirect(
        f'https://discord.com/oauth2/authorize'
        f'?client_id={CLIENT_ID}'
        f'&redirect_uri={quote(REDIRECT_URI, safe="")}'
        f'&response_type=code'
        f'&scope=identify+guilds'
    )


@app.route('/auth')
def auth_callback():
    code = request.args.get('code')
    if not code:
        return redirect(url_for('login'))
    r = requests.post(f'{API}/oauth2/token', data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
    })
    if not r.ok:
        return redirect(url_for('login'))
    token_data = r.json()
    user_r = requests.get(f'{API}/users/@me', headers=_bearer(token_data['access_token']))
    if not user_r.ok:
        return redirect(url_for('login'))
    session['user']         = user_r.json()
    session['access_token'] = token_data['access_token']
    return redirect(url_for('servers'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Server selection ──────────────────────────────────────────────────────────

@app.route('/servers')
def servers():
    if _require_login():
        return redirect(url_for('login'))
    user_guilds   = _user_guilds(session['access_token'])
    bot_guild_ids = _bot_guild_ids()

    admin_guilds = []
    for g in user_guilds:
        perms = int(g.get('permissions', 0))
        if not ((perms & 0x8) or (perms & 0x20)):
            continue
        icon = g.get('icon')
        g['icon_url']    = f'https://cdn.discordapp.com/icons/{g["id"]}/{icon}.png' if icon else None
        g['bot_present'] = g['id'] in bot_guild_ids
        admin_guilds.append(g)

    invite = (
        f'https://discord.com/oauth2/authorize'
        f'?client_id={CLIENT_ID}&permissions=8&scope=bot+applications.commands'
    )
    return render_template('servers.html', guilds=admin_guilds,
                           user=session['user'], invite_base=invite)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/server/<guild_id>')
def dashboard(guild_id):
    if _require_login():
        return redirect(url_for('login'))
    db = get_session()
    try:
        welcome  = db.query(WelcomeConfig).filter_by(guild_id=guild_id).first()
        goodbye  = db.query(GoodbyeConfig).filter_by(guild_id=guild_id).first()
        autorole = db.query(AutoRoleConfig).filter_by(guild_id=guild_id).first()
        sr_msgs  = db.query(SelfRoleMessage).filter_by(guild_id=guild_id).order_by(SelfRoleMessage.sort_order).all()

        selfroles = []
        for sm in sr_msgs:
            color_hex = f'#{sm.embed_color:06x}' if sm.embed_color else '#5865f2'
            selfroles.append({
                'id':               sm.id,
                'channel_id':       sm.channel_id,
                'message_id':       sm.message_id,
                'embed_title':      sm.embed_title,
                'embed_description': sm.embed_description,
                'embed_color':      color_hex,
                'embed_image_url':  sm.embed_image_url or '',
                'interaction_type': sm.interaction_type or 'buttons',
                'single_select':    bool(sm.single_select),
                'buttons': [
                    {'id': b.id, 'role_id': b.role_id,
                     'label': b.label, 'emoji': b.emoji or '', 'style': b.style}
                    for b in sm.buttons
                ]
            })

        channels   = _text_channels(guild_id)
        roles      = _roles(guild_id)
        guild_info = _guild(guild_id)

        ch_map   = {c['id']: c['name'] for c in channels}
        role_map = {r['id']: r['name'] for r in roles}

        # Leveling data
        lv_cfg    = db.query(LevelConfig).filter_by(guild_id=guild_id).first()
        lv_roles  = db.query(LevelRole).filter_by(guild_id=guild_id).order_by(LevelRole.level).all()
        xp_mr     = db.query(XpMultiplierRole).filter_by(guild_id=guild_id).all()
        xp_mc     = db.query(XpMultiplierChannel).filter_by(guild_id=guild_id).all()
        no_xp_ch  = db.query(NoXpChannel).filter_by(guild_id=guild_id).all()
        no_xp_ro  = db.query(NoXpRole).filter_by(guild_id=guild_id).all()

        bot_admins = db.query(BotAdminConfig).filter_by(guild_id=guild_id).all()
        bad_words      = db.query(BadWordConfig).filter_by(guild_id=guild_id).all()
        warn_punishments = db.query(WarnPunishment).filter_by(guild_id=guild_id).order_by(WarnPunishment.warn_count).all()

        return render_template('dashboard.html',
            user=session['user'],
            guild=guild_info,
            guild_id=guild_id,
            channels=channels,
            roles=roles,
            ch_map=ch_map,
            role_map=role_map,
            welcome=welcome,
            goodbye=goodbye,
            autorole=autorole,
            selfroles=selfroles,
            lv_cfg=lv_cfg,
            lv_roles=[{'id': r.id, 'level': r.level, 'role_id': r.role_id} for r in lv_roles],
            xp_mr=[{'id': r.id, 'role_id': r.role_id, 'multiplier': r.multiplier} for r in xp_mr],
            xp_mc=[{'id': r.id, 'channel_id': r.channel_id, 'multiplier': r.multiplier} for r in xp_mc],
            no_xp_ch=[{'id': r.id, 'channel_id': r.channel_id} for r in no_xp_ch],
            no_xp_ro=[{'id': r.id, 'role_id': r.role_id} for r in no_xp_ro],
            cmd_channels=lv_cfg.cmd_channels if lv_cfg else [],
            bot_admins=[{'id': a.id, 'user_id': a.user_id} for a in bot_admins],
            bad_words=[{'id': w.id, 'word': w.word, 'enabled': w.enabled} for w in bad_words],
            warn_punishments=[{
                'id': p.id, 'warn_count': p.warn_count,
                'action': p.action, 'timeout_duration': p.timeout_duration or ''
            } for p in warn_punishments],
        )
    finally:
        db.close()


# ── API: Welcome / Goodbye ────────────────────────────────────────────────────

@app.route('/api/server/<gid>/welcome', methods=['POST'])
def api_welcome(gid):
    if _require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        cfg = db.query(WelcomeConfig).filter_by(guild_id=gid).first()
        if not cfg:
            cfg = WelcomeConfig(guild_id=gid)
            db.add(cfg)
        cfg.enabled    = bool(data.get('enabled'))
        cfg.channel_id = data.get('channel_id') or None
        cfg.message    = data.get('message', cfg.message)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/goodbye', methods=['POST'])
def api_goodbye(gid):
    if _require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        cfg = db.query(GoodbyeConfig).filter_by(guild_id=gid).first()
        if not cfg:
            cfg = GoodbyeConfig(guild_id=gid)
            db.add(cfg)
        cfg.enabled    = bool(data.get('enabled'))
        cfg.channel_id = data.get('channel_id') or None
        cfg.message    = data.get('message', cfg.message)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


# ── API: Auto-Roles ───────────────────────────────────────────────────────────

@app.route('/api/server/<gid>/autorole', methods=['POST'])
def api_autorole(gid):
    if _require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        cfg = db.query(AutoRoleConfig).filter_by(guild_id=gid).first()
        if not cfg:
            cfg = AutoRoleConfig(guild_id=gid)
            db.add(cfg)
        cfg.enabled  = bool(data.get('enabled'))
        cfg.role_ids = data.get('role_ids', [])
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


# ── API: Self-Role Messages ───────────────────────────────────────────────────

@app.route('/api/server/<gid>/selfroles', methods=['POST'])
def api_sr_create(gid):
    if _require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        color_int = int(data.get('embed_color', '#5865f2').lstrip('#'), 16)
        sm = SelfRoleMessage(
            guild_id          = gid,
            channel_id        = data.get('channel_id') or None,
            embed_title       = data.get('embed_title', 'Self Roles'),
            embed_description = data.get('embed_description', 'Wähle deine Rollen!'),
            embed_color       = color_int,
            embed_image_url   = data.get('embed_image_url') or None,
            interaction_type  = data.get('interaction_type', 'buttons'),
            single_select     = bool(data.get('single_select', False)),
        )
        db.add(sm)
        db.commit()
        return jsonify({'ok': True, 'id': sm.id})
    finally:
        db.close()


@app.route('/api/server/<gid>/selfroles/<int:mid>', methods=['PUT'])
def api_sr_update(gid, mid):
    if _require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        sm = db.query(SelfRoleMessage).filter_by(id=mid, guild_id=gid).first()
        if not sm:
            return jsonify({'error': 'Not found'}), 404
        if 'embed_title'       in data: sm.embed_title       = data['embed_title']
        if 'embed_description' in data: sm.embed_description = data['embed_description']
        if 'embed_color'       in data: sm.embed_color       = int(data['embed_color'].lstrip('#'), 16)
        if 'embed_image_url'   in data: sm.embed_image_url   = data['embed_image_url'] or None
        if 'channel_id'        in data: sm.channel_id        = data['channel_id'] or None
        if 'interaction_type'  in data: sm.interaction_type  = data['interaction_type']
        if 'single_select'     in data: sm.single_select     = bool(data['single_select'])
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/selfroles/<int:mid>', methods=['DELETE'])
def api_sr_delete(gid, mid):
    if _require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        sm = db.query(SelfRoleMessage).filter_by(id=mid, guild_id=gid).first()
        if not sm:
            return jsonify({'error': 'Not found'}), 404
        if sm.message_id and sm.channel_id:
            requests.delete(f'{API}/channels/{sm.channel_id}/messages/{sm.message_id}',
                            headers=_bot())
        db.delete(sm)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/selfroles/<int:mid>/post', methods=['POST'])
def api_sr_post(gid, mid):
    if _require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        sm = db.query(SelfRoleMessage).filter_by(id=mid, guild_id=gid).first()
        if not sm:
            return jsonify({'error': 'Not found'}), 404
        if not sm.channel_id:
            return jsonify({'error': 'Kein Channel ausgewählt'}), 400

        ok, err = _post_sr_message(sm, db)
        if ok:
            return jsonify({'ok': True, 'message_id': sm.message_id})
        return jsonify({'error': err}), 400
    finally:
        db.close()


# ── API: Self-Role Reorder ───────────────────────────────────────────────────

@app.route('/api/server/<gid>/selfroles/reorder', methods=['POST'])
def api_sr_reorder(gid):
    if _require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    ordered_ids = [int(x) for x in request.json.get('order', [])]
    db = get_session()
    try:
        for i, mid in enumerate(ordered_ids):
            sm = db.query(SelfRoleMessage).filter_by(id=mid, guild_id=gid).first()
            if sm:
                sm.sort_order = i
        db.commit()

        # Group already-posted messages by channel
        from collections import defaultdict
        by_channel = defaultdict(list)
        for mid in ordered_ids:
            sm = db.query(SelfRoleMessage).filter_by(id=mid, guild_id=gid).first()
            if sm and sm.channel_id and sm.message_id:
                by_channel[sm.channel_id].append(sm)

        errors = []
        for channel_id, msgs in by_channel.items():
            if len(msgs) < 2:
                continue
            for sm in msgs:
                requests.delete(f'{API}/channels/{channel_id}/messages/{sm.message_id}',
                                headers={'Authorization': f'Bot {BOT_TOKEN}'})
                sm.message_id = None
            db.commit()
            for sm in msgs:
                ok, err = _post_sr_message(sm, db)
                if not ok:
                    errors.append(f'{sm.embed_title}: {err}')

        if errors:
            return jsonify({'ok': False, 'errors': errors}), 207
        return jsonify({'ok': True})
    finally:
        db.close()


# ── API: Self-Role Buttons ────────────────────────────────────────────────────

@app.route('/api/server/<gid>/selfroles/<int:mid>/buttons', methods=['POST'])
def api_sr_btn_add(gid, mid):
    if _require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        sm = db.query(SelfRoleMessage).filter_by(id=mid, guild_id=gid).first()
        if not sm:
            return jsonify({'error': 'Not found'}), 404
        btn = SelfRoleButton(
            message_id_fk = mid,
            role_id       = data['role_id'],
            label         = data['label'],
            emoji         = data.get('emoji') or None,
            style         = data.get('style', 'primary'),
        )
        db.add(btn)
        db.commit()
        return jsonify({'ok': True, 'id': btn.id})
    finally:
        db.close()


@app.route('/api/server/<gid>/selfroles/<int:mid>/buttons/<int:bid>', methods=['DELETE'])
def api_sr_btn_del(gid, mid, bid):
    if _require_login():
        return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        btn = db.query(SelfRoleButton).filter_by(id=bid, message_id_fk=mid).first()
        if not btn:
            return jsonify({'error': 'Not found'}), 404
        db.delete(btn)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


# ── API: Leveling ─────────────────────────────────────────────────────────────

@app.route('/api/server/<gid>/leveling/general', methods=['POST'])
def api_lv_general(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        cfg = db.query(LevelConfig).filter_by(guild_id=gid).first()
        if not cfg:
            cfg = LevelConfig(guild_id=gid)
            db.add(cfg)
        cfg.enabled  = bool(data.get('enabled'))
        cfg.xp_min   = int(data.get('xp_min', 15))
        cfg.xp_max   = int(data.get('xp_max', 25))
        cfg.cooldown = int(data.get('cooldown', 60))
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/levelup', methods=['POST'])
def api_lv_levelup(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        cfg = db.query(LevelConfig).filter_by(guild_id=gid).first()
        if not cfg:
            cfg = LevelConfig(guild_id=gid)
            db.add(cfg)
        cfg.levelup_mode       = data.get('levelup_mode', 'current')
        cfg.levelup_channel_id = data.get('levelup_channel_id') or None
        cfg.levelup_message    = data.get('levelup_message', cfg.levelup_message)
        cfg.role_stack         = bool(data.get('role_stack', True))
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/voice', methods=['POST'])
def api_lv_voice(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        cfg = db.query(LevelConfig).filter_by(guild_id=gid).first()
        if not cfg:
            cfg = LevelConfig(guild_id=gid)
            db.add(cfg)
        cfg.voice_enabled         = bool(data.get('voice_enabled'))
        cfg.voice_xp_min          = int(data.get('voice_xp_min', 10))
        cfg.voice_xp_max          = int(data.get('voice_xp_max', 20))
        cfg.voice_interval        = int(data.get('voice_interval', 5))
        cfg.voice_ignore_muted    = bool(data.get('voice_ignore_muted', True))
        cfg.voice_ignore_deafened = bool(data.get('voice_ignore_deafened', True))
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/level-roles', methods=['POST'])
def api_lv_role_add(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        lr = LevelRole(guild_id=gid, level=int(data['level']), role_id=data['role_id'])
        db.add(lr)
        db.commit()
        return jsonify({'ok': True, 'id': lr.id})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/level-roles/<int:rid>', methods=['DELETE'])
def api_lv_role_del(gid, rid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        lr = db.query(LevelRole).filter_by(id=rid, guild_id=gid).first()
        if lr: db.delete(lr)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/xp-mult-roles', methods=['POST'])
def api_lv_xpmr_add(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        r = XpMultiplierRole(guild_id=gid, role_id=data['role_id'], multiplier=float(data.get('multiplier', 2.0)))
        db.add(r)
        db.commit()
        return jsonify({'ok': True, 'id': r.id})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/xp-mult-roles/<int:rid>', methods=['DELETE'])
def api_lv_xpmr_del(gid, rid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        r = db.query(XpMultiplierRole).filter_by(id=rid, guild_id=gid).first()
        if r: db.delete(r)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/xp-mult-channels', methods=['POST'])
def api_lv_xpmc_add(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        r = XpMultiplierChannel(guild_id=gid, channel_id=data['channel_id'], multiplier=float(data.get('multiplier', 2.0)))
        db.add(r)
        db.commit()
        return jsonify({'ok': True, 'id': r.id})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/xp-mult-channels/<int:rid>', methods=['DELETE'])
def api_lv_xpmc_del(gid, rid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        r = db.query(XpMultiplierChannel).filter_by(id=rid, guild_id=gid).first()
        if r: db.delete(r)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/no-xp-channels', methods=['POST'])
def api_lv_noxpch_add(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        r = NoXpChannel(guild_id=gid, channel_id=data['channel_id'])
        db.add(r)
        db.commit()
        return jsonify({'ok': True, 'id': r.id})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/no-xp-channels/<int:rid>', methods=['DELETE'])
def api_lv_noxpch_del(gid, rid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        r = db.query(NoXpChannel).filter_by(id=rid, guild_id=gid).first()
        if r: db.delete(r)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/no-xp-roles', methods=['POST'])
def api_lv_noxpr_add(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        r = NoXpRole(guild_id=gid, role_id=data['role_id'])
        db.add(r)
        db.commit()
        return jsonify({'ok': True, 'id': r.id})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/no-xp-roles/<int:rid>', methods=['DELETE'])
def api_lv_noxpr_del(gid, rid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        r = db.query(NoXpRole).filter_by(id=rid, guild_id=gid).first()
        if r: db.delete(r)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/cmd-channels', methods=['POST'])
def api_lv_cmdch_add(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    db = get_session()
    try:
        cfg = db.query(LevelConfig).filter_by(guild_id=gid).first()
        if not cfg:
            cfg = LevelConfig(guild_id=gid)
            db.add(cfg)
        chs = cfg.cmd_channels
        ch_id = data.get('channel_id')
        if ch_id and ch_id not in chs:
            chs.append(ch_id)
            cfg.cmd_channels = chs
            db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/leveling/cmd-channels/<channel_id>', methods=['DELETE'])
def api_lv_cmdch_del(gid, channel_id):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        cfg = db.query(LevelConfig).filter_by(guild_id=gid).first()
        if cfg:
            chs = cfg.cmd_channels
            if channel_id in chs:
                chs.remove(channel_id)
                cfg.cmd_channels = chs
                db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


# ── API: Bot-Admins ───────────────────────────────────────────────────────────

@app.route('/api/server/<gid>/bot-admins', methods=['POST'])
def api_admin_add(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    user_id = request.json.get('user_id', '').strip()
    if not user_id.isdigit():
        return jsonify({'error': 'Ungültige User-ID'}), 400
    db = get_session()
    try:
        exists = db.query(BotAdminConfig).filter_by(guild_id=gid, user_id=user_id).first()
        if exists:
            return jsonify({'error': 'Bereits vorhanden'}), 409
        entry = BotAdminConfig(guild_id=gid, user_id=user_id)
        db.add(entry)
        db.commit()
        return jsonify({'ok': True, 'id': entry.id})
    finally:
        db.close()


@app.route('/api/server/<gid>/bot-admins/<int:aid>', methods=['DELETE'])
def api_admin_del(gid, aid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        entry = db.query(BotAdminConfig).filter_by(id=aid, guild_id=gid).first()
        if entry:
            db.delete(entry)
            db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


# ── API: Moderation / Bad-Words ───────────────────────────────────────────────

@app.route('/api/server/<gid>/moderation/warn-punishments', methods=['POST'])
def api_wp_add(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    data = request.json or {}
    warn_count = data.get('warn_count')
    action     = data.get('action', '').strip()
    timeout_dur = data.get('timeout_duration', '').strip() or None
    if not isinstance(warn_count, int) or warn_count < 1:
        return jsonify({'error': 'Ungültige Warn-Anzahl'}), 400
    if action not in ('timeout', 'kick', 'ban'):
        return jsonify({'error': 'Ungültige Aktion'}), 400
    db = get_session()
    try:
        exists = db.query(WarnPunishment).filter_by(guild_id=gid, warn_count=warn_count).first()
        if exists:
            return jsonify({'error': f'Für Warn {warn_count} existiert bereits eine Strafe'}), 409
        entry = WarnPunishment(guild_id=gid, warn_count=warn_count,
                               action=action, timeout_duration=timeout_dur)
        db.add(entry)
        db.commit()
        return jsonify({'ok': True, 'id': entry.id})
    finally:
        db.close()


@app.route('/api/server/<gid>/moderation/warn-punishments/<int:pid>', methods=['DELETE'])
def api_wp_del(gid, pid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        entry = db.query(WarnPunishment).filter_by(id=pid, guild_id=gid).first()
        if entry:
            db.delete(entry)
            db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/moderation/badwords', methods=['POST'])
def api_bw_add(gid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    word = (request.json or {}).get('word', '').strip().lower()
    if not word:
        return jsonify({'error': 'Kein Wort angegeben'}), 400
    db = get_session()
    try:
        exists = db.query(BadWordConfig).filter_by(guild_id=gid, word=word).first()
        if exists:
            return jsonify({'error': 'Bereits vorhanden'}), 409
        entry = BadWordConfig(guild_id=gid, word=word, enabled=True)
        db.add(entry)
        db.commit()
        return jsonify({'ok': True, 'id': entry.id})
    finally:
        db.close()


@app.route('/api/server/<gid>/moderation/badwords/<int:wid>', methods=['DELETE'])
def api_bw_del(gid, wid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        entry = db.query(BadWordConfig).filter_by(id=wid, guild_id=gid).first()
        if entry:
            db.delete(entry)
            db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()


@app.route('/api/server/<gid>/moderation/badwords/<int:wid>/toggle', methods=['POST'])
def api_bw_toggle(gid, wid):
    if _require_login(): return jsonify({'error': 'Unauthorized'}), 401
    db = get_session()
    try:
        entry = db.query(BadWordConfig).filter_by(id=wid, guild_id=gid).first()
        if not entry:
            return jsonify({'error': 'Nicht gefunden'}), 404
        entry.enabled = not entry.enabled
        db.commit()
        return jsonify({'ok': True, 'enabled': entry.enabled})
    finally:
        db.close()


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, port=port, host='0.0.0.0')
