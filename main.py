import discord, requests, time, random, pyfiglet, json, os, asyncio
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread
import io
from gtts import gTTS
import yt_dlp
from youtubesearchpython import VideosSearch
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import re
from openai import OpenAI

# Load Opus for voice functionality
if not discord.opus.is_loaded():
    try:
        # Try to load from Nix paths first
        discord.opus.load_opus('libopus.so.0')
        print("✅ Opus library loaded successfully")
    except:
        try:
            discord.opus.load_opus('opus')
        except:
            try:
                import glob
                opus_paths = glob.glob('/nix/store/*/lib/libopus.so*')
                if opus_paths:
                    discord.opus.load_opus(opus_paths[0])
                    print("✅ Opus library loaded from Nix store")
                else:
                    raise Exception("No Opus library found")
            except:
                print("❌ ERROR: Could not load Opus library. Voice features will not work.")
                print("💡 Restart your Repl after adding Opus to fix this issue.")

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
OWNER_IDS = [1020354393691918356, 123456789012345678, 786907113749741618]  # Add your second user ID here

# OpenAI setup
try:
    openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    print("✅ OpenAI client initialized")
except Exception as e:
    openai_client = None
    print(f"⚠️ OpenAI setup failed: {e}. Add OPENAI_API_KEY to secrets.")
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="meow ", case_insensitive=True, intents=intents)
bot.start_time = time.time()
log_channels = {}
welcome_channel_id = None
cooldowns = {}
snipes = []

# Security system variables
security_settings = {}
whitelisted_users = set()
locked_channels = set()
recent_joins = []
recent_deletions = {"channels": [], "roles": [], "kicks": [], "bans": []}
anti_nuke_enabled = {}

# Load security data
security_file = "security.json"
if os.path.exists(security_file):
    with open(security_file, "r") as f:
        security_data = json.load(f)
        whitelisted_users = set(security_data.get("whitelist", []))
        anti_nuke_enabled = security_data.get("anti_nuke", {})
else:
    security_data = {"whitelist": [], "anti_nuke": {}}

def save_security():
    security_data["whitelist"] = list(whitelisted_users)
    security_data["anti_nuke"] = anti_nuke_enabled
    with open(security_file, "w") as f:
        json.dump(security_data, f)

if not os.path.exists("users.json"):
    with open("users.json", "w") as f:
        json.dump({}, f)

# Marriage system
marriage_file = "marriages.json"
if not os.path.exists(marriage_file):
    with open(marriage_file, "w") as f:
        json.dump({}, f)

def load_marriages():
    with open(marriage_file) as f:
        return json.load(f)

def save_marriages(data):
    with open(marriage_file, "w") as f:
        json.dump(data, f)

marriages = load_marriages()

# Soundboard data
soundboard_file = "soundboard.json"
if not os.path.exists(soundboard_file):
    with open("soundboard.json", "w") as f:
        json.dump({"sounds": {}}, f)

def load_soundboard():
    with open(soundboard_file) as f:
        return json.load(f)

def save_soundboard(data):
    with open(soundboard_file, "w") as f:
        json.dump(data, f)

soundboard_data = load_soundboard()

def load_users():
    with open("users.json") as f:
        return json.load(f)

def save_users(data):
    with open("users.json", "w") as f:
        json.dump(data, f)

users = load_users()

def keep_alive():
    app = Flask('')
    @app.route('/')
    def home(): return "✅ MeowBot is alive!"
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

LOG_CHANNEL_NAMES = {
    "member_join": "member-join",
    "member_leave": "member-leave",
    "message_delete": "message-delete",
    "message_edit": "message-edit",
    "role_create": "role-create",
    "role_delete": "role-delete",
    "role_update": "role-update",
    "channel_create": "channel-create",
    "channel_delete": "channel-delete",
    "channel_update": "channel-update",
    "ban": "bans",
    "unban": "unbans",
    "presence": "presence",
    "reaction_add": "reaction-add",
    "reaction_remove": "reaction-remove",
    "command_logs": "command-logs"
}


async def ensure_log_channels(guild):
    category = discord.utils.get(guild.categories, name="logs")
    if not category:
        category = await guild.create_category("logs")
    overwrite = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True)
    }
    for key, name in LOG_CHANNEL_NAMES.items():
        ch = discord.utils.get(guild.text_channels, name=name)
        if not ch:
            ch = await guild.create_text_channel(name, overwrites=overwrite, category=category)
        log_channels[key] = ch

def update_user(uid):
    if str(uid) not in users:
        users[str(uid)] = {"xp": 0, "level": 1, "balance": 0, "bio": ""}
        save_users(users)

def add_xp(uid, amount):
    update_user(uid)
    users[str(uid)]["xp"] += amount
    if users[str(uid)]["xp"] >= users[str(uid)]["level"] * 100:
        users[str(uid)]["xp"] = 0
        users[str(uid)]["level"] += 1
    save_users(users)

def check_cooldown(uid, command, secs):
    now = time.time()
    if uid in cooldowns and command in cooldowns[uid]:
        elapsed = now - cooldowns[uid][command]
        if elapsed < secs:
            return secs - int(elapsed)
    cooldowns.setdefault(uid, {})[command] = now
    return 0

async def auto_lockdown(guild, reason):
    """Automatically lock all channels during security threat"""
    try:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).manage_channels:
                await channel.set_permissions(guild.default_role, send_messages=False)
                locked_channels.add(channel.id)

        # Alert admins
        if log_channels.get("command_logs"):
            embed = discord.Embed(title="🔒 AUTO LOCKDOWN ACTIVATED", description=reason, color=0xff0000)
            await log_channels["command_logs"].send(embed=embed)
    except:
        pass

def is_whitelisted(user_id):
    """Check if user is whitelisted"""
    return user_id in whitelisted_users or user_id in OWNER_IDS

async def check_anti_nuke(guild, action_type, user, target=None):
    """Monitor for nuke attempts"""
    if not anti_nuke_enabled.get(str(guild.id), False):
        return

    if is_whitelisted(user.id):
        return

    now = time.time()
    user_actions = recent_deletions.setdefault(action_type, [])
    user_actions.append({"user": user.id, "time": now, "target": target})

    # Clean old actions (last 60 seconds)
    user_actions[:] = [a for a in user_actions if now - a["time"] < 60]

    # Count actions by this user in last 30 seconds
    user_recent = len([a for a in user_actions if a["user"] == user.id and now - a["time"] < 30])

    # Trigger on 3+ deletions in 30 seconds
    if user_recent >= 3:
        await handle_nuke_attempt(guild, user, action_type)

async def handle_nuke_attempt(guild, user, action_type):
    """Handle detected nuke attempt"""
    try:
        member = guild.get_member(user.id)
        if member:
            # Remove dangerous permissions
            for role in member.roles:
                if role.permissions.administrator or role.permissions.manage_channels or role.permissions.manage_roles:
                    try:
                        await member.remove_roles(role)
                    except:
                        pass

            # Timeout the user
            await member.timeout(discord.utils.utcnow() + discord.timedelta(hours=1))

        # Alert in logs
        if log_channels.get("command_logs"):
            embed = discord.Embed(
                title="🚨 NUKE ATTEMPT DETECTED", 
                description=f"User: {user}\nAction: {action_type}\nUser has been stripped of permissions and timed out.",
                color=0xff0000
            )
            await log_channels["command_logs"].send(embed=embed)

        # Auto lockdown
        await auto_lockdown(guild, f"Nuke attempt by {user}")

    except Exception as e:
        print(f"Error handling nuke attempt: {e}")

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} is online")

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    update_user(msg.author.id)
    add_xp(msg.author.id, 5)
    await bot.process_commands(msg)

@bot.event
async def on_member_join(member):
    # Track recent joins for raid detection
    now = time.time()
    recent_joins.append({"member": member, "time": now})
    recent_joins[:] = [j for j in recent_joins if now - j["time"] < 60]  # Keep last 60 seconds

    # Raid detection (5+ joins in 30 seconds)
    recent_count = len([j for j in recent_joins if now - j["time"] < 30])
    if recent_count >= 5 and str(member.guild.id) in anti_nuke_enabled and anti_nuke_enabled[str(member.guild.id)]:
        await auto_lockdown(member.guild, "Raid detected - multiple rapid joins")

    if log_channels.get("member_join"):
        await log_channels["member_join"].send(f"✅ Member Joined: {member.mention}")
    if welcome_channel_id:
        ch = bot.get_channel(welcome_channel_id)
        if ch:
            await ch.send(f"👑 tanginamo sir tumambay ka ha{member.mention}!")

