# Multi-Platform Media Downloader Bot

Telegram бот для завантаження медіа з YouTube, Instagram, Facebook та TikTok.

## Підтримувані платформи

✅ **YouTube** - audio (MP3 192kbps) + video (360p/480p/720p)  
✅ **Instagram** - пости, reels, IGTV, фото, карусель з фото  
✅ **Facebook** - відеопости та Watch  
✅ **TikTok** - відео (включно з короткими посиланнями)

## Особливості

- 🎯 Автоматичне визначення платформи
- 🎬 Вибір якості для YouTube (360p/480p/720p)
- 📦 Підтримка каруселів Instagram
- 📤 Custom Telegram Bot API (підтримка файлів до 2GB)
- 🍪 Автоматичне оновлення cookies кожні 4 години
- 🧹 Автоматичне очищення файлів після надсилання
- ⏱️ Progress bar з ETA
- 🔒 Single instance lock

## Cookie Management

Бот використовує єдиний файл cookies для всіх платформ.  
**📖 Детальні інструкції: [COOKIE_MANAGEMENT.md](COOKIE_MANAGEMENT.md)**

### Швидка настройка cookies

Перший раз (на локальному сервері з GUI):
```bash
cd /mnt/laravel/youtube-audio-downloader
source venv/bin/activate
python3 cookie_refresher.py --login
```

Відкриється браузер - залогінься на YouTube, Instagram, Facebook.  
Cookies автоматично збережуться та будуть оновлюватись кожні 4 години через Kubernetes CronJob.

## Deployment

### Kubernetes (Production)

```bash
# Build та push Docker image
cd /mnt/laravel/youtube-audio-downloader
docker build -t wonchoe/ytdl-bot:latest .
docker push wonchoe/ytdl-bot:latest

# Deploy (файли в wonchoeyt repo)
kubectl apply -f k8s/

# Restart deployment
kubectl rollout restart deployment/ytdl-bot -n wonchoeyoutubebot

# Перевірка
kubectl get pods -n wonchoeyoutubebot
kubectl logs -n wonchoeyoutubebot deployment/ytdl-bot --tail=50
```

### Docker Compose (Local)

```bash
docker-compose up -d
docker-compose logs -f
```

## Структура проекту

```
/mnt/laravel/youtube-audio-downloader/
├── app.py                    # Main Telegram bot
├── cookie_refresher.py       # Cookie management (login + auto-refresh)
├── entrypoint.sh            # Docker entrypoint
├── Dockerfile               # Container definition
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (TELEGRAM_BOT_TOKEN)
├── downloaders/             # Platform-specific downloaders
│   ├── youtube.py          # YouTube (yt-dlp with cookies)
│   ├── instagram.py        # Instagram (yt-dlp + instaloader + gallery-dl)
│   ├── facebook.py         # Facebook (yt-dlp with cookies)
│   └── tiktok.py           # TikTok (yt-dlp)
├── utils/                   # Helpers
│   ├── progress.py         # Progress bar
│   └── telegram_api.py     # Custom Telegram Bot API client
├── COOKIE_MANAGEMENT.md     # Cookie setup guide
└── README.md               # This file
```

## Troubleshooting

### YouTube: "Sign in to confirm you're not a bot"
→ Див. [COOKIE_MANAGEMENT.md](COOKIE_MANAGEMENT.md)

### Instagram: "401 Unauthorized"
→ Запусти `python3 cookie_refresher.py --login` та залогінься на Instagram

### Facebook downloads не працюють
→ Перевір cookies: `cat /var/www/ytdl-cookies.txt | grep facebook`

### CronJob не оновлює cookies
```bash
kubectl logs -n wonchoeyoutubebot -l job-name=cookie-refresher --tail=50
```

## Environment Variables

- `TELEGRAM_BOT_TOKEN` - Telegram Bot API token (required)
- Custom Telegram Bot API: `https://tgbot.agro-post.com` (2GB file support)

## License

MIT
- Збільшені timeouts до 120 секунд

## Структура проекту

```
youtube-audio-downloader/
├── app.py                      # Основний бот
├── downloaders/
│   ├── __init__.py
│   ├── base.py                # Базовий клас
│   ├── youtube.py             # YouTube downloader
│   ├── instagram.py           # Instagram downloader
│   ├── facebook.py            # Facebook downloader
│   └── tiktok.py              # TikTok downloader
├── utils/
│   ├── cleanup.py             # Автоочищення
│   └── upload.py              # Upload на gofile.io
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Ліцензія

MIT
