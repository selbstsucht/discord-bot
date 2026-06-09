import asyncio
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import init_db

load_dotenv()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    print(f'✅ Bot eingeloggt als {bot.user} (ID: {bot.user.id})')
    try:
        synced = await bot.tree.sync()
        print(f'   Slash-Commands synchronisiert: {len(synced)}')
    except Exception as e:
        print(f'   Sync-Fehler: {e}')


async def main():
    init_db()
    async with bot:
        await bot.load_extension('cogs.welcome')
        await bot.load_extension('cogs.autorole')
        await bot.load_extension('cogs.selfroles')
        await bot.load_extension('cogs.leveling')
        await bot.start(os.getenv('BOT_TOKEN'))


if __name__ == '__main__':
    asyncio.run(main())
