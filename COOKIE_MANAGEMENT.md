# Cookie Management Guide

## Огляд системи

Бот використовує єдиний файл куків `/var/www/ytdl-cookies.txt` для всіх платформ:
- YouTube/Google
- Facebook
- Instagram

Куки автоматично оновлюються кожні 4 години через Kubernetes CronJob.

## Перший запуск (Initial Setup)

### На локальному сервері з GUI:

1. Перейди в директорію проекту:
```bash
cd /mnt/laravel/youtube-audio-downloader
```

2. Активуй venv та запусти інтерактивний логін:
```bash
source venv/bin/activate
python3 cookie_refresher.py --login
```

3. Відкриється браузер Chromium з трьома сайтами:
   - YouTube → Залогінься через Google акаунт
   - Facebook → Залогінься (якщо потрібно)
   - Instagram → **ОБОВ'ЯЗКОВО залогінься**

4. Після логіну на всіх сайтах натисни **Enter** в терміналі

5. Перевір що куки збереглися:
```bash
python3 cookie_refresher.py
# Має показати:
# YouTube cookies: ~40+
# Facebook cookies: ~9+
# Instagram cookies: ~8+
```

6. Перевір файл куків:
```bash
cat /var/www/ytdl-cookies.txt | grep -E "instagram|facebook|youtube" | wc -l
# Має бути 50+ куків
```

## Відправка куків на production сервер

### Локально (після логіну):

1. Створи архів з куками та Playwright профілем:
```bash
cd ~
tar -czf ytdl-cookies-backup.tar.gz -C /var/www ytdl-cookies.txt playwright-profile
ls -lh ytdl-cookies-backup.tar.gz  # ~70-100MB
```

2. Завантаж на S3:
```bash
aws s3 cp ytdl-cookies-backup.tar.gz s3://rental-project/
```

### На production сервері (K8s node):

1. Завантаж архів з S3:
```bash
aws s3 cp s3://rental-project/ytdl-cookies-backup.tar.gz /tmp/
```

2. Розпакуй в `/var/www`:
```bash
sudo tar -xzf /tmp/ytdl-cookies-backup.tar.gz -C /var/www
```

3. Перевір файли:
```bash
ls -la /var/www/ytdl-cookies.txt /var/www/playwright-profile/
cat /var/www/ytdl-cookies.txt | grep instagram | wc -l  # Має бути 8+
```

4. Restart pod для підхоплення нових куків:
```bash
kubectl rollout restart deployment/ytdl-bot -n wonchoeyoutubebot
```

## Автоматичне оновлення (CronJob)

CronJob `cookie-refresher` запускається **кожні 4 години**:
```
Schedule: 0 */4 * * *
```

Перевірка статусу:
```bash
# Подивитись останні запуски
kubectl get cronjobs -n wonchoeyoutubebot
kubectl get jobs -n wonchoeyoutubebot

# Логи останнього job
kubectl logs -n wonchoeyoutubebot job/cookie-refresher-<timestamp> --tail=50

# Має показати:
# ✅ Saved 59 cookies to /var/www/ytdl-cookies.txt
# 📊 YouTube cookies: 42
# 📊 Facebook cookies: 9
# 📊 Instagram cookies: 8
```

## Troubleshooting

### Проблема: Instagram повертає 401 Unauthorized

**Причина**: Куки Instagram застаріли або не збереглися

**Рішення**:
1. Запусти `python3 cookie_refresher.py --login` локально
2. **ОБОВ'ЯЗКОВО залогінься на Instagram** в браузері
3. Натисни Enter після логіну
4. Перевір куки: `cat /var/www/ytdl-cookies.txt | grep instagram`
5. Якщо куків немає - повтори крок 1-4
6. Відправ на production (див. розділ вище)

### Проблема: YouTube повертає "Sign in to confirm you're not a bot"

**Причина**: Куки YouTube/Google застаріли

**Рішення**:
1. Перевір CronJob логи - чи оновлюються куки?
2. Якщо ні - перезапусти локальний логін (див. вище)
3. Перевір що є критичні куки:
```bash
cat /var/www/ytdl-cookies.txt | grep -E "(SAPISID|SSID|__Secure-1PSID|__Secure-3PSID)"
```
4. Має бути мінімум 4 критичні куки

### Проблема: Facebook downloads не працюють

**Причина**: Куки Facebook застаріли

**Рішення**: Такий же як для Instagram - перелогін через `--login`

### Проблема: Permission denied при створенні куків

**На локальному сервері**:
```bash
sudo mkdir -p /var/www/playwright-profile
sudo chown -R $(whoami):$(whoami) /var/www/playwright-profile
sudo touch /var/www/ytdl-cookies.txt
sudo chown $(whoami):$(whoami) /var/www/ytdl-cookies.txt
```

