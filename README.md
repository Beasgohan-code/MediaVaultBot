# MediaVaultBot

**Modern personal media bot — 2026 edition**

- Your own **download history** library (browse / search / send)
- Public platform downloads via **yt-dlp** (YouTube, Reddit, X, TikTok, Instagram public, Vimeo, SoundCloud, +1000 sites)
- **PostgreSQL** + SQLAlchemy 2 async
- **Kurigram** (latest Telegram MTProto)
- Docker-ready
- Progress bars, favorites, auto-delete, admin tools

> **Personal use only.**  
> Use it for media you own or public content you are allowed to access.  
> No custom scrapers for cosplay sites or arbitrary private websites.

---

## Features

### download history
- Folder browsing with pagination
- Full-text search
- Direct send (video / audio / photo / document)
- Favorites

### Public URLs (yt-dlp)
Just paste a link. Supported out of the box:
- YouTube / youtu.be
- Reddit
- X (Twitter)
- TikTok
- Instagram (public posts)
- Vimeo, SoundCloud, Twitch clips, Facebook public
- Thousands more sites that yt-dlp supports

### Bot quality-of-life
- Real-time progress + speed + ETA
- Configurable auto-delete of sent files
- Ban system & admin management
- PostgreSQL persistence
- Caching + retries
- Clean HTML UI

---

## Quick Start (Docker – recommended)

```bash
cp .env.example .env
# Edit .env (Telegram + optional Drive SA)

# Optional: place service_account.json / cookies.txt next to docker-compose.yml

docker compose up -d --build
docker compose logs -f bot
```

The compose file starts both the bot and a PostgreSQL 16 container.

---

## Local (without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit DATABASE_URL to your local Postgres

# Create DB
createdb mediavault

python __main__.py
```

---

## download history setup (optional)

1. Google Cloud Console → create project → enable **Drive API**
2. Create **Service Account** → download JSON → rename to `service_account.json`
3. Share the folder that contains your media with the service-account email (Viewer is enough)
4. Optionally set `DRIVE_ROOT_FOLDER_ID` to that folder

---

## yt-dlp notes

- For age-restricted or region-locked public videos you may need a `cookies.txt` (export from browser).
- Max filesize is limited both by yt-dlp config and Telegram (~2 GB).
- Playlists are disabled by default (single video only).

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + menu |
| `/help` | Help |
| `/browse` | Drive browser |
| `/search <q>` | Search Drive |
| `/favs` | Favorites |
| `/sites` | Supported public platforms |
| `/stats` | Stats (admin) |
| `/autodel <secs>` | Auto-delete timer |
| `/ban` `/unban` | Moderation |
| `/admins` | Admin list |
| `/ping` | Latency |

Paste any supported URL directly in chat.

---

## Project layout

```
MediaVaultBot/
├── __main__.py
├── config.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── core/
│   ├── database.py      # PostgreSQL
│   ├── drive.py         # download history
│   ├── ytdlp.py         # Public platform downloader
│   ├── utils.py
│   └── state.py
└── telegram/
    ├── decorators.py
    └── plugins/
        ├── commands.py
        ├── browse.py
        ├── search.py
        ├── download.py      # Drive file send
        └── url_download.py  # yt-dlp handler
```

---

## Environment variables

See `.env.example`. Most important:

- `API_ID`, `API_HASH`, `BOT_TOKEN`, `OWNER_ID`
- `DATABASE_URL`
- `GOOGLE_SERVICE_ACCOUNT_FILE` + `DRIVE_ROOT_FOLDER_ID`
- `YTDLP_ENABLED`, `YTDLP_MAX_FILESIZE`, `YTDLP_COOKIES_FILE`

---

## Disclaimer

This bot is a personal media helper.  
Do not use it to download or redistribute content you do not have the right to access.  
The maintainers are not responsible for misuse.

---

Enjoy your library.

---

## Cookies & Age-restricted / NSFW content

Two methods (priority: file > browser):

```env
# cookies.txt
YTDLP_COOKIES_FILE=/path/to/cookies.txt

