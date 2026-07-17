# Persian Doz Bot — Python (aiogram) port

A migration of the original Cloudflare Worker / D1 Telegram Connect-Four
("Doz") bot to a standalone Python service (Python 3.12, aiogram 3,
aiosqlite). Game rules, message text (Persian + English), keyboards,
timers, admin panel, referrals, and history are all preserved.

## What's in this migration, and how it was verified

This is a large codebase (~3,600 lines of JS across texts, store, game
engine, keyboards, and handlers), so rather than asking you to trust a
blind transliteration, two of the highest-risk pieces were verified
programmatically against the original source during the port:

- **`telegram/texts.py`** (169 keys × 2 languages, including ~76
  message-formatting functions) was generated directly from the JS
  source with a small script (load the real `T` object in Node, convert
  every arrow-function template to an equivalent Python f-string
  function) rather than being retyped by hand, then spot-checked against
  the live JS output for plain strings, multi-arg functions, string
  concatenation, and the two functions using `||` — all matched exactly.
- **`game/board.py`** (win detection, move validation, board rendering)
  was checked by simulating 200 pseudo-random games in the original JS
  and replaying the identical move sequences through the Python port —
  board state, winner, and winning-cell coordinates matched on all 200.
- Every handler function (`handleStart`, `routeAction`, `handleMessage`,
  `handleCallbackQuery`, `handleGameInviteAccept`, `handleFriendRemove`,
  `checkChannelGate`/`isChannelMember`/`parseChannelIdentifier`, etc.) was
  ported by reading the corresponding original function and translating
  it line-for-line, then diffed back against the source line ranges
  during review (see the "Design notes / deviations" section below for
  the handful of intentional structural differences).

What this environment could **not** do: install `aiogram`/`aiosqlite`
(no network access) and actually run the bot end-to-end against Telegram.
Every module was syntax-checked and the dependency-free modules
(`game/`, `database/models.py`, `telegram/texts.py`, `telegram/formatting.py`)
were also imported and smoke-tested. **Before deploying, run it against
a real bot token in polling mode and click through the main flows once**
(start, play a friend game to completion, matchmaking, a timeout, the
admin panel, and a group `/game`) — treat this as a thoroughly-reviewed
first draft, not a certified-tested release.

## Architecture

```
project/
├── app.py                   # entrypoint: wiring, polling/webhook modes
├── config.py                 # env var loading
├── context.py                 # AppContext (bot, repo, config, timers) - DI'd into every handler
├── schema.sql                 # consolidated fresh-install schema
├── database/
│   ├── models.py               # dataclasses: User, Game, Player, Settings, ...
│   ├── repository.py           # aiosqlite queries — 1:1 port of store.js's Store class
│   ├── utils.py                 # id/time helpers with no external deps
│   └── migrations/              # the original 4 incremental D1 migrations, as separate files
├── telegram/
│   ├── client.py                 # thin wrapper around aiogram's Bot (same method names as telegram.js)
│   ├── keyboards.py               # every keyboard builder from keyboards.js
│   ├── texts.py                   # generated from texts.js (see above)
│   ├── formatting.py               # escapeHtml + renderInfoCard/RecordList/Leaderboard
│   └── handlers/
│       ├── messages.py              # handleMessage() port — one router-level handler
│       └── callbacks.py             # handleCallbackQuery() port — one router-level handler
├── game/
│   ├── board.py                 # ROWS/COLS, win detection, move validation — verified (see above)
│   ├── engine.py                  # Game/Player construction helpers, REASON_KEYS
│   ├── games.py                     # startGame/handleMove/finishGame/group-game/friend-invite orchestration
│   ├── matchmaking.py                 # random-match queue
│   └── timer.py                        # asyncio replacement for the GameTimerDO Durable Object
├── services/
│   ├── users.py, friends.py, referrals.py, rewards.py, ranking.py, admin.py
│   └── channel.py                # mandatory-channel-join gate + bot-username resolution
└── storage/
    └── sqlite.py                 # aiosqlite connection + schema bootstrap
```

## Design notes / deviations from a literal transliteration

A few places were translated idiomatically rather than 1:1, since a
faithful *behavioral* port is the goal, not a faithful *syntax* port:

- **Durable Object timers → asyncio tasks.** `game/timer.py` replaces the
  Cloudflare `GameTimerDO` (one Durable Object instance per game, with a
  persistent alarm) with one `asyncio` background task per active game.
  Since asyncio tasks don't survive a process restart the way a DO's
  alarm does, `app.py` calls `TimerManager.recover()` on startup, which
  re-arms every in-progress game's timer based on elapsed time since
  `turn_started_at` (including firing an immediate timeout for a game
  that was already overdue while the process was down).
- **Conversational state kept in the database, not aiogram's FSM.** The
  admin panel and "add friend by ID" flows use the same
  `admin_state`/`user_state` tables the original used (a single pending
  action per user, persisted in SQLite) rather than aiogram's
  `FSMContext`. This was a deliberate choice: it's the exact mechanism
  that already gives the original bot restart-survival for pending input,
  and adding a second, parallel state-management system on top would add
  complexity without changing behavior. `telegram/handlers/messages.py`
  checks these tables directly, mirroring `handleMessage`'s own ordering.
- **`game/games.py` is a new file**, not in the originally-sketched
  `game/` layout — it holds the orchestration functions that need both
  the database and Telegram (`startGame`, `handleMove`, `finishGame`,
  group-game flow, friend-invite accept/reject). `game/engine.py` and
  `game/board.py` stay dependency-free (pure game state), matching the
  spirit of "engine = rules, services/handlers = side effects" rather
  than splitting strictly by original filename.
- **`schema.sql` is consolidated**, not four sequential ALTER TABLEs —
  since this is a fresh SQLite database rather than an existing D1
  database being migrated forward, every column exists from the first
  `CREATE TABLE`. The original four migrations are preserved verbatim
  under `database/migrations/` for reference / for applying to an
  existing database incrementally instead.

## Setup

```bash
cp .env.example .env
# edit .env: set BOT_TOKEN (from @BotFather) and ADMIN_IDS (your numeric Telegram user id)

pip install -r requirements.txt
python app.py
```

That's it for local/simple deployment — `RUN_MODE=polling` (the default)
needs no public URL, no HTTPS certificate, and no inbound port; it just
makes outbound long-poll requests to Telegram. A fresh SQLite database
and schema are created automatically at `DATABASE_PATH` (default
`data/bot.db`) on first run.

### Docker

```bash
cp .env.example .env   # fill in BOT_TOKEN / ADMIN_IDS as above
docker compose up --build -d
```

The SQLite file persists in the `bot_data` named volume across restarts.

### Webhook mode (optional)

Set in `.env`:
```
RUN_MODE=webhook
WEBHOOK_BASE_URL=https://your-domain.example   # must be reachable over HTTPS by Telegram
WEBHOOK_SECRET=some-random-string
```
`app.py` registers the webhook with Telegram on startup and runs an
`aiohttp` server on `WEB_SERVER_PORT` (default 8080) — put this behind
your existing reverse proxy / TLS termination.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BOT_TOKEN` | yes | — | Token from @BotFather |
| `ADMIN_IDS` | no | (none) | Comma-separated numeric Telegram user IDs allowed to use `/admin` |
| `BOT_USERNAME` | no | resolved via `getMe()` | Skips a lookup for building referral links |
| `DATABASE_PATH` | no | `data/bot.db` | SQLite file location |
| `RUN_MODE` | no | `polling` | `polling` or `webhook` |
| `WEBHOOK_BASE_URL` | only if webhook | — | Public HTTPS base URL |
| `WEBHOOK_PATH` | no | `/webhook` | Path Telegram POSTs updates to |
| `WEBHOOK_SECRET` | no | (none) | Telegram's `secret_token` header check |
| `WEB_SERVER_HOST` / `WEB_SERVER_PORT` | no | `0.0.0.0` / `8080` | Webhook server bind address |

## Admin panel

Send `/admin` from an account listed in `ADMIN_IDS` to configure the
support link, mandatory channel, referral/signup bonus amounts, add
coins to one or all users, view current settings, or reset a stuck
user (ends their active game as a resignation, clears the matchmaking
queue and any pending input state).
