import discord
from discord.ext import commands, tasks
import json
import asyncio
import datetime
import os

from keep_alive import keep_alive  # Agar tetap online di Replit

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Muat config
with open("config.json", "r") as f:
    config = json.load(f)

# Muat atau buat file pelanggaran
if os.path.exists("violations.json"):
    with open("violations.json", "r") as f:
        user_violations = json.load(f)
else:
    user_violations = {}

# Simpan pelanggaran ke file
def save_violations():
    with open("violations.json", "w") as f:
        json.dump(user_violations, f, indent=2)

# Pembersih pelanggaran lama
@tasks.loop(hours=24)
async def cleanup_violations():
    now = datetime.datetime.utcnow().timestamp()
    changed = False
    for user_id in list(user_violations.keys()):
        new_data = [v for v in user_violations[user_id] if now - v["timestamp"] < 365*24*3600]
        if len(new_data) != len(user_violations[user_id]):
            user_violations[user_id] = new_data
            changed = True
    if changed:
        save_violations()

@bot.event
async def on_ready():
    print(f"{bot.user} sudah online!")
    cleanup_violations.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    content = message.content.lower()
    now = datetime.datetime.utcnow().timestamp()

    # Deteksi spam manual
    if not hasattr(bot, "last_messages"):
        bot.last_messages = {}
    if user_id in bot.last_messages:
        last_msg, last_time = bot.last_messages[user_id]
        if last_msg == content and (now - last_time) < 5:
            await handle_violation(message, "kamu mengirim pesan spam", 3)
            return
    bot.last_messages[user_id] = (content, now)

    for keyword, points in config["keywords"].items():
        for word in keyword.split("|"):
            if word in content:
                await handle_violation(message, f"kamu berkata kasar ({word})", points)
                return

    await bot.process_commands(message)

def get_total_points(user_id):
    return sum(v["points"] for v in user_violations.get(user_id, []))

def get_punishment(points):
    if points == 1:
        return "warning", None
    elif points == 2:
        return "timeout", 3600
    elif points == 3:
        return "timeout", 86400
    elif points == 4:
        return "kick", None
    elif points == 5:
        return "tempban", 604800
    elif points >= 6:
        return "ban", None
    return None, None

async def handle_violation(message, reason, point):
    await message.delete()
    user_id = str(message.author.id)
    now = datetime.datetime.utcnow().timestamp()
    user_violations.setdefault(user_id, []).append({"reason": reason, "points": point, "timestamp": now})
    save_violations()

    total = get_total_points(user_id)
    punishment, duration = get_punishment(total)

    await give_punishment(message.author, message.guild, punishment, duration, reason, total, message.channel)

async def give_punishment(member, guild, action, duration, reason, total, channel):
    police_channel = discord.utils.get(guild.text_channels, name="🏤︱kantor-polisi")
    announce_channel = discord.utils.get(guild.text_channels, name="📢︱pengumuman-kota")
    jail_channel = discord.utils.get(guild.text_channels, name="🚨︱penjara")
    jail_role = discord.utils.get(guild.roles, name="narapidana")

    embed = discord.Embed(title="Pelanggaran Terdeteksi", color=0xff0000)
    embed.add_field(name="Nama", value=member.mention, inline=True)
    embed.add_field(name="Pelanggaran", value=reason, inline=True)
    embed.add_field(name="Total Poin", value=total, inline=True)
    embed.set_footer(text=f"Hukuman: {action}")

    if action == "warning":
        await channel.send(f"{member.mention}, kamu mendapat peringatan karena: **{reason}**")
    elif action == "timeout":
        await member.edit(timeout=datetime.datetime.utcnow() + datetime.timedelta(seconds=duration))
        await jail_channel.set_permissions(member, read_messages=True, send_messages=False)
        await member.add_roles(jail_role)
        await jail_channel.send(f"{member.mention} dijebloskan ke penjara selama {duration//3600} jam karena: **{reason}**")
        await asyncio.sleep(duration)
        await member.remove_roles(jail_role)
        await jail_channel.send(f"{member.mention} telah bebas dari penjara.")
    elif action == "kick":
        await guild.kick(member, reason=reason)
    elif action == "tempban":
        await guild.ban(member, reason=reason)
        await asyncio.sleep(duration)
        await guild.unban(discord.Object(id=member.id))
    elif action == "ban":
        await guild.ban(member, reason=reason)

    if police_channel:
        await police_channel.send(embed=embed)
    if announce_channel:
        await announce_channel.send(embed=embed)

keep_alive()  # Jaga agar bot tetap online
bot.run(config["token"])