# OR pull live from browser
YTDLP_COOKIES_FROM_BROWSER=chrome
# YTDLP_COOKIES_FROM_BROWSER=firefox:default-release
# YTDLP_COOKIES_FROM_BROWSER=edge
```

On Docker the browser method only works if the browser profile is accessible inside the container (usually better on bare-metal / VPS).

### Terms of Use

Users must accept `/tos` before the first download.  
The disclaimer makes clear that **all downloads are at the user’s own risk**, including any NSFW or age-restricted public content they choose to request.  
The bot author / host is not responsible for the URLs users submit.

---

## New features (this build)

### Quality selector
After pasting a URL the bot shows:
- Best / 1080p / 720p / 480p / 360p / Audio only

### Multi-user quotas
```env
QUOTA_DAILY_DOWNLOADS=20
QUOTA_DAILY_MB=2048
QUOTA_ADMIN_UNLIMITED=true
```
Check with `/quota`. Resets UTC midnight.

### Inline mode
1. Talk to @BotFather → /setinline → enable
2. Type `@YourBot query` in any chat to search Drive

### Cookies helper
`/cookies` shows current status + how to export cookies.txt or use cookies-from-browser.

---

## Latest upgrades

- **Real format list** from yt-dlp (“All formats” button)
- **Download queue** (global + per-user) with **Cancel** button
- **Preferred quality** remembered per user
- **Health** endpoint `:8080/health`
- **Temp cleanup** background task
- **Drive breadcrumbs** + sort (Name / Size / Date)
- **Rate limit** (links per minute)
- **Ban with expiry**: `/ban <id> <days> [reason]`
- Playlist cap via `YTDLP_PLAYLIST_MAX`

---

## Ultimate build features

| Area | Commands / behavior |
|------|---------------------|
| Library | `/library query` unified history + Drive |
| Collections | `/collections` `/watchlater` `/colnew` `/coladd` |
| Queue | `/queue` + cancel buttons |
| Schedule | `/schedule 2h URL` `/schedules` |
| Formats | Presets + full yt-dlp format list |
| ffmpeg | Audio extract / mux (when available) |
| Subs | Auto-download en/hi subs when present |
| Tags | guessit auto SxxExx / year |
| Deep links | `t.me/Bot?start=dl_<base64url>` |
| Share | Set `SHARE_CHANNEL` for one-tap share |
| UI | Blockquotes across responses |
| Health | `:8080/health` + Docker HEALTHCHECK |

---

## Deploy on Railway

1. Push this repo to GitHub (or use Railway CLI).
2. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**.
3. **Add plugin** → **PostgreSQL**.
4. Open the **bot service** → **Variables** → add:

```text
API_ID=
API_HASH=
BOT_TOKEN=
OWNER_ID=
BOT_USERNAME=
YTDLP_ENABLED=true
REQUIRE_TOS_ACCEPT=true
HEALTH_PORT=8080
```

`DATABASE_URL` is injected automatically from the Postgres plugin (bot converts it to `asyncpg`).

5. Settings → use **Dockerfile** builder (see `railway.toml` / `railway.json`).
6. Deploy. Check logs for `Bot online as @...`.

CLI alternative:

```bash
npm i -g @railway/cli
railway login
railway init
railway add --plugin postgres
railway up
railway variables set API_ID=... BOT_TOKEN=... OWNER_ID=...
```

---

## Deploy on Render

1. Push repo to GitHub.
2. [render.com](https://render.com) → **New** → **Blueprint**.
3. Connect the repo (uses `render.yaml`).
4. Render creates **PostgreSQL** + **web** service.
5. In the web service **Environment**, set:

```text
API_ID=
API_HASH=
BOT_TOKEN=
OWNER_ID=
BOT_USERNAME=
```

`DATABASE_URL` comes from the linked database.

6. Deploy. Open logs until you see the bot online.

**Note:** Free/starter tiers have limits on CPU, disk, and sleep. For heavy yt-dlp use, prefer a paid plan or a VPS with `docker compose`.

---

## Files for cloud deploy

| File | Platform |
|------|----------|
| `Dockerfile` | Railway, Render, any Docker host |
| `railway.toml` / `railway.json` | Railway |
| `render.yaml` | Render Blueprint |
| `Procfile` | Generic worker hint |
| `docker-compose.yml` | Local / VPS |


## Note
Google Drive was removed. This bot is yt-dlp + Postgres only.