@bot.event
async def on_member_remove(member):
    ch = log_channels.get("member_leave")
    if ch:
        await ch.send(f"❌ Member Left: {member.mention} left.")

@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    snipes.insert(0, message)
    if len(snipes) > 10: snipes.pop()
    ch = log_channels.get("message_delete")
    if ch:
        embed = discord.Embed(title="🗑️ Message Deleted", description=message.content, color=0xff5555)
        embed.set_author(name=message.author, icon_url=message.author.display_avatar.url)
        await ch.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if before.content != after.content and not before.author.bot:
        ch = log_channels.get("message_edit")
        if ch:
            embed = discord.Embed(title="✏️ Message Edited", color=0x55aaff)
            embed.add_field(name="Before", value=before.content or "None", inline=False)
            embed.add_field(name="After", value=after.content or "None", inline=False)
            embed.set_author(name=before.author, icon_url=before.author.display_avatar.url)
            await ch.send(embed=embed)

@bot.event
async def on_guild_channel_delete(channel):
    """Monitor channelfor anti-nuke"""
    if hasattr(channel, 'guild'):
        async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
            await check_anti_nuke(channel.guild, "channels", entry.user, channel.name)
            break

@bot.event
async def on_guild_role_delete(role):
    """Monitor role deletions for anti-nuke"""
    async for entry in role.guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
        await check_anti_nuke(role.guild, "roles", entry.user, role.name)
        break

@bot.event
async def on_member_remove(member):
    ch = log_channels.get("member_leave")
    if ch:
        await ch.send(f"❌ Member Left: {member.mention} left.")

    # Check if it was a kick for anti-nuke
    try:
        async for entry in member.guild.audit_logs(action=discord.AuditLogAction.kick, limit=1):
            if entry.target == member:
                await check_anti_nuke(member.guild, "kicks", entry.user, member.name)
                break
    except:
        pass

@bot.event
async def on_member_ban(guild, user):
    """Monitor bans for anti-nuke"""
    try:
        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=1):
            if entry.target == user:
                await check_anti_nuke(guild, "bans", entry.user, user.name)
                break
    except:
        pass

@bot.tree.command(name="setup_logs")
async def setup_logs(interaction: discord.Interaction):
    await ensure_log_channels(interaction.guild)
    await interaction.response.send_message("✅ Logs setup complete", ephemeral=True)

@bot.tree.command(name="setwelcomechannel")
@app_commands.checks.has_permissions(administrator=True)
async def setwelcome(interaction: discord.Interaction):
    global welcome_channel_id
    welcome_channel_id = interaction.channel.id
    await interaction.response.send_message("✅ Welcome channel set!", ephemeral=True)

@bot.command()
async def testlogs(ctx):
    for key, ch in log_channels.items():
        await ch.send(f"✅ Test log: {key}")

@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@bot.command()
async def snipe(ctx, index: int = 1):
    if index > len(snipes) or index < 1:
        return await ctx.send("❌ No snipe found at that index.")
    msg = snipes[index - 1]
    embed = discord.Embed(title=f"💬 Sniped Message #{index}", description=msg.content or "[no content]", color=0xff9999)
    embed.set_author(name=msg.author, icon_url=msg.author.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def status(ctx):
    uptime = int(time.time() - bot.start_time)
    await ctx.send(f"📶 Online | ⏱️ Uptime: {uptime}s | Guilds: {len(bot.guilds)}")

@bot.command()
async def helpme(ctx):
    await ctx.send("**📜 MeowBot Help**\nUse `meow cmds` to see all commands.")

@bot.command()
async def cmds(ctx):
    await ctx.send("📖 All Commands: meow helpme, status, av, myoui, ascii, snipe, ping, testlogs, setbio, profile, bal, setbal, setlevel, daily, cf, dice, gunfight, shop, sayd, leaderboard, rate, ship, insult, serverinfo, userinfo, uptime, meme, cat, dog, guess, trivia, slots, highlow, deposit, withdraw, rob, work, invest, warn, warnings, mute, unmute, purge, whitelist, antinuke, lockdown, unlockdown, raidmode, security, marry, divorce, couples, 8ball, soundboard, addsound, playsound, removesound, sounds, join, leave, stop, tts, ask, imagine")

# Marriage System Commands
@bot.command()
async def marry(ctx, member: discord.Member):
    """Propose marriage to another member"""
    if member.bot:
        return await ctx.send("❌ You can't marry a bot!")

    if member.id == ctx.author.id:
        return await ctx.send("❌ You can't marry yourself!")

    # Check if either user is already married
    user_id = str(ctx.author.id)
    target_id = str(member.id)

    if user_id in marriages or target_id in marriages:
        return await ctx.send("❌ One of you is already married!")

    # Send proposal
    embed = discord.Embed(
        title="💍 Marriage Proposal",
        description=f"{ctx.author.mention} has proposed to {member.mention}!",
        color=0xff69b4
    )
    embed.add_field(name="💕", value=f"{member.mention}, do you accept?\nReact with 💍 to accept or ❌ to decline", inline=False)

    msg = await ctx.send(embed=embed)
    await msg.add_reaction("💍")
    await msg.add_reaction("❌")

    def check(reaction, user):
        return user == member and str(reaction.emoji) in ["💍", "❌"] and reaction.message.id == msg.id

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)

        if str(reaction.emoji) == "💍":
            # Accept proposal
            marriages[user_id] = {
                "partner": target_id,
                "married_at": time.time(),
                "anniversary": time.strftime("%Y-%m-%d")
            }
            marriages[target_id] = {
                "partner": user_id,
                "married_at": time.time(),
                "anniversary": time.strftime("%Y-%m-%d")
            }
            save_marriages(marriages)

            # Give marriage bonus
            update_user(ctx.author.id)
            update_user(member.id)
            users[user_id]["balance"] += 1000
            users[target_id]["balance"] += 1000
            save_users(users)

            embed = discord.Embed(
                title="💖 Marriage Successful!",
                description=f"🎉 {ctx.author.mention} and {member.mention} are now married!\n💰 You both received 1000 myouins as a wedding gift!",
                color=0x00ff00
            )
            await ctx.send(embed=embed)

        else:
            embed = discord.Embed(
                title="💔 Proposal Declined",
                description=f"{member.mention} declined the proposal.",
                color=0xff0000
            )
            await ctx.send(embed=embed)

    except asyncio.TimeoutError:
        await ctx.send("💔 Proposal timed out.")

@bot.command()
async def divorce(ctx):
    """Divorce your current partner"""
    user_id = str(ctx.author.id)

    if user_id not in marriages:
        return await ctx.send("❌ You're not married!")

    partner_id = marriages[user_id]["partner"]
    try:
        partner = await bot.fetch_user(int(partner_id))
        partner_name = partner.name
    except:
        partner_name = "Unknown User"

    # Remove both marriages
    del marriages[user_id]
    if partner_id in marriages:
        del marriages[partner_id]
    save_marriages(marriages)

    embed = discord.Embed(
        title="💔 Divorce Finalized",
        description=f"{ctx.author.mention} and {partner_name} are now divorced.",
        color=0x808080
    )
    await ctx.send(embed=embed)

