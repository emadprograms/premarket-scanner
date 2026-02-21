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

# Setup intents for message reading
intents = discord.Intents.default()
intents.message_content = True

# Initialize Bot
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user.name} ({bot.user.id})')
    print('Bot is ready to receive commands.')

@bot.command(name="turnon")
async def trigger_fetch(ctx, duration: str = "2h"):
    """Triggers the Premarket Scanner Backend.
    Usage: !turnon [duration]
    Example: !turnon 1h"""
    
    # Visual feedback focused on Premarket Scanner identity
    status_msg = await ctx.send(
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
    
    # We trigger the workflow on the 'main' branch
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
                    await status_msg.edit(content="💠 **Transmission Successful!**\n> **Scanner Backend** is initializing... Fetching live runner link... 📡")
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
                                    # The first run is the most recent one we just triggered
                                    live_url = runs_data["workflow_runs"][0]["html_url"]
                                    break
                            else:
                                print(f"Failed to fetch runs on attempt {attempt}: {runs_resp.status}")
                    
                    final_msg_content = (
                        f"💠 **Transmission Successful!**\n"
                        f"> **Scanner Backend** is booting up for `{duration}`.\n"
                    )
                    
                    if live_url:
                        final_msg_content += f"> 🔗 **[Monitor Live Runner on GitHub]({live_url})**\n\n"
                    else:
                        final_msg_content += f"> (Live link could not be retrieved - check GitHub Actions manually)\n\n"
                        
                    final_msg_content += "> The frontend at Vercel will connect automatically via Cloudflare tunnel once the engine is hot. ⚡"
                    
                    await status_msg.edit(content=final_msg_content)
                else:
                    response_json = await response.json() if response.content_type == 'application/json' else {}
                    error_details = response_json.get("message", await response.text())
                    await status_msg.edit(content=f"❌ **Failed to trigger workflow.**\nGitHub API Error ({response.status}): `{error_details}`")
                    print(f"Failed to trigger: {response.status} - {await response.text()}")
            
    except Exception as e:
        await status_msg.edit(content=f"⚠️ **Internal Error:** Could not reach GitHub.\n`{str(e)}`")
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
                            
                        await ctx.send(msg)
                    else:
                        await ctx.send("❓ **No workflow runs found.**")
                else:
                    await ctx.send(f"❌ **Failed to fetch status:** GitHub returned {response.status}")
    except Exception as e:
        await ctx.send(f"⚠️ **Error fetching status:** `{str(e)}`")

@bot.command(name="turnoff")
async def turn_off(ctx):
    """Cancels the currently running Premarket Scanner Backend."""
    status_msg = await ctx.send("🛑 **Attempting to shut down the Scanner Engine...**")
    
    # 1. Fetch the latest run to get its ID
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
                        await status_msg.edit(content="❓ **No workflow runs found to cancel.**")
                        return
                    
                    latest_run = runs[0]
                    run_id = latest_run["id"]
                    status = latest_run["status"]
                    
                    if status in ["completed", "cancelled", "skipped", "failure"]:
                        await status_msg.edit(content=f"⏸️ **The Scanner Engine is already inactive.** (Status: `{status}`)")
                        return
                    
                    # 2. Cancel the specific run ID
                    cancel_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs/{run_id}/cancel"
                    async with session.post(cancel_url, headers=headers) as cancel_resp:
                        if cancel_resp.status in [202, 204]:
                            await status_msg.edit(content="🛑 **Termination Signal Sent!**\n> The Scanner Engine is shutting down. The Cloudflare Tunnel will close momentarily. 🔌")
                        else:
                            error_text = await cancel_resp.text()
                            await status_msg.edit(content=f"❌ **Failed to send termination signal:** `HTTP {cancel_resp.status}`\n`{error_text}`")
                else:
                    await status_msg.edit(content=f"❌ **Failed to fetch active runs:** GitHub returned `{response.status}`")
    except Exception as e:
        await status_msg.edit(content=f"⚠️ **Error during shutdown sequence:** `{str(e)}`")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("CRITICAL: DISCORD_BOT_TOKEN is missing.")
        exit(1)
    if not GITHUB_TOKEN:
        print("CRITICAL: GITHUB_TOKEN (or GITHUB_PAT) is missing.")
        exit(1)
        
    print("Starting Premarket Scanner bot...")
    bot.run(DISCORD_TOKEN)
