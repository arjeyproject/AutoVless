# استقرار روی Cloudflare Pages (به‌جای Worker)

از این نسخه، پیش‌فرض ربات پنل‌ها را به‌صورت **پروژه Cloudflare Pages** می‌سازد، نه اسکریپت Worker. همان کدِ ورکر، همان پروتکل‌ها، همان اشتراک — فقط روی زیرساخت Pages و با `*.pages.dev` به‌جای `*.workers.dev`.

## چرا Pages؟

* همان موتور V8 و همان `export default fetch` — کد ورکر بدون هیچ تغییری به‌صورت `_worker.js` (حالت Advanced Mode) اجرا می‌شود.
* دامنه اختصاصی با API خودِ Pages وصل می‌شود و کلادفلر DNS و گواهی TLS را خودش می‌سازد؛ بدون رکورد دستی.
* سهمیه رایگان و سطوح سوءاستفاده روی اکانت خود کاربر می‌ماند، دقیقاً مثل Worker.
* مشکل «workers.dev در ایران رزولوو نمی‌شود» با همان استراتژی قبلی حل می‌شود: اگر اکانت کاربر دامنه فعال داشته باشد، همان دامنه SNI و Host کانفیگ‌ها می‌شود و `pages.dev` فقط fallback است.

## توکن کلادفلر

دسترسی‌های لازم (دکمه «ساخت توکن» ربات همه را از پیش انتخاب می‌کند):

| دسترسی | سطح | برای |
|---|---|---|
| **Cloudflare Pages: Edit** | Account | ساخت پروژه، دیپلوی، دامنه اختصاصی |
| Workers Scripts: Edit | Account | مسیر fallback و حذف پنل‌های قدیمی Worker |
| Account Settings: Read | Account | یافتن account_id |
| Zone: Read | Zone | انتخاب دامنه اختصاصی |
| Workers Routes: Edit | Zone | اتصال دامنه در حالت Worker |
| DNS: Edit | Zone | حالت Worker |

اگر توکن فقط دسترسی Worker داشته باشد و Pages نداشته باشد، پیام خطا دقیقاً می‌گوید کدام دسترسی کم است.

## مراحل دیپلوی (چه چیزی واقعاً اتفاق می‌افتد)

1. `POST /accounts/{id}/pages/projects` — ساخت پروژه با `production_branch: main` (اگر موجود باشد، استفاده مجدد).
2. `PATCH /accounts/{id}/pages/projects/{name}` — ثبت متغیرهای محیطی (UUID، ENDPOINTS، رله‌ها و…) روی `deployment_configs.production.env_vars`. هر دیپلوی این متغیرها را در لحظه ساخت snap می‌کند.
3. `GET /accounts/{id}/pages/projects/{name}/upload-token` — توکن آپلود (۵ دقیقه اعتبار).
4. `POST /pages/assets/upload` — آپلود `_worker.js` به‌صورت base64؛ کلیدِ هر فایل `blake3(base64(محتوا) + پسوند)` است (دقیقاً الگوریتم wrangler — پیاده‌سازی خالص پایتون در `bot/blake3pure.py` و اگر پکیج `blake3` نصب باشد همان استفاده می‌شود).
5. `POST /pages/assets/upsert-hashes` — قطعی‌سازی هش‌ها.
6. `POST /accounts/{id}/pages/projects/{name}/deployments` — ساخت دیپلوی با manifest `{"​/_worker.js": hash}` و branch `main`.

پس از آن میزبان `<project>.pages.dev` آماده است؛ ربات `/uuid/health` را تا جواب OK چک می‌کند و بعد دامنه اختصاصی را وصل می‌کند.

## تنظیم‌ها (`.env`)

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `DEPLOY_TARGET` | `pages` | `workers` رفتار قبلی |
| `HTTPUPGRADE` | `true` | ترنسپورت HTTPUpgrade در اشتراک‌ها |
| `XHTTP` | `true` | ترنسپورت XHTTP (stream-one) در اشتراک‌ها |
| `PAGES_AUTOPILOT_MAX_AGE` | `604800` | سقف عمر آدرس‌های پنل Pages قبل از دیپلوی مجدد |

## نکته سهمیه دیپلوی

پلن رایگان Pages تعداد دیپلوی ماهانه محدود دارد. به همین دلیل autopilot برای پنل‌های Pages کِدِ جداگانه دارد (پیش‌فرض هفتگی). در فاصله بین دیپلوی‌ها، اشتراک همچنان **خودش را تازه می‌کند**: ورکر در هر fetch ساب، منابع IP تمیز را زنده می‌کشد و بهترین آدرس‌ها را سوار می‌کند؛ کاربر فقط Update کلاینت را می‌زند.

## تست بدون اکانت

```
python3 scripts/verify_pages.py      # هش blake3، manifest، لینک‌ها، تنوع رنج
node scripts/test-worker-xhttp.mjs   # تونل XHTTP stream-one + مسیرهای اشتراک ورکر
```
