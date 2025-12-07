# 🗺️ Cookies Path Mapping

## Нова структура шляхів

### Host Server (K3s Node)
```
/var/www/ytdl-cookies.txt
```
- Файл на сервері з cookies в будь-якому форматі
- Оновлюється вручну через `scp` або редагування

### Kubernetes Volume Mount
```yaml
volumeMounts:
  - name: cookies-file
    mountPath: /app/ytdl-cookies.txt
    readOnly: false

volumes:
  - name: cookies-file
    hostPath:
      path: /var/www/ytdl-cookies.txt
      type: FileOrCreate
```
- K8s монтує `/var/www/ytdl-cookies.txt` → `/app/ytdl-cookies.txt`

### Container Startup (entrypoint.sh)
```bash
# 1. Читає /app/ytdl-cookies.txt (hostPath mount)
# 2. Конвертує формат (пробіли → табуляція)
# 3. Записує в /tmp/ytdl-cookies.txt
```

### Python Downloaders
Всі downloaders читають з:
```python
cookies_path = "/tmp/ytdl-cookies.txt"
```

**Файли:**
- `downloaders/youtube.py` - line 92
- `downloaders/instagram.py` - lines 98, 197
- `downloaders/facebook.py` - line 14
- `downloaders/tiktok.py` - не використовує cookies

---

## Workflow оновлення cookies

### 1. Експорт cookies з браузера
```bash
# На вашій машині
yt-dlp --cookies-from-browser chrome --cookies youtube_cookies.txt https://www.youtube.com
```

### 2. Завантаження на сервер
```bash
scp youtube_cookies.txt your-server:/var/www/ytdl-cookies.txt
```

### 3. Перевірка монтування
```bash
# SSH на K3s node
cat /var/www/ytdl-cookies.txt | tail -5
```

Перевірте чи є специфічний тестовий рядок (наприклад `.facebook1.com`)

### 4. Рестарт pod
```bash
kubectl rollout restart deployment/ytdl-bot -n wonchoeyoutubebot
```

### 5. Перевірка логів
```bash
kubectl logs -f deployment/ytdl-bot -n wonchoeyoutubebot
```

Шукайте:
```
📋 Found cookies at /app/ytdl-cookies.txt
📦 Cookie file size: XXXX bytes
✅ Fixed XX cookies
📊 Final cookies status: XX cookies, XXXX bytes
```

---

## Troubleshooting

### Cookies не монтуються
**Симптом:** Pod показує `⚠️ Warning: /app/ytdl-cookies.txt not found`

**Рішення:**
```bash
# 1. Перевірте чи існує файл на host
ls -la /var/www/ytdl-cookies.txt

# 2. Перевірте права доступу
chmod 644 /var/www/ytdl-cookies.txt

# 3. Перевірте deployment
kubectl describe pod -n wonchoeyoutubebot | grep -A 5 Mounts

# 4. Recreate pod
kubectl delete pod -n wonchoeyoutubebot -l app=ytdl-bot
```

### Cookies монтуються але застарілі
**Симптом:** `WARNING: [youtube] The provided YouTube account cookies are no longer valid`

**Рішення:**
1. Експортуйте СВІЖІ cookies з браузера (метод вище)
2. Замініть файл на сервері
3. Рестарт pod

### Формат cookies неправильний
**Симптом:** `WARNING: skipping cookie file entry due to invalid length`

**Не хвилюйтесь!** Entrypoint автоматично конвертує формат:
- Вхід: пробіли між полями
- Вихід: табуляція (Netscape формат)

---

## Перевірка чи працюють cookies

### У логах бота має бути:
```
✅ Node.js detected: v20.19.6
📊 Final cookies status: 30+ cookies, 3000+ bytes
🍪 YouTube cookies loaded: 30+ cookies
✅ Critical cookies found: __Secure-3PSID, __Secure-1PSID, SAPISID, SSID
```

### НЕ має бути:
```
❌ WARNING: [youtube] The provided YouTube account cookies are no longer valid
❌ ERROR: Sign in to confirm you're not a bot
```

---

## Автоматизація

### Скрипт для оновлення cookies
```bash
#!/bin/bash
# update-ytdl-cookies.sh

echo "🍪 Exporting YouTube cookies..."
yt-dlp --cookies-from-browser chrome --cookies /tmp/yt_cookies.txt https://www.youtube.com

if [ $? -eq 0 ]; then
    echo "📤 Uploading to server..."
    scp /tmp/yt_cookies.txt your-server:/var/www/ytdl-cookies.txt
    
    echo "🔄 Restarting bot..."
    ssh your-server "kubectl rollout restart deployment/ytdl-bot -n wonchoeyoutubebot"
    
    echo "✅ Done! Check logs:"
    echo "   kubectl logs -f deployment/ytdl-bot -n wonchoeyoutubebot"
else
    echo "❌ Failed to export cookies"
    exit 1
fi
```

---

**Останнє оновлення:** 2025-12-07  
**Версія:** 2.0 (unified ytdl-cookies.txt path)