**На production (K8s node)**:
```bash
sudo mkdir -p /var/www/playwright-profile
sudo chown -R ubuntu:www-data /var/www/playwright-profile
sudo chown ubuntu:www-data /var/www/ytdl-cookies.txt
```

### Проблема: CronJob не оновлює куки

Перевір:
```bash
# Pod статус
kubectl get pods -n wonchoeyoutubebot | grep cookie-refresher

# Логи
kubectl logs -n wonchoeyoutubebot -l job-name=cookie-refresher-<latest> --tail=100

# Перевір що mountPath правильний
kubectl describe cronjob/cookie-refresher -n wonchoeyoutubebot | grep -A5 "Mounts:"
# Має бути:
#   /var/www/ytdl-cookies.txt
#   /var/www/playwright-profile
```

### Проблема: Браузер не відкривається при `--login`

**Причина**: Немає GUI або Playwright не встановлений

**Рішення**:
```bash
# Встанови Playwright
pip install playwright==1.40.0
playwright install chromium

# Встанови системні залежності
sudo apt-get install -y libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libwayland-client0
```

## Архітектура системи

```
┌─────────────────────────────────────────┐
│  Локальний сервер (GUI)                 │
│  ┌─────────────────────────────────┐    │
│  │ cookie_refresher.py --login     │    │
│  │ → Chromium headless             │    │
│  │ → Manual login (YouTube/FB/IG)  │    │
│  │ → Save to playwright-profile/   │    │
│  └─────────────────────────────────┘    │
│           ↓                              │
│  /var/www/ytdl-cookies.txt (59 cookies) │
│  /var/www/playwright-profile/ (~96MB)   │
└─────────────────────────────────────────┘
           ↓ tar + S3
┌─────────────────────────────────────────┐
│  S3: rental-project/                    │
│  ytdl-cookies-backup.tar.gz             │
└─────────────────────────────────────────┘
           ↓ kubectl cp / tar extract
┌─────────────────────────────────────────┐
│  Production K8s Node                    │
│  /var/www/ytdl-cookies.txt              │
│  /var/www/playwright-profile/           │
│           ↑                              │
│  ┌───────┴────────────────────────┐     │
│  │  CronJob: cookie-refresher     │     │
│  │  Schedule: 0 */4 * * *         │     │
│  │  → Playwright headless         │     │
│  │  → Visit YouTube/FB/IG         │     │
│  │  → Extract cookies             │     │
│  │  → Update ytdl-cookies.txt     │     │
│  └────────────────────────────────┘     │
│           ↓ hostPath mount               │
│  ┌────────────────────────────────┐     │
│  │  Pod: ytdl-bot                 │     │
│  │  → Reads /var/www/ytdl-cookies │     │
│  │  → yt-dlp uses cookies         │     │
│  │  → Downloads work ✅           │     │
│  └────────────────────────────────┘     │
└─────────────────────────────────────────┘
```

## Важливі файли

- `/var/www/ytdl-cookies.txt` - Netscape format cookies для всіх платформ
- `/var/www/playwright-profile/` - Persistent browser profile з сесіями
- `cookie_refresher.py` - Скрипт для логіну та оновлення куків
- `k8s/cookie-refresher-cronjob.yaml` - CronJob для автоматичного оновлення
- `k8s/dep.yaml` - Deployment з hostPath mount

## Команди швидкого доступу

```bash
# Локально: Повний цикл оновлення куків
cd /mnt/laravel/youtube-audio-downloader
source venv/bin/activate
python3 cookie_refresher.py --login
python3 cookie_refresher.py  # Перевірка
cd ~ && tar -czf ytdl-cookies-backup.tar.gz -C /var/www ytdl-cookies.txt playwright-profile
aws s3 cp ytdl-cookies-backup.tar.gz s3://rental-project/

# Production: Завантаження та застосування
aws s3 cp s3://rental-project/ytdl-cookies-backup.tar.gz /tmp/
sudo tar -xzf /tmp/ytdl-cookies-backup.tar.gz -C /var/www
kubectl rollout restart deployment/ytdl-bot -n wonchoeyoutubebot

# Перевірка що працює
kubectl logs -n wonchoeyoutubebot deployment/ytdl-bot --tail=50 | grep -E "(Instagram|Facebook|YouTube)"
```

## Lifecycle куків

- **YouTube/Google**: ~2-3 місяці (при регулярному refresh)
- **Instagram**: ~7-14 днів (вимагає частіше оновлення)
- **Facebook**: ~30 днів

**CronJob schedule (кожні 4 години)** забезпечує актуальність куків для всіх платформ.