@bot.command()
async def couples(ctx):
    """Show all married couples in the server"""
    if not marriages:
        return await ctx.send("💔 No couples found in this server.")

    embed = discord.Embed(title="💕 Server Couples", color=0xff69b4)

    processed = set()
    couple_count = 0

    for user_id, data in marriages.items():
        if user_id in processed:
            continue

        partner_id = data["partner"]
        if partner_id in processed:
            continue

        try:
            user = ctx.guild.get_member(int(user_id))
            partner = ctx.guild.get_member(int(partner_id))

            if user and partner:  # Both users are in this server
                anniversary = data.get("anniversary", "Unknown")
                married_days = int((time.time() - data["married_at"]) // 86400)

                embed.add_field(
                    name=f"💑 {user.display_name} & {partner.display_name}",
                    value=f"📅 Married: {anniversary}\n⏰ Days together: {married_days}",
                    inline=True
                )
                couple_count += 1
                processed.add(user_id)
                processed.add(partner_id)
        except:
            continue

    if couple_count == 0:
        return await ctx.send("💔 No couples found in this server.")

    embed.set_footer(text=f"Total couples: {couple_count}")
    await ctx.send(embed=embed)

@bot.command()
async def av(ctx):
    user = ctx.author
    if ctx.message.mentions:
        user = ctx.message.mentions[0]
    elif ctx.message.reference:
        msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        user = msg.author
    await ctx.send(f"{user.display_name}'s avatar:\n{user.display_avatar.url}")

@bot.command()
async def myoui(ctx): await ctx.send("# SI MYOUI ANG GOD!!")

@bot.command()
async def ascii(ctx, *, text):
    if len(text) > 20:
        return await ctx.send("⚠️ Text too long.")
    result = pyfiglet.figlet_format(text)
    await ctx.send(f"```\n{result}```")

@bot.command()
async def sayd(ctx, *, msg: str):
    await ctx.message.delete()
    await ctx.send(msg)

@bot.command()
async def setbio(ctx, *, bio: str):
    update_user(ctx.author.id)
    users[str(ctx.author.id)]["bio"] = bio[:100]
    save_users(users)
    await ctx.send("✅ Bio set.")

@bot.command()
async def profile(ctx):
    update_user(ctx.author.id)
    u = users[str(ctx.author.id)]
    embed = discord.Embed(title=f"{ctx.author.name}'s Profile", color=0x77ccff)
    embed.add_field(name="Level", value=u["level"])
    embed.add_field(name="XP", value=u["xp"])
    embed.add_field(name="Balance", value=u["balance"])
    embed.add_field(name="Bio", value=u.get("bio", "None"))
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def bal(ctx):
    update_user(ctx.author.id)
    await ctx.send(f"💰 You have {users[str(ctx.author.id)]['balance']} myouins.")

@bot.command()
async def setbal(ctx, member: discord.Member, amount: int):
    if ctx.author.id not in OWNER_IDS: return
    update_user(member.id)
    users[str(member.id)]["balance"] = amount
    save_users(users)
    await ctx.send(f"✅ Balance set.")

@bot.command()
async def setlevel(ctx, member: discord.Member, level: int):
    if ctx.author.id not in OWNER_IDS: return
    update_user(member.id)
    users[str(member.id)]["level"] = level
    save_users(users)
    await ctx.send(f"✅ Level set.")

@bot.command()
async def daily(ctx):
    uid = ctx.author.id
    cd = check_cooldown(uid, "daily", 86400)
    if cd: return await ctx.send(f"🕒 Wait {cd}s for next daily.")
    update_user(uid)
    users[str(uid)]["balance"] += 500
    save_users(users)
    await ctx.send("💸 You claimed 500 myouins!")

@bot.command()
async def cf(ctx, side: str = None, amount: str = None):
    uid = ctx.author.id
    update_user(uid)
    if side not in ["heads", "tails"]: return await ctx.send("Choose heads/tails.")
    user_bal = users[str(uid)]["balance"]
    bet = user_bal if amount == "all" else int(amount or 0)
    if bet <= 0 or bet > user_bal: return await ctx.send("Invalid amount.")
    result = random.choice(["heads", "tails"])
    win = side == result
    users[str(uid)]["balance"] += bet if win else -bet
    save_users(users)
    await ctx.send(f"{'✅ Won' if win else '❌ Lost'}! It was `{result}`.")

@bot.command()
async def dice(ctx, guess: int):
    if guess < 1 or guess > 6: return await ctx.send("Guess 1–6.")
    roll = random.randint(1, 6)
    if guess == roll:
        users[str(ctx.author.id)]["balance"] += 300
        await ctx.send(f"🎲 Rolled {roll}. +300 myouins!")
    else:
        await ctx.send(f"🎲 Rolled {roll}. Try again.")
    save_users(users)

@bot.command()
async def gunfight(ctx, member: discord.Member):
    winner = random.choice([ctx.author, member])
    loser = member if winner == ctx.author else ctx.author
    await ctx.send(f"🔫 {ctx.author.mention} vs {member.mention}... Bang!")
    await ctx.send(f"💥 {loser.mention} got hit! 1 min timeout.")
    try:
        await loser.timeout(discord.utils.utcnow() + discord.timedelta(minutes=1))
    except: pass

@bot.command()
async def shop(ctx):
    await ctx.send("🛍️ Shop:\n1. XP Booster - 1000 myouins")

@bot.command()
async def leaderboard(ctx, category: str = "level"):
    """Enhanced server leaderboards with multiple categories"""
    valid_categories = ["level", "xp", "balance", "activity", "warnings"]
    if category not in valid_categories:
        return await ctx.send(f"❌ Invalid category. Choose from: {', '.join(valid_categories)}")

    # Filter users who are in this server
    server_users = {}
    for uid, data in users.items():
        member = ctx.guild.get_member(int(uid))
        if member:
            server_users[uid] = data

    if category == "level":
        sorted_users = sorted(server_users.items(), key=lambda x: x[1]["level"], reverse=True)
        title = "🏆 Level Leaderboard"
        value_key = "level"
        emoji = "⭐"
    elif category == "xp":
        sorted_users = sorted(server_users.items(), key=lambda x: x[1]["xp"], reverse=True)
        title = "📈 XP Leaderboard"
        value_key = "xp"
        emoji = "✨"
    elif category == "balance":
        sorted_users = sorted(server_users.items(), key=lambda x: x[1]["balance"], reverse=True)
        title = "💰 Richest Members"
        value_key = "balance"
        emoji = "💎"
    elif category == "activity":
        sorted_users = sorted(server_users.items(), key=lambda x: x[1]["xp"] + (x[1]["level"] * 100), reverse=True)
        title = "🔥 Most Active Members"
        value_key = None
        emoji = "⚡"
    elif category == "warnings":
        sorted_users = sorted(server_users.items(), key=lambda x: len(x[1].get("warns", [])), reverse=True)
        title = "⚠️ Most Warned Members"
        value_key = "warns"
        emoji = "🚨"

    embed = discord.Embed(title=title, color=0xffd700)

    for i, (uid, data) in enumerate(sorted_users[:10]):
        try:
            user = ctx.guild.get_member(int(uid))
            if not user:
                continue

            if category == "activity":
                value = f"Level {data['level']} | {data['xp']} XP"
            elif category == "warnings":
                value = f"{len(data.get('warns', []))} warnings"
            else:
                value = data[value_key]

            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            embed.add_field(
                name=f"{medal} {user.display_name}",
                value=f"{emoji} {value}",
                inline=False
            )
        except:
            continue

    embed.set_footer(text=f"Server: {ctx.guild.name} | Use 'leaderboard <category>' for different rankings")
    await ctx.send(embed=embed)

@bot.command()
async def rate(ctx, *, thing: str):
    await ctx.send(f"🧠 I rate `{thing}` a {random.randint(1,10)}/10.")

@bot.command()
async def ship(ctx, u1: discord.Member, u2: discord.Member):
    score = random.randint(1, 100)
    await ctx.send(f"💘 Ship score between {u1.display_name} & {u2.display_name}: {score}%")

@bot.command()
async def insult(ctx, member: discord.Member):
    roasts = ["Bobo kang putanginamoka magbigti kana jajaha", "poide pakamatay kana? wala naman kasing may pake sa'yo", "hoy hampaslupa kainin mo burat koxxx"]
    await ctx.send(f"🔥 {member.mention}, {random.choice(roasts)}")

@bot.command()
async def uptime(ctx):
    await ctx.send(f"⏱️ Uptime: {int(time.time() - bot.start_time)}s")

@bot.command()
async def serverinfo(ctx):
    g = ctx.guild
    await ctx.send(f"🏰 Server: {g.name}\n👥 Members: {g.member_count}\n🆔 ID: {g.id}")

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"🙋‍♂️ User: {member.name}\n🆔 ID: {member.id}\n🕐 Joined: {member.joined_at}")

@bot.command()
async def whois(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"👤 Name: {member}\nID: {member.id}\nCreated: {member.created_at}")

@bot.command()
async def meme(ctx):
    r = requests.get("https://meme-api.com/gimme").json()
    await ctx.send(r["url"])

@bot.command()
async def cat(ctx):
    r = requests.get("https://api.thecatapi.com/v1/images/search").json()
    await ctx.send(r[0]["url"])

