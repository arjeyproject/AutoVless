# معماری مقاوم برای شبکه‌های ناپایدار

این تغییرات «ضدسانسور تضمینی» نیستند. در قطع سراسری، whitelist، یا مسدودسازی فعال، هیچ پروتکل واحدی قابل اتکا نیست. هدف این شاخه کاهش تک‌نقطه‌ی شکست و امکان بازگشت سریع است.

## اجزا

1. مسیر اصلی: VLESS + Reality روی TCP/443 با کلید و شناسه‌ی تصادفی.
2. مسیر پشتیبان: VLESS + XHTTP/TLS پشت دامنه‌ای که مالک آن هستید. از دامنه‌ی سرویس دیگران برای پوشش استفاده نکنید.
3. مسیر WARP: فقط برای کاربردهای UDP و تماس، نه به‌عنوان تنها مسیر. وضعیت WARP را دوره‌ای بررسی کنید.
4. health-check: چند URL واقعی HTTPS را از چند شبکه بررسی کنید و فقط مسیر سالم را در اشتراک منتشر کنید.
5. توزیع: subscription را با توکن جدا برای هر کاربر صادر کنید و توکن‌ها را در Git، issue، log یا پیام عمومی ذخیره نکنید.

## نصب

```bash
# روی Ubuntu/Debian و با دسترسی root
cd /opt
sudo git clone https://github.com/arjeyproject/AutoVLESS.git
cd AutoVLESS
sudo git checkout iran-resilience
sudo bash scripts/harden-host.sh
```

سپس 3x-ui/Xray را طبق پنل خود نصب کنید و مقادیر فایل نمونه را فقط در پنل یا فایل محلی تنظیم کنید:

```bash
install -m 600 configs/xray-multi-path.json.example /root/xray-multi-path.json
sudoedit /root/xray-multi-path.json
```

برای بررسی مسیرها:

```bash
ENDPOINTS='https://edge-a.example/health https://edge-b.example/health' \
  bash scripts/check-paths.sh
```

## نکات عملی

- Reality و XHTTP را با یک کلید، path یا نام‌گذاری مشترک منتشر نکنید.
- از `TCP Brutal` و تنظیمات غیرعادی congestion control استفاده نکنید؛ الگوی قابل تشخیص می‌سازد.
- IPv6 را فقط وقتی فعال کنید که واقعاً از بیرون و داخل کشور تست شده باشد.
- پنل 3x-ui را روی اینترنت عمومی باز نگذارید؛ دسترسی مدیریتی را با firewall یا VPN مدیریتی محدود کنید.
- قبل از انتشار عمومی، هر مسیر را از حداقل دو ISP و در ساعات مختلف تست کنید.
- برای WARP/AmneziaWG endpointهای متعدد داشته باشید، اما secrets و license را در Git قرار ندهید.

## rollback

هر تغییر شبکه را جداگانه deploy کنید. اگر health-checkها شکست خوردند، مسیر جدید را از subscription حذف کنید و به آخرین مسیر سالم برگردید. هیچ اسکریپت این مخزن نباید با `curl | bash` از URL ناشناس اجرا شود.
