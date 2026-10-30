# Proxy Scrape Bot

Your own Discord bot that reads the checkout webhooks in a channel and posts a **proxy summary + timeline**:
which proxy providers you used, how many checkouts each got, success rates, and a minute-by-minute chart.

Reads **Valor, Shikari, sniped.gg and Refract** webhooks. It runs on **your own computer** with **your own bot**:
nothing is sent anywhere except back to your Discord channel, and nothing is saved.

> **Privacy:** only the proxy's **provider and type** are shown (e.g. "Vaultedproxies", "Proxy-haus · mobile",
> "ISP", "No proxy data"). Proxy logins, IPs, your proxy list names, emails, profiles and order numbers are never
> posted or stored.

## 1. Make your bot (once, ~3 minutes)
1. Open the [Discord Developer Portal](https://discord.com/developers/applications) > **New Application** > give it
   a name (e.g. "Proxy Scrape") > **Create**.
2. Left menu **Bot**:
   - **Reset Token** > **Copy**. Keep it secret: anyone with it can control your bot.
   - Under **Privileged Gateway Intents**, switch on **Message Content Intent** > **Save Changes**. (Without it the
     bot can't read webhook embeds.)
3. That's it. The app opens the page to add the bot to your server on its first start.

## 2. Run it
**Windows:** download `ProxyScrapeBot.exe` from [Releases](../../releases) and double-click it.
- Windows may say "Windows protected your PC" (the app isn't code-signed): **More info** > **Run anyway**.
- The first start opens a small window asking for your **bot token** (it shows as dots). It's saved on your
  computer only, in `%APPDATA%\ProxyScrapeBot\config.json`. Times on the chart use your computer's own timezone.
- There's **no window to keep open**: the bot runs in the background with an icon by the clock (bottom right; click
  the **^** arrow if you don't see it). Right-click it for: status, **Add to server**, **Start with Windows**
  (tick it and the bot starts whenever you log in), **Change token**, **Open log**, **Quit**.
- The bot is online while that icon is there, so while your PC is on. **Quit** takes it offline.
- Once it's online, it **opens the "add to server" page in your browser by itself** (and copies the link: Ctrl+V
  to paste it somewhere). Pick your server > **Continue** > **Authorize**. You need Manage Server in that server.
  Add it to another server later: tray icon > **Add to server**.
- **No page opened?** Developer Portal > your app > **OAuth2** > **URL Generator**: tick **bot** and
  **applications.commands**, then under Bot Permissions tick View Channels, Send Messages, Embed Links, Attach Files,
  Read Message History. Copy the **Generated URL** at the bottom and open it.

**Mac / Linux (or Windows with Python 3.11+):**
```bash
git clone https://github.com/Shoyo679/proxy-scrape-bot
cd proxy-scrape-bot
python -m pip install -r requirements.txt
python run.py
```

To change the token later: tray icon > **Change token** (or `python run.py --reset`). To remove everything: Quit,
untick Start with Windows first, then delete the `%APPDATA%\ProxyScrapeBot` folder.

## 3. Use it
In the channel with your checkout webhooks, type **`/proxy scrape`**:

| option | what to put |
|---|---|
| `start` | Right-click the first webhook > **Copy Message Link** (or Copy Message ID). Or a date: `2026-10-30`, `today`, `yesterday` |
| `end` *(optional)* | The last message (link or ID), or the last day (date). Empty = up to now |
| `include` *(optional)* | `success + all fails` (default) or `success only` |
| `channel` *(optional)* | Another channel to read (default: this one) |

The bot posts a summary (providers, types, failures) and the **Proxy Timeline** image in the channel:
success rate, attempts per minute (green = success, red = failed), one row per proxy provider with a dot each minute
it was used, and the busiest minutes. Long ranges switch to 5-minute, hourly or daily columns, and quiet gaps over
15 minutes are cut out of the chart. `/proxy help` shows a short how-to.

**Who can use it:** members with **Manage Server** by default. Server owners can change that in
Server Settings > Integrations > your bot.

**Counts:** success = "Checked Out" / "Successful Checkout" / review hold; failed = declined, error or cancelled.
Valor's later order checks ("Order Still Good" / "Order Canceled!") aren't attempts and are left out. Webhooks from
other bots are skipped (the summary says how many). One scrape reads at most 50,000 messages.

## Problems
- **"Discord rejected that token"**: copy a fresh token (Bot > Reset Token) and paste it when asked.
- **"Turn on MESSAGE CONTENT INTENT"**: see step 1.2.
- **`/proxy` doesn't show up**: make sure you added the bot with the page it opened (or the URL Generator with
  **applications.commands** ticked), then restart the app. You need Manage Server to see it. Discord can take a
  minute; restarting Discord (Ctrl+R) helps.
- **"I can't read #channel"**: give the bot View Channel and Read Message History in that channel.

## For developers
`psb/scan.py` (read a channel) → `psb/report.py` (numbers) → `psb/chart.py` (image, Pillow) → `psb/bot.py`
(Discord). Proxy rules: `psb/proxies.py`; webhook formats: `psb/parse.py`. Tests: `python -m unittest discover -s tests`.
Releases: push a tag `vX.Y.Z` and GitHub Actions builds `ProxyScrapeBot.exe` (`.github/workflows/release.yml`).

MIT licence.