@bot.command()
async def dog(ctx):
    r = requests.get("https://dog.ceo/api/breeds/image/random").json()
    await ctx.send(r["message"])

@bot.command()
async def guess(ctx, num: int):
    win = random.randint(1, 100)
    await ctx.send("🎯 You guessed right!" if num == win else f"❌ Nope, it was {win}.")

@bot.command()
async def trivia(ctx):
    r = requests.get("https://opentdb.com/api.php?amount=1").json()["results"][0]
    await ctx.send(f"📚 Trivia:\n{r['question']}\nAnswer: ||{r['correct_answer']}||")

@bot.command()
async def slots(ctx):
    icons = ["🍒", "🍋", "🔔", "💎"]
    res = [random.choice(icons) for _ in range(3)]
    await ctx.send("🎰 " + " ".join(res) + "\n" + ("✅ Jackpot!" if res.count(res[0]) == 3 else "❌ Better luck!"))

@bot.command()
async def highlow(ctx):
    base = random.randint(1, 100)
    await ctx.send(f"🃏 Base number: {base}. Type `higher` or `lower`.")
    try:
        msg = await bot.wait_for("message", check=lambda m: m.author == ctx.author, timeout=15)
        new = random.randint(1, 100)
        res = "✅ Correct!" if (msg.content.lower() == "higher" and new > base) or (msg.content.lower() == "lower" and new < base) else f"❌ Wrong! It was {new}"
        await ctx.send(res)
    except: await ctx.send("⌛ Timed out.")

@bot.command()
async def deposit(ctx, amount: int):
    update_user(ctx.author.id)
    await ctx.send(f"🏦 Deposited {amount} to bank. (Feature not implemented)")

@bot.command()
async def withdraw(ctx, amount: int):
    update_user(ctx.author.id)
    await ctx.send(f"🏧 Withdrew {amount} from bank. (Feature not implemented)")

@bot.command()
async def rob(ctx, member: discord.Member):
    if check_cooldown(ctx.author.id, "rob", 300): return await ctx.send("⌛ Cooldown active.")
    amt = random.randint(1, 300)
    update_user(ctx.author.id)
    update_user(member.id)
    if users[str(member.id)]["balance"] >= amt:
        users[str(member.id)]["balance"] -= amt
        users[str(ctx.author.id)]["balance"] += amt
        await ctx.send(f"🦹 You robbed {amt} from {member.display_name}")
    else:
        await ctx.send("❌ Target too poor.")
    save_users(users)

@bot.command()
async def work(ctx):
    if check_cooldown(ctx.author.id, "work", 60): return await ctx.send("⌛ Wait a bit.")
    amt = random.randint(100, 400)
    update_user(ctx.author.id)
    users[str(ctx.author.id)]["balance"] += amt
    save_users(users)
    await ctx.send(f"🛠️ You worked and earned {amt}!")

@bot.command()
async def invest(ctx, amount: int):
    uid = str(ctx.author.id)
    update_user(ctx.author.id)
    if users[uid]["balance"] < amount or amount <= 0: return await ctx.send("❌ Invalid.")
    win = random.choice([True, False])
    users[uid]["balance"] += amount if win else -amount
    save_users(users)
    await ctx.send(f"{'📈 Investment succeeded! +' if win else '📉 Lost -'}{amount} myouins.")

@bot.command(name="8ball")
async def eightball(ctx, *, question: str = None):
    """Ask the magic 8ball a question"""
    if not question:
        return await ctx.send("❌ You need to ask a question! Example: `meow 8ball Will I be rich?`")

    responses = [
        # Positive responses
        "🔮 It is certain",
        "🔮 Without a doubt", 
        "🔮 Yes definitely",
        "🔮 You may rely on it",
        "🔮 As I see it, yes",
        "🔮 Most likely",
        "🔮 Outlook good",
        "🔮 Yes",
        "🔮 Signs point to yes",

        # Neutral responses
        "🔮 Reply hazy, try again",
        "🔮 Ask again later",
        "🔮 Better not tell you now",
        "🔮 Cannot predict now",
        "🔮 Concentrate and ask again",

        # Negative responses
        "🔮 Don't count on it",
        "🔮 My reply is no",
        "🔮 My sources say no",
        "🔮 My sources say no",
        "🔮 Outlook not so good",
        "🔮 Very doubtful"
    ]

    response = random.choice(responses)

    embed = discord.Embed(title="🎱 Magic 8-Ball", color=0x800080)
    embed.add_field(name="❓ Question", value=question, inline=False)
    embed.add_field(name="🔮 Answer", value=response, inline=False)
    embed.set_footer(text=f"Asked by {ctx.author.name}")

    await ctx.send(embed=embed)

@bot.command()
async def warn(ctx, member: discord.Member, *, reason=None):
    update_user(member.id)
    users[str(member.id)].setdefault("warns", []).append(reason or "No reason")
    save_users(users)
    await ctx.send(f"⚠️ Warned {member.mention}")

@bot.command()
async def warnings(ctx, member: discord.Member):
    update_user(member.id)
    warns = users[str(member.id)].get("warns", [])
    await ctx.send(f"⚠️ {member.display_name} has {len(warns)} warnings.")

@bot.command()
async def mute(ctx, member: discord.Member, minutes: int = 5):
    until = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
    await member.timeout(until)
    await ctx.send(f"🔇 {member.mention} muted for {minutes} minutes.")

@bot.command()
async def unmute(ctx, member: discord.Member):
    await member.edit(timed_out_until=None)
    await ctx.send(f"🔊 {member.mention} unmuted.")

@bot.command()
async def purge(ctx, amt: int):
    if not ctx.author.guild_permissions.manage_messages: return
    await ctx.channel.purge(limit=amt + 1)
    await ctx.send(f"🧹 Purged {amt} messages.")

# Security Commands
@bot.command()
async def whitelist(ctx, action: str = None, member: discord.Member = None):
    """Manage whitelist for anti-nuke protection"""
    if ctx.author.id not in OWNER_IDS and not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ You need administrator permissions.")

    if action == "add" and member:
        whitelisted_users.add(member.id)
        save_security()
        await ctx.send(f"✅ Added {member.mention} to whitelist.")
    elif action == "remove" and member:
        whitelisted_users.discard(member.id)
        save_security()
        await ctx.send(f"❌ Removed {member.mention} from whitelist.")
    elif action == "list":
        if not whitelisted_users:
            return await ctx.send("📝 Whitelist is empty.")
        users_list = []
        for uid in whitelisted_users:
            try:
                user = await bot.fetch_user(uid)
                users_list.append(f"• {user.name}")
            except:
                users_list.append(f"• Unknown User ({uid})")
        await ctx.send(f"📝 **Whitelisted Users:**\n" + "\n".join(users_list))
    elif action == "clear":
        whitelisted_users.clear()
        save_security()
        await ctx.send("🗑️ Whitelist cleared.")
    else:
        await ctx.send("❌ Usage: `whitelist add/remove @user` or `whitelist list/clear`")

@bot.command()
async def antinuke(ctx, action: str = None):
    """Toggle anti-nuke protection"""
    if ctx.author.id not in OWNER_IDS and not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ You need administrator permissions.")

    guild_id = str(ctx.guild.id)

    if action == "on":
        anti_nuke_enabled[guild_id] = True
        save_security()
        await ctx.send("🛡️ Anti-nuke protection **ENABLED**")
    elif action == "off":
        anti_nuke_enabled[guild_id] = False
        save_security()
        await ctx.send("⚠️ Anti-nuke protection **DISABLED**")
    else:
        status = "**ENABLED**" if anti_nuke_enabled.get(guild_id, False) else "**DISABLED**"
        await ctx.send(f"🛡️ Anti-nuke protection is currently {status}\nUse `antinuke on/off` to toggle.")

@bot.command()
async def lockdown(ctx, reason: str = "Manual lockdown"):
    """Lock all channels in the server"""
    if ctx.author.id not in OWNER_IDS and not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ You need administrator permissions.")

    locked_count = 0
    for channel in ctx.guild.text_channels:
        try:
            if channel.permissions_for(ctx.guild.me).manage_channels:
                await channel.set_permissions(ctx.guild.default_role, send_messages=False)
                locked_channels.add(channel.id)
                locked_count += 1
        except:
            continue

    embed = discord.Embed(
        title="🔒 SERVER LOCKDOWN", 
        description=f"**Reason:** {reason}\n**Channels locked:** {locked_count}", 
        color=0xff0000
    )
    await ctx.send(embed=embed)

