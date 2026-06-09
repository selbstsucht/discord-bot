import discord
from discord.ext import commands
from database import get_session, AutoRoleConfig


class AutoRoleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        db = get_session()
        try:
            cfg = db.query(AutoRoleConfig).filter_by(guild_id=str(member.guild.id)).first()
            if not cfg or not cfg.enabled:
                return
            for role_id in cfg.role_ids:
                role = member.guild.get_role(int(role_id))
                if role:
                    try:
                        await member.add_roles(role, reason='Auto-Role bei Beitritt')
                    except discord.Forbidden:
                        pass
        finally:
            db.close()


async def setup(bot):
    await bot.add_cog(AutoRoleCog(bot))
