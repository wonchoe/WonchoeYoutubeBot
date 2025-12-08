#!/usr/bin/env python3
"""
Автоматичне оновлення YouTube cookies через headless браузер
Запускається як sidecar або cronjob
"""

import asyncio
import json
import logging
from pathlib import Path
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cookie_refresher")

COOKIE_FILE = Path("/var/www/ytdl-cookies.txt")
SITES = [
    "https://www.youtube.com",
    "https://www.facebook.com", 
    "https://www.instagram.com"
]


async def refresh_cookies(save_html=False):
    """Оновити cookies з браузера де користувач залогінений"""
    
    log.info("🔄 Starting cookie refresh for YouTube, Facebook, Instagram...")
    
    async with async_playwright() as p:
        # Запускаємо Chrome з persistent context (зберігає логін між запусками)
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="/var/www/playwright-profile",
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ],
        )
        
        try:
            page = await browser.new_page()
            
            # Відвідуємо всі сайти для оновлення cookies
            for site in SITES:
                log.info(f"📱 Opening {site}...")
                await page.goto(site, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
            
            # Зберігаємо HTML для debug (тільки YouTube)
            if save_html:
                await page.goto(SITES[0], wait_until="domcontentloaded", timeout=30000)
                html_content = await page.content()
                html_path = Path("/tmp/youtube_debug.html")
                html_path.write_text(html_content)
                log.info(f"📄 HTML saved to {html_path}")
                log.info(f"   View: cat /tmp/youtube_debug.html | head -100")
            
            # Перевіряємо cookies замість DOM елементів (більш надійно)
            cookies = await browser.cookies()
            youtube_cookies = [c for c in cookies if 'youtube.com' in c.get('domain', '')]
            
            # Перевіряємо критичні auth cookies
            critical_cookies = ['SAPISID', 'SSID', '__Secure-1PSID', '__Secure-3PSID']
            has_auth = any(
                c.get('name') in critical_cookies 
                for c in youtube_cookies
            )
            
            if not has_auth:
                log.warning("⚠️ Not logged in! Manual login required.")
                log.warning("   Please run: python cookie_refresher.py --login")
                log.info(f"   Found {len(youtube_cookies)} cookies but no auth cookies")
                return False
            
            log.info("✅ Logged in, extracting cookies...")
            
            # Отримуємо всі cookies (вже маємо з перевірки вище)
            all_cookies = await browser.cookies()
            
            # Фільтруємо cookies для YouTube, Facebook, Instagram, Google
            relevant_cookies = [
                c for c in all_cookies
                if any(domain in c.get('domain', '') for domain in [
                    'youtube.com', 'google.com', 
                    'facebook.com', 'fb.com',
                    'instagram.com', 'cdninstagram.com'
                ])
            ]
            
            if not relevant_cookies:
                log.error("❌ No cookies found for any platform")
                return False
            
            # Конвертуємо в Netscape format
            netscape_lines = ["# Netscape HTTP Cookie File\n"]
            
            for cookie in relevant_cookies:
                domain = cookie.get('domain', '')
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = cookie.get('path', '/')
                secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                
                # Виправляємо expires: -1 -> 0 (session cookie)
                expires = cookie.get('expires', -1)
                if expires == -1 or expires < 0:
                    expiration = "0"
                else:
                    expiration = str(int(expires))
                
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                
                line = f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n"
                netscape_lines.append(line)
            
            # Зберігаємо
            COOKIE_FILE.write_text(''.join(netscape_lines))
            
            # Логуємо критичні cookies для діагностики
            critical_found = [
                c.get('name') for c in relevant_cookies
                if c.get('name') in critical_cookies
            ]
            
            log.info(f"✅ Saved {len(relevant_cookies)} cookies to {COOKIE_FILE}")
            log.info(f"📊 Cookie file size: {COOKIE_FILE.stat().st_size} bytes")
            log.info(f"✅ Critical YouTube cookies: {', '.join(critical_found)}")
            
            # Статистика по платформах
            youtube_count = len([c for c in relevant_cookies if 'youtube.com' in c.get('domain', '') or 'google.com' in c.get('domain', '')])
            facebook_count = len([c for c in relevant_cookies if 'facebook.com' in c.get('domain', '') or 'fb.com' in c.get('domain', '')])
            instagram_count = len([c for c in relevant_cookies if 'instagram.com' in c.get('domain', '')])
            
            log.info(f"📊 YouTube cookies: {youtube_count}")
            log.info(f"📊 Facebook cookies: {facebook_count}")
            log.info(f"📊 Instagram cookies: {instagram_count}")
            
            # Перевіряємо критичні cookies
            cookie_names = [c.get('name') for c in relevant_cookies]
            critical = ['__Secure-3PSID', '__Secure-1PSID', 'SAPISID', 'SSID']
            found = [c for c in critical if c in cookie_names]
            
            if found:
                log.info(f"✅ Critical cookies present: {', '.join(found)}")
            else:
                log.warning(f"⚠️ Missing critical cookies: {', '.join(critical)}")
            
            return True
            
        except Exception as e:
            log.error(f"❌ Error: {e}")
            return False
        
        finally:
            await browser.close()


async def interactive_login():
    """Інтерактивний логін для першого разу"""
    
    log.info("🔐 Interactive login mode...")
    log.info("   Browser will open, please login to YouTube, Facebook, and Instagram")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="/var/www/playwright-profile",
            headless=False,  # Видимий браузер
            args=[
                '--disable-blink-features=AutomationControlled',
            ],
        )
        
        try:
            page = await browser.new_page()
            
            # Відкриваємо всі сайти для логіну
            for i, site in enumerate(SITES, 1):
                await page.goto(site)
                log.info(f"📱 Opened {site} ({i}/{len(SITES)})")
                await asyncio.sleep(5)  # Збільшено час для завантаження
            
            log.info("📱 Please:")
            log.info("   1. Login to YouTube/Google account")
            log.info("   2. Login to Facebook account (if needed)")
            log.info("   3. Login to Instagram account (if needed)")
            log.info("   4. Press Enter here when done...")
            
            input()  # Wait for user
            
            log.info("✅ Saving cookies...")
            
            # Зберігаємо cookies
            cookies = await browser.cookies()
            youtube_cookies = [
                c for c in cookies 
                if 'youtube.com' in c.get('domain', '') or 'google.com' in c.get('domain', '')
            ]
            
            # Netscape format
            netscape_lines = ["# Netscape HTTP Cookie File\n"]
            for cookie in youtube_cookies:
                domain = cookie.get('domain', '')
                flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                path = cookie.get('path', '/')
                secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                expiration = str(int(cookie.get('expires', -1)))
                name = cookie.get('name', '')
                value = cookie.get('value', '')
                
                line = f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}\n"
                netscape_lines.append(line)
            
            COOKIE_FILE.write_text(''.join(netscape_lines))
            
            log.info(f"✅ Saved {len(youtube_cookies)} cookies")
            log.info(f"📁 Cookie file: {COOKIE_FILE}")
            log.info("✅ You can now run automatic refresh")
            
        finally:
            await browser.close()


async def main():
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--login":
        await interactive_login()
    elif len(sys.argv) > 1 and sys.argv[1] == "--debug":
        log.info("🐛 Debug mode: will save HTML")
        success = await refresh_cookies(save_html=True)
        sys.exit(0 if success else 1)
    else:
        success = await refresh_cookies(save_html=False)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
