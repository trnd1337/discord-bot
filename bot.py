from __future__ import annotations

import asyncio
import ipaddress
import platform
import subprocess
import os
import random
import time
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
import requests
from discord import app_commands
from discord.ext import commands


def load_dotenv_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv_file()

GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "1452798779848655038"))
TOKEN = os.getenv("DISCORD_TOKEN")
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN")
if TOKEN:
    TOKEN = TOKEN.strip()
    if TOKEN.lower().startswith("bot "):
        TOKEN = TOKEN[4:].strip()
BRAND_COLOR = 0x7C3AED
ERROR_COLOR = 0xEF4444
SUCCESS_COLOR = 0x22C55E
IP_CACHE_TTL_SECONDS = 300
LOL_REGION_DOMAINS = {
    "euw": "euw.op.gg",
    "eune": "eune.op.gg",
    "na": "na.op.gg",
    "kr": "www.op.gg",
    "lan": "lan.op.gg",
    "las": "las.op.gg",
    "br": "br.op.gg",
    "oce": "oce.op.gg",
    "ru": "ru.op.gg",
    "tr": "tr.op.gg",
    "jp": "jp.op.gg",
    "sg": "sg.op.gg",
    "ph": "ph.op.gg",
    "th": "th.op.gg",
    "tw": "tw.op.gg",
    "vn": "vn.op.gg",
}


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
commands_synced = False
ip_lookup_cache: dict[str, tuple[float, dict]] = {}


def make_embed(title: str, color: int = BRAND_COLOR, description: Optional[str] = None) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="//")
    return embed


async def send_interaction_error(interaction: discord.Interaction, message: str) -> None:
    payload = {"content": f"Error: {message}", "ephemeral": True}
    if interaction.response.is_done():
        await interaction.followup.send(**payload)
    else:
        await interaction.response.send_message(**payload)


async def fetch_discord_user(user_id: str) -> Optional[discord.User]:
    if not user_id.isdigit():
        return None

    try:
        return await bot.fetch_user(int(user_id))
    except (discord.NotFound, discord.HTTPException):
        return None


async def fetch_ip_info(ip: str) -> dict:
    if not IPINFO_TOKEN:
        raise RuntimeError("IPINFO_TOKEN is not configured.")

    cached = ip_lookup_cache.get(ip)
    now = time.monotonic()
    if cached and now - cached[0] < IP_CACHE_TTL_SECONDS:
        return cached[1]

    def request_ip_info() -> dict:
        response = requests.get(
            f"https://ipinfo.io/{ip}/json",
            params={"token": IPINFO_TOKEN},
            timeout=8,
        )
        response.raise_for_status()
        return response.json()

    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, request_ip_info)
    ip_lookup_cache[ip] = (now, data)
    return data


async def fetch_ping_ip_status(ip: str) -> dict:
    try:
        ipaddress.ip_address(ip)
    except ValueError as error:
        raise ValueError("Invalid IP address.") from error
    loop = asyncio.get_running_loop()

    def local_ping() -> dict:
        cmd = ["ping", "-c", "4", ip]
        if platform.system() == "Windows":
            cmd = ["ping", "-n", "4", ip]

        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=15)
        except Exception as err:
            return {"provider": "local", "fallback": None, "error": str(err)}

        times: list[float] = []
        for line in output.splitlines():
            if "time=" in line:
                part = line.split("time=", 1)[1]
                token = part.split()[0]
                token = token.replace("ms", "")
                try:
                    times.append(float(token))
                except ValueError:
                    continue
        return {"provider": "local", "fallback": times}

    return await loop.run_in_executor(None, local_ping)


def pingip_embed(ip: str, data: dict) -> discord.Embed:
    provider = data.get("provider")
    result = data.get("result")
    fallback = data.get("fallback")
    text = data.get("text")
    alive = False
    lines: list[str] = []

    if provider == "hackertarget" and isinstance(text, str):
        # Show raw hackertarget output
        raw_lines = [ln for ln in text.splitlines() if ln.strip()]
        if raw_lines:
            lines = raw_lines[:10]
            # try to detect success
            alive = any("bytes=" in ln or "time=" in ln for ln in raw_lines)
        else:
            lines = ["No ping output from hackertarget"]

    elif fallback is not None:
        # fallback contains list of ms values
        if isinstance(fallback, list) and fallback:
            alive = True
            lines = [f"Local ping: {t} ms" for t in fallback]
        else:
            lines = ["No local ping replies"]
    elif isinstance(result, list):
        for index, node in enumerate(result, start=1):
            if not node or not isinstance(node, list):
                lines.append(f"Node {index}: dead")
                continue
            node_status: list[str] = []
            for entry in node:
                if not isinstance(entry, list) or not entry:
                    node_status.append("dead")
                    continue
                delay = entry[0]
                if delay in {None, "timeout", "null"}:
                    node_status.append("dead")
                    continue
                try:
                    float(delay)
                    node_status.append(f"{delay} ms")
                    alive = True
                except (TypeError, ValueError):
                    node_status.append(str(delay))
            lines.append(f"Node {index}: {', '.join(node_status)}")
    else:
        lines.append("No ping results available.")

    status_text = "alive" if alive else "dead"
    embed = make_embed(f"IP Ping: {ip}", SUCCESS_COLOR if alive else ERROR_COLOR)
    embed.add_field(name="Status", value=status_text, inline=True)
    provider_label = data.get("provider") or "local"
    if provider_label == "hackertarget":
        provider_label = "api.hackertarget.com"
    elif provider_label == "local":
        provider_label = "local ping"
    embed.add_field(name="Provider", value=provider_label, inline=True)
    if lines:
        embed.add_field(name="Results", value="\n".join(lines[:6]), inline=False)
    return embed


