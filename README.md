# 🎮 Persian Doz Arena

<div align="center">

![Version](https://img.shields.io/badge/version-2.0-blue)
![Python](https://img.shields.io/badge/Python-3.12+-green)
![Aiogram](https://img.shields.io/badge/Aiogram-3.x-0098EA)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57)

### A Modern Competitive Telegram Gaming Platform

Fast • Social • Competitive • Beautiful

</div>

---

## ✨ Overview

Persian Doz Arena is a next-generation Telegram gaming platform built with Python, Aiogram, and SQLite.

Designed with a modern gaming experience in mind, it combines matchmaking, rankings, achievements, referrals, tournaments, and social features into a polished Telegram-native experience.

---

## 🚀 Features

### 🎯 Gameplay
- Real-time multiplayer matches
- Friend invitations
- Random matchmaking
- Move timers
- Automatic win detection
- Match history

### 🏆 Competitive System
- Global leaderboard
- Seasonal rankings
- Elo rating system
- Win/Loss statistics
- Performance tracking

### 👥 Social Features
- Friends system
- Referral rewards
- User profiles
- Online player discovery
- Shared match results

### 🎁 Rewards & Economy
- Daily rewards
- Coin system
- Achievement rewards
- Referral bonuses
- Seasonal rewards

### 🛡️ Administration
- Broadcast messages
- User management
- Economy controls
- Statistics dashboard
- Configuration management

---

## 🎨 UI Philosophy

### Modern Gaming Experience

```text
┌─────────────────────────────┐
│ 🎮 Persian Doz Arena        │
│                             │
│ 👤 Player Profile           │
│ 💰 Coins                    │
│ 🏆 Rank                     │
│ ⭐ Level                     │
└─────────────────────────────┘
```

### Recommended Button Layout

```text
┌───────────────────────┐
│ ⚡ Quick Match        │
└───────────────────────┘

┌────────────┬──────────┐
│ 👥 Friend  │ 🏆 Rank │
└────────────┴──────────┘

┌────────────┬──────────┐
│ 🎁 Reward  │ 📈 Stats │
└────────────┴──────────┘

┌────────────┬──────────┐
│ 👤 Profile │ ⚙ Menu  │
└────────────┴──────────┘
```

### UX Principles

- Minimal clicks
- Mobile-first navigation
- Persistent keyboard
- Fast response time
- Consistent layouts
- Clear visual hierarchy

---

## 🏗 Architecture

```text
app.py
│
├── database/
├── telegram/
├── game/
├── services/
├── storage/
└── config.py
```

### Core Components

| Component | Purpose |
|------------|----------|
| Game Engine | Match logic |
| Matchmaking | Opponent discovery |
| Timer System | Turn management |
| Referral Service | Growth system |
| Ranking Service | Competitive ladder |
| Admin Service | Management tools |

---

## 🎮 Main Navigation

### User Menu

- ⚡ Quick Match
- 👥 Play Friend
- 🏆 Leaderboard
- 🎁 Daily Reward
- 📈 Statistics
- 👤 Profile
- 🎒 Inventory
- 💎 Store
- ⚙ Settings

### Admin Menu

- 👥 Users
- 🎮 Games
- 💰 Economy
- 📢 Broadcast
- 🎁 Rewards
- 🎟 Coupons
- 📈 Analytics
- ⚙ Settings

---

## 🏅 Achievement System

| Achievement | Reward |
|------------|---------|
| First Win | 100 Coins |
| 10 Wins | 500 Coins |
| Win Streak x5 | Badge |
| Invite 10 Friends | Premium Frame |
| Top 100 Rank | Special Title |

---

## 📦 Installation

```bash
git clone repository-url
cd persian-doz-arena

pip install -r requirements.txt

cp .env.example .env

python app.py
```

---

## ⚙ Environment Variables

```env
BOT_TOKEN=YOUR_BOT_TOKEN
ADMIN_IDS=123456789
DATABASE_PATH=data/bot.db
RUN_MODE=polling
```

---

## 🌟 Future Roadmap

- Tournament System
- Spectator Mode
- Battle Pass
- Premium Membership
- Clan System
- Advanced Analytics
- Theme Marketplace
- Seasonal Events

---

## ❤️ Design Goals

- Premium visual identity
- Competitive gaming atmosphere
- High engagement
- Fast navigation
- Clean architecture
- Easy maintenance
- Scalable growth

---

<div align="center">

### Persian Doz Arena

Built for modern Telegram gaming communities.

</div>
