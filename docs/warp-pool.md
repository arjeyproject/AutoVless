# WARP endpoint pools

Two pools. Ten healthy endpoints each. One agent that keeps them that way.

```
                    WarpEP address space  (bot/warpep.py)
                    IPv4 anycast /24s  +  IPv6 anycast /64s
                    the WARP UDP port ladder, primary first
                                   |
                       per-prefix sampling (no clustering)
                                   |
   sweep  ──────────────────────────────────────────  one real handshake each
                                   |
   confirm  ────────────────────────────────────────  several spaced handshakes
              latency (median) · jitter · loss ratio
                                   |
   verdict  ────────────────────────────────────────  WarpEP health 0-100
              loss dominates, then latency, then jitter
                                   |
   deep check  ─────────────────────────────────────  real ICMP through a real
              (only with the warpep package installed)   tunnel, decrypted back
                                   |
                     ┌─────────────┴─────────────┐
                 IPv4 pool                   IPv6 pool
                 10 healthy                  10 healthy
                 sorted by ping              sorted by ping
                     │                            │
        "Other operators" button        "Irancell" button
```

## Why two pools

Irancell (MTN) shapes and drops IPv4 WARP hard while usually leaving its IPv6
path alone. Every other Iranian operator behaves the other way round. One mixed
pool cannot serve both: pressing a button has to hand you an endpoint of the
right *family*, not a lucky draw.

So the user flow asks exactly one question. **📶 Irancell → a healthy IPv6
endpoint. 🌐 Other operators → a healthy IPv4 endpoint.** Nothing is inferred
from the phone number or the interface language, because a wrong guess here is a
config that cannot connect and a user who blames the bot.

## What "healthy" means

Three things, and nothing softer:

1. **It answered.** A real Noise_IK WireGuard initiation, cryptographically
   verified, several times, spaced apart. WARP endpoints answer nothing else:
   there is no TCP socket to connect to and ICMP says nothing about a UDP port,
   so a completed handshake is the only honest reachability test there is.
   Spacing matters because Iranian DPI often lets the first handshake through and
   kills the session a second later.
2. **It scored.** WarpEP's 0-100 health formula, where loss dominates, latency
   comes second and jitter third. Below `WARP_HEALTH_FLOOR` it never enters a
   pool.
3. **It carried traffic.** With the `warpep` package installed, the best few rows
   get a full tunnel: handshake, transport keys, real ICMP echo sealed in and
   decrypted on the way back. An endpoint that handshakes and then swallows
   traffic is marked failed and **deleted**, because it is worse than dead: it
   looks alive to every cheap check there is.

The floor is enforced by `warpstore.upsert`, which is the only door into a pool.
That makes "healthy endpoints only" a property of the storage layer rather than a
promise made by whichever caller happens to be writing.

## The agent

`PoolAgent` in `bot/warppool.py` runs on its own, every `WARP_AGENT_INTERVAL`
seconds:

1. re-probe every endpoint in both pools
2. delete the dead and anything that fell under the floor
3. re-sort the survivors by ping
4. top up any pool that is below target

Nobody should have to press a button for the pools to be correct. The buttons in
the admin panel exist so a human can *see* the agent's work and force it.

## The two admin buttons

Admin panel → **🏊 استخر اندپوینت‌ها**

| Button | What it does |
| --- | --- |
| ♻️ تازه‌سازی استخر | Sweeps the address space for **new** endpoints, both families, in the background. Answers instantly and edits its own message when the sweep lands. |
| ♻️ تازه‌سازی IPv4 / IPv6 | The same, one family only. |
| 🩺 بررسی کامل اندپوینت‌ها | Re-pings **everything already stored**, deletes the dead, re-sorts by ping and prints a verdict: `✅ سالم` / `⚠️ ناقص` / `⛔️ خالی`. This is the button that answers "is our pool healthy". |
| 📋 فهرست استخر | Every endpoint in both pools, ping order, with a badge saying what was actually proven about it. |

Badges: 🟢 traffic proven · ✅ excellent · 🟡 good · 🟠 poor · ⚠️ answers but
carries nothing · 💀 dead.

## Settings

Everything has a working default. Nothing below is required.