def format_lol_region(region: str) -> str:
    return LOL_REGION_DOMAINS.get(region.strip().lower(), "www.op.gg")


def parse_loltrack_query(text: str) -> tuple[str, str]:
    parts = text.strip().split()
    if parts and parts[-1].lower() in LOL_REGION_DOMAINS:
        return " ".join(parts[:-1]).strip(), parts[-1].lower()
    return text.strip(), "euw"


async def fetch_lol_tracker(username: str, region: str = "euw") -> dict:
    if not username:
        raise ValueError("Provide a League of Legends summoner name.")

    # Build op.gg profile URL in the form:
    # https://op.gg/lol/summoners/{region}/{name-with-dash}
    # Convert discriminator from `#KOREA` to `-KOREA` as op.gg expects.
    name_dash = username.strip()
    # Replace any trailing '#something' with '-something' and keep the rest of the name
    name_dash = name_dash.replace('#', '-')
    if not name_dash:
        raise ValueError("Provide a valid summoner name.")
    profile_url = f"https://op.gg/lol/summoners/{region}/{urllib.parse.quote(name_dash)}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html"}
    response = requests.get(profile_url, headers=headers, timeout=15)
    response.raise_for_status()
    html = response.text
    # Try to extract meta description first (reliable source for rank/LP/win-loss)
    rank = None
    lp = None
    win_loss = None
    kda = None

    md = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html, re.IGNORECASE)
    meta_desc = md.group(1) if md else None
    if meta_desc:
        # meta description often looks like: "name / Iron 4 40LP / 51Win 72Lose ..."
        parts = [p.strip() for p in meta_desc.split('/') if p.strip()]
        # rank and lp are usually in the first or second part
        for part in parts[:2]:
            # capture rank like 'Iron 4' or 'Silver 2'
            m = re.search(r'(?i)\b(Iron|Bronze|Silver|Gold|Platinum|Diamond|Emerald|Master|Grandmaster|Challenger)\b\s*([0-9IVXLCDM]*)', part)
            if m:
                rank = m.group(1).capitalize()
                if m.group(2):
                    rank = f"{rank} {m.group(2)}"
            # capture LP like '40LP' or '40 LP'
            m2 = re.search(r'(?i)([0-9,]+)\s*LP', part)
            if m2:
                lp = m2.group(1) + "LP"
        # win/loss may be in the next part
        for part in parts[1:3]:
            m3 = re.search(r'(?i)([0-9]+)W\s*([0-9]+)L', part)
            if m3:
                win_loss = f"{m3.group(1)}W {m3.group(2)}L"

    # If kda not present in meta, search page for KDA pattern
    kda_match = re.search(r'(?i)([0-9]+\.?[0-9]*\s*:\s*[0-9]+\.?[0-9]*\s*:\s*[0-9]+\.?[0-9]*)', html)
    if kda_match:
        kda = kda_match.group(1).strip()

    # If rank still not found, attempt looser page-matching as a fallback
    if not rank:
        rank_match = re.search(r'(?i)(?:TierRank|tier-rank|divisions|LeagueInfo|Tier|tier)[^>]*>([^<]+)<', html)
        if rank_match:
            candidate = rank_match.group(1).strip()
            # ignore obvious non-rank menu items
            if candidate.lower() not in ("leaderboards", "leaderboard"):
                rank = candidate

    # Try to find a profile icon. Prefer op.gg profile_icons pattern, then img patterns, then og:image.
    icon_url = None
    # look for op.gg static profile icons (e.g. profileIcon7063.jpg)
    m_icon = re.search(r'(https?://[^"\s]*profile_icons/profileIcon[0-9]+\.[a-zA-Z0-9_?=&%\.-]+)', html)
    if m_icon:
        icon_url = m_icon.group(1)
    else:
        # Look for an <img> with profile-like class
        img_match = re.search(r'<img[^>]+class="[^"]*(?:profile-icon|ProfileIcon|SummonerIcon|Profile__icon|size-16)[^"]*"[^>]+src="([^"]+)"', html, re.IGNORECASE)
        if img_match:
            icon_url = img_match.group(1)
        else:
            # Fallback: first image that looks like a summoner/user icon or cdn
            img_match2 = re.search(r'<img[^>]+src="([^"]*(?:summoner|usericon|userIcons|profile|opgg-static|opgg-static.akamaized|profile_icons|cdn.op.gg)[^"]*)"', html, re.IGNORECASE)
            if img_match2:
                icon_url = img_match2.group(1)
            else:
                og = re.search(r'<meta property="og:image" content="([^"]+)"', html, re.IGNORECASE)
                if og:
                    icon_url = og.group(1)

    # Normalize protocol-relative and relative URLs
    if icon_url:
        if icon_url.startswith("//"):
            icon_url = "https:" + icon_url
        elif icon_url.startswith("/"):
            icon_url = f"https://{format_lol_region(region)}" + icon_url

    return {
        "provider": "lol",
        "profile_url": profile_url,
        "rank": rank,
        "lp": lp,
        "win_loss": win_loss,
        "kda": kda,
        "icon_url": icon_url,
        "region": region.lower(),
    }


