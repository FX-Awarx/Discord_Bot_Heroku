import discord
import os
from discord.ext import commands
from keep_alive import keep_alive

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

keep_alive()
token = os.environ['TOKEN']
bot.run(token)
