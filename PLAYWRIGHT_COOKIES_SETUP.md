# YouTube Cookies Auto-Refresh Setup

## Рішення: Headless Browser з Playwright

YouTube блокує все окрім cookies з реального браузера. Playwright зберігає браузерну сесію яка:
- ✅ Залишається залогіненою між запусками
- ✅ Автоматично оновлює cookies
- ✅ Працює стабільно місяцями
- ✅ Не потребує постійних оновлень

## Крок 1: Перший логін (один раз)

### На локальній машині з GUI:

```bash
cd /mnt/laravel/youtube-audio-downloader

# Встановіть Playwright якщо ще немає
pip install playwright
playwright install chromium

# Запустіть інтерактивний логін
python3 cookie_refresher.py --login
```

Відкриється браузер:
1. Залогіньтесь у свій YouTube/Google акаунт
2. Дочекайтесь поки побачите свій аватар у правому верхньому куті
3. Натисніть Enter в терміналі

Результат:
```
✅ Saved 47 cookies
📁 Cookie file: /tmp/ytdl-cookies.txt
✅ You can now run automatic refresh
```

## Крок 2: Копіювання на сервер

```bash
# Playwright profile (зберігає логін)
scp -r /tmp/playwright-profile user@k8s-host:/var/www/

# Cookies file
scp /tmp/ytdl-cookies.txt user@k8s-host:/var/www/
```

## Крок 3: Deploy в Kubernetes

```bash
cd /mnt/laravel/k3s-cursor.style/ytld

# Apply CronJob для автоматичного оновлення
kubectl apply -f base/cookie-refresher-cronjob.yaml

# Перебілдіть image з Playwright
docker build -t wonchoe/ytdl-bot:latest /mnt/laravel/youtube-audio-downloader
docker push wonchoe/ytdl-bot:latest

# Apply оновлений deployment
kubectl apply -f base/dep.yaml
kubectl rollout restart deployment/ytdl-bot -n wonchoeyoutubebot
```

## Крок 4: Тестування

```bash
# Перевірте що cookies оновлюються
kubectl logs -f cronjob/youtube-cookie-refresher -n wonchoeyoutubebot
```

Повинні побачити:
```
🔄 Starting cookie refresh...
📱 Opening YouTube...
✅ Logged in, extracting cookies...
✅ Saved 47 cookies to /tmp/ytdl-cookies.txt
✅ Critical cookies present: __Secure-3PSID, __Secure-1PSID, SAPISID, SSID
```

## Як працює

1. **Playwright зберігає браузерну сесію** в `/tmp/playwright-profile`
   - Ця директорія містить всі дані браузера (логін, історію, cookies)
   - Монтується через hostPath щоб зберігатись між рестартами

2. **CronJob запускається кожні 4 години**
   - Відкриває headless Chrome з збереженим профілем
   - Перевіряє чи залогінений (шукає аватар)
   - Витягує свіжі cookies
   - Зберігає в Netscape format для yt-dlp

3. **Bot використовує завжди свіжі cookies**
   - Читає `/tmp/ytdl-cookies.txt` при кожному запиті
   - Cookies оновлюються автоматично cronjob'ом

## Переваги над іншими методами

| Метод | Час життя | Стабільність | Складність | Auto-refresh |
|-------|-----------|--------------|------------|--------------|
| **Playwright** | Місяці | ⭐⭐⭐⭐⭐ | Середня | ✅ Так |
| Manual cookies | 5-10 хвилин | ⭐ | Легко | ❌ Ні |
| OAuth | Deprecated | ❌ | - | - |

## Troubleshooting

### "Not logged in! Manual login required"

Браузерна сесія застаріла. Перелогіньтесь:

```bash
# На машині з GUI
python3 cookie_refresher.py --login

# Скопіюйте оновлений profile
scp -r /tmp/playwright-profile user@k8s-host:/var/www/
```

### CronJob fails

```bash
# Перевірте логи
kubectl logs job/youtube-cookie-refresher-XXXXX -n wonchoeyoutubebot

# Запустіть вручну для тестування
kubectl create job manual-refresh --from=cronjob/youtube-cookie-refresher -n wonchoeyoutubebot
```

### Cookies not updating

Перевірте що playwright-profile правильно змонтований:

```bash
kubectl exec -it deployment/ytdl-bot -n wonchoeyoutubebot -- ls -la /tmp/playwright-profile
```

## Моніторинг

Додайте алерт якщо cookies не оновлювались > 6 годин:

```bash
# Перевірка останньої модифікації
stat /var/www/ytdl-cookies.txt
```

## Підсумок

✅ **Один раз логін** → працює місяцями  
✅ **Автоматичне оновлення** кожні 4 години  
✅ **Найстабільніше** рішення для production  
✅ **Не потребує** постійного втручання  