def loltrack_embed(username: str, region: str, data: dict) -> discord.Embed:
    embed = make_embed(f"LoL Tracker: {username}", SUCCESS_COLOR)
    icon = data.get("icon_url")
    if icon:
        try:
            embed.set_thumbnail(url=icon)
        except Exception:
            pass
    embed.add_field(name="Region", value=region.upper(), inline=True)
    embed.add_field(name="Profile", value=f"[Open profile]({data.get('profile_url')})", inline=True)

    rank = data.get("rank") or "Unknown"
    embed.add_field(name="Rank", value=rank, inline=True)
    if data.get("lp"):
        embed.add_field(name="LP", value=data["lp"], inline=True)
    if data.get("win_loss"):
        embed.add_field(name="Win/Loss", value=data["win_loss"], inline=True)
    if data.get("kda"):
        embed.add_field(name="KDA", value=data["kda"], inline=True)

    if rank == "Unknown":
        embed.description = "Could not parse full profile details; open the profile link for the latest info."
    return embed


def ip_lookup_embed(data: dict, fallback_ip: str) -> discord.Embed:
    embed = make_embed(f"IP Lookup: {data.get('ip', fallback_ip)}")
    fields = [
        ("Country", data.get("country", "N/A"), True),
        ("Region", data.get("region", "N/A"), True),
        ("City", data.get("city", "N/A"), True),
        ("Postal", data.get("postal", "N/A"), True),
        ("ISP / Org", data.get("org", "N/A"), True),
        ("Hostname", data.get("hostname", "N/A"), True),
        ("Coordinates", data.get("loc", "N/A"), False),
        ("Timezone", data.get("timezone", "N/A"), False),
    ]
    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)

    country = data.get("country")
    if country and len(country) == 2:
        embed.set_thumbnail(url=f"https://flagcdn.com/w320/{country.lower()}.png")
    embed.set_footer(text="Data from ipinfo.io")
    return embed


def moderation_embed(title: str, member: discord.abc.User, moderator: discord.abc.User, reason: Optional[str] = None) -> discord.Embed:
    embed = make_embed(title)
    embed.add_field(name="User", value=f"{member.mention}\n`{member.id}`", inline=True)
    embed.add_field(name="By", value=moderator.mention, inline=True)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def command_center_embed() -> discord.Embed:
    embed = make_embed("Command Center", description="Your shiny little moderation console.")
    embed.add_field(name="/whois", value="Look up a public IP address.", inline=False)
    embed.add_field(name="/pingip", value="Ping an IP address with the local system ping command.", inline=False)
    embed.add_field(name="/loltrack", value="Track a League of Legends summoner account.", inline=False)
    embed.add_field(name="/whoisuser", value="Show detailed Discord user info by member, ID, or username.", inline=False)
    embed.add_field(name="/purge", value="Delete 1-100 recent messages.", inline=False)
    embed.add_field(name="/slowmode, /lock, /unlock", value="Channel moderation tools.", inline=False)
    embed.add_field(name="/timeout, /untimeout", value="Manage member timeouts.", inline=False)
    embed.add_field(name="/kick, /ban, /unban", value="Moderation actions with clean embeds.", inline=False)
    embed.add_field(name="/ping, /server, /avatar", value="Fast utility commands. `/avatar` also supports user IDs.", inline=False)
    embed.add_field(name="/poll, /roll, /coinflip, /choose", value="Community and fun commands.", inline=False)
    embed.add_field(name="Mention Mode", value="Use commands like `@bot ping`, `@bot avatar 123`, or `@bot roll 2d20`.", inline=False)
    return embed