```env
# ---- the two pools ----------------------------------------------------
WARP_POOL_TARGET=10        # healthy endpoints kept per family
WARP_POOL_SAMPLE=24        # addresses probed per prefix on a refresh
WARP_POOL_PORTS=3          # how many discovered ports a refresh sweeps
WARP_HEALTH_FLOOR=55       # minimum WarpEP health (0-100) to enter a pool
WARP_REFRESH_GAP=60        # seconds between two refreshes of one family

# ---- the deep tunnel check (needs the warpep package) ----------------
WARP_DEEP_VERIFY=1
WARP_DEEP_TOP=4            # how many of the best rows get the deep check
WARP_DEEP_ECHOES=2
WARP_DEEP_TIMEOUT=3.0

# ---- the agent --------------------------------------------------------
WARP_AGENT=1
WARP_AGENT_INTERVAL=300    # seconds between two agent passes
WARP_AGENT_AUDIT_EVERY=1   # agent passes between two full audits
```

Tighter pools on a small box: `WARP_POOL_SAMPLE=12`, `WARP_AGENT_INTERVAL=600`.
Stricter about quality: `WARP_HEALTH_FLOOR=70`. Turn the deep check off entirely
with `WARP_DEEP_VERIFY=0`.

---

# بروزرسانی سرور و اعمال تغییرات

## ۱) گرفتن تغییرات

```bash
cd /opt/autovless          # یا هر جایی که پروژه را نصب کرده‌اید
git fetch --all
git pull --ff-only
```

اگر روی شاخه‌ی این تغییرات کار می‌کنید:

```bash
git fetch origin feat/warp-endpoint-pools
git checkout feat/warp-endpoint-pools
```

## ۲) نصب اختیاری WarpEP (برای تست عبور ترافیک)

بدون این هم همه‌چیز کار می‌کند، چون نسخه‌ی داخلی فضای آدرس و فرمول سلامت WarpEP
در پروژه هست. با نصب آن، تست «عبور واقعی ترافیک از تونل» هم فعال می‌شود:

```bash
apt-get install -y git
pip install -r requirements-optional.txt
```

در حالت داکر، این را به `Dockerfile` اضافه کنید (بعد از نصب requirements):

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends git \
 && pip install --no-cache-dir -r requirements-optional.txt \
 && apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
```

صفحه‌ی «استخر» در پنل مدیریتی خودش می‌گوید کدام نسخه فعال است:
`warpep 2.x` یا `warpep (vendored)`.

## ۳) تنظیمات دلخواه در `.env`

```bash
nano .env      # مقادیر بخش Settings بالا را اضافه کنید (همه اختیاری‌اند)
```

## ۴) بالا آوردن

**داکر (روش پیشنهادی):**

```bash
docker compose up -d --build
docker compose logs -f --tail=80
```

**بدون داکر (systemd):**

```bash
pip install -r requirements.txt
systemctl restart autovless
journalctl -u autovless -f
```

## ۵) بررسی اینکه واقعاً کار می‌کند

۱. در لاگ‌ها این خط باید بیاید:

```
warp pool agent started (every 300s, 10 per family, floor 55, deep on)
```

۲. پیام «بات بالا آمد» برای ادمین‌ها باید وضعیت هر دو استخر را نشان دهد:

```
🏊 warp pools: IPv4 10/10 · IPv6 10/10 (agent on, source warpep ...)
```

۳. در ربات: پنل مدیریتی → 🏊 استخر اندپوینت‌ها → ♻️ تازه‌سازی استخر،
سپس 🩺 بررسی کامل اندپوینت‌ها. باید `✅ استخر سالم است` بگیرید.

۴. به‌عنوان کاربر: 🧬 وارپ → ساخت → 📶 ایرانسل.
باید یک فایل `.conf` با `Endpoint = [2606:4700:...]:2408` بگیرید، و با
🌐 سایر اپراتورها یک `Endpoint = 188.114.x.y:2408`.

## ۶) اگر استخر خالی ماند

نشانه‌ی این است که UDP وارپ از خود سرور بیرون نمی‌رود، نه اینکه اندپوینتی وجود
ندارد. به ترتیب:

```bash
docker compose logs --tail=200 | grep -i "warp ports reachable"
```

- اگر برای `v6` هیچ پورتی جواب نداده، سرور IPv6 ندارد. IPv6 را روی سرور فعال
  کنید (بدون آن استخر ایرانسل هیچ‌وقت پر نمی‌شود).
- اگر برای هیچ خانواده‌ای جواب نداده، `WARP_PORTS=2408,500,1701` را ست کنید و
  دوباره امتحان کنید.
- `WARP_HEALTH_FLOOR` را موقتاً روی `40` بگذارید تا ببینید چیزی هست یا نه.
