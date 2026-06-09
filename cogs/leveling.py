import time
import random
import discord
from discord import app_commands
from discord.ext import commands
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

            # No-XP channel check
            no_xp_ch = {r.channel_id for r in db.query(NoXpChannel).filter_by(guild_id=gid).all()}
            if str(message.channel.id) in no_xp_ch:
                return

            # No-XP role check
            no_xp_roles = {r.role_id for r in db.query(NoXpRole).filter_by(guild_id=gid).all()}
            member_role_ids = {str(r.id) for r in message.author.roles}
            if no_xp_roles & member_role_ids:
                return

            # Cooldown check
            now = int(time.time())
            ul = db.query(UserLevel).filter_by(guild_id=gid, user_id=str(message.author.id)).first()
            if not ul:
                ul = UserLevel(guild_id=gid, user_id=str(message.author.id))
                db.add(ul)

            if now - ul.last_xp_at < cfg.cooldown:
                return

            # Calculate XP with multipliers
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

            # Recalculate level
            new_level, _, _ = xp_progress(ul.xp)
            ul.level = new_level
            db.commit()

            if new_level > old_level:
                await self._handle_level_up(message, cfg, ul, new_level, db, gid)
        finally:
            db.close()

    async def _handle_level_up(self, message, cfg, ul, new_level, db, gid):
        # Assign level roles
        level_roles = db.query(LevelRole).filter_by(guild_id=gid).order_by(LevelRole.level).all()
        earned_role_ids = [lr.role_id for lr in level_roles if lr.level <= new_level]
        exact_role_ids  = [lr.role_id for lr in level_roles if lr.level == new_level]
        all_role_ids    = [lr.role_id for lr in level_roles]

        member = message.author
        try:
            if cfg.role_stack:
                # Add all earned roles
                for rid in earned_role_ids:
                    role = message.guild.get_role(int(rid))
                    if role and role not in member.roles:
                        await member.add_roles(role, reason=f'Level {new_level} erreicht')
            else:
                # Remove all level roles, add only the current one
                for rid in all_role_ids:
                    role = message.guild.get_role(int(rid))
                    if role and role in member.roles and rid not in exact_role_ids:
                        await member.remove_roles(role, reason='Level-Rolle ersetzt')
                for rid in exact_role_ids:
                    role = message.guild.get_role(int(rid))
                    if role and role not in member.roles:
                        await member.add_roles(role, reason=f'Level {new_level} erreicht')
        except discord.Forbidden:
            pass

        # Level-up notification
        if cfg.levelup_mode == 'disabled':
            return

        lv_msg = (cfg.levelup_message
                  .replace('{user}', member.mention)
                  .replace('{username}', member.display_name)
                  .replace('{level}', str(new_level))
                  .replace('{server}', message.guild.name))

        if cfg.levelup_mode == 'dm':
            try:
                await member.send(lv_msg)
            except discord.Forbidden:
                pass
        elif cfg.levelup_mode == 'custom' and cfg.levelup_channel_id:
            ch = message.guild.get_channel(int(cfg.levelup_channel_id))
            if ch:
                await ch.send(lv_msg)
        else:  # current
            await message.channel.send(lv_msg)

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

            # Server rank
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
                member = interaction.guild.get_member(int(ul.user_id))
                name = member.display_name if member else f'<@{ul.user_id}>'
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