def server_embed(guild: discord.Guild) -> discord.Embed:
    embed = make_embed(guild.name)
    embed.add_field(name="Members", value=str(guild.member_count), inline=True)
    embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=True)
    embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "R"), inline=True)
    embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
    embed.add_field(name="Boosts", value=str(guild.premium_subscription_count), inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


def roll_embed(dice: str) -> tuple[Optional[discord.Embed], Optional[str]]:
    try:
        count_text, sides_text = dice.lower().split("d", 1)
        count = int(count_text or "1")
        sides = int(sides_text)
    except ValueError:
        return None, "Use dice format like `1d6`, `2d20`, or `4d8`."

    if not 1 <= count <= 20 or not 2 <= sides <= 1000:
        return None, "Dice must be between `1d2` and `20d1000`."

    rolls = [random.randint(1, sides) for _ in range(count)]
    embed = make_embed("Dice Roll", SUCCESS_COLOR)
    embed.add_field(name="Dice", value=f"`{count}d{sides}`", inline=True)
    embed.add_field(name="Total", value=f"**{sum(rolls)}**", inline=True)
    embed.add_field(name="Rolls", value=", ".join(str(roll) for roll in rolls), inline=False)
    return embed, None


async def ensure_moderatable(interaction: discord.Interaction, member: discord.Member) -> bool:
    if member == interaction.user:
        await send_interaction_error(interaction, "You cannot moderate yourself.")
        return False
    if member == interaction.guild.me:
        await send_interaction_error(interaction, "I refuse to bonk myself with my own clipboard.")
        return False
    if member.top_role >= interaction.user.top_role and interaction.guild.owner_id != interaction.user.id:
        await send_interaction_error(interaction, "That member has an equal or higher role than you.")
        return False
    if member.top_role >= interaction.guild.me.top_role:
        await send_interaction_error(interaction, "That member has an equal or higher role than me.")
        return False
    return True


async def ensure_message_moderatable(message: discord.Message, member: discord.Member) -> bool:
    if not message.guild:
        await message.channel.send("This command only works in a server.")
        return False
    if member == message.author:
        await message.channel.send("You cannot moderate yourself.")
        return False
    if member == message.guild.me:
        await message.channel.send("I refuse to bonk myself with my own clipboard.")
        return False
    if member.top_role >= message.author.top_role and message.guild.owner_id != message.author.id:
        await message.channel.send("That member has an equal or higher role than you.")
        return False
    if member.top_role >= message.guild.me.top_role:
        await message.channel.send("That member has an equal or higher role than me.")
        return False
    return True


async def member_from_message(message: discord.Message, text: str) -> Optional[discord.Member]:
    if not message.guild:
        return None

    mentioned_members = [member for member in message.mentions if member != bot.user]
    if mentioned_members:
        return mentioned_members[0]

    token = text.split(maxsplit=1)[0] if text else ""
    if token.isdigit():
        member = message.guild.get_member(int(token))
        if member:
            return member
        try:
            return await message.guild.fetch_member(int(token))
        except (discord.NotFound, discord.HTTPException):
            return None

    return None


def strip_member_argument(message: discord.Message, text: str, member: discord.Member) -> str:
    cleaned = text.strip()
    for mention in (member.mention, f"<@!{member.id}>", str(member.id)):
        if cleaned.startswith(mention):
            return cleaned[len(mention):].strip()
    parts = cleaned.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


@bot.event
async def on_ready() -> None:
    global commands_synced
    if not commands_synced:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        commands_synced = True

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="/help"),
        status=discord.Status.online,
    )
    print(f"Bot started as {bot.user}")


@bot.tree.command(name="help", description="Show the bot command menu")
async def help_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=command_center_embed(), ephemeral=True)


@bot.tree.command(name="ping", description="Check the bot latency")
async def ping(interaction: discord.Interaction) -> None:
    latency_ms = round(bot.latency * 1000)
    embed = make_embed("Pong", SUCCESS_COLOR, f"Gateway latency: **{latency_ms}ms**")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="server", description="Show server information")
async def server(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=server_embed(interaction.guild))


def avatar_embed(user: discord.abc.User, title_name: str) -> discord.Embed:
    embed = make_embed(f"{title_name}'s Avatar")
    avatar_url = user.display_avatar.url
    embed.set_image(url=avatar_url)
    embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="Open", value=f"[Avatar URL]({avatar_url})", inline=True)
    return embed


def whoisuser_embed(user: discord.User, guild_member: Optional[discord.Member] = None) -> discord.Embed:
    embed = make_embed(f"User Info: {user}")
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="Discord Tag", value=f"{user.name}#{user.discriminator}", inline=True)
    embed.add_field(name="User ID", value=f"`{user.id}`", inline=True)
    embed.add_field(name="Bot Account", value="Yes" if user.bot else "No", inline=True)
    embed.add_field(name="Account Created", value=discord.utils.format_dt(user.created_at, "R"), inline=True)

    if guild_member is not None:
        embed.add_field(name="Display Name", value=guild_member.display_name, inline=True)
        embed.add_field(name="Joined Server", value=discord.utils.format_dt(guild_member.joined_at, "R"), inline=True)
        embed.add_field(name="Top Role", value=guild_member.top_role.mention, inline=True)
        embed.add_field(name="Roles", value=str(len(guild_member.roles) - 1), inline=True)
        embed.add_field(name="Server Nickname", value=guild_member.nick or "None", inline=True)

    return embed


