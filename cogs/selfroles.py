import discord
from discord.ext import commands


class SelfRoleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get('custom_id', '')
        if not custom_id.startswith('selfrole_'):
            return

        # custom_id format: selfrole_{msg_db_id}_{role_id}
        parts = custom_id.split('_', 2)
        if len(parts) != 3:
            return

        role_id = parts[2]
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
                await interaction.user.add_roles(role, reason='Self-Role hinzugefügt')
                await interaction.response.send_message(
                    f'✅ Rolle **{role.name}** wurde hinzugefügt!', ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                '❌ Fehlende Berechtigungen zum Vergeben dieser Rolle.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(SelfRoleCog(bot))