@bot.command()
async def unlockdown(ctx):
    """Unlock all previously locked channels"""
    if ctx.author.id not in OWNER_IDS and not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ You need administrator permissions.")

    unlocked_count = 0
    for channel_id in list(locked_channels):
        channel = ctx.guild.get_channel(channel_id)
        if channel:
            try:
                await channel.set_permissions(ctx.guild.default_role, send_messages=None)
                locked_channels.remove(channel_id)
                unlocked_count += 1
            except:
                continue

    embed = discord.Embed(
        title="🔓 LOCKDOWN LIFTED", 
        description=f"**Channels unlocked:** {unlocked_count}", 
        color=0x00ff00
    )
    await ctx.send(embed=embed)

@bot.command()
async def raidmode(ctx, action: str = None):
    """Toggle raid mode protection"""
    if ctx.author.id not in OWNER_IDS and not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ You need administrator permissions.")

    guild_id = str(ctx.guild.id)

    if action == "on":
        anti_nuke_enabled[guild_id] = True
        save_security()
        await auto_lockdown(ctx.guild, "Raid mode activated manually")
        await ctx.send("🚨 **RAID MODE ACTIVATED** - Server locked down")
    elif action == "off":
        # Unlock channels
        for channel_id in list(locked_channels):
            channel = ctx.guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.set_permissions(ctx.guild.default_role, send_messages=None)
                    locked_channels.remove(channel_id)
                except:
                    continue
        await ctx.send("✅ **RAID MODE DEACTIVATED** - Channels unlocked")
    else:
        await ctx.send("❌ Usage: `raidmode on/off`")

@bot.command()
async def security(ctx):
    """Show security status"""
    if ctx.author.id not in OWNER_IDS and not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ You need administrator permissions.")

    guild_id = str(ctx.guild.id)
    antinuke_status = "🟢 **ENABLED**" if anti_nuke_enabled.get(guild_id, False) else "🔴 **DISABLED**"
    whitelist_count = len(whitelisted_users)
    locked_count = len(locked_channels)

    embed = discord.Embed(title="🛡️ Security Status", color=0x55aaff)
    embed.add_field(name="Anti-Nuke", value=antinuke_status, inline=True)
    embed.add_field(name="Whitelisted Users", value=f"{whitelist_count} users", inline=True)
    embed.add_field(name="Locked Channels", value=f"{locked_count} channels", inline=True)
    embed.add_field(name="Recent Joins", value=f"{len(recent_joins)} in last minute", inline=True)

    await ctx.send(embed=embed)

# Soundboard System
@bot.command()
async def soundboard(ctx):
    """Show available sounds"""
    sounds = soundboard_data.get("sounds", {})

    if not sounds:
        return await ctx.send("🔇 No sounds available! Add some with `meow addsound <name> <text>`")

    embed = discord.Embed(title="🔊 Available Sounds", color=0x00ff88)

    for sound_name, sound_data in sounds.items():
        embed.add_field(
            name=f"🎵 {sound_name}",
            value=f"Text: `{sound_data['text'][:50]}{'...' if len(sound_data['text']) > 50 else ''}`\nAdded by: {sound_data.get('author', 'Unknown')}",
            inline=True
        )

    embed.set_footer(text="Use 'meow playsound <name>' to play a sound")
    await ctx.send(embed=embed)

@bot.command()
async def addsound(ctx, name: str, *, text: str):
    """Add a new sound to the soundboard"""
    if len(name) > 20:
        return await ctx.send("❌ Sound name must be 20 characters or less!")

    if len(text) > 200:
        return await ctx.send("❌ Sound text must be 200 characters or less!")

    # Check if sound already exists
    sounds = soundboard_data.get("sounds", {})
    if name.lower() in [s.lower() for s in sounds.keys()]:
        return await ctx.send(f"❌ Sound `{name}` already exists!")

    # Add the sound
    soundboard_data.setdefault("sounds", {})[name] = {
        "text": text,
        "author": ctx.author.name,
        "created_at": time.time()
    }
    save_soundboard(soundboard_data)

    embed = discord.Embed(
        title="✅ Sound Added!",
        description=f"Sound `{name}` has been added to the soundboard!",
        color=0x00ff00
    )
    embed.add_field(name="Text", value=text, inline=False)
    await ctx.send(embed=embed)

# Voice Channel Commands
@bot.command()
async def join(ctx):
    """Join the user's voice channel"""
    if not ctx.author.voice:
        return await ctx.send("❌ magjoin ka muna sa vc tanga")

    channel = ctx.author.voice.channel

    if ctx.voice_client is None:
        await channel.connect()
        await ctx.send(f"✅ Joined {channel.name}")
    else:
        await ctx.voice_client.move_to(channel)
        await ctx.send(f"✅ Moved to {channel.name}")

@bot.command()
async def leave(ctx):
    """Leave the current voice channel"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("✅ Left voice channel")
    else:
        await ctx.send("❌ Not connected to a voice channel")

@bot.command()
async def stop(ctx):
    """Stop any currently playing audio"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏹️ Stopped audio")
    else:
        await ctx.send("❌ Nothing is playing")

@bot.command()
async def tts(ctx, *, text: str):
    """Text-to-speech in voice channel"""
    if not ctx.author.voice:
        return await ctx.send("❌ You need to be in a voice channel!")

    if len(text) > 200:
        return await ctx.send("❌ Text too long (max 200 characters)")

    voice_channel = ctx.author.voice.channel
    audio_file = None
    guild_id = ctx.guild.id
    was_playing_music = False

    try:
        # Connect to voice channel if not connected
        if ctx.voice_client is None:
            voice_client = await voice_channel.connect()
        else:
            voice_client = ctx.voice_client
            # Move to user's channel if in different channel
            if voice_client.channel != voice_channel:
                await voice_client.move_to(voice_channel)

        # Check if music was playing and pause it
        if voice_client.is_playing():
            was_playing_music = True
            voice_client.pause()
            await asyncio.sleep(0.5)

        # Generate TTS
        tts = gTTS(text=text, lang='en', slow=False)
        audio_file = f"tts_{int(time.time())}.mp3"
        tts.save(audio_file)

        # Verify file exists and has content
        if not os.path.exists(audio_file) or os.path.getsize(audio_file) == 0:
            return await ctx.send("❌ Failed to generate TTS audio file")

        # Wait a moment for file to be fully written
        await asyncio.sleep(0.5)

        # Play TTS audio
        source = discord.FFmpegPCMAudio(audio_file)

        # Callback for cleanup and resuming music
        def cleanup_audio(error):
            if error:
                print(f"TTS playback error: {error}")
            
            # Clean up TTS file
            try:
                if audio_file and os.path.exists(audio_file):
                    os.remove(audio_file)
            except Exception as cleanup_error:
                print(f"TTS cleanup error: {cleanup_error}")
            
            # Resume music if it was playing
            if was_playing_music and voice_client and voice_client.is_paused():
                try:
                    voice_client.resume()
                except:
                    pass

        voice_client.play(source, after=cleanup_audio)
        await ctx.send(f"🗣️ Playing TTS: `{text}`")

    except discord.errors.ClientException as client_error:
        print(f"Discord client error: {client_error}")
        await ctx.send(f"❌ Discord error: {str(client_error)}")
        # Resume music if there was an error
        if was_playing_music and ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
    except Exception as general_error:
        print(f"General TTS error: {general_error}")
        import traceback
        traceback.print_exc()
        await ctx.send(f"❌ TTS Error: {str(general_error)}")
        # Resume music if there was an error
        if was_playing_music and ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
    finally:
        # Fallback cleanup if something went wrong
        if audio_file and os.path.exists(audio_file):
            try:
                # Only clean up if not currently playing (let the callback handle it)
                if not (ctx.voice_client and ctx.voice_client.is_playing()):
                    os.remove(audio_file)
            except:
                pass