async def resolve_whoisuser_target(
    interaction: discord.Interaction,
    member: Optional[discord.Member],
    user_id: Optional[str],
    username: Optional[str],
) -> tuple[discord.User, Optional[discord.Member]]:
    if member and (user_id or username):
        raise ValueError("Use only one of member, user_id, or username.")

    if member is not None:
        return member, member

    if user_id is not None:
        user = await fetch_discord_user(user_id)
        if user is None:
            raise ValueError("I could not find a Discord user with that ID.")
        guild_member = None
        if interaction.guild is not None:
            guild_member = interaction.guild.get_member(int(user_id))
        return user, guild_member

    if username is not None:
        guild_member = None
        if interaction.guild is not None:
            guild_member = interaction.guild.get_member_named(username)
            if guild_member is None:
                matches = [
                    member for member in interaction.guild.members
                    if member.name.lower() == username.lower()
                    or member.display_name.lower() == username.lower()
                    or f"{member.name}#{member.discriminator}".lower() == username.lower()
                ]
                if len(matches) == 1:
                    guild_member = matches[0]
                elif len(matches) > 1:
                    raise ValueError("Multiple users matched that username. Use username#discriminator or user ID.")

        if guild_member is not None:
            return guild_member, guild_member

        cached = [
            user for user in bot.users
            if f"{user.name}#{user.discriminator}".lower() == username.lower()
            or user.name.lower() == username.lower()
        ]
        if len(cached) == 1:
            return cached[0], None
        if len(cached) > 1:
            raise ValueError("Multiple cached users matched that username. Use username#discriminator or user ID.")

        raise ValueError("No Discord user found with that username.")

    raise ValueError("Provide a member, user_id, or username.")


@bot.tree.command(name="whoisuser", description="Show detailed info about a Discord user by member, ID, or username")
@app_commands.describe(
    member="Server member to inspect",
    user_id="Discord user ID for someone outside this server",
    username="Discord username or username#discriminator",
)
async def whoisuser(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
) -> None:
    try:
        target_user, guild_member = await resolve_whoisuser_target(interaction, member, user_id, username)
    except ValueError as error:
        await send_interaction_error(interaction, str(error))
        return

    await interaction.response.send_message(embed=whoisuser_embed(target_user, guild_member))


@bot.tree.command(name="avatar", description="Show an avatar for yourself, a server member, or any user ID")
@app_commands.describe(
    member="Server member whose avatar you want",
    user_id="Discord user ID for someone outside this server",
)
async def avatar(
    interaction: discord.Interaction,
    member: Optional[discord.Member] = None,
    user_id: Optional[str] = None,
) -> None:
    if member and user_id:
        await send_interaction_error(interaction, "Use either `member` or `user_id`, not both.")
        return

    if user_id:
        user = await fetch_discord_user(user_id)
        if not user:
            await send_interaction_error(interaction, "I could not find a Discord user with that ID.")
            return

        await interaction.response.send_message(embed=avatar_embed(user, str(user)))
        return

    member = member or interaction.user
    await interaction.response.send_message(embed=avatar_embed(member, member.display_name))


@bot.tree.command(name="poll", description="Create a quick yes/no poll")
@app_commands.describe(question="The poll question")
async def poll(interaction: discord.Interaction, question: str) -> None:
    embed = make_embed("Poll", description=question)
    embed.add_field(name="Vote", value="Use the reactions below.", inline=False)
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    await message.add_reaction("\N{THUMBS UP SIGN}")
    await message.add_reaction("\N{THUMBS DOWN SIGN}")


@bot.tree.command(name="roll", description="Roll dice, like 1d6 or 2d20")
@app_commands.describe(dice="Dice format, for example 1d6 or 2d20")
async def roll(interaction: discord.Interaction, dice: str = "1d6") -> None:
    embed, error = roll_embed(dice)
    if error:
        await send_interaction_error(interaction, error)
        return

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="coinflip", description="Flip a coin")
async def coinflip(interaction: discord.Interaction) -> None:
    result = random.choice(["Pajura", "Cap"])
    embed = make_embed("Coin Flip", SUCCESS_COLOR, f"**{result}**")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="choose", description="Let the bot choose from comma-separated options")
@app_commands.describe(options="Example: pizza, sushi, tacos")
async def choose(interaction: discord.Interaction, options: str) -> None:
    choices = [option.strip() for option in options.split(",") if option.strip()]
    if len(choices) < 2:
        await send_interaction_error(interaction, "Give me at least two comma-separated options.")
        return

    picked = random.choice(choices)
    embed = make_embed("I Choose...", SUCCESS_COLOR, f"**{picked}**")
    embed.add_field(name="Options", value=", ".join(choices[:20]), inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="whois", description="Get information about a public IP address")
@app_commands.describe(ip="The IP address to look up")
async def whois(interaction: discord.Interaction, ip: str) -> None:
    await interaction.response.defer()
    try:
        data = await fetch_ip_info(ip)
        if "bogon" in data or "error" in data:
            await interaction.followup.send(f"Invalid or private IP: `{ip}`")
            return
        await interaction.followup.send(embed=ip_lookup_embed(data, ip))
    except Exception as error:
        await interaction.followup.send(f"Error: `{error}`")


@whois.error
async def whois_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    await send_interaction_error(interaction, str(error))


@bot.tree.command(name="pingip", description="Ping an IP address with the local system ping command")
@app_commands.describe(ip="The IP address to ping")
async def pingip(interaction: discord.Interaction, ip: str) -> None:
    await interaction.response.defer()
    try:
        ping_data = await fetch_ping_ip_status(ip)
        await interaction.followup.send(embed=pingip_embed(ip, ping_data))
    except ValueError as error:
        await send_interaction_error(interaction, str(error))
    except Exception as error:
        await interaction.followup.send(f"Error: `{error}`")


