# Premarket Scanner AI Updates

## 2026-03-12 (Discord Bot Error Handling Improvements)

Improved the resilience and error handling of the Discord bot (`discord_bot/bot.py`) to prevent it from crashing gracefully during transient Discord server outages or GitHub API failures.

### Changes Made
1. **`discord_retry()` Helper Function:**
   - Added a generic retry wrapper for Discord API calls (`ctx.send`, `msg.edit`) on 5xx errors (e.g. 503 Service Unavailable).
   - Retries up to 3 times with exponential backoff (2s → 4s → give up).

2. **Global Error Handler (`on_command_error`):**
   - Implemented a Catch-all error handler for unhandled command exceptions.
   - Distinguishes between:
     - `discord.DiscordServerError` (Discord server outage) -> informs users it's a Discord server issue, not a bot bug.
     - `aiohttp.ClientError` (Network error) -> informs users it's an external service reachability issue.
     - `commands.MissingRequiredArgument` / `commands.BadArgument`.

3. **Accurate Command Output Messaging:**
   - Replaced generic `⚠️ Internal Error: Could not reach GitHub` with more specific errors differentiating GitHub API issues from Discord send failures in the `!turnon`, `!turnoff` and `!status` commands.
   - All visual feedback logic wraps sending messages with the new retry helper so the bot reliably survives transient connection drops.
