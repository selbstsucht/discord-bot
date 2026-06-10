import re
import discord
from datetime import timedelta
from discord import app_commands
from discord.ext import commands
from database import get_session, BotAdminConfig, UserLevel

_XP_TABLE = [40, 60, 70, 80, 90, 140, 165, 190, 200, 205, 280, 305, 325, 340, 350]

def _xp_for_next(level: int) -> int:
    return _XP_TABLE[level] if level < len(_XP_TABLE) else 350 + 40 * (level - 14)

def _total_xp_for_level(level: int) -> int:
    return sum(_xp_for_next(i) for i in range(level))

def _parse_duration(s: str) -> timedelta | None:
    m = re.fullmatch(r'(\d+)(s|m|h|d)', s.strip().lower())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return {'s': timedelta(seconds=n), 'm': timedelta(minutes=n),
            'h': timedelta(hours=n),   'd': timedelta(days=min(n, 28))}[unit]

async def _is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.id == interaction.guild.owner_id:
        return True
    db = get_session()
    try:
        return db.query(BotAdminConfig).filter_by(
            guild_id=str(interaction.guild_id),
            user_id=str(interaction.user.id)
        ).first() is not None
    finally:
        db.close()


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    admin = app_commands.Group(
        name='admin',
        description='Bot-Admin Befehle',
    )

    # ── /admin general ────────────────────────────────────────────────────────

    general = app_commands.Group(parent=admin, name='general', description='Allgemeine Befehle')

    @general.command(name='unflood', description='Löscht eine bestimmte Anzahl Nachrichten im aktuellen Channel')
    @app_commands.describe(anzahl='Anzahl der zu löschenden Nachrichten (1–100)')
    async def unflood(self, interaction: discord.Interaction,
                      anzahl: app_commands.Range[int, 1, 100]):
        if not await _is_admin(interaction):
            await interaction.response.send_message('❌ Keine Berechtigung.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=anzahl)
        await interaction.followup.send(f'✅ {len(deleted)} Nachricht(en) gelöscht.', ephemeral=True)

    # ── /admin levelsystem ────────────────────────────────────────────────────

    levelsystem = app_commands.Group(parent=admin, name='levelsystem', description='Leveling verwalten')

    @levelsystem.command(name='resetxp', description='Setzt XP und Level eines Nutzers zurück')
    @app_commands.describe(member='Der Nutzer')
    async def resetxp(self, interaction: discord.Interaction, member: discord.Member):
        if not await _is_admin(interaction):
            await interaction.response.send_message('❌ Keine Berechtigung.', ephemeral=True)
            return
        db = get_session()
        try:
            ul = db.query(UserLevel).filter_by(
                guild_id=str(interaction.guild_id), user_id=str(member.id)).first()
            if ul:
                ul.xp = 0
                ul.level = 0
                ul.last_xp_at = 0
                db.commit()
            await interaction.response.send_message(
                f'✅ XP von **{member.display_name}** wurde zurückgesetzt.', ephemeral=True)
        finally:
            db.close()

    @levelsystem.command(name='setlevel', description='Setzt das Level eines Nutzers')
    @app_commands.describe(member='Der Nutzer', level='Das neue Level (0–500)')
    async def setlevel(self, interaction: discord.Interaction, member: discord.Member,
                       level: app_commands.Range[int, 0, 500]):
        if not await _is_admin(interaction):
            await interaction.response.send_message('❌ Keine Berechtigung.', ephemeral=True)
            return
        db = get_session()
        try:
            ul = db.query(UserLevel).filter_by(
                guild_id=str(interaction.guild_id), user_id=str(member.id)).first()
            if not ul:
                ul = UserLevel(guild_id=str(interaction.guild_id), user_id=str(member.id))
                db.add(ul)
            ul.xp = _total_xp_for_level(level)
            ul.level = level
            db.commit()
            await interaction.response.send_message(
                f'✅ **{member.display_name}** ist jetzt Level **{level}**.', ephemeral=True)
        finally:
            db.close()

    @levelsystem.command(name='givexp', description='Gibt einem Nutzer XP')
    @app_commands.describe(member='Der Nutzer', amount='Menge XP (1–1.000.000)')
    async def givexp(self, interaction: discord.Interaction, member: discord.Member,
                     amount: app_commands.Range[int, 1, 1_000_000]):
        if not await _is_admin(interaction):
            await interaction.response.send_message('❌ Keine Berechtigung.', ephemeral=True)
            return
        db = get_session()
        try:
            ul = db.query(UserLevel).filter_by(
                guild_id=str(interaction.guild_id), user_id=str(member.id)).first()
            if not ul:
                ul = UserLevel(guild_id=str(interaction.guild_id), user_id=str(member.id),
                               xp=0, level=0, last_xp_at=0)
                db.add(ul)
            ul.xp = (ul.xp or 0) + amount
            # Recalculate level
            total, lvl = ul.xp, 0
            while total >= _xp_for_next(lvl):
                total -= _xp_for_next(lvl)
                lvl += 1
            ul.level = lvl
            db.commit()
            await interaction.response.send_message(
                f'✅ **{member.display_name}** hat **{amount:,} XP** erhalten. (Level {lvl})', ephemeral=True)
        finally:
            db.close()

    @levelsystem.command(name='clearlevels', description='Setzt ALLE XP auf diesem Server zurück')
    @app_commands.describe(bestaetigung='Tippe CONFIRM zur Bestätigung')
    async def clearlevels(self, interaction: discord.Interaction, bestaetigung: str):
        if not await _is_admin(interaction):
            await interaction.response.send_message('❌ Keine Berechtigung.', ephemeral=True)
            return
        if bestaetigung != 'CONFIRM':
            await interaction.response.send_message(
                '❌ Bitte genau `CONFIRM` eingeben um alle Level zu löschen.', ephemeral=True)
            return
        db = get_session()
        try:
            count = db.query(UserLevel).filter_by(guild_id=str(interaction.guild_id)).delete()
            db.commit()
            await interaction.response.send_message(
                f'✅ {count} Nutzer-Level wurden gelöscht.', ephemeral=True)
        finally:
            db.close()

    # ── /admin moderation ─────────────────────────────────────────────────────

    moderation = app_commands.Group(parent=admin, name='moderation', description='Moderation')

    @moderation.command(name='timeout', description='Gibt einem Nutzer einen Timeout')
    @app_commands.describe(member='Der Nutzer', dauer='z.B. 10m, 2h, 1d (max 28d)', grund='Grund (optional)')
    async def timeout(self, interaction: discord.Interaction, member: discord.Member,
                      dauer: str, grund: str = 'Kein Grund angegeben'):
        if not await _is_admin(interaction):
            await interaction.response.send_message('❌ Keine Berechtigung.', ephemeral=True)
            return
        delta = _parse_duration(dauer)
        if not delta:
            await interaction.response.send_message(
                '❌ Ungültige Dauer. Beispiele: `10m`, `2h`, `1d`', ephemeral=True)
            return
        try:
            await member.timeout(delta, reason=f'{grund} (von {interaction.user})')
            await interaction.response.send_message(
                f'✅ **{member.display_name}** hat einen Timeout für **{dauer}** erhalten.\n'
                f'Grund: {grund}', ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message('❌ Fehlende Berechtigungen.', ephemeral=True)

    @moderation.command(name='kick', description='Kickt einen Nutzer vom Server')
    @app_commands.describe(member='Der Nutzer', grund='Grund (optional)')
    async def kick(self, interaction: discord.Interaction, member: discord.Member,
                   grund: str = 'Kein Grund angegeben'):
        if not await _is_admin(interaction):
            await interaction.response.send_message('❌ Keine Berechtigung.', ephemeral=True)
            return
        try:
            await member.kick(reason=f'{grund} (von {interaction.user})')
            await interaction.response.send_message(
                f'✅ **{member.display_name}** wurde gekickt.\nGrund: {grund}', ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message('❌ Fehlende Berechtigungen.', ephemeral=True)

    @moderation.command(name='ban', description='Bannt einen Nutzer vom Server')
    @app_commands.describe(member='Der Nutzer', grund='Grund (optional)',
                           nachrichten_loeschen='Nachrichten der letzten X Tage löschen (0–7)')
    async def ban(self, interaction: discord.Interaction, member: discord.Member,
                  grund: str = 'Kein Grund angegeben',
                  nachrichten_loeschen: app_commands.Range[int, 0, 7] = 0):
        if not await _is_admin(interaction):
            await interaction.response.send_message('❌ Keine Berechtigung.', ephemeral=True)
            return
        try:
            await member.ban(reason=f'{grund} (von {interaction.user})',
                             delete_message_days=nachrichten_loeschen)
            await interaction.response.send_message(
                f'✅ **{member.display_name}** wurde gebannt.\nGrund: {grund}', ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message('❌ Fehlende Berechtigungen.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