@bot.tree.command(name="loltrack", description="Track a League of Legends summoner account")
@app_commands.describe(username="Summoner name", region="Region code like euw, na, kr")
async def loltrack(interaction: discord.Interaction, username: str, region: str = "euw") -> None:
    await interaction.response.defer()
    try:
        tracker_data = await fetch_lol_tracker(username, region)
        await interaction.followup.send(embed=loltrack_embed(username, region, tracker_data))
    except Exception as error:
        await interaction.followup.send(f"Error: `{error}`")


@bot.tree.command(name="purge", description="Delete recent messages")
@app_commands.describe(amount="Number of messages to delete, from 1 to 100")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]) -> None:
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"Deleted **{len(deleted)}** messages.", ephemeral=True)


@purge.error
async def purge_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    await send_interaction_error(interaction, str(error))


@bot.tree.command(name="slowmode", description="Set this channel's slowmode")
@app_commands.describe(seconds="Slowmode delay in seconds, from 0 to 21600")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]) -> None:
    await interaction.channel.edit(slowmode_delay=seconds, reason=f"Slowmode changed by {interaction.user}")
    if seconds == 0:
        message = "Slowmode disabled for this channel."
    else:
        message = f"Slowmode set to **{seconds} seconds**."
    await interaction.response.send_message(message, ephemeral=True)


@slowmode.error
async def slowmode_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    await send_interaction_error(interaction, str(error))


@bot.tree.command(name="lock", description="Lock this channel for the default role")
@app_commands.describe(reason="Reason for locking the channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction, reason: str = "No reason provided") -> None:
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite,
        reason=f"{reason} | Locked by {interaction.user}",
    )
    embed = make_embed("Channel Locked", ERROR_COLOR, reason)
    embed.add_field(name="Channel", value=interaction.channel.mention, inline=True)
    embed.add_field(name="By", value=interaction.user.mention, inline=True)
    await interaction.response.send_message(embed=embed)


@lock.error
async def lock_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    await send_interaction_error(interaction, str(error))


@bot.tree.command(name="unlock", description="Unlock this channel for the default role")
@app_commands.describe(reason="Reason for unlocking the channel")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction, reason: str = "No reason provided") -> None:
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None
    await interaction.channel.set_permissions(
        interaction.guild.default_role,
        overwrite=overwrite,
        reason=f"{reason} | Unlocked by {interaction.user}",
    )
    embed = make_embed("Channel Unlocked", SUCCESS_COLOR, reason)
    embed.add_field(name="Channel", value=interaction.channel.mention, inline=True)
    embed.add_field(name="By", value=interaction.user.mention, inline=True)
    await interaction.response.send_message(embed=embed)


@unlock.error
async def unlock_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    await send_interaction_error(interaction, str(error))


@bot.tree.command(name="timeout", description="Timeout a member")
@app_commands.describe(member="The member to timeout", minutes="Duration in minutes", reason="Reason for timeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320] = 10,
    reason: str = "No reason provided",
) -> None:
    if not await ensure_moderatable(interaction, member):
        return
    until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    await member.timeout(until, reason=f"{reason} | Timeout by {interaction.user}")
    embed = moderation_embed("Member Timed Out", member, interaction.user, reason)
    embed.add_field(name="Duration", value=f"{minutes} minutes", inline=True)
    await interaction.response.send_message(embed=embed)


@timeout.error
async def timeout_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    await send_interaction_error(interaction, str(error))


