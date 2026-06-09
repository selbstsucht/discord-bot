import discord
from discord.ext import commands
from database import get_session, SelfRoleMessage


class SelfRoleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── Component interactions (buttons + select menu) ────────────────────────

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id      = interaction.data.get('custom_id', '')
        component_type = interaction.data.get('component_type', 0)

        if component_type == 2 and custom_id.startswith('selfrole_') and not custom_id.startswith('selfrole_menu_'):
            parts = custom_id.split('_', 2)
            if len(parts) == 3:
                await self._handle_button(interaction, parts[1], parts[2])

        elif component_type == 3 and custom_id.startswith('selfrole_menu_'):
            msg_db_id = custom_id[len('selfrole_menu_'):]
            await self._handle_select(interaction, msg_db_id, interaction.data.get('values', []))

    async def _handle_button(self, interaction: discord.Interaction, msg_db_id: str, role_id: str):
        db = get_session()
        try:
            sm = db.query(SelfRoleMessage).filter_by(id=int(msg_db_id)).first()
            single       = bool(sm.single_select) if sm else False
            all_role_ids = [b.role_id for b in sm.buttons] if sm else []
        except Exception:
            single, all_role_ids = False, []
        finally:
            db.close()

        try:
            role = interaction.guild.get_role(int(role_id))
        except (ValueError, AttributeError):
            await interaction.response.send_message('❌ Ungültige Rolle.', ephemeral=True)
            return
        if not role:
            await interaction.response.send_message('❌ Rolle nicht gefunden!', ephemeral=True)
            return

        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason='Self-Role entfernt')
                await interaction.response.send_message(
                    f'✅ Rolle **{role.name}** wurde entfernt.', ephemeral=True)
            else:
                if single and all_role_ids:
                    to_remove = [r for r in interaction.user.roles
                                 if str(r.id) in all_role_ids and str(r.id) != str(role_id)]
                    if to_remove:
                        await interaction.user.remove_roles(*to_remove, reason='Self-Role Single-Select')
                await interaction.user.add_roles(role, reason='Self-Role hinzugefügt')
                await interaction.response.send_message(
                    f'✅ Rolle **{role.name}** wurde hinzugefügt!', ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                '❌ Fehlende Berechtigungen zum Vergeben dieser Rolle.', ephemeral=True)

    async def _handle_select(self, interaction: discord.Interaction, msg_db_id: str, selected_role_ids: list):
        db = get_session()
        try:
            sm = db.query(SelfRoleMessage).filter_by(id=int(msg_db_id)).first()
            if not sm:
                await interaction.response.send_message('❌ Nachricht nicht gefunden.', ephemeral=True)
                return
            all_role_ids = {b.role_id for b in sm.buttons}
        except Exception:
            await interaction.response.send_message('❌ Fehler beim Laden.', ephemeral=True)
            return
        finally:
            db.close()

        try:
            to_remove = [r for r in interaction.user.roles
                         if str(r.id) in all_role_ids and str(r.id) not in selected_role_ids]
            to_add = []
            for rid in selected_role_ids:
                r = interaction.guild.get_role(int(rid))
                if r and r not in interaction.user.roles:
                    to_add.append(r)

            if to_remove:
                await interaction.user.remove_roles(*to_remove, reason='Self-Role Select entfernt')
            if to_add:
                await interaction.user.add_roles(*to_add, reason='Self-Role Select hinzugefügt')

            if to_add or to_remove:
                parts = []
                if to_add:
                    parts.append('✅ Hinzugefügt: ' + ', '.join(f'**{r.name}**' for r in to_add))
                if to_remove:
                    parts.append('➖ Entfernt: ' + ', '.join(f'**{r.name}**' for r in to_remove))
                await interaction.response.send_message('\n'.join(parts), ephemeral=True)
            else:
                await interaction.response.send_message('Keine Änderungen vorgenommen.', ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message('❌ Fehlende Berechtigungen.', ephemeral=True)

    # ── Reaction roles ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        await self._handle_reaction(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        await self._handle_reaction(payload, add=False)

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent, add: bool):
        db = get_session()
        try:
            sm = db.query(SelfRoleMessage).filter_by(message_id=str(payload.message_id)).first()
            if not sm or (sm.interaction_type or 'buttons') != 'reactions':
                return
            emoji_str   = str(payload.emoji)
            matched_btn = next((b for b in sm.buttons if b.emoji and b.emoji.strip() == emoji_str), None)
            if not matched_btn:
                return
            single       = bool(sm.single_select)
            other_emojis = [b.emoji.strip() for b in sm.buttons
                            if b.emoji and b.emoji.strip() != emoji_str] if single else []
        finally:
            db.close()

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member:
            try:
                member = await guild.fetch_member(payload.user_id)
            except Exception:
                return

        role = guild.get_role(int(matched_btn.role_id))
        if not role:
            return

        try:
            if add:
                await member.add_roles(role, reason='Self-Role Reaction')
                if single and other_emojis:
                    channel = guild.get_channel(payload.channel_id)
                    if channel:
                        try:
                            msg = await channel.fetch_message(payload.message_id)
                            for em in other_emojis:
                                try:
                                    await msg.remove_reaction(em, member)
                                except (discord.Forbidden, discord.HTTPException):
                                    pass
                        except (discord.NotFound, discord.HTTPException):
                            pass
            else:
                if role in member.roles:
                    await member.remove_roles(role, reason='Self-Role Reaction entfernt')
        except discord.Forbidden:
            pass


async def setup(bot):
    await bot.add_cog(SelfRoleCog(bot))
