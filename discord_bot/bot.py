import os
import discord
from discord.ext import commands
import aiohttp
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load local environment variables if present
load_dotenv()

# Configuration from Environment Variables
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", os.getenv("GITHUB_PAT")) # Fallback for consistency
GITHUB_REPO = os.getenv("GITHUB_REPO", "emadprograms/premarket-scanner")
WORKFLOW_FILENAME = os.getenv("WORKFLOW_FILENAME", "backend-runner.yml")

# Retry configuration
MAX_DISCORD_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds, doubles each attempt


# ─── Retry Helper ────────────────────────────────────────────────────────────

async def discord_retry(coro_func, *args, **kwargs):
    """Retry a Discord API call (send/edit) on transient 5xx errors.
    
    Args:
        coro_func: An async callable (e.g. ctx.send or msg.edit).
        *args, **kwargs: Arguments forwarded to coro_func.
    
    Returns:
        The result of the successful call.
    
    Raises:
        The last DiscordServerError if all retries are exhausted,
        or any non-5xx error immediately.
    """
    last_error = None
    for attempt in range(1, MAX_DISCORD_RETRIES + 1):
        try:
            return await coro_func(*args, **kwargs)
        except discord.DiscordServerError as e:
            last_error = e
            if attempt < MAX_DISCORD_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(f"[RETRY] Discord 5xx on attempt {attempt}/{MAX_DISCORD_RETRIES}, "
                      f"retrying in {delay}s... ({e.status}: {e.text})")
                await asyncio.sleep(delay)
            else:
                print(f"[RETRY] Discord 5xx on final attempt {attempt}/{MAX_DISCORD_RETRIES}, giving up.")
    raise last_error


# ─── Setup ───────────────────────────────────────────────────────────────────

# Setup intents for message reading
intents = discord.Intents.default()
intents.message_content = True

# Initialize Bot
bot = commands.Bot(command_prefix="!", intents=intents)


# ─── Global Error Handler ───────────────────────────────────────────────────

@bot.event
async def on_command_error(ctx, error):
    """Catch-all error handler for unhandled command exceptions."""
    # Unwrap the CommandInvokeError to get the original cause
    original = getattr(error, "original", error)

    if isinstance(original, discord.DiscordServerError):
        msg = (f"⚠️ **Discord is having issues** (HTTP {original.status})\n"
               f"> This is a Discord server-side outage — not a bug in the bot.\n"
               f"> Please try again in a minute.")
    elif isinstance(original, aiohttp.ClientError):
        msg = (f"⚠️ **Network error** — could not reach an external service.\n"
               f"> `{type(original).__name__}: {original}`")
    elif isinstance(original, commands.MissingRequiredArgument):
        msg = f"❌ **Missing argument:** `{original.param.name}`\n> Usage: `{ctx.command.help or ctx.command.signature}`"
    elif isinstance(original, commands.BadArgument):
        msg = f"❌ **Bad argument:** {original}"
    else:
        msg = f"⚠️ **Unexpected error:** `{type(original).__name__}: {original}`"
        print(f"[ERROR] Unhandled exception in !{ctx.command}: {original}", flush=True)

    try:
        await discord_retry(ctx.send, msg)
    except Exception:
        # If we truly can't send anything, just log it
        print(f"[ERROR] Could not send error message to Discord: {msg}", flush=True)


# ─── Events & Commands ──────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user.name} ({bot.user.id})')
    print('Bot is ready to receive commands.')

@bot.command(name="turnon")
async def trigger_fetch(ctx, duration: str = "2h"):
    """Triggers the Premarket Scanner Backend.
    Usage: !turnon [duration]
    Example: !turnon 1h"""
    
    # Visual feedback — uses retry so a transient 503 doesn't kill the command
    status_msg = await discord_retry(
        ctx.send,
        f"🚀 **Connecting to Premarket Scanner Engine...**\n"
        f"> **Requested Duration:** `{duration}`\n"
        f"Dispatching signal to GitHub Actions..."
    )
    
    # Prepare GitHub API request
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILENAME}/dispatches"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    data = {
        "ref": "main",
        "inputs": {
            "duration": duration
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                # GitHub returns 204 No Content on a successful dispatch
                if response.status == 204:
                    await discord_retry(
                        status_msg.edit,
                        content="💠 **Transmission Successful!**\n> **Scanner Backend** is initializing... Fetching live runner link... 📡"
                    )
                    print(f"Triggered backend via Discord user: {ctx.author}")
                    
                    # Try up to 3 times with 4s wait each (total 12s) to get the run URL
                    live_url = None
                    for attempt in range(1, 4):
                        await asyncio.sleep(4)
                        print(f"Attempt {attempt} to fetch live link...")
                        
                        runs_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILENAME}/runs"
                        async with session.get(runs_url, headers=headers) as runs_resp:
                            if runs_resp.status == 200:
                                runs_data = await runs_resp.json()
                                if runs_data.get("workflow_runs"):
                                    live_url = runs_data["workflow_runs"][0]["html_url"]
                                    break
                            else:
                                print(f"Failed to fetch runs on attempt {attempt}: {runs_resp.status}")
                    
                    final_msg_content = (
                        f"💠 **Transmission Successful!**\n"
                        f"> **Scanner Backend** is booting up for `{duration}`.\n"
                    )
                    
                    if live_url:
                        final_msg_content += f"> 🔗 **[Monitor Live Runner on GitHub]({live_url})**\n"
                    else:
                        final_msg_content += f"> (Live link could not be retrieved - check GitHub Actions manually)\n"
                        
                    final_msg_content += f"> 🌐 **[Open Scanner Frontend](https://premarket-scanner.vercel.app)**\n\n"
                    final_msg_content += "> The frontend at Vercel will connect automatically via Cloudflare tunnel once the engine is hot. ⚡"
                    
                    await discord_retry(status_msg.edit, content=final_msg_content)
                else:
                    response_json = await response.json() if response.content_type == 'application/json' else {}
                    error_details = response_json.get("message", await response.text())
                    await discord_retry(
                        status_msg.edit,
                        content=f"❌ **Failed to trigger workflow.**\nGitHub API Error ({response.status}): `{error_details}`"
                    )
                    print(f"Failed to trigger: {response.status} - {error_details}")
            
    except aiohttp.ClientError as e:
        await discord_retry(
            status_msg.edit,
            content=f"⚠️ **Network Error:** Could not reach GitHub API.\n`{type(e).__name__}: {e}`"
        )
        print(f"Network error triggering workflow: {e}")
    except discord.DiscordServerError:
        # Already retried via discord_retry — if we're here the edit itself failed after retries.
        # The global handler will catch this via CommandInvokeError.
        raise
    except Exception as e:
        await discord_retry(
            status_msg.edit,
            content=f"⚠️ **Unexpected Error:** `{type(e).__name__}: {e}`"
        )
        print(f"Exception triggering workflow: {e}")