@bot.command()
async def playsound(ctx, name: str, voice: str = "no"):
    """Play a sound from the soundboard (optionally in voice channel)"""
    sounds = soundboard_data.get("sounds", {})

    # Find sound (case insensitive)
    sound_key = None
    for key in sounds.keys():
        if key.lower() == name.lower():
            sound_key = key
            break

    if not sound_key:
        return await ctx.send(f"❌ Sound `{name}` not found! Use `meow soundboard` to see available sounds.")

    sound_data = sounds[sound_key]

    # Check if user wants voice playback
    if voice.lower() in ["voice", "vc", "yes", "v"]:
        # Check if user is in a voice channel
        if not ctx.author.voice:
            return await ctx.send("❌ You need to be in a voice channel to play sounds!")

        voice_channel = ctx.author.voice.channel

        try:
            # Connect to voice channel
            if ctx.voice_client is None:
                voice_client = await voice_channel.connect()
            else:
                voice_client = ctx.voice_client
                if voice_client.channel != voice_channel:
                    await voice_client.move_to(voice_channel)

            # Generate TTS audio
            tts = gTTS(text=sound_data["text"], lang='en', slow=False)

            # Save to temporary file
            audio_file = f"temp_sound_{int(time.time())}.mp3"
            tts.save(audio_file)

            # Play audio
            if voice_client.is_playing():
                voice_client.stop()

            voice_client.play(discord.FFmpegPCMAudio(audio_file))

            embed = discord.Embed(
                title=f"🔊 Playing in Voice: {sound_key}",
                description=f"Playing TTS of: {sound_data['text']}",
                color=0x00ff88
            )
            embed.set_footer(text=f"Added by {sound_data.get('author', 'Unknown')}")
            await ctx.send(embed=embed)

            # Clean up file after playing
            def cleanup(error):
                try:
                    os.remove(audio_file)
                except:
                    pass

            voice_client.source = discord.PCMVolumeTransformer(voice_client.source)

            # Wait for audio to finish then cleanup
            while voice_client.is_playing():
                await asyncio.sleep(1)

            try:
                os.remove(audio_file)
            except:
                pass

        except Exception as e:
            await ctx.send(f"❌ Error playing sound in voice: {e}")
    else:
        # Text-based playback (original functionality)
        embed = discord.Embed(
            title=f"🔊 Playing: {sound_key}",
            description=sound_data["text"],
            color=0x00ff88
        )
        embed.set_footer(text=f"Added by {sound_data.get('author', 'Unknown')} | Use 'voice' parameter for VC playback")
        await ctx.send(embed=embed)

@bot.command()
async def removesound(ctx, name: str):
    """Remove a sound from the soundboard"""
    if ctx.author.id not in OWNER_IDS and not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ You need administrator permissions to remove sounds.")

    sounds = soundboard_data.get("sounds", {})

    # Find sound (case insensitive)
    sound_key = None
    for key in sounds.keys():
        if key.lower() == name.lower():
            sound_key = key
            break

    if not sound_key:
        return await ctx.send(f"❌ Sound `{name}` not found!")

    # Remove the sound
    del sounds[sound_key]
    save_soundboard(soundboard_data)

    await ctx.send(f"✅ Sound `{sound_key}` has been removed from the soundboard.")

@bot.command()
async def sounds(ctx):
    """Quick list of all sound names"""
    sounds = soundboard_data.get("sounds", {})

    if not sounds:
        return await ctx.send("🔇 No sounds available!")

    sound_list = ", ".join(sounds.keys())

    embed = discord.Embed(
        title="🎵 Sound List",
        description=f"**Available sounds:** {sound_list}",
        color=0x00ff88
    )
    embed.set_footer(text=f"Total: {len(sounds)} sounds | Use 'meow playsound <name>' to play")

    await ctx.send(embed=embed)

from PIL import Image, ImageDraw, ImageFont
import io
import textwrap

@bot.command()
async def brat(ctx, *, text: str):
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    # Create image with text
    width, height = 200, 100
    background_color = (255, 182, 193)
    text_color = (0, 0, 0)

    img = Image.new('RGB', (width, height), background_color)
    draw = ImageDraw.Draw(img)

    try:
        font_main = ImageFont.truetype("DejaVuSans.ttf", 200)      # Increased font size
        font_user = ImageFont.truetype("DejaVuSans.ttf", 150)
    except IOError:
        font_main = ImageFont.load_default()
        font_user = ImageFont.load_default()

    wrapped_text = textwrap.fill(text, width=30)
    bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font_main)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    text_x = (width - text_width) // 2
    text_y = (height - text_height) // 2
    draw.multiline_text((text_x, text_y), wrapped_text, fill=text_color, font=font_main, align="center")

    username_text = f"- {ctx.author.name}"
    user_bbox = draw.textbbox((0, 0), username_text, font=font_user)
    user_height = user_bbox[3] - user_bbox[1]
    draw.text((2, height - user_height - 2), username_text, fill=text_color, font=font_user)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    await ctx.send(file=discord.File(buffer, "brat.png"))

@bot.command()
async def role(ctx, member: discord.Member = None, *, role_name: str = None):
    # Only allow the OWNER_IDS to use
    if ctx.author.id not in OWNER_IDS:
        await ctx.send("❌ Bawal sa'yo 'to tanga hahahaha.")
        return

    if not member or not role_name:
        await ctx.send("❌ Usage: `meow role @user role_name`")
        return

    bot_member = ctx.guild.me

    # Find the closest matching role by name (case insensitive)
    role_name_lower = role_name.lower()
    matching_roles = [r for r in ctx.guild.roles if role_name_lower in r.name.lower()]

    if not matching_roles:
        await ctx.send(f"❌ No roles found matching `{role_name}`")
        return

    role = matching_roles[0]

    if role >= bot_member.top_role:
        await ctx.send("❌ I can't manage that role—it’s higher than mine.")
        return

    if not bot_member.guild_permissions.manage_roles:
        await ctx.send("❌ I need the `Manage Roles` permission.")
        return

    try:
        if role in member.roles:
            await member.remove_roles(role)
            await ctx.send(f"➖ Removed `{role.name}` from {member.mention}")
        else:
            await member.add_roles(role)
            await ctx.send(f"➕ Added `{role.name}` to {member.mention}")
    except discord.Forbidden:
        await ctx.send("❌ I don’t have permission to edit that role.")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


import json, os
from datetime import datetime

afk_file = "afk.json"

# Load AFK data
if os.path.exists(afk_file):
    with open(afk_file, "r") as f:
        afk_users = json.load(f)
else:
    afk_users = {}

def save_afk():
    with open(afk_file, "w") as f:
        json.dump(afk_users, f)

@bot.command()
async def afk(ctx, *, reason="Walang sinabi"):
    now = datetime.utcnow().isoformat()
    afk_users[str(ctx.author.id)] = {"reason": reason, "since": now}
    save_afk()
    await ctx.send(f"{ctx.author.mention} AFK ka na. Reason: {reason}")

# 👇 This replaces your old on_message — so replace it exactly if you already have one.
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # XP system
    update_user(message.author.id)
    add_xp(message.author.id, 5)

    # Remove AFK on message
    user_id = str(message.author.id)
    if user_id in afk_users:
        del afk_users[user_id]
        save_afk()
        await message.channel.send(f"{message.author.mention} Welcome back gang! Tinanggal ko na AFK mo nigga.")

    # Mention detection
    for user in message.mentions:
        uid = str(user.id)
        if uid in afk_users:
            afk_data = afk_users[uid]
            reason = afk_data["reason"]
            since = datetime.fromisoformat(afk_data["since"])
            now = datetime.utcnow()
            duration = now - since
            minutes = int(duration.total_seconds() // 60)
            seconds = int(duration.total_seconds() % 60)
            if minutes >= 60:
                hours = minutes // 60
                mins = minutes % 60
                time_str = f"{hours}h {mins}m ago"
            elif minutes > 0:
                time_str = f"{minutes}m {seconds}s ago"
            else:
                time_str = f"{seconds}s ago"
            await message.channel.send(f"Afk yan, {reason} daw — {time_str}")

    await bot.process_commands(message)

# AI Commands
@bot.command()
async def ask(ctx, *, question: str = None):
    """Ask ChatGPT a question"""
    if not openai_client:
        return await ctx.send("❌ OpenAI not configured. Add OPENAI_API_KEY to secrets.")
    
    if not question:
        return await ctx.send("❌ Please provide a question! Example: `meow ask What is Python?`")

    if len(question) > 500:
        return await ctx.send("❌ Question too long (max 500 characters)")

    # Check cooldown
    cooldown = check_cooldown(ctx.author.id, "ask", 30)
    if cooldown:
        return await ctx.send(f"⏳ Cooldown active. Wait {cooldown}s before asking again.")

    try:
        # Show typing indicator
        async with ctx.typing():
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful Discord bot assistant. Keep responses under 1900 characters. Be friendly and concise."},
                    {"role": "user", "content": question}
                ],
                max_tokens=500,
                temperature=0.7
            )
            
            answer = response.choices[0].message.content
            
            # Split long responses
            if len(answer) > 1900:
                chunks = [answer[i:i+1900] for i in range(0, len(answer), 1900)]
                for i, chunk in enumerate(chunks):
                    embed = discord.Embed(
                        title=f"🤖 ChatGPT Response {i+1}/{len(chunks)}" if len(chunks) > 1 else "🤖 ChatGPT Response",
                        description=chunk,
                        color=0x00a67e
                    )
                    if i == 0:
                        embed.add_field(name="Question", value=question[:1000], inline=False)
                    await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    title="🤖 ChatGPT Response",
                    description=answer,
                    color=0x00a67e
                )
                embed.add_field(name="Question", value=question[:1000], inline=False)
                embed.set_footer(text=f"Asked by {ctx.author.name}")
                await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command()
