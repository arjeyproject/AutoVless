# راهنمای نصب AutoVless از صفر تا صد

این راهنما برای Ubuntu 22.04 یا 24.04 نوشته شده است. حداقل پیشنهادی: ۱ هسته CPU، یک گیگابایت RAM و ۱۰ گیگابایت فضای خالی. دامنه برای مینی‌اپ و زرین‌پال الزامی است و باید رکورد `A` آن به IP سرور اشاره کند.

## ۱) ساخت ربات و شناسه مدیر

در تلگرام به `@BotFather` بروید، `/newbot` را بزنید و مقدار `BOT_TOKEN` را بردارید. برای شناسه عددی خودتان به `@userinfobot` پیام بدهید و عدد را در `ADMIN_IDS` قرار دهید.

## ۲) نصب سریع

با SSH وارد سرور شوید و اجرا کنید:

```bash
sudo apt update && sudo apt install -y curl git ca-certificates
bash <(curl -fsSL https://raw.githubusercontent.com/arjeyproject/AutoVless/main/install.sh)
```

روش دستی:

```bash
git clone https://github.com/arjeyproject/AutoVless.git /opt/autovless
cd /opt/autovless
bash install.sh
```

در پرسش‌های نصب، توکن ربات، شناسه مدیر و دامنه را وارد کنید. اگر دامنه ندارید، `WEBAPP_URL` و `PUBLIC_URL` را بعداً در فایل `.env` تنظیم کنید. مقدار `SECRET_KEY` را طولانی و تصادفی بگذارید:

```bash
openssl rand -hex 32
```

## ۳) متغیرهای مهم `.env`

```env
BOT_TOKEN=توکن_ربات
ADMIN_IDS=123456789
SECRET_KEY=رشته_تصادفی_طولانی
WEBAPP_URL=https://bot.example.com
PUBLIC_URL=https://bot.example.com
API_PORT=8088
SS=true
```

`SS=true` برای فعال بودن Shadowsocks است. اگر نمی‌خواهید فعال باشد، آن را `false` کنید. هر کاربر پنل شخصی خود را روی Cloudflare می‌سازد، بنابراین ترافیک آن پنل از VPS شما عبور نمی‌کند.

## ۴) دامنه و HTTPS

در DNS یک رکورد `A` برای دامنه به IP سرور بسازید. سپس Caddy را نصب کنید:

```bash
sudo apt install -y caddy
sudo tee /etc/caddy/Caddyfile >/dev/null <<'CADDY'
bot.example.com {
    reverse_proxy 127.0.0.1:8088
}
CADDY
sudo systemctl reload caddy
```

به جای `bot.example.com` دامنه واقعی خودتان را بنویسید. Caddy گواهی HTTPS را خودکار می‌گیرد. قبل از تست، مطمئن شوید پورت‌های ۸۰ و ۴۴۳ در فایروال باز هستند:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## ۵) راه‌اندازی و بررسی

```bash
cd /opt/autovless
docker compose up -d --build
docker compose ps
docker compose logs -f
```

پس از روشن شدن، در ربات `/start` و سپس `/app` را امتحان کنید. در BotFather می‌توانید از `/newapp` یا تنظیم Menu Button استفاده کنید و آدرس `WEBAPP_URL` را بدهید.

## ۶) تنظیم پرداخت

از پنل مدیریت ربات، گزینه `💳 درگاه پرداخت ورود` را باز کنید. پرداخت اجباری، مبلغ تومان، مبلغ Stars، مدت اعتبار و درگاه را از همان‌جا تنظیم کنید. Telegram Stars به تنظیمات بیرونی نیاز ندارد. برای زرین‌پال، Merchant ID و دامنه HTTPS لازم است؛ ابتدا حالت Sandbox را فعال و با مبلغ آزمایشی تست کنید، بعد خاموشش کنید. آدرس callback را ربات خودش نشان می‌دهد و نباید دستی حدس زده شود.

## ۷) Cloudflare برای ساخت پنل

در Cloudflare یک API Token بسازید که دسترسی لازم برای ساخت و مدیریت Workers و زیردامنه مورد استفاده را داشته باشد. توکن را فقط داخل مینی‌اپ و برای حساب خود کاربر وارد کنید، نه در گروه یا چت عمومی.

## ۸) استفاده در آیفون

برای iOS، روش پیشنهادی فایل و QR مربوط به AmneziaWG است. اپ AmneziaWG را از App Store نصب کنید، سپس فایل یا QR بخش iOS را وارد کنید. فایل استاندارد WireGuard هم برای اپ رسمی ارائه می‌شود و لینک Hiddify با نویز برای شبکه‌هایی که WireGuard خام را فیلتر می‌کنند در دسترس است.

برای Shadowsocks از Hiddify، Shadowrocket یا NekoBox استفاده کنید. چون این اتصال با `v2ray-plugin` ساخته می‌شود، کلاینتی انتخاب کنید که WebSocket و v2ray-plugin را پشتیبانی کند.

## ۹) به‌روزرسانی، پشتیبان و عیب‌یابی

```bash
cd /opt/autovless
git pull
docker compose up -d --build
docker compose logs --tail=200 -f
```

داده‌های کاربران و تنظیمات در پوشه `data/` است. قبل از به‌روزرسانی نسخه پشتیبان بگیرید:

```bash
tar -czf autovless-data-$(date +%F).tar.gz data .env
```

اگر کانتینر مدام restart می‌شود، مجوز داده را اصلاح کنید:

```bash
sudo chown -R 10001:10001 /opt/autovless/data
```

اگر مینی‌اپ باز نمی‌شود، HTTPS، مقدار `WEBAPP_URL` و دسترسی پورت ۸۰ و ۴۴۳ را بررسی کنید. اگر API پاسخ نمی‌دهد، لاگ‌ها و پورت ۸۰۸۸ را بررسی کنید. برای تست محلی روی خود سرور:

```bash
curl -I http://127.0.0.1:8088/health
```

پنل‌های قدیمی با اجرای autopilot یا rebuild binding جدید Shadowsocks را می‌گیرند؛ اگر نگرفتند یک‌بار `docker compose up -d --build` و بازسازی پنل را اجرا کنید.
