import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
import io
import time
import os

# ⚠️ Fake token for testing
GUILD_ID = 1394313660482064487
STAFF_ROLE_ID = 1397784810046357636
LOG_CHANNEL_ID = 1397785298372657233

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = commands.Bot(command_prefix="!", intents=intents)
tree = client.tree
setup_data = {}
cooldowns = {}  # user_id: timestamp
user_ticket_channels = {}  # user_id: channel_id


class SetupModal(ui.Modal, title="Ticket Setup"):
    title_input = ui.TextInput(label="Panel Title", required=True)
    description_input = ui.TextInput(label="Panel Description", style=discord.TextStyle.paragraph, required=True)
    button_label_input = ui.TextInput(label="Button Label", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        setup_data[interaction.guild.id] = {
            "title": self.title_input.value,
            "description": self.description_input.value,
            "button_label": self.button_label_input.value,
        }
        await interaction.response.send_message("✅ Setup saved! Use `/panel` to send the ticket panel.", ephemeral=True)


@tree.command(name="setup", description="Set up the ticket panel")
async def setup(interaction: discord.Interaction):
    await interaction.response.send_modal(SetupModal())


@tree.command(name="panel", description="Send the ticket panel embed")
async def panel(interaction: discord.Interaction):
    config = setup_data.get(interaction.guild.id)
    if not config:
        await interaction.response.send_message("❌ You must run `/setup` first.", ephemeral=True)
        return

    embed = discord.Embed(
        title=config["title"],
        description=config["description"],
        color=discord.Color.blurple()
    )
    view = TicketView(config["button_label"])
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Panel sent!", ephemeral=True)


class TicketView(ui.View):
    def __init__(self, button_label):
        super().__init__(timeout=None)
        self.add_item(TicketButton(label=button_label))


class TicketButton(ui.Button):
    def __init__(self, label):
        super().__init__(label=label, style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        now = time.time()
        cooldown_seconds = 60

        # Prevent multiple tickets per user
        if user.id in user_ticket_channels:
            existing_channel = guild.get_channel(user_ticket_channels[user.id])
            if existing_channel and existing_channel.category and existing_channel.category.name == "Tickets":
                await interaction.response.send_message(
                    f"❌ You already have an open ticket: {existing_channel.mention}",
                    ephemeral=True
                )
                return
            else:
                # Cleanup invalid ticket reference
                user_ticket_channels.pop(user.id)

        # Cooldown check
        if user.id in cooldowns and now - cooldowns[user.id] < cooldown_seconds:
            remaining = int(cooldown_seconds - (now - cooldowns[user.id]))
            await interaction.response.send_message(
                f"⏳ Please wait {remaining} seconds before opening another ticket.",
                ephemeral=True
            )
            return

        cooldowns[user.id] = now

        config = setup_data.get(guild.id)
        category = discord.utils.get(guild.categories, name="Tickets")
        if category is None:
            category = await guild.create_category("Tickets")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_role(STAFF_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        channel = await guild.create_text_channel(
            name=f"ticket-{user.name}".replace(" ", "-").lower(),
            overwrites=overwrites,
            category=category,
            topic=f"Ticket opened by {user}",
            reason="New ticket"
        )

        user_ticket_channels[user.id] = channel.id  # Store reference

        embed = discord.Embed(
            title="📩 Welcome to Support!",
            description="Please describe your issue clearly. Our staff will assist you shortly.\n_Thank you for your patience!_",
            color=discord.Color.green()
        )
        embed.set_footer(text="Ticket System", icon_url=guild.icon.url if guild.icon else None)

        view = TicketControlView()

        await channel.send(
            content=f"{user.mention} has opened a ticket.",
            embed=embed,
            view=view
        )

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"📥 Ticket opened by {user.mention}: {channel.mention}")

        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)


class TicketControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ClaimButton())
        self.add_item(CloseButton())


class ClaimButton(ui.Button):
    def __init__(self):
        super().__init__(label="🎯 Claim", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        if STAFF_ROLE_ID not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("❌ Only staff can claim this ticket.", ephemeral=True)
            return

        await interaction.channel.send(f"🎯 {interaction.user.mention} has claimed this ticket.")
        await interaction.response.defer()


class CloseButton(ui.Button):
    def __init__(self):
        super().__init__(label="❌ Close", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("🕒 Closing ticket in 5 seconds...", ephemeral=True)
        await asyncio.sleep(5)

        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)

        lines = []
        async for msg in interaction.channel.history(limit=100, oldest_first=True):
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
            author = f"{msg.author.name}#{msg.author.discriminator}"
            content = msg.content or "[No text content]"
            lines.append(f"[{timestamp}] {author}: {content}")

        transcript_text = "\n".join(lines)
        transcript_file = discord.File(io.StringIO(transcript_text), filename=f"{interaction.channel.name}.txt")

        if log_channel:
            await log_channel.send(
                content=f"🗃️ Transcript from `{interaction.channel.name}` closed by {interaction.user.mention}",
                file=transcript_file
            )

        # Remove user entry from tracking map
        for user_id, channel_id in list(user_ticket_channels.items()):
            if channel_id == interaction.channel.id:
                del user_ticket_channels[user_id]

        await interaction.channel.delete()


@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {client.user}")


client.run(os.getenv("DISCORD_TOKEN"))
