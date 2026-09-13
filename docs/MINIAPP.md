# مینی‌اپ AutoVless — آموزش صفر تا صد

مینی‌اپ یک صفحه‌ی وب است که داخل تلگرام باز می‌شود و با API خود ربات حرف می‌زند.
دو چیز لازم دارد و هر دو غیرقابل‌مذاکره‌اند:

1. **HTTPS.** تلگرام صفحه‌ی `http://` را باز نمی‌کند.
2. **همان دامنه برای صفحه و API.** صفحه‌ی HTTPS نمی‌تواند به API روی `http://IP:8088`
   درخواست بزند (مرورگر جلوی mixed content را می‌گیرد). پس هر دو را از یک دامنه سرو می‌کنیم.

خود ربات هم فایل‌های `webapp/` را سرو می‌کند و هم `/api` را، پس فقط یک TLS جلویش لازم است.

---

## گام ۰ — چیزهایی که باید داشته باشی

* ربات AutoVless در حال اجرا (داکر یا systemd)
* یک دامنه یا ساب‌دامنه، مثلاً `app.example.com`
* رکورد `A` آن ساب‌دامنه روی آی‌پی سرور
* پورت‌های ۸۰ و ۴۴۳ باز

اگر دامنه نداری، بخش «بدون دامنه» را در پایین بخوان.

## گام ۱ — API را روشن کن

در `.env` کنار بقیه‌ی تنطیمات:

```env
API_ENABLED=1
API_HOST=0.0.0.0
API_PORT=8088
WEBAPP_URL=https://app.example.com
```

بعد ربات را ری‌استارت کن:

```bash
cd /opt/autovless
docker compose up -d
docker compose logs --tail=30 | grep "mini app"
# mini app api listening on 0.0.0.0:8088 (static: /app/webapp)
```

تست محلی:

```bash
curl -s http://127.0.0.1:8088/api/health
# {"ok": true, "brand": "AutoVless", "webapp": true}
```

> کامپوز با `network_mode: host` بالا می‌آید، پس پورت خودبه‌خود روی سرور شنیده می‌شود و
> `ports:` لازم نیست.

## گام ۲ — TLS با Caddy (دو خط، گواهی خودکار)

```bash
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update && apt-get install -y caddy
```

`/etc/caddy/Caddyfile` را دقیقاً این کن:

```caddyfile
app.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:8088
}
```

```bash
systemctl restart caddy
curl -s https://app.example.com/api/health
```

گواهی Let's Encrypt خودکار گرفته و تمدید می‌شود.

<details>
<summary>اگر nginx را ترجیح می‌دهی</summary>

```nginx
server {
    listen 443 ssl http2;
    server_name app.example.com;

    ssl_certificate     /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8088;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```
گواهی را با `certbot --nginx -d app.example.com` بگیر.
</details>

## گام ۳ — دکمه‌ی مینی‌اپ در BotFather

دو راه دارد و بهتر است هر دو را انجام بدهی:

**الف) دکمه‌ی منوی ربات (کنار جعبه‌ی تایپ)**

1. به [@BotFather](https://t.me/BotFather) برو → `/mybots` → ربات خودت
2. `Bot Settings` → `Menu Button` → `Configure menu button`
3. آدرس: `https://app.example.com` — عنوان: `🚀 AutoVless`

**ب) داخل خود ربات**

دستور `/app` یا دکمه‌ی «🚀 مینی‌اپ» در منوی اصلی، مینی‌اپ را با payload کاربر باز می‌کند.
این مسیر فقط وقتی نشان داده می‌شود که `WEBAPP_URL` پر باشد.

## گام ۴ — تست

از داخل تلگرام باز کن (نه مرورگر). باید ببینی:

* هدر با نام برند، دکمه‌ی زبان و دکمه‌ی پوسته
* آمار زنده‌ی استخر آی‌پی
* نویگیشن پایین با قطره‌ی متحرک: خانه / پنل / وارپ / رایگان / بیشتر
* اگر ادمین هستی، کارت «🛠 پنل مدیریت» در تب «بیشتر»

اگر پیام «این صفحه را از داخل تلگرام باز کن» آمد یعنی `initData` نیست — یعنی صفحه را
در مرورگر باز کرده‌ای. طبیعی است.

## چه کارهایی در مینی‌اپ انجام می‌شود