@bot.command(name="status")
async def check_status(ctx):
    """Checks the status of the runner."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILENAME}/runs?per_page=1"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    runs_data = await response.json()
                    runs = runs_data.get("workflow_runs", [])
                    if runs:
                        latest = runs[0]
                        status = latest.get("status")
                        conclusion = latest.get("conclusion")
                        run_url = latest.get("html_url")
                        
                        msg = f"📊 **Latest Runner Status:** `{status}`"
                        if conclusion:
                            msg += f" (Result: `{conclusion}`)"
                        if run_url:
                            msg += f"\n> 🔗 **[View Log]({run_url})**"
                            
                        await discord_retry(ctx.send, msg)
                    else:
                        await discord_retry(ctx.send, "❓ **No workflow runs found.**")
                else:
                    await discord_retry(ctx.send, f"❌ **Failed to fetch status:** GitHub returned {response.status}")
    except aiohttp.ClientError as e:
        await discord_retry(ctx.send, f"⚠️ **Network Error:** Could not reach GitHub API.\n`{type(e).__name__}: {e}`")
    except discord.DiscordServerError:
        raise  # Let the global handler deal with it
    except Exception as e:
        await discord_retry(ctx.send, f"⚠️ **Unexpected Error:** `{type(e).__name__}: {e}`")

@bot.command(name="turnoff")
async def turn_off(ctx):
    """Cancels the currently running Premarket Scanner Backend."""
    status_msg = await discord_retry(ctx.send, "🛑 **Attempting to shut down the Scanner Engine...**")
    
    runs_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_FILENAME}/runs?per_page=1"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(runs_url, headers=headers) as response:
                if response.status == 200:
                    runs_data = await response.json()
                    runs = runs_data.get("workflow_runs", [])
                    if not runs:
                        await discord_retry(status_msg.edit, content="❓ **No workflow runs found to cancel.**")
                        return
                    
                    latest_run = runs[0]
                    run_id = latest_run["id"]
                    status = latest_run["status"]
                    
                    if status in ["completed", "cancelled", "skipped", "failure"]:
                        await discord_retry(
                            status_msg.edit,
                            content=f"⏸️ **The Scanner Engine is already inactive.** (Status: `{status}`)"
                        )
                        return
                    
                    cancel_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs/{run_id}/cancel"
                    async with session.post(cancel_url, headers=headers) as cancel_resp:
                        if cancel_resp.status in [202, 204]:
                            await discord_retry(
                                status_msg.edit,
                                content="🛑 **Termination Signal Sent!**\n> The Scanner Engine is shutting down. The Cloudflare Tunnel will close momentarily. 🔌"
                            )
                        else:
                            error_text = await cancel_resp.text()
                            await discord_retry(
                                status_msg.edit,
                                content=f"❌ **Failed to send termination signal:** `HTTP {cancel_resp.status}`\n`{error_text}`"
                            )
                else:
                    await discord_retry(
                        status_msg.edit,
                        content=f"❌ **Failed to fetch active runs:** GitHub returned `{response.status}`"
                    )
    except aiohttp.ClientError as e:
        await discord_retry(
            status_msg.edit,
            content=f"⚠️ **Network Error:** Could not reach GitHub API.\n`{type(e).__name__}: {e}`"
        )
    except discord.DiscordServerError:
        raise  # Let the global handler deal with it
    except Exception as e:
        await discord_retry(
            status_msg.edit,
            content=f"⚠️ **Unexpected Error:** `{type(e).__name__}: {e}`"
        )

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("CRITICAL: DISCORD_BOT_TOKEN is missing.")
        exit(1)
    if not GITHUB_TOKEN:
        print("CRITICAL: GITHUB_TOKEN (or GITHUB_PAT) is missing.")
        exit(1)
        
    print("Starting Premarket Scanner bot...")
    bot.run(DISCORD_TOKEN)
