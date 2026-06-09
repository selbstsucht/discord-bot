import discord
from discord.ext import commands
from database import get_session, WelcomeConfig, GoodbyeConfig


class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        db = get_session()
        try:
            cfg = db.query(WelcomeConfig).filter_by(guild_id=str(member.guild.id)).first()
            if not cfg or not cfg.enabled or not cfg.channel_id:
                return
            channel = member.guild.get_channel(int(cfg.channel_id))
            if not channel:
                return
            msg = (cfg.message
                   .replace('{user}', member.mention)
                   .replace('{username}', member.display_name)
                   .replace('{server}', member.guild.name))
            await channel.send(msg)
        finally:
            db.close()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        db = get_session()
        try:
            cfg = db.query(GoodbyeConfig).filter_by(guild_id=str(member.guild.id)).first()
            if not cfg or not cfg.enabled or not cfg.channel_id:
                return
            channel = member.guild.get_channel(int(cfg.channel_id))
            if not channel:
                return
            msg = (cfg.message
                   .replace('{user}', member.mention)
                   .replace('{username}', member.display_name)
                   .replace('{server}', member.guild.name))
            await channel.send(msg)
        finally:
            db.close()


async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
