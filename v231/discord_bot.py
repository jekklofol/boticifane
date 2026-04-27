"""
Please Donate Bot v2 — Discord Bot (discord.py 2.x)
Run: python discord_bot.py
Install: pip install discord.py
"""

import discord
from discord import app_commands, ui
from discord.ext import commands
import asyncio, time, os, io, json, logging

import db_v2
from config import DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, DISCORD_ADMIN_DC_ID, API_BASE_URL

logging.basicConfig(level=logging.INFO)

# ── Guild config (populated via /admin setup) ─────────────────────────────
_DC_CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "discord_cfg.json")

def _load_dc_cfg() -> dict:
    if os.path.exists(_DC_CFG_PATH):
        with open(_DC_CFG_PATH) as f:
            return json.load(f)
    return {"announcements_channel": 0, "bot_commands_channel": 0,
            "support_category": 0, "get_started_channel": 0, "ticket_channel": 0}

def _save_dc_cfg(cfg: dict):
    with open(_DC_CFG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Invite cache: code → use_count ────────────────────────────────────────
_invite_cache: dict[str, int] = {}

# ── Bot setup ─────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
GUILD_OBJ = discord.Object(id=DISCORD_GUILD_ID)


# ── Helpers ───────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id == DISCORD_ADMIN_DC_ID


def _fmt_dur(secs: int) -> str:
    if secs <= 0:
        return "—"
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:   return f"{h}h {m}m"
    if m:   return f"{m}m {s}s"
    return f"{s}s"


def _trial_time_str(expires_at: float) -> str:
    left = expires_at - time.time()
    if left <= 0:
        return "expired"
    d = int(left // 86400)
    h = int((left % 86400) // 3600)
    m = int((left % 3600) // 60)
    if d > 0: return f"{d}d {h}h"
    return f"{h}h {m}m"


def _bar(ratio: float, width: int = 8) -> str:
    filled = round(max(0.0, min(1.0, ratio)) * width)
    return "█" * filled + "░" * (width - filled)


# ── Referral threshold check ───────────────────────────────────────────────

async def _check_dc_ref_thresholds(ref_dc_id: int):
    ref_count = db_v2.dc_get_ref_count(ref_dc_id)
    lic = db_v2.dc_get_license_by_dc(ref_dc_id)

    if ref_count >= 2 and lic and lic.get("key_type") == "trial":
        new_key = db_v2.dc_give_lifetime_key(ref_dc_id)
        try:
            user = bot.get_user(ref_dc_id)
            if user:
                embed = discord.Embed(
                    title="🎉 You got lifetime access!",
                    description=(
                        f"You invited **{ref_count} friends** — lifetime key unlocked!\n\n"
                        f"♾ New key: `{new_key}`\n\n"
                        "Restart the script with your new key."
                    ),
                    color=0x00ff88,
                )
                await user.send(embed=embed)
        except Exception:
            pass

    elif ref_count == 3:
        try:
            user = bot.get_user(ref_dc_id)
            if user:
                embed = discord.Embed(
                    title="💸 Referral earnings unlocked!",
                    description=(
                        "You've invited **3 friends!**\n\n"
                        "You now earn **10% of their Robux earnings** automatically.\n"
                        "Check your balance with `/refs`."
                    ),
                    color=0xffd700,
                )
                await user.send(embed=embed)
        except Exception:
            pass


# ── Invite helper ─────────────────────────────────────────────────────────

async def _get_or_create_invite(guild: discord.Guild, dc_id: int) -> str:
    existing = db_v2.dc_get_user_invite(dc_id)
    if existing:
        code = existing["invite_code"]
        try:
            guild_invites = await guild.invites()
            if any(inv.code == code for inv in guild_invites):
                return f"discord.gg/{code}"
        except Exception:
            pass

    cfg = _load_dc_cfg()
    channel = guild.get_channel(cfg.get("bot_commands_channel", 0))
    if not channel:
        channel = next((ch for ch in guild.text_channels if not ch.name.startswith("ticket-")), None)
    if not channel:
        return "(no invite available — run /admin setup first)"

    try:
        invite = await channel.create_invite(max_age=0, max_uses=0, unique=True, reason=f"ref:{dc_id}")
        db_v2.dc_upsert_invite(invite.code, dc_id)
        _invite_cache[invite.code] = invite.uses
        return f"discord.gg/{invite.code}"
    except Exception as e:
        return f"(could not create invite: {e})"


# ── Events ────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    global _invite_cache
    await bot.tree.sync(guild=GUILD_OBJ)
    print(f"[Discord] Ready as {bot.user} | guild={DISCORD_GUILD_ID}")

    guild = bot.get_guild(DISCORD_GUILD_ID)
    if guild:
        try:
            invites = await guild.invites()
            _invite_cache = {inv.code: inv.uses for inv in invites}
            print(f"[Discord] Cached {len(_invite_cache)} invites")
        except Exception as e:
            print(f"[Discord] Could not cache invites: {e}")

    # Re-register persistent views so buttons survive bot restarts
    bot.add_view(CreateTicketView())
    bot.add_view(CloseTicketView())


@bot.event
async def on_member_join(member: discord.Member):
    if member.guild.id != DISCORD_GUILD_ID:
        return

    db_v2.dc_upsert_user(member.id, member.name, member.display_name)

    # Invite tracking — find which invite was used
    try:
        guild = member.guild
        invites_now = await guild.invites()
        used_code = None
        for inv in invites_now:
            if inv.uses > _invite_cache.get(inv.code, 0):
                used_code = inv.code
                break
        _invite_cache.update({inv.code: inv.uses for inv in invites_now})

        if used_code:
            invite_row = db_v2.dc_get_invite(used_code)
            if invite_row and invite_row["dc_id"] != member.id:
                db_v2.dc_set_referred_by(member.id, invite_row["dc_id"])
                await _check_dc_ref_thresholds(invite_row["dc_id"])
    except Exception as e:
        print(f"[Discord] Invite tracking error: {e}")

    # Auto trial key on join
    lic = db_v2.dc_get_license_by_dc(member.id)
    if not lic:
        key = db_v2.dc_give_trial_key(member.id)
        try:
            embed = discord.Embed(
                title="👋 Welcome!",
                description=(
                    "This bot auto-farms Robux in **Please Donate**.\n"
                    "It approaches players and asks for donations — fully on autopilot.\n\n"
                    "┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                    f"🎁 Your trial key **(3 days)**:\n`{key}`\n\n"
                    "┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
                    "**Get started:**\n"
                    "1. `/getscript` — download the loader\n"
                    "2. Open **Xeno** → join **Please Donate** → inject → enter key\n\n"
                    "♾ Invite **2 friends** → lifetime access\n"
                    "Use `/refs` in the server to get your invite link."
                ),
                color=0x5865F2,
            )
            await member.send(embed=embed)
        except Exception:
            pass


# ── User slash commands ───────────────────────────────────────────────────

@bot.tree.command(name="start", description="Get started — check your key status", guild=GUILD_OBJ)
async def cmd_start(interaction: discord.Interaction):
    dc_id = interaction.user.id
    db_v2.dc_upsert_user(dc_id, interaction.user.name, interaction.user.display_name)

    lic = db_v2.dc_get_license_by_dc(dc_id)
    ref_count = db_v2.dc_get_ref_count(dc_id)
    ref_link = await _get_or_create_invite(interaction.guild, dc_id)

    # Has valid key
    if lic and db_v2.is_key_valid(lic):
        key_type   = lic.get("key_type", "lifetime")
        expires_at = lic.get("expires_at")
        bound      = lic.get("roblox_name") or lic.get("roblox_user_id") or "not bound"

        if key_type == "trial" and expires_at:
            time_left = _trial_time_str(expires_at)
            if ref_count < 2:
                needed = 2 - ref_count
                status_text = (
                    f"⏳ Trial — **{time_left}** remaining\n"
                    f"🔗 Invite **{needed}** more friend(s) for lifetime:\n{ref_link}"
                )
            else:
                status_text = f"⏳ Trial — **{time_left}** remaining (lifetime pending restart)"
        else:
            ref_balance = db_v2.dc_get_ref_balance(dc_id)
            bal_str = f"\n💸 R${ref_balance:,} earned from referrals" if ref_balance > 0 else ""
            status_text = f"♾ **Lifetime**{bal_str}"

        embed = discord.Embed(title="👋 Welcome back!", color=0x5865F2)
        embed.add_field(name="Key", value=f"`{lic['key']}`", inline=False)
        embed.add_field(name="Roblox account", value=bound, inline=True)
        embed.add_field(name="Referrals", value=f"**{ref_count}** invited", inline=True)
        embed.add_field(name="Status", value=status_text, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Trial expired
    if lic and lic.get("key_type") == "trial":
        if ref_count >= 2:
            new_key = db_v2.dc_give_lifetime_key(dc_id)
            embed = discord.Embed(
                title="♾ Trial expired — but you qualified!",
                description=f"You invited **{ref_count} friends** → **lifetime access granted!**\n\n🔑 New key: `{new_key}`",
                color=0x00ff88,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        needed = 2 - ref_count
        embed = discord.Embed(
            title="⏰ Trial Expired",
            description=(
                f"Invite **{needed}** more friend(s) to continue:\n{ref_link}\n\n"
                f"Progress: **{ref_count}/2** {_bar(ref_count / 2)}"
            ),
            color=0xff4444,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # New user — issue trial
    key = db_v2.dc_give_trial_key(dc_id)
    embed = discord.Embed(
        title="👋 Welcome!",
        description=(
            "This bot auto-farms Robux in **Please Donate**.\n"
            "It approaches players and asks for donations — fully on autopilot.\n\n"
            "┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            f"🎁 Your trial key **(3 days)**:\n`{key}`\n\n"
            "┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
            "**Get started:**\n"
            "1. `/getscript` — download the loader\n"
            "2. Open **Xeno** → join **Please Donate** → inject → enter key\n\n"
            f"♾ Invite **2 friends** for lifetime access:\n{ref_link}"
        ),
        color=0x5865F2,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="key", description="Show your current key", guild=GUILD_OBJ)
async def cmd_key(interaction: discord.Interaction):
    lic = db_v2.dc_get_license_by_dc(interaction.user.id)
    if not lic:
        await interaction.response.send_message("❌ No key yet. Use `/start` first.", ephemeral=True)
        return

    valid    = db_v2.is_key_valid(lic)
    key_type = "♾ Lifetime" if lic.get("key_type") == "lifetime" else "⏳ Trial"
    status   = "✅ Active" if valid else "❌ Expired / Revoked"

    embed = discord.Embed(title="🔑 Your Key", color=0x5865F2 if valid else 0xff4444)
    embed.add_field(name="Key",    value=f"`{lic['key']}`", inline=False)
    embed.add_field(name="Type",   value=key_type,          inline=True)
    embed.add_field(name="Status", value=status,            inline=True)
    if lic.get("expires_at") and lic.get("key_type") == "trial":
        embed.add_field(name="Expires in", value=_trial_time_str(lic["expires_at"]), inline=True)
    if lic.get("roblox_name"):
        embed.add_field(name="Roblox account", value=lic["roblox_name"], inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="stats", description="View your current session stats", guild=GUILD_OBJ)
async def cmd_stats(interaction: discord.Interaction):
    lic = db_v2.dc_get_license_by_dc(interaction.user.id)
    if not lic or not db_v2.is_key_valid(lic):
        await interaction.response.send_message("❌ No active key. Use `/start` first.", ephemeral=True)
        return

    accounts = db_v2.get_all_accounts_by_license(lic["key"])
    if not accounts:
        await interaction.response.send_message(
            "📊 No accounts running yet.\nLaunch the script first, then check back!", ephemeral=True
        )
        return

    now = time.time()
    embed = discord.Embed(title="📊 Your Stats", color=0x5865F2)

    total_r, total_d, total_ap, total_ag = 0, 0, 0, 0
    for acc in accounts[:5]:
        is_online = (now - (acc.get("last_seen") or 0)) < 35
        icon = "🟢" if is_online else "⚫"
        r  = (acc.get("robux_gross") or 0)    + (acc.get("robux_alltime") or 0)
        d  = (acc.get("donations") or 0)      + (acc.get("donations_alltime") or 0)
        ap = (acc.get("approached") or 0)     + (acc.get("approached_alltime") or 0)
        ag = (acc.get("agreed") or 0)         + (acc.get("agreed_alltime") or 0)
        total_r += r; total_d += d; total_ap += ap; total_ag += ag
        conv = f"{ag/ap*100:.0f}%" if ap > 0 else "0%"
        dur  = f" · {_fmt_dur(int(now - acc['session_start']))}" if is_online and acc.get("session_start") else ""
        embed.add_field(
            name=f"{icon} {acc.get('name', acc['id'])}",
            value=f"R${r:,} · {d} donations · {conv} conv{dur}",
            inline=False,
        )

    embed.add_field(name="Total earned", value=f"**R${total_r:,}**",                         inline=True)
    embed.add_field(name="Donations",    value=f"**{total_d}**",                               inline=True)
    if total_ap > 0:
        embed.add_field(name="Conversion", value=f"**{total_ag/total_ap*100:.1f}%**", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="refs", description="Your referrals and invite link", guild=GUILD_OBJ)
async def cmd_refs(interaction: discord.Interaction):
    dc_id = interaction.user.id
    db_v2.dc_upsert_user(dc_id, interaction.user.name, interaction.user.display_name)

    ref_count   = db_v2.dc_get_ref_count(dc_id)
    ref_balance = db_v2.dc_get_ref_balance(dc_id)
    ref_link    = await _get_or_create_invite(interaction.guild, dc_id)
    lic         = db_v2.dc_get_license_by_dc(dc_id)
    key_type    = (lic.get("key_type", "trial") if lic else "trial")

    embed = discord.Embed(title="👥 Referrals", color=0x5865F2)
    embed.add_field(name="Invited",               value=f"**{ref_count}** friends",             inline=True)
    embed.add_field(name="Progress to lifetime",  value=f"**{min(ref_count,2)}/2** {_bar(min(ref_count,2)/2)}", inline=True)

    if ref_count >= 3:
        embed.add_field(name="💸 Your earnings (10%)", value=f"**R${ref_balance:,}**", inline=False)

    if key_type == "trial" and ref_count < 2:
        embed.add_field(
            name="⚡ Keep inviting!",
            value=f"**{2 - ref_count}** more friend(s) → lifetime access",
            inline=False,
        )
    if ref_count >= 2 and key_type == "trial":
        embed.add_field(name="🎁 Almost there!", value="You qualify for lifetime — use `/start` to claim it.", inline=False)

    embed.add_field(name="Your invite link", value=ref_link, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="getscript", description="Download the script loader", guild=GUILD_OBJ)
async def cmd_getscript(interaction: discord.Interaction):
    lic = db_v2.dc_get_license_by_dc(interaction.user.id)
    if not lic or not db_v2.is_key_valid(lic):
        await interaction.response.send_message("❌ No active key. Use `/start` first.", ephemeral=True)
        return

    loader_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loader_v2.lua")
    if not os.path.exists(loader_path):
        await interaction.response.send_message("❌ Loader file not found — contact admin.", ephemeral=True)
        return

    with open(loader_path, "rb") as f:
        data = f.read()

    await interaction.response.send_message(
        "📜 **loader_v2.lua** — inject this in Roblox\n\n"
        "1. Open **Xeno** injector\n"
        "2. Join **Please Donate** in Roblox\n"
        "3. Inject → paste your key → press **START**\n\n"
        f"🔑 Your key: `{lic['key']}`",
        file=discord.File(io.BytesIO(data), filename="loader_v2.lua"),
        ephemeral=True,
    )


@bot.tree.command(name="dashboard", description="Open your web dashboard", guild=GUILD_OBJ)
async def cmd_dashboard(interaction: discord.Interaction):
    lic = db_v2.dc_get_license_by_dc(interaction.user.id)
    if not lic or not db_v2.is_key_valid(lic):
        await interaction.response.send_message("❌ No active key. Use `/start` first.", ephemeral=True)
        return

    token = db_v2.create_dashboard_token(lic["key"])
    url   = f"{API_BASE_URL.rstrip('/')}/dashboard?token={token}"

    embed = discord.Embed(title="🌐 Your Dashboard", color=0x5865F2)
    embed.description = (
        f"[🔗 Open Dashboard]({url})\n\n"
        "⏳ Link expires in **1 hour**\n"
        "🔒 Don't share this link"
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="guide", description="How to set up and run the script", guild=GUILD_OBJ)
async def cmd_guide(interaction: discord.Interaction):
    embed = discord.Embed(title="🚀 Quick Start Guide", color=0x5865F2)
    embed.add_field(
        name="Steps",
        value=(
            "1. `/getscript` — download loader_v2.lua\n"
            "2. Open **Xeno** injector\n"
            "3. Join **Please Donate** in Roblox\n"
            "4. Inject → enter your key → **START**"
        ),
        inline=False,
    )
    embed.add_field(
        name="⚠️ Before you start",
        value=(
            "**Gamepass** — required or players can't donate:\n"
            "create.roblox.com → Creations → any game → Monetization → Passes → Create a Pass\n\n"
            "**Face Verification** — required! Without it the bot can't chat.\n\n"
            "**VPN** — required if Cloudflare is blocked in your country."
        ),
        inline=False,
    )
    embed.add_field(
        name="🔒 Security",
        value="Your key is bound to your PC (HWID). Can't be shared. Switched PCs? Use `/support`.",
        inline=False,
    )
    embed.add_field(
        name="🔄 Multiple accounts",
        value="Install MultiRoblox + Roblox Account Manager, run the script in each client with the same key.",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="news", description="Latest updates", guild=GUILD_OBJ)
async def cmd_news(interaction: discord.Interaction):
    embed = discord.Embed(title="📣 What's New — v23", color=0x5865F2)
    embed.add_field(
        name="🧠 Smarter Script",
        value="Rewritten conversation engine. Bot adapts to responses — compliments, varied phrases, persistence. 2-3× better conversion.",
        inline=False,
    )
    embed.add_field(
        name="⚡ Stability",
        value="Auto server-hop when server is empty. AFK kick protection. Anti-mod detection. Auto-reconnect. Runs hours without restart.",
        inline=False,
    )
    embed.add_field(
        name="🌐 Dashboard",
        value="Real-time stats, conversation logs, conversion rates, session history.\nGet your link: `/dashboard`",
        inline=False,
    )
    embed.add_field(
        name="🎁 Referrals",
        value="2 friends → lifetime access\n3+ friends → 10% of their earnings\nGet your link: `/refs`",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ── Ticket system ─────────────────────────────────────────────────────────

class CreateTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📩 Create Ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket_v1")
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        user  = interaction.user

        # One ticket per user
        ticket_name = f"ticket-{user.name.lower()[:20].replace(' ', '-')}"
        existing = discord.utils.get(guild.text_channels, name=ticket_name)
        if existing:
            await interaction.response.send_message(
                f"❌ You already have an open ticket: {existing.mention}", ephemeral=True
            )
            return

        cfg      = _load_dc_cfg()
        category = guild.get_channel(cfg.get("support_category", 0))

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user:               discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        admin_member = guild.get_member(DISCORD_ADMIN_DC_ID)
        if admin_member:
            overwrites[admin_member] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        channel = await guild.create_text_channel(
            name=ticket_name,
            category=category,
            overwrites=overwrites,
            topic=f"ticket:{user.id}",
        )

        embed = discord.Embed(
            title="📬 Support Ticket",
            description=(
                f"Hey {user.mention}! Describe your issue and we'll get back to you.\n\n"
                "**Common issues:**\n"
                "• HWID mismatch (switched PC) — share your key\n"
                "• Script not working — include error details\n"
                "• Payout request — include amount and username\n"
                "• Other questions\n\n"
                "Click **Close Ticket** when resolved."
            ),
            color=0x5865F2,
        )
        await channel.send(embed=embed, view=CloseTicketView())
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)


class CloseTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_v1")
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        channel = interaction.channel
        topic   = channel.topic or ""

        is_creator = str(interaction.user.id) in topic
        is_admin   = _is_admin(interaction.user.id)

        if not (is_creator or is_admin):
            await interaction.response.send_message(
                "❌ Only the ticket creator or admin can close this.", ephemeral=True
            )
            return

        await interaction.response.send_message("🔒 Closing in 5 seconds...")
        await asyncio.sleep(5)
        await channel.delete()


# ── Admin command group ────────────────────────────────────────────────────

admin_group = app_commands.Group(name="admin", description="Admin commands", guild_ids=[DISCORD_GUILD_ID])


@admin_group.command(name="stats", description="Global bot statistics")
async def admin_stats(interaction: discord.Interaction):
    if not _is_admin(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return

    active_lic  = db_v2.count_licenses()
    active_acc  = db_v2.count_active_accounts()
    total_r     = db_v2.total_robux()
    dc_users    = db_v2.dc_count_users()

    embed = discord.Embed(title="📊 Global Stats", color=0x5865F2)
    embed.add_field(name="Active licenses",     value=f"**{active_lic}**",   inline=True)
    embed.add_field(name="Active accounts now", value=f"**{active_acc}**",   inline=True)
    embed.add_field(name="Total robux earned",  value=f"**R${total_r:,}**",  inline=True)
    embed.add_field(name="Discord users",       value=f"**{dc_users}**",     inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@admin_group.command(name="give", description="Give lifetime key to a Discord user")
@app_commands.describe(user="User to give key to")
async def admin_give(interaction: discord.Interaction, user: discord.Member):
    if not _is_admin(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return

    db_v2.dc_upsert_user(user.id, user.name, user.display_name)
    key = db_v2.dc_give_license(user.id)

    try:
        embed = discord.Embed(
            title="🎁 Lifetime access granted!",
            description=f"♾ Key: `{key}`\n\nUse `/getscript` to download the loader.",
            color=0x00ff88,
        )
        await user.send(embed=embed)
    except Exception:
        pass

    await interaction.response.send_message(
        f"✅ Gave lifetime key `{key}` to {user.mention}", ephemeral=True
    )


@admin_group.command(name="revoke", description="Revoke a user's key")
@app_commands.describe(user="User to revoke")
async def admin_revoke(interaction: discord.Interaction, user: discord.Member):
    if not _is_admin(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return

    lic = db_v2.dc_get_license_by_dc(user.id)
    if not lic:
        await interaction.response.send_message(f"❌ {user.mention} has no license.", ephemeral=True)
        return

    db_v2.revoke_license(lic["key"])
    await interaction.response.send_message(
        f"✅ Revoked key `{lic['key']}` for {user.mention}", ephemeral=True
    )


@admin_group.command(name="broadcast", description="Post announcement to #announcements")
@app_commands.describe(message="Message to broadcast")
async def admin_broadcast(interaction: discord.Interaction, message: str):
    if not _is_admin(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return

    cfg     = _load_dc_cfg()
    channel = interaction.guild.get_channel(cfg.get("announcements_channel", 0))
    if not channel:
        await interaction.response.send_message(
            "❌ Announcements channel not configured. Run `/admin setup` first.", ephemeral=True
        )
        return

    embed = discord.Embed(title="📣 Announcement", description=message, color=0x5865F2)
    embed.set_footer(text=f"Posted by {interaction.user.display_name}")
    await channel.send("@everyone", embed=embed)
    await interaction.response.send_message("✅ Broadcast sent.", ephemeral=True)


@admin_group.command(name="user", description="View info about a Discord user")
@app_commands.describe(user="User to look up")
async def admin_user(interaction: discord.Interaction, user: discord.Member):
    if not _is_admin(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return

    dc_user   = db_v2.dc_get_user(user.id)
    lic       = db_v2.dc_get_license_by_dc(user.id)
    ref_count = db_v2.dc_get_ref_count(user.id)

    embed = discord.Embed(title=f"👤 {user.display_name}", color=0x5865F2)
    embed.add_field(name="Discord ID",  value=str(user.id), inline=True)
    embed.add_field(name="Referrals",   value=str(ref_count), inline=True)

    if dc_user:
        joined = dc_user.get("created_at")
        embed.add_field(name="Joined bot", value=f"<t:{int(joined)}:R>" if joined else "—", inline=True)
        if dc_user.get("ref_balance", 0) > 0:
            embed.add_field(name="Ref balance", value=f"R${dc_user['ref_balance']:,}", inline=True)

    if lic:
        valid    = db_v2.is_key_valid(lic)
        key_type = lic.get("key_type", "lifetime")
        status   = "✅ Active" if valid else "❌ Inactive"
        embed.add_field(name="Key",      value=f"`{lic['key']}`", inline=False)
        embed.add_field(name="Type",     value=key_type, inline=True)
        embed.add_field(name="Status",   value=status, inline=True)
        if lic.get("roblox_name"):
            embed.add_field(name="Roblox", value=lic["roblox_name"], inline=True)
    else:
        embed.add_field(name="License", value="none", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@admin_group.command(name="setup", description="Create server channel structure")
async def admin_setup(interaction: discord.Interaction):
    if not _is_admin(interaction.user.id):
        await interaction.response.send_message("❌ No access.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    cfg   = _load_dc_cfg()
    log   = []

    def _find_ch(name):
        # точное совпадение
        ch = discord.utils.get(guild.channels, name=name)
        if ch:
            return ch
        # поиск по вхождению (для каналов с эмодзи-префиксом типа "📣-announcements")
        for ch in guild.channels:
            if name in ch.name:
                return ch
        return None

    def _find_cat(name):
        cat = discord.utils.get(guild.categories, name=name)
        if cat:
            return cat
        for cat in guild.categories:
            if name.lower() in cat.name.lower():
                return cat
        return None

    # #announcements
    ann_ch = _find_ch("announcements")
    if not ann_ch:
        ann_ch = await guild.create_text_channel("announcements", topic="Bot announcements & updates")
        await ann_ch.set_permissions(guild.default_role, send_messages=False)
        log.append("Created #announcements")
    cfg["announcements_channel"] = ann_ch.id

    # #get-started
    gs_ch = _find_ch("get-started")
    if not gs_ch:
        gs_ch = await guild.create_text_channel("get-started", topic="How to use the bot")
        await gs_ch.set_permissions(guild.default_role, send_messages=False)
        log.append("Created #get-started")
    cfg["get_started_channel"] = gs_ch.id

    # #bot-commands
    bc_ch = _find_ch("bot-commands")
    if not bc_ch:
        bc_ch = await guild.create_text_channel("bot-commands", topic="Use bot commands here")
        log.append("Created #bot-commands")
    cfg["bot_commands_channel"] = bc_ch.id

    # Support category + #create-ticket
    sup_cat = _find_cat("Support")
    if not sup_cat:
        sup_cat = await guild.create_category("Support")
        log.append("Created Support category")
    cfg["support_category"] = sup_cat.id

    ticket_ch = _find_ch("create-ticket")
    if not ticket_ch:
        ticket_ch = await guild.create_text_channel(
            "create-ticket",
            category=sup_cat,
            topic="Click to open a support ticket",
        )
        await ticket_ch.set_permissions(guild.default_role, send_messages=False)
        log.append("Created #create-ticket")
    cfg["ticket_channel"] = ticket_ch.id

    _save_dc_cfg(cfg)

    # ── #rules ────────────────────────────────────────────────────────────
    rules_ch = _find_ch("rules") or _find_ch("📌-rules") or _find_ch("🚩-rules")
    if rules_ch:
        e = discord.Embed(title="📌 Rules", color=0x5865F2)
        e.description = (
            "**1.** No sharing keys — each key is bound to your PC (HWID)\n"
            "**2.** No spam or self-promotion\n"
            "**3.** Be respectful to everyone\n"
            "**4.** No scamming or chargebacks\n"
            "**5.** Support tickets only in <#" + str(ticket_ch.id) + ">\n\n"
            "Breaking rules → permanent ban."
        )
        await rules_ch.send(embed=e)
        log.append("Posted in #rules")

    # ── #announcements ────────────────────────────────────────────────────
    ann_embed = discord.Embed(title="👋 Welcome to PD AutoFarm!", color=0x5865F2)
    ann_embed.description = (
        "The most powerful **Please Donate** automation bot.\n\n"
        "🤖 The bot walks up to players and asks for donations — fully automatic\n"
        "♾ Free 3-day trial for every new member\n"
        "💸 Invite friends → earn Robux passively\n\n"
        f"**Get started → <#{bc_ch.id}>**\n"
        f"**Guide → <#{gs_ch.id}>**"
    )
    await ann_ch.send(embed=ann_embed)
    log.append("Posted in #announcements")

    # ── #get-started ──────────────────────────────────────────────────────
    guide_embed = discord.Embed(title="🚀 How to Get Started", color=0x5865F2)
    guide_embed.description = (
        "**Step 1** — Use `/start` in <#" + str(bc_ch.id) + "> to get your **free 3-day trial key**\n\n"
        "**Step 2** — Use `/getscript` to download `loader_v2.lua`\n\n"
        "**Step 3** — Open **Xeno** injector → join **Please Donate** in Roblox → inject the script\n\n"
        "**Step 4** — Paste your key → press **START** → the bot does everything automatically\n\n"
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
        "**⚠️ Requirements before launching:**\n"
        "• **Gamepass** — create one at create.roblox.com → Monetization → Passes (so players can donate)\n"
        "• **Face Verification** — required for chat (Roblox Settings → Privacy)\n"
        "• **VPN** — if Cloudflare is blocked in your country\n\n"
        "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
        "**♾ Get Lifetime Access**\n"
        "Invite **2 friends** using your referral link (`/refs`) → automatic lifetime upgrade\n\n"
        "**💸 Earn from Referrals**\n"
        "Invite **3+ friends** → earn **10%** of their Robux earnings automatically\n\n"
        "**🔒 Key Security**\n"
        "Your key is bound to your PC (HWID). Switched PCs? Open a ticket in <#" + str(ticket_ch.id) + ">"
    )
    await gs_ch.send(embed=guide_embed)
    log.append("Posted in #get-started")

    # ── #bot-commands ─────────────────────────────────────────────────────
    bc_embed = discord.Embed(title="🤖 Bot Commands", color=0x5865F2)
    bc_embed.description = (
        "Use slash commands here — responses are **private** (only you can see them)\n\n"
        "**Getting started:**\n"
        "`/start` — get your trial key or check status\n"
        "`/getscript` — download the loader file\n"
        "`/guide` — setup instructions\n\n"
        "**Your account:**\n"
        "`/key` — show your current key\n"
        "`/stats` — live session statistics\n"
        "`/dashboard` — open web dashboard\n\n"
        "**Referrals:**\n"
        "`/refs` — your referral link & earnings\n\n"
        "**Other:**\n"
        "`/news` — latest updates\n"
        "`/support` — open a support ticket"
    )
    await bc_ch.send(embed=bc_embed)
    log.append("Posted in #bot-commands")

    # ── #leaderboard ──────────────────────────────────────────────────────
    lb_ch = _find_ch("leaderboard") or _find_ch("📊-leaderboard") or _find_ch("🏆-leaderboard")
    if lb_ch:
        e = discord.Embed(title="🏆 Leaderboard", color=0xFFD700)
        e.description = (
            "Top earners will be posted here.\n\n"
            "*Stats update automatically as members farm.*"
        )
        await lb_ch.send(embed=e)
        log.append("Posted in #leaderboard")

    # ── #general ──────────────────────────────────────────────────────────
    gen_ch = _find_ch("general") or _find_ch("💬-general")
    if gen_ch:
        e = discord.Embed(title="💬 General Chat", color=0x5865F2)
        e.description = (
            "Welcome to **PD AutoFarm**! 👋\n\n"
            "Chat here, share tips, flex your earnings.\n"
            f"New? Head to <#{gs_ch.id}> to get started."
        )
        await gen_ch.send(embed=e)
        log.append("Posted in #general")

    # ── #flex ─────────────────────────────────────────────────────────────
    flex_ch = _find_ch("flex") or _find_ch("📸-flex")
    if flex_ch:
        e = discord.Embed(title="📸 Flex Your Earnings", color=0xFFD700)
        e.description = (
            "Share screenshots of your Robux earnings here!\n\n"
            "Show off your stats from `/dashboard` 💰"
        )
        await flex_ch.send(embed=e)
        log.append("Posted in #flex")

    # ── #help ─────────────────────────────────────────────────────────────
    help_ch = _find_ch("help") or _find_ch("❓-help")
    if help_ch:
        e = discord.Embed(title="❓ Help", color=0x5865F2)
        e.description = (
            "**Quick answers:**\n\n"
            "**Q: Script not loading?**\n"
            "→ Make sure you have a valid key (`/key`) and your Roblox has Face Verification enabled\n\n"
            "**Q: Key expired?**\n"
            "→ Use `/refs` to get your invite link and invite 2 friends for lifetime access\n\n"
            "**Q: Switched PC?**\n"
            "→ Open a support ticket in <#" + str(ticket_ch.id) + ">\n\n"
            "**Q: No donations coming in?**\n"
            "→ Make sure you have a **Gamepass** set up on your Roblox account\n\n"
            f"Still stuck? Open a ticket → <#{ticket_ch.id}>"
        )
        await help_ch.send(embed=e)
        log.append("Posted in #help")

    # ── #updates ──────────────────────────────────────────────────────────
    upd_ch = _find_ch("updates") or _find_ch("🗞️-updates") or _find_ch("📰-updates")
    if upd_ch:
        e = discord.Embed(title="🗞️ Updates — v23", color=0x5865F2)
        e.description = (
            "**🧠 Smarter Script**\n"
            "Rewritten conversation engine. Bot adapts to player responses — compliments, varied phrases, persistence. 2-3× better conversion.\n\n"
            "**⚡ Stability**\n"
            "Auto server-hop, AFK protection, anti-mod detection, auto-reconnect. Runs for hours.\n\n"
            "**🌐 Dashboard**\n"
            "Real-time stats, conversation logs, conversion rates. Use `/dashboard` to access.\n\n"
            "**🎁 Referral System**\n"
            "2 friends → lifetime access\n"
            "3+ friends → 10% of their earnings\n\n"
            "*More updates coming soon.*"
        )
        await upd_ch.send(embed=e)
        log.append("Posted in #updates")

    # ── #create-ticket ────────────────────────────────────────────────────
    ticket_embed = discord.Embed(title="📬 Support", color=0x5865F2)
    ticket_embed.description = (
        "Need help? Click below to open a **private support ticket**.\n\n"
        "**Common issues:**\n"
        "• HWID mismatch (switched PC)\n"
        "• Script not working\n"
        "• Payout request\n"
        "• Any other questions"
    )
    await ticket_ch.send(embed=ticket_embed, view=CreateTicketView())
    log.append("Posted ticket button in #create-ticket")

    result = "✅ **Server setup complete!**\n" + "\n".join(f"• {x}" for x in log)
    await interaction.followup.send(result, ephemeral=True)


bot.tree.add_command(admin_group)


# ── Entry point ───────────────────────────────────────────────────────────

def main():
    db_v2.init_db()
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
