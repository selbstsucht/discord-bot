import os
import requests
from flask import Flask, session, redirect, request, url_for, render_template, jsonify
from dotenv import load_dotenv
from database import (init_db, get_session,
                      WelcomeConfig, GoodbyeConfig, AutoRoleConfig,
                      SelfRoleMessage, SelfRoleButton)

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
        f'&redirect_uri={REDIRECT_URI}'
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
        sr_msgs  = db.query(SelfRoleMessage).filter_by(guild_id=guild_id).all()

        selfroles = []
        for sm in sr_msgs:
            color_hex = f'#{sm.embed_color:06x}' if sm.embed_color else '#5865f2'
            selfroles.append({
                'id':              sm.id,
                'channel_id':      sm.channel_id,
                'message_id':      sm.message_id,
                'embed_title':     sm.embed_title,
                'embed_description': sm.embed_description,
                'embed_color':     color_hex,
                'embed_image_url': sm.embed_image_url or '',
                'buttons': [
                    {'id': b.id, 'role_id': b.role_id,
                     'label': b.label, 'emoji': b.emoji or '', 'style': b.style}
                    for b in sm.buttons
                ]
            })

        channels  = _text_channels(guild_id)
        roles     = _roles(guild_id)
        guild_info = _guild(guild_id)

        ch_map   = {c['id']: c['name'] for c in channels}
        role_map = {r['id']: r['name'] for r in roles}

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

        embed = {
            'title':       sm.embed_title,
            'description': sm.embed_description,
            'color':       sm.embed_color or 0x5865F2,
        }
        if sm.embed_image_url:
            embed['image'] = {'url': sm.embed_image_url}

        components = []
        row = {'type': 1, 'components': []}
        for i, btn in enumerate(sm.buttons[:25]):
            if i > 0 and i % 5 == 0:
                components.append(row)
                row = {'type': 1, 'components': []}
            b = {
                'type':      2,
                'label':     btn.label,
                'custom_id': f'selfrole_{sm.id}_{btn.role_id}',
                'style':     STYLE_MAP.get(btn.style, 1),
            }
            if btn.emoji:
                b['emoji'] = {'name': btn.emoji}
            row['components'].append(b)
        if row['components']:
            components.append(row)

        payload = {'embeds': [embed], 'components': components}

        if sm.message_id:
            r = requests.patch(
                f'{API}/channels/{sm.channel_id}/messages/{sm.message_id}',
                json=payload, headers=_bot())
        else:
            r = requests.post(
                f'{API}/channels/{sm.channel_id}/messages',
                json=payload, headers=_bot())

        if r.ok:
            sm.message_id = r.json()['id']
            db.commit()
            return jsonify({'ok': True, 'message_id': sm.message_id})
        return jsonify({'error': r.text}), 400
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


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, port=port, host='0.0.0.0')
