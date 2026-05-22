#!/usr/bin/env python3
"""
Quick standalone verification of the Discord notification path. Calls
post_recap_to_discord() with fabricated game data — no Claude API call, no
admin write, no ESPN fetch. Lets you confirm the Cloudflare Worker secret
+ webhook routing are correct without spending money or polluting admin.

Usage:
  export DISCORD_PROXY_URL='https://nsmt-discord-proxy.old-glitter-7307.workers.dev'
  export DISCORD_PROXY_SECRET='<the shared secret>'
  python test_discord.py

Success = a "🧪 Wizards Test Recap" thread appears in #recap-pipeline.
Delete it after verifying.
"""
from datetime import date
from generate_content import post_recap_to_discord

fake_team = {
    "name": "Washington Wizards (TEST)",
    "league": "NBA",
    "persona": "Casper Wexler",
    "voice": "modern, analytics-first NBA tone",
    "channel_target": "RECAPS",  # change to "WIZARDS" once that webhook is configured
}
fake_summary = {
    "score": "Washington Wizards 112, Boston Celtics 108",
    "venue": "Capital One Arena",
}
fake_title = "🧪 Wizards Test Recap — Snap Losing Streak with 112-108 Win"
fake_body = (
    "This is a TEST notification from test_discord.py — confirms the Discord "
    "notification path works without calling Claude or writing to admin.\n\n"
    "The full article body would normally appear here, with multiple "
    "paragraphs of game recap content. The new embed format renders the "
    "entire piece directly in Discord so reviewers can read without clicking "
    "through to admin.\n\n"
    "Delete this thread after verifying."
)

ok = post_recap_to_discord(
    title=fake_title,
    body=fake_body,
    team=fake_team,
    summary=fake_summary,
    game_date=date.today(),
)

if ok:
    print("\n✓ Test passed. Check #recap-pipeline in Discord for the test thread.")
    raise SystemExit(0)

print("\n✗ Test failed. See errors above. Common causes:")
print("  - DISCORD_PROXY_URL or DISCORD_PROXY_SECRET not exported in this shell")
print("  - Worker secret DISCORD_WEBHOOK_URL_RECAPS not set (run `wrangler secret put`)")
print("  - Webhook URL is wrong / deleted")
raise SystemExit(1)