async def imagine(ctx, *, prompt: str = None):
    """Generate an image using DALL-E"""
    if not openai_client:
        return await ctx.send("❌ OpenAI not configured. Add OPENAI_API_KEY to secrets.")
    
    if not prompt:
        return await ctx.send("❌ Please provide a description! Example: `meow imagine a cat wearing a crown`")

    if len(prompt) > 400:
        return await ctx.send("❌ Prompt too long (max 400 characters)")

    # Check cooldown (longer for image generation)
    cooldown = check_cooldown(ctx.author.id, "imagine", 60)
    if cooldown:
        return await ctx.send(f"⏳ Cooldown active. Wait {cooldown}s before generating another image.")

    try:
        # Show typing indicator
        async with ctx.typing():
            response = openai_client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            
            image_url = response.data[0].url
            
            embed = discord.Embed(
                title="🎨 AI Generated Image",
                description=f"**Prompt:** {prompt}",
                color=0xff6b6b
            )
            embed.set_image(url=image_url)
            embed.set_footer(text=f"Generated by {ctx.author.name} using DALL-E 3")
            
            await ctx.send(embed=embed)

    except Exception as e:
        error_msg = str(e)
        if "content_policy_violation" in error_msg:
            await ctx.send("❌ Your prompt violates OpenAI's content policy. Please try a different prompt.")
        elif "billing" in error_msg.lower():
            await ctx.send("❌ OpenAI API quota exceeded. Please check your billing.")
        else:
            await ctx.send(f"❌ Error generating image: {error_msg}")

# Music system
music_queues = {}
current_tracks = {}
loop_modes = {}  # 'off', 'track', 'queue'
volume_levels = {}

# Spotify configuration (add your credentials to secrets)
try:
    spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
    spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')

    if spotify_client_id and spotify_client_secret:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=spotify_client_id,
            client_secret=spotify_client_secret
        ))
    else:
        spotify = None
        print("⚠️ Spotify credentials not found. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to secrets.")
except Exception as e:
    spotify = None
    print(f"⚠️ Spotify setup failed: {e}")

# YT-DLP options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extractaudio': True,
    'audioformat': 'mp3',
    'audioquality': '192K',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

def get_guild_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = []
    return music_queues[guild_id]

def format_duration(seconds):
    """Convert seconds to MM:SS format"""
    if not seconds:
        return "Unknown"
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes}:{seconds:02d}"

def detect_url_type(url):
    """Detect the type of music URL"""
    if 'spotify.com' in url:
        if '/track/' in url:
            return 'spotify_track'
        elif '/playlist/' in url:
            return 'spotify_playlist'
        elif '/album/' in url:
            return 'spotify_album'
    elif 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    elif 'soundcloud.com' in url:
        return 'soundcloud'
    return 'direct'

async def search_youtube(query):
    """Search YouTube for a track"""
    try:
        search = VideosSearch(query, limit=1)
        result = search.result()
        if result['result']:
            video = result['result'][0]
            # Convert duration from MM:SS to seconds if needed
            duration_str = video.get('duration', 'Unknown')
            duration_seconds = None
            
            if duration_str and duration_str != 'Unknown':
                try:
                    # Parse MM:SS format
                    if ':' in duration_str:
                        parts = duration_str.split(':')
                        if len(parts) == 2:
                            minutes, seconds = map(int, parts)
                            duration_seconds = minutes * 60 + seconds
                        elif len(parts) == 3:
                            hours, minutes, seconds = map(int, parts)
                            duration_seconds = hours * 3600 + minutes * 60 + seconds
                except:
                    pass
            
            return {
                'title': video['title'],
                'url': video['link'],
                'duration': duration_seconds,
                'duration_str': duration_str,
                'thumbnail': video.get('thumbnails', [{}])[0].get('url'),
                'channel': video.get('channel', {}).get('name', 'Unknown')
            }
    except Exception as e:
        print(f"YouTube search error: {e}")
    return None

async def get_spotify_track_info(track_id):
    """Get Spotify track information"""
    if not spotify:
        return None

    try:
        track = spotify.track(track_id)
        duration_seconds = track['duration_ms'] // 1000
        return {
            'title': f"{track['artists'][0]['name']} - {track['name']}",
            'artist': track['artists'][0]['name'],
            'name': track['name'],
            'duration': duration_seconds,
            'duration_str': format_duration(duration_seconds),
            'external_urls': track['external_urls'],
            'preview_url': track.get('preview_url')
        }
    except Exception as e:
        print(f"Spotify API error: {e}")
    return None

async def get_spotify_playlist_tracks(playlist_id):
    """Get tracks from Spotify playlist"""
    if not spotify:
        return []

    try:
        results = spotify.playlist_tracks(playlist_id)
        tracks = []

        for item in results['items']:
            if item['track'] and item['track']['type'] == 'track':
                track = item['track']
                duration_seconds = track['duration_ms'] // 1000
                tracks.append({
                    'title': f"{track['artists'][0]['name']} - {track['name']}",
                    'artist': track['artists'][0]['name'],
                    'name': track['name'],
                    'duration': duration_seconds,
                    'duration_str': format_duration(duration_seconds),
                })

        return tracks
    except Exception as e:
        print(f"Spotify playlist error: {e}")
    return []

async def process_music_input(input_str, requester):
    """Process various types of music input (URL, search query, etc.)"""
    url_type = detect_url_type(input_str)

    if url_type == 'spotify_track':
        # Extract Spotify track ID
        track_id = re.search(r'track/([a-zA-Z0-9]+)', input_str)
        if track_id:
            track_info = await get_spotify_track_info(track_id.group(1))
            if track_info:
                # Search for the track on YouTube
                youtube_result = await search_youtube(track_info['title'])
                if youtube_result:
                    return [{
                        'title': track_info['title'],
                        'url': youtube_result['url'],
                        'duration': track_info['duration'],
                        'duration_str': format_duration(track_info['duration']),
                        'requester': requester,
                        'thumbnail': youtube_result.get('thumbnail'),
                        'source': 'Spotify → YouTube'
                    }]

    elif url_type == 'spotify_playlist':
        # Extract Spotify playlist ID
        playlist_id = re.search(r'playlist/([a-zA-Z0-9]+)', input_str)
        if playlist_id:
            tracks = await get_spotify_playlist_tracks(playlist_id.group(1))
            results = []
            for track in tracks[:50]:  # Limit to 50 tracks
                youtube_result = await search_youtube(track['title'])
                if youtube_result:
                    results.append({
                        'title': track['title'],
                        'url': youtube_result['url'],
                        'duration': track['duration'],
                        'duration_str': format_duration(track['duration']),
                        'requester': requester,
                        'thumbnail': youtube_result.get('thumbnail'),
                        'source': 'Spotify Playlist → YouTube'
                    })
            return results

    elif url_type == 'youtube' or url_type == 'soundcloud' or url_type == 'direct':
        # Direct URL
        return [{
            'title': 'Loading...',
            'url': input_str,
            'requester': requester,
            'source': url_type.title()
        }]

    else:
        # Search query
        youtube_result = await search_youtube(input_str)
        if youtube_result:
            return [{
                'title': youtube_result['title'],
                'url': youtube_result['url'],
                'duration_str': youtube_result.get('duration', 'Unknown'),
                'requester': requester,
                'thumbnail': youtube_result.get('thumbnail'),
                'source': 'YouTube Search'
            }]

    return []

