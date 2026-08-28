# The pool curator

## Why this exists

Finding a clean Cloudflare edge address is the easy half. The hard half is that
it stops being clean while nobody is looking, and until something notices, the
pool keeps handing it out. That is what a config showing `-1ms` actually is: not
a bad scanner, a stale pool.

Before this agent, the pool only ever demoted. A missed live check bumped a
`fails` counter, selection filtered on `fails < MAX_FAILS`, and the row stayed in
the table forever. Three separate checks had to catch the same address before it
was even hidden, nothing was ever deleted, and every sweep made the table bigger
and its average quality worse.

## What the curator does, every cycle

1. **Picks the stale rows.** Anything nobody has confirmed for `CURATOR_RECHECK`
   seconds, oldest first, verified rows first because those are the ones users
   are holding right now.
2. **Speaks the client's sentence.** TCP, then TLS with a live panel hostname as
   the SNI, then `GET <ws path>` with `Upgrade: websocket`. Only `101 Switching
   Protocols` counts. `CURATOR_ROUNDS` attempts, `CURATOR_REQUIRED` of them have
   to answer, so a single blip cannot condemn a good address and a single lucky
   answer cannot save a bad one.
3. **Writes history, not a snapshot.** Every address carries `ok_count`,
   `bad_count`, a signed `streak`, the last time it actually passed (`ok_at`) and
   an EWMA `reliability`. Selection prefers *recently confirmed and historically
   reliable* over *fast*, because a 60ms address nobody has reached in an hour is
   not a 60ms address.
4. **Deletes, and does not merely hide.** Any one of these is enough:
   - `CURATOR_STRIKES` consecutive misses
   - `reliability` under `CURATOR_FLOOR` once there are `CURATOR_MIN_SAMPLES`
     samples behind it
   - nothing confirmed at all for `CURATOR_STALE` seconds
5. **Grows the pool back.** `POOL_TARGET` is a per-port floor measured in *fresh
   verified* rows. Any port under it is handed to the sweep immediately, and the
   trim that follows a sweep can never take a port below the target.
6. **Re-points the panels.** Every panel that was serving a deleted address is
   pushed to the front of the autopilot queue and refreshed on the spot, same
   script, same uuid, same subscription URL. A clean pool with dirty panels is,
   from the user's side, identical to doing nothing.
7. **Curates the relay chain too.** A relay that fails `RELAY_STRIKES` checks is
   deleted rather than demoted: a dead relay at the head of a failover chain
   makes every session pay its timeout, which users report as "it connects but
   nothing loads".

## The safety valve

If `CURATOR_ABORT` (default 85%) or more of a batch misses, the honest
conclusion is not that the internet died. It is that this box lost its route, or
the reference panel the probes verify against was deleted. So that cycle purges
**nothing**, the reference hostname is dropped so the next sweep elects a live
one, and the passes are still recorded, because good news is never dangerous.

This is why a bad night on the server cannot empty your pool.

## Knobs

| Key | Default | Meaning |
| --- | --- | --- |
| `CURATOR` | `true` | Master switch. Also togglable live from the admin options screen |
| `CURATOR_INTERVAL` | `300` | Seconds between cycles |
| `CURATOR_BATCH` | `160` | Addresses rechecked per cycle |
| `CURATOR_RECHECK` | `900` | An address is due once it is this old |
| `CURATOR_ROUNDS` / `CURATOR_REQUIRED` | `3` / `2` | Probes per address, and how many must answer |
| `CURATOR_STRIKES` | `3` | Consecutive misses before deletion |
| `CURATOR_FLOOR` | `0.4` | Reliability floor, 0 to 1 |
| `CURATOR_MIN_SAMPLES` | `5` | Samples required before the floor applies |
| `CURATOR_STALE` | `14400` | Delete anything unconfirmed for this long |
| `CURATOR_ABORT` | `0.85` | Miss ratio that cancels the purge for a cycle |
| `CURATOR_PUSH` | `true` | Re-point panels that served a deleted address |
| `CURATOR_PUSH_BATCH` | `6` | Panels refreshed immediately per cycle |
| `POOL_TARGET` | `40` | Fresh verified rows every port is kept at |
| `POOL_SIZE` | `720` | Whole-pool budget for the trim |
| `RELAY_STRIKES` | `3` | Failed checks before a relay is deleted |

## Watching it work

```bash
docker compose logs -f | grep curator
```

```
curator: checked 160, kept 141, deleted 19, pushed 4 panels, grew 63, dropped 2 relays
```

The admin panel shows the same numbers under **Scan engine**, with a
**Curate and grow the pool** button that runs a cycle on demand. Every cycle is
also written to the event log as `curator`, and a cancelled purge as
`curator_abort`.

---

## به فارسی

آی‌پی تمیز فاسدشدنی است: امروز جواب می‌دهد، فردا ممکن است فیلتر شود. قبل از این
ایجنت، آی‌پی مرده فقط «تنزل رتبه» می‌گرفت و برای همیشه در دیتابیس می‌ماند، پس
باز هم به کاربر داده می‌شد و کانفیگ `-1ms` می‌شد.

نگهبان استخر هر چند دقیقه آی‌پی‌های ذخیره‌شده را دقیقاً روی همان پورتی که در
کانفیگ کاربر است، با همان مسیر کلاینت (TLS با SNI پنل واقعی و بعد آپگرید
وب‌سوکت) تست می‌کند. فقط پاسخ `101` قبول است.

- آی‌پی سالم: نگه داشته می‌شود و سابقه‌اش بهتر می‌شود
- آی‌پی منفی: بعد از چند خطای پشت‌سرهم **کاملاً حذف می‌شود**، نه مخفی
- پورت کم‌عمق: بلافاصله دستور اسکن جدید صادر می‌شود تا حجم استخر بالا برود
- پنلی که آی‌پی حذف‌شده را سرو می‌کرد: همان لحظه با آی‌پی سالم جایگذاری می‌شود،
  بدون تغییر لینک اشتراک و بدون این که کاربر کاری کند
- رله‌های مرده هم به همین شکل حذف می‌شوند

و یک ضامن امنیتی: اگر تقریباً همه‌ی تست‌های یک دور شکست بخورد، یعنی مشکل از
سرور خودمان است، پس هیچ آی‌پی‌ای حذف نمی‌شود.