| تب | امکانات |
|---|---|
| خانه | آمار زنده، وضعیت مسیر AI، رله‌ی پین‌شده، لینک‌های پشتیبانی |
| پنل | ساخت پنل با توکن (با نمایش پنج مرحله)، بازسازی، حذف، اعمال آی‌پی تازه، پینگ زنده، QR، لینک اشتراک VLESS/Trojan/هردو/Clash/sing-box، فایل فرگمنت، کپی تک‌تک کانفیگ‌ها |
| وارپ | انتخاب دستگاه (iOS/Android/Windows/macOS) و شبکه (IPv4 / ایرانسل IPv6)، ساخت اکانت واقعی وارپ، دانلود `.conf`، لینک `wireguard://` |
| رایگان | VLESS / Trojan / هر دو روی سرور مشترک، با تست هندشیک واقعی و لینک اشتراک خودتازه‌شو |
| بیشتر | دعوت دوستان با نوار پیشرفت، زبان، دارک/لایت/خودکار، پنل ادمین |

پنل ادمین در مینی‌اپ: روشن/خاموش کردن همه‌ی گزینه‌ها (سرویس، ساخت، عضویت اجباری، وارپ،
پشتیبانی، اتوپایلوت، کیوریتور، قفل دعوت، بخش رایگان، خود مینی‌اپ)، تعیین تعداد دعوت،
افزودن/حذف سرور رایگان، بررسی سلامت، مکان‌یابی رله‌ها.

## امنیت

هیچ توکن یا رمزی در صفحه نیست. تلگرام هر اجرای مینی‌اپ را با HMAC مشتق از توکن ربات
امضا می‌کند؛ صفحه همان `initData` را در هدر `X-Init-Data` می‌فرستد و سرور امضا را چک
می‌کند. آیدی کاربر از داخل داده‌ی **امضاشده** خوانده می‌شود، نه از چیزی که کلاینت گفته.
امضاهای قدیمی‌تر از `INIT_DATA_TTL` رد می‌شوند و مسیرهای ادمین دوباره جداگانه چک می‌شوند.

## بدون دامنه: Cloudflare Tunnel

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared
cloudflared tunnel --url http://localhost:8088
```

یک آدرس `https://<random>.trycloudflare.com` می‌دهد؛ همان را در `WEBAPP_URL` و BotFather
بگذار. آدرس موقتی است، برای تست خوب است نه برای همیشه.

## میزبانی روی GitHub Pages (اختیاری)

اگر می‌خواهی فایل‌های استاتیک روی Pages باشند و فقط API روی سرور:

1. در ریپو: Settings → Pages → Branch `main` → پوشه‌ی `/webapp`
2. API باید HTTPS باشد (گام ۲ را انجام بده)
3. آدرس مینی‌اپ را با پارامتر API بده:
   `https://<user>.github.io/AutoVless/?api=https://api.example.com`

CORS از سمت API باز است. با این حال حالت «همه از یک دامنه» ساده‌تر و سریع‌تر است.

## عیب‌یابی

| نشانه | علت | درمان |
|---|---|---|
| صفحه سفید در تلگرام | `WEBAPP_URL` روی `http` است | HTTPS اجباری است |
| `unauthorised` | صفحه بیرون تلگرام باز شده یا ساعت سرور خیلی جلو/عقب است | `timedatectl set-ntp true` |
| آمار می‌آید ولی دکمه‌ها کار نمی‌کنند | صفحه از دامنه‌ای غیر از API لود شده | `?api=` را بده یا هر دو را یک دامنه کن |
| `mini app api` در لاگ نیست | `API_ENABLED=0` یا پورت اشغال است | مقدار را ۱ کن، پورت را عوض کن |
| دکمه‌ی مینی‌اپ در ربات نیست | `WEBAPP_URL` خالی است | پرش کن و ری‌استارت |
| QR نمی‌آید | `qrcode` نصب نیست | `pip install -r requirements.txt` |

---

# English quick start

```env
API_ENABLED=1
API_PORT=8088
WEBAPP_URL=https://app.example.com
```

```caddyfile
app.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:8088
}
```

Restart the bot, restart Caddy, then set the same URL as the Menu Button in
BotFather. The bot serves both the static app and `/api` from one origin, which is
what keeps a Telegram mini app (HTTPS only) able to call its own backend. Auth is
Telegram's signed `initData`, verified on every request; there is no token in the
page. `/app` inside the bot opens the same app.
