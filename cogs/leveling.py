import time
import random
import discord
from discord import app_commands
from discord.ext import commands, tasks
from database import (get_session, LevelConfig, UserLevel, LevelRole,
                      XpMultiplierRole, XpMultiplierChannel, NoXpChannel, NoXpRole)


def xp_for_next_level(level: int) -> int:
    return (6 * level * level + 60 * level + 120) // 10


def xp_progress(total_xp: int):
    """Returns (level, xp_in_current_level, xp_needed_for_next_level)."""
    level = 0
    remaining = total_xp
    while remaining >= xp_for_next_level(level):
        remaining -= xp_for_next_level(level)
        level += 1
    return level, remaining, xp_for_next_level(level)


def level_color(level: int) -> discord.Color:
    if level < 15:  return discord.Color.from_str('#95a5a6')  # Grau   – neue Member
    if level < 25:  return discord.Color.from_str('#2ecc71')  # Grün   – ~2–8 Tage
    if level < 35:  return discord.Color.from_str('#3498db')  # Blau   – ~8–20 Tage
    if level < 50:  return discord.Color.from_str('#9b59b6')  # Lila   – ~20–54 Tage
    if level < 62:  return discord.Color.from_str('#f1c40f')  # Gold   – ~54–95 Tage
    if level < 70:  return discord.Color.from_str('#e67e22')  # Orange – ~95–130 Tage
    return discord.Color.from_str('#e74c3c')                  # Rot    – 130+ Tage


def progress_bar(current: int, total: int, length: int = 18) -> str:
    filled = int(length * current / total) if total > 0 else 0
    pct = int(100 * current / total) if total > 0 else 0
    return f'`{"▓" * filled}{"░" * (length - filled)}` {pct}%'


class LevelingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._voice_last_xp: dict[str, dict[str, int]] = {}  # {guild_id: {user_id: timestamp}}
        self.voice_xp_task.start()

    def cog_unload(self):
        self.voice_xp_task.cancel()

    # ── Shared level-up handler ───────────────────────────────────────────────

    async def _apply_level_up(self, guild, member, cfg, new_level, db, gid, fallback_channel=None):
        level_roles = db.query(LevelRole).filter_by(guild_id=gid).order_by(LevelRole.level).all()
        earned_role_ids = [lr.role_id for lr in level_roles if lr.level <= new_level]
        exact_role_ids  = [lr.role_id for lr in level_roles if lr.level == new_level]
        all_role_ids    = [lr.role_id for lr in level_roles]

        try:
            if cfg.role_stack:
                for rid in earned_role_ids:
                    role = guild.get_role(int(rid))
                    if role and role not in member.roles:
                        await member.add_roles(role, reason=f'Level {new_level} erreicht')
            else:
                for rid in all_role_ids:
                    role = guild.get_role(int(rid))
                    if role and role in member.roles and rid not in exact_role_ids:
                        await member.remove_roles(role, reason='Level-Rolle ersetzt')
                for rid in exact_role_ids:
                    role = guild.get_role(int(rid))
                    if role and role not in member.roles:
                        await member.add_roles(role, reason=f'Level {new_level} erreicht')
        except discord.Forbidden:
            pass

        if cfg.levelup_mode == 'disabled':
            return

        lv_msg = (cfg.levelup_message
                  .replace('{user}', member.mention)
                  .replace('{username}', member.display_name)
                  .replace('{level}', str(new_level))
                  .replace('{server}', guild.name))

        if cfg.levelup_mode == 'dm':
            try:
                await member.send(lv_msg)
            except discord.Forbidden:
                pass
        elif cfg.levelup_mode == 'custom' and cfg.levelup_channel_id:
            ch = guild.get_channel(int(cfg.levelup_channel_id))
            if ch:
                await ch.send(lv_msg)
        elif fallback_channel:
            await fallback_channel.send(lv_msg)

    # ── Message XP ───────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        db = get_session()
        try:
            gid = str(message.guild.id)
            cfg = db.query(LevelConfig).filter_by(guild_id=gid).first()
            if not cfg or not cfg.enabled:
                return

            no_xp_ch = {r.channel_id for r in db.query(NoXpChannel).filter_by(guild_id=gid).all()}
            if str(message.channel.id) in no_xp_ch:
                return

            no_xp_roles = {r.role_id for r in db.query(NoXpRole).filter_by(guild_id=gid).all()}
            member_role_ids = {str(r.id) for r in message.author.roles}
            if no_xp_roles & member_role_ids:
                return

            now = int(time.time())
            ul = db.query(UserLevel).filter_by(guild_id=gid, user_id=str(message.author.id)).first()
            if not ul:
                ul = UserLevel(guild_id=gid, user_id=str(message.author.id))
                db.add(ul)

            if now - ul.last_xp_at < cfg.cooldown:
                return

            base_xp = random.randint(cfg.xp_min, cfg.xp_max)
            multiplier = 1.0

            role_mults = {r.role_id: r.multiplier
                          for r in db.query(XpMultiplierRole).filter_by(guild_id=gid).all()}
            for rid in member_role_ids:
                if rid in role_mults:
                    multiplier = max(multiplier, role_mults[rid])

            ch_mults = {r.channel_id: r.multiplier
                        for r in db.query(XpMultiplierChannel).filter_by(guild_id=gid).all()}
            if str(message.channel.id) in ch_mults:
                multiplier = max(multiplier, ch_mults[str(message.channel.id)])

            earned_xp = int(base_xp * multiplier)
            old_level = ul.level
            ul.xp += earned_xp
            ul.last_xp_at = now

            new_level, _, _ = xp_progress(ul.xp)
            ul.level = new_level
            db.commit()

            if new_level > old_level:
                await self._apply_level_up(
                    message.guild, message.author, cfg, new_level, db, gid,
                    fallback_channel=message.channel
                )
        finally:
            db.close()

    # ── Voice XP Task ─────────────────────────────────────────────────────────

    @tasks.loop(minutes=1)
    async def voice_xp_task(self):
        now = int(time.time())
        db = get_session()
        try:
            for guild in self.bot.guilds:
                gid = str(guild.id)
                cfg = db.query(LevelConfig).filter_by(guild_id=gid).first()
                if not cfg or not cfg.enabled or not cfg.voice_enabled:
                    continue

                interval_secs = cfg.voice_interval * 60
                no_xp_ch    = {r.channel_id for r in db.query(NoXpChannel).filter_by(guild_id=gid).all()}
                no_xp_roles = {r.role_id    for r in db.query(NoXpRole).filter_by(guild_id=gid).all()}

                if gid not in self._voice_last_xp:
                    self._voice_last_xp[gid] = {}

                for vc in guild.voice_channels:
                    if str(vc.id) in no_xp_ch:
                        continue
                    for member in vc.members:
                        if member.bot:
                            continue
                        vs = member.voice
                        if cfg.voice_ignore_muted and vs.self_mute:
                            continue
                        if cfg.voice_ignore_deafened and vs.self_deaf:
                            continue

                        uid = str(member.id)
                        if now - self._voice_last_xp[gid].get(uid, 0) < interval_secs:
                            continue

                        member_role_ids = {str(r.id) for r in member.roles}
                        if no_xp_roles & member_role_ids:
                            continue

                        xp_gain = random.randint(cfg.voice_xp_min, cfg.voice_xp_max)
                        ul = db.query(UserLevel).filter_by(guild_id=gid, user_id=uid).first()
                        if not ul:
                            ul = UserLevel(guild_id=gid, user_id=uid)
                            db.add(ul)

                        old_level = ul.level
                        ul.xp += xp_gain
                        new_level, _, _ = xp_progress(ul.xp)
                        ul.level = new_level
                        db.commit()

                        self._voice_last_xp[gid][uid] = now

                        if new_level > old_level:
                            fallback = guild.system_channel or next(
                                (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None
                            )
                            await self._apply_level_up(
                                guild, member, cfg, new_level, db, gid,
                                fallback_channel=fallback
                            )
        finally:
            db.close()

    @voice_xp_task.before_loop
    async def before_voice_xp_task(self):
        await self.bot.wait_until_ready()

    # ── /rank ─────────────────────────────────────────────────────────────────

    @app_commands.command(name='rank', description='Zeige deinen oder den Rang eines anderen Nutzers.')
    @app_commands.describe(member='Der Nutzer dessen Rang du sehen möchtest (optional)')
    async def rank(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        db = get_session()
        try:
            gid = str(interaction.guild_id)
            cfg = db.query(LevelConfig).filter_by(guild_id=gid).first()
            if not cfg or not cfg.enabled:
                await interaction.response.send_message('❌ Das Leveling-System ist nicht aktiviert.', ephemeral=True)
                return

            allowed = cfg.cmd_channels
            if allowed and str(interaction.channel_id) not in allowed:
                mentions = ' '.join(f'<#{c}>' for c in allowed)
                await interaction.response.send_message(
                    f'❌ Dieser Befehl ist nur in {mentions} erlaubt.', ephemeral=True)
                return

            ul = db.query(UserLevel).filter_by(guild_id=gid, user_id=str(target.id)).first()
            total_xp = ul.xp if ul else 0
            level, xp_in_level, xp_needed = xp_progress(total_xp)

            all_users = db.query(UserLevel).filter_by(guild_id=gid).order_by(UserLevel.xp.desc()).all()
            rank_pos = next((i + 1 for i, u in enumerate(all_users) if u.user_id == str(target.id)), len(all_users))

            embed = discord.Embed(color=level_color(level))
            embed.set_author(name=f'{target.display_name}\'s Rang',
                             icon_url=target.display_avatar.url)
            embed.add_field(name='Level', value=f'**{level}**', inline=True)
            embed.add_field(name='Rang', value=f'**#{rank_pos}** von {len(all_users)}', inline=True)
            embed.add_field(name='Gesamt XP', value=f'**{total_xp:,}**', inline=True)
            embed.add_field(
                name=f'Fortschritt zu Level {level + 1}',
                value=f'{progress_bar(xp_in_level, xp_needed)}\n{xp_in_level:,} / {xp_needed:,} XP',
                inline=False
            )
            await interaction.response.send_message(embed=embed)
        finally:
            db.close()

    # ── /leaderboard ──────────────────────────────────────────────────────────

    @app_commands.command(name='leaderboard', description='Zeige die Top 10 Nutzer dieses Servers.')
    async def leaderboard(self, interaction: discord.Interaction):
        db = get_session()
        try:
            gid = str(interaction.guild_id)
            cfg = db.query(LevelConfig).filter_by(guild_id=gid).first()
            if not cfg or not cfg.enabled:
                await interaction.response.send_message('❌ Das Leveling-System ist nicht aktiviert.', ephemeral=True)
                return

            allowed = cfg.cmd_channels
            if allowed and str(interaction.channel_id) not in allowed:
                mentions = ' '.join(f'<#{c}>' for c in allowed)
                await interaction.response.send_message(
                    f'❌ Dieser Befehl ist nur in {mentions} erlaubt.', ephemeral=True)
                return

            top = db.query(UserLevel).filter_by(guild_id=gid).order_by(UserLevel.xp.desc()).limit(10).all()
            if not top:
                await interaction.response.send_message('Noch keine Nutzer im Leaderboard.', ephemeral=True)
                return

            medals = ['🥇', '🥈', '🥉']
            lines = []
            for i, ul in enumerate(top):
                prefix = medals[i] if i < 3 else f'`#{i+1}`'
                level, xp_in, xp_need = xp_progress(ul.xp)
                m = interaction.guild.get_member(int(ul.user_id))
                name = m.display_name if m else f'<@{ul.user_id}>'
                lines.append(f'{prefix} **{name}** — Level {level} · {ul.xp:,} XP')

            embed = discord.Embed(
                title=f'🏆 Leaderboard — {interaction.guild.name}',
                description='\n'.join(lines),
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed)
        finally:
            db.close()


async def setup(bot):
    await bot.add_cog(LevelingCog(bot))