async def play_next(ctx):
    guild_id = ctx.guild.id
    queue = get_guild_queue(guild_id)
    loop_mode = loop_modes.get(guild_id, 'off')

    # Handle loop modes
    if loop_mode == 'track' and guild_id in current_tracks:
        # Replay current track
        next_track = current_tracks[guild_id].copy()
    elif queue:
        next_track = queue.pop(0)
        if loop_mode == 'queue':
            # Add back to end of queue
            queue.append(next_track.copy())
    else:
        current_tracks.pop(guild_id, None)
        return

    if ctx.voice_client:
        try:
            player = await YTDLSource.from_url(next_track['url'], loop=ctx.bot.loop, stream=True)
            current_tracks[guild_id] = next_track

            # Set volume
            volume = volume_levels.get(guild_id, 0.5)
            player.volume = volume

            def after_playing(error):
                if error:
                    print(f'Player error: {error}')
                coro = play_next(ctx)
                fut = asyncio.run_coroutine_threadsafe(coro, ctx.bot.loop)
                try:
                    fut.result()
                except:
                    pass

            ctx.voice_client.play(player, after=after_playing)

            embed = discord.Embed(title="🎵 Now Playing", description=f"**{next_track['title']}**", color=0x1db954)
            if next_track.get('thumbnail'):
                embed.set_thumbnail(url=next_track['thumbnail'])
            embed.add_field(name="Duration", value=next_track.get('duration_str', 'Unknown'), inline=True)
            embed.add_field(name="Requested by", value=next_track['requester'], inline=True)
            embed.add_field(name="Source", value=next_track.get('source', 'Unknown'), inline=True)

            # Add loop mode info
            loop_emoji = {"off": "➡️", "track": "🔂", "queue": "🔁"}
            embed.add_field(name="Loop", value=f"{loop_emoji.get(loop_mode, '➡️')} {loop_mode.title()}", inline=True)
            embed.add_field(name="Volume", value=f"🔊 {int(volume * 100)}%", inline=True)

            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ Error playing track: {e}")
            await play_next(ctx)
    else:
        current_tracks.pop(guild_id, None)

@bot.command(name="play")
async def play(ctx, *, query):
    """Play music from YouTube, Spotify, etc."""
    if not ctx.author.voice:
        return await ctx.send("❌ You need to be in a voice channel to play music!")

    channel = ctx.author.voice.channel
    guild_id = ctx.guild.id
    queue = get_guild_queue(guild_id)

    try:
        # Connect to voice channel if not connected
        if ctx.voice_client is None:
            voice_client = await channel.connect()
        else:
            voice_client = ctx.voice_client
            if voice_client.channel != channel:
                await voice_client.move_to(channel)

        # Process music input
        tracks = await process_music_input(query, ctx.author.name)

        if not tracks:
            return await ctx.send("❌ No tracks found.")

        # Extract proper track info for tracks marked as 'Loading...'
        for track in tracks:
            if track['title'] == 'Loading...':
                try:
                    # Extract info from YouTube URL
                    data = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: ytdl.extract_info(track['url'], download=False)
                    )
                    if data:
                        track['title'] = data.get('title', track['url'])
                        track['duration'] = data.get('duration')
                        track['duration_str'] = format_duration(data.get('duration')) if data.get('duration') else 'Unknown'
                        track['thumbnail'] = data.get('thumbnail')
                except Exception as e:
                    print(f"Error extracting track info: {e}")
                    track['title'] = track['url']  # Fallback to URL

        # Add tracks to queue
        queue.extend(tracks)
        music_queues[guild_id] = queue  # Update queue

        # Start playing if not already playing
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
        else:
            # Confirmation for queue addition
            if len(tracks) == 1:
                await ctx.send(f"🎵 Added to queue: **{tracks[0]['title']}**")
            else:
                await ctx.send(f"🎵 Added {len(tracks)} tracks to the queue.")

    except discord.errors.ClientException as client_error:
        print(f"Discord client error: {client_error}")
        await ctx.send(f"❌ Discord error: {str(client_error)}")
    except Exception as general_error:
        print(f"General music error: {general_error}")
        import traceback
        traceback.print_exc()
        await ctx.send(f"❌ Music Error: {str(general_error)}")

@bot.command(name="queue")
async def queue_list(ctx):
    """List the current music queue"""
    guild_id = ctx.guild.id
    queue = get_guild_queue(guild_id)

    if not queue:
        return await ctx.send("Queue is empty.")

    embed = discord.Embed(title="🎵 Music Queue", color=0x1db954)
    for i, track in enumerate(queue[:10]):  # Show up to 10 tracks
        embed.add_field(
            name=f"{i+1}. {track['title']}",
            value=f"Duration: {track.get('duration_str', 'Unknown')}, Requested by: {track['requester']}",
            inline=False
        )

    if len(queue) > 10:
        embed.set_footer(text=f"And {len(queue) - 10} more...")

    await ctx.send(embed=embed)

@bot.command(name="skip")
async def skip(ctx):
    """Skip the current song"""
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        return await ctx.send("❌ Not playing anything.")

    ctx.voice_client.stop()
    await ctx.send("⏭️ Skipped the current song.")

@bot.command(name="pause")
async def pause(ctx):
    """Pause the current song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused.")
    else:
        await ctx.send("❌ Not playing anything.")

@bot.command(name="resume")
async def resume(ctx):
    """Resume the current song"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed.")
    else:
        await ctx.send("❌ Not paused.")

@bot.command(name="loop")
async def loop_mode(ctx, mode="off"):
    """Set loop mode: off, track, queue"""
    guild_id = ctx.guild.id
    if mode not in ["off", "track", "queue"]:
        return await ctx.send("❌ Invalid loop mode. Choose off, track, or queue.")

    loop_modes[guild_id] = mode
    loop_emoji = {"off": "➡️", "track": "🔂", "queue": "🔁"}
    await ctx.send(f"{loop_emoji.get(mode, '➡️')} Loop mode set to {mode}.")

@bot.command(name="volume")
async def set_volume(ctx, volume: int):
    """Set the volume (0-100)"""
    if not (0 <= volume <= 100):
        return await ctx.send("❌ Volume must be between 0 and 100.")

    guild_id = ctx.guild.id
    volume_levels[guild_id] = volume / 100
    if ctx.voice_client and ctx.voice_client.source:
        ctx.voice_client.source.volume = volume / 100
    await ctx.send(f"🔊 Volume set to {volume}%.")

@bot.command(name="nowplaying")
async def now_playing(ctx):
    """Show the currently playing song"""
    guild_id = ctx.guild.id
    track = current_tracks.get(guild_id)

    if not track:
        return await ctx.send("❌ Not playing anything.")

    embed = discord.Embed(title="🎵 Now Playing", description=f"**{track['title']}**", color=0x1db954)
    if track.get('thumbnail'):
        embed.set_thumbnail(url=track['thumbnail'])
    embed.add_field(name="Duration", value=track.get('duration_str', 'Unknown'), inline=True)
    embed.add_field(name="Requested by", value=track['requester'], inline=True)
    embed.add_field(name="Source", value=track.get('source', 'Unknown'), inline=True)
    loop_mode = loop_modes.get(guild_id, 'off')
    loop_emoji = {"off": "➡️", "track": "🔂", "queue": "🔁"}
    embed.add_field(name="Loop", value=f"{loop_emoji.get(loop_mode, '➡️')} {loop_mode.title()}", inline=True)
    volume = volume_levels.get(guild_id, 0.5)
    embed.add_field(name="Volume", value=f"🔊 {int(volume * 100)}%", inline=True)

    await ctx.send(embed=embed)

@bot.command(name="remove")
async def remove_from_queue(ctx, index: int):
    """Remove a song from the queue at a specific index."""
    guild_id = ctx.guild.id
    queue = get_guild_queue(guild_id)

    if not queue:
        return await ctx.send("❌ The queue is empty.")

    if 1 <= index <= len(queue):
        removed_track = queue.pop(index - 1)
        await ctx.send(f"✅ Removed **{removed_track['title']}** from the queue.")
    else:
        await ctx.send("❌ Invalid index. Please provide a number within the queue range.")

keep_alive()
bot.run(TOKEN)