import discord
from discord.ext import commands
from discord import app_commands
import asyncio

intents = discord.Intents.default()
client = commands.Bot(command_prefix="!", intents=intents)
tree = client.tree

@client.event
async def on_ready():
    synced = await tree.sync()
    print(f"🔧 Synced {len(synced)} command(s)")
    print(f"✅ Logged in as {client.user}")

@tree.command(name="ping", description="Check the bot's latency")
async def ping_command(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! 🏓 `{round(client.latency * 1000)}ms`")

client.run("MTM4MzY5NjMwOTUxNjc2NzI5Mg.G1hefJ.MSfkcYR3YIf60IX9MPiCGYiHoIjeh4hTRO0Tvw")