@bot.tree.command(name="untimeout", description="Remove timeout from a member")
@app_commands.describe(member="The member to untimeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member) -> None:
    if not await ensure_moderatable(interaction, member):
        return
    await member.timeout(None, reason=f"Untimeout by {interaction.user}")
    embed = moderation_embed("Member Untimed Out", member, interaction.user)
    await interaction.response.send_message(embed=embed)


@untimeout.error
async def untimeout_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    await send_interaction_error(interaction, str(error))


@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.describe(member="The member to kick", reason="Reason for kick")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided") -> None:
    if not await ensure_moderatable(interaction, member):
        return
    await member.kick(reason=f"{reason} | Kick by {interaction.user}")
    await interaction.response.send_message(embed=moderation_embed("Member Kicked", member, interaction.user, reason))


@kick.error
async def kick_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    await send_interaction_error(interaction, str(error))


@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.describe(member="The member to ban", reason="Reason for ban")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided") -> None:
    if not await ensure_moderatable(interaction, member):
        return
    await member.ban(reason=f"{reason} | Ban by {interaction.user}")
    await interaction.response.send_message(embed=moderation_embed("Member Banned", member, interaction.user, reason))


@ban.error
async def ban_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    await send_interaction_error(interaction, str(error))


@bot.tree.command(name="unban", description="Unban a user by ID")
@app_commands.describe(user_id="The ID of the user to unban")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str, reason: str = "No reason provided") -> None:
    user = await bot.fetch_user(int(user_id))
    await interaction.guild.unban(user, reason=f"{reason} | Unban by {interaction.user}")
    embed = make_embed("Member Unbanned", SUCCESS_COLOR)
    embed.add_field(name="User", value=f"{user}\n`{user_id}`", inline=True)
    embed.add_field(name="By", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_thumbnail(url=user.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@unban.error
async def unban_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    await send_interaction_error(interaction, str(error))


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if bot.user and bot.user.mentioned_in(message):
        content = message.content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        command, _, rest = content.partition(" ")
        command = command.lower()
        rest = rest.strip()

        if command in {"help", "commands"}:
            await message.channel.send(embed=command_center_embed())

        elif command == "ping":
            latency_ms = round(bot.latency * 1000)
            await message.channel.send(embed=make_embed("Pong", SUCCESS_COLOR, f"Gateway latency: **{latency_ms}ms**"))

        elif command == "server":
            if not message.guild:
                await message.channel.send("This command only works in a server.")
            else:
                await message.channel.send(embed=server_embed(message.guild))

        elif command == "avatar":
            target_text = rest.strip()
            member = await member_from_message(message, target_text) if target_text else None
            if member:
                await message.channel.send(embed=avatar_embed(member, member.display_name))
            elif target_text:
                user = await fetch_discord_user(target_text)
                if not user:
                    await message.channel.send("Usage: `@bot avatar`, `@bot avatar @user`, or `@bot avatar 123456789012345678`")
                else:
                    await message.channel.send(embed=avatar_embed(user, str(user)))
            else:
                await message.channel.send(embed=avatar_embed(message.author, message.author.display_name))

        elif command in {"userinfo", "whoisuser"}:
            member = await member_from_message(message, rest) if rest else message.author
            if not isinstance(member, discord.Member):
                await message.channel.send("Usage: `@bot whoisuser` or `@bot whoisuser @user`")
            else:
                await message.channel.send(embed=whoisuser_embed(member, member))

        elif command == "pingip":
            if not rest:
                await message.channel.send("Usage: `@bot pingip 1.1.1.1`")
            else:
                try:
                    ping_data = await fetch_ping_ip_status(rest)
                    await message.channel.send(embed=pingip_embed(rest, ping_data))
                except ValueError as error:
                    await message.channel.send(f"Error: {error}")
                except Exception as error:
                    await message.channel.send(f"Error: {error}")

        elif command == "loltrack":
            if not rest:
                await message.channel.send("Usage: `@bot loltrack summonerName [region]`")
            else:
                username, region = parse_loltrack_query(rest)
                if not username:
                    await message.channel.send("Usage: `@bot loltrack summonerName [region]`")
                else:
                    try:
                        track_data = await fetch_lol_tracker(username, region)
                        await message.channel.send(embed=loltrack_embed(username, region, track_data))
                    except Exception as error:
                        await message.channel.send(f"Error: {error}")

        elif command == "poll":
            if not rest:
                await message.channel.send("Usage: `@bot poll Should we play tonight?`")
            else:
                embed = make_embed("Poll", description=rest)
                embed.add_field(name="Vote", value="Use the reactions below.", inline=False)
                poll_message = await message.channel.send(embed=embed)
                await poll_message.add_reaction("\N{THUMBS UP SIGN}")
                await poll_message.add_reaction("\N{THUMBS DOWN SIGN}")

        elif command == "roll":
            embed, error = roll_embed(rest or "1d6")
            if error:
                await message.channel.send(error)
            else:
                await message.channel.send(embed=embed)

        elif command == "coinflip":
            result = random.choice(["Heads", "Tails"])
            await message.channel.send(embed=make_embed("Coin Flip", SUCCESS_COLOR, f"**{result}**"))

        elif command == "choose":
            choices = [option.strip() for option in rest.split(",") if option.strip()]
            if len(choices) < 2:
                await message.channel.send("Usage: `@bot choose pizza, sushi, tacos`")
            else:
                picked = random.choice(choices)
                embed = make_embed("I Choose...", SUCCESS_COLOR, f"**{picked}**")
                embed.add_field(name="Options", value=", ".join(choices[:20]), inline=False)
                await message.channel.send(embed=embed)

        elif command == "whois":
            ip = rest
            if not ip:
                await message.channel.send("Usage: `@bot whois 1.1.1.1`")
                return
            try:
                data = await fetch_ip_info(ip)
                if "bogon" in data or "error" in data:
                    await message.channel.send(f"Invalid or private IP: `{ip}`")
                    return
                await message.channel.send(embed=ip_lookup_embed(data, ip))
            except Exception as error:
                await message.channel.send(f"Error: `{error}`")

        elif command == "purge":
            if not message.guild:
                await message.channel.send("This command only works in a server.")
                return
            if not message.author.guild_permissions.manage_messages:
                await message.channel.send("You do not have permission to do that.")
                return
            if rest.isdigit() and 1 <= int(rest) <= 100:
                amount = int(rest)
                await message.channel.purge(limit=amount + 1)
                reply = await message.channel.send(f"Deleted **{amount}** messages.")
                await reply.delete(delay=3)
            else:
                await message.channel.send("Usage: `@bot purge 10`")

        elif command == "slowmode":
            if not message.guild:
                await message.channel.send("This command only works in a server.")
                return
            if not message.author.guild_permissions.manage_channels:
                await message.channel.send("You do not have permission to do that.")
                return
            if not rest.isdigit() or not 0 <= int(rest) <= 21600:
                await message.channel.send("Usage: `@bot slowmode 5` with seconds from 0 to 21600.")
                return
            seconds = int(rest)
            await message.channel.edit(slowmode_delay=seconds, reason=f"Slowmode changed by {message.author}")
            await message.channel.send("Slowmode disabled." if seconds == 0 else f"Slowmode set to **{seconds} seconds**.")

        elif command in {"lock", "unlock"}:
            if not message.guild:
                await message.channel.send("This command only works in a server.")
                return
            if not message.author.guild_permissions.manage_channels:
                await message.channel.send("You do not have permission to do that.")
                return
            locked = command == "lock"
            reason = rest or "No reason provided"
            overwrite = message.channel.overwrites_for(message.guild.default_role)
            overwrite.send_messages = False if locked else None
            await message.channel.set_permissions(
                message.guild.default_role,
                overwrite=overwrite,
                reason=f"{reason} | {command.title()}ed by {message.author}",
            )
            title = "Channel Locked" if locked else "Channel Unlocked"
            color = ERROR_COLOR if locked else SUCCESS_COLOR
            embed = make_embed(title, color, reason)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.add_field(name="By", value=message.author.mention, inline=True)
            await message.channel.send(embed=embed)

        elif command in {"timeout", "untimeout", "kick", "ban"}:
            if not message.guild:
                await message.channel.send("This command only works in a server.")
                return
            required_permission = {
                "timeout": message.author.guild_permissions.moderate_members,
                "untimeout": message.author.guild_permissions.moderate_members,
                "kick": message.author.guild_permissions.kick_members,
                "ban": message.author.guild_permissions.ban_members,
            }[command]
            if not required_permission:
                await message.channel.send("You do not have permission to do that.")
                return

            member = await member_from_message(message, rest)
            if not member:
                await message.channel.send(f"Usage: `@bot {command} @user`")
                return
            if not await ensure_message_moderatable(message, member):
                return

            details = strip_member_argument(message, rest, member)
            if command == "timeout":
                parts = details.split(maxsplit=1)
                minutes = 10
                reason = "No reason provided"
                if parts and parts[0].isdigit():
                    minutes = int(parts[0])
                    reason = parts[1] if len(parts) > 1 else reason
                elif details:
                    reason = details
                if not 1 <= minutes <= 40320:
                    await message.channel.send("Timeout minutes must be from 1 to 40320.")
                    return
                until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
                await member.timeout(until, reason=f"{reason} | Timeout by {message.author}")
                embed = moderation_embed("Member Timed Out", member, message.author, reason)
                embed.add_field(name="Duration", value=f"{minutes} minutes", inline=True)
                await message.channel.send(embed=embed)
            elif command == "untimeout":
                await member.timeout(None, reason=f"Untimeout by {message.author}")
                await message.channel.send(embed=moderation_embed("Member Untimed Out", member, message.author))
            elif command == "kick":
                reason = details or "No reason provided"
                await member.kick(reason=f"{reason} | Kick by {message.author}")
                await message.channel.send(embed=moderation_embed("Member Kicked", member, message.author, reason))
            elif command == "ban":
                reason = details or "No reason provided"
                await member.ban(reason=f"{reason} | Ban by {message.author}")
                await message.channel.send(embed=moderation_embed("Member Banned", member, message.author, reason))

        elif command == "unban":
            if not message.guild:
                await message.channel.send("This command only works in a server.")
                return
            if not message.author.guild_permissions.ban_members:
                await message.channel.send("You do not have permission to do that.")
                return
            parts = rest.split(maxsplit=1)
            user_id = parts[0] if parts else ""
            reason = parts[1] if len(parts) > 1 else "No reason provided"
            user = await fetch_discord_user(user_id)
            if not user:
                await message.channel.send("Usage: `@bot unban 123456789012345678 reason`")
                return
            await message.guild.unban(user, reason=f"{reason} | Unban by {message.author}")
            embed = make_embed("Member Unbanned", SUCCESS_COLOR)
            embed.add_field(name="User", value=f"{user}\n`{user_id}`", inline=True)
            embed.add_field(name="By", value=message.author.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.set_thumbnail(url=user.display_avatar.url)
            await message.channel.send(embed=embed)

        elif command:
            await message.channel.send("Unknown mention command. Try `@bot help`.")

    await bot.process_commands(message)


if not TOKEN:
    raise RuntimeError("Set DISCORD_TOKEN before starting the bot.")

print("Using Discord token from .env/environment.")

try:
    bot.run(TOKEN)
except discord.LoginFailure as error:
    raise RuntimeError(
        "Discord rejected DISCORD_TOKEN. Copy the bot token from Discord Developer Portal > "
        "Applications > your app > Bot > Reset Token, then paste only that token into .env."
    ) from error
