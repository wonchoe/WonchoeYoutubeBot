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
YOUTUBE_URL = "https://www.youtube.com"


async def refresh_cookies(save_html=False):
    """Оновити cookies з браузера де користувач залогінений"""
    
    log.info("🔄 Starting cookie refresh...")
    
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
            
            # Перевіряємо чи вже залогінені
            log.info("📱 Opening YouTube...")
            await page.goto(YOUTUBE_URL, wait_until="domcontentloaded", timeout=30000)
            
            # Чекаємо завантаження
            await asyncio.sleep(5)
            
            # Зберігаємо HTML для debug
            if save_html:
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
            
            # Фільтруємо тільки YouTube і Google cookies
            youtube_cookies = [
                c for c in all_cookies
                if 'youtube.com' in c.get('domain', '') or 'google.com' in c.get('domain', '')
            ]
            
            if not youtube_cookies:
                log.error("❌ No YouTube cookies found")
                return False
            
            # Конвертуємо в Netscape format
            netscape_lines = ["# Netscape HTTP Cookie File\n"]
            
            for cookie in youtube_cookies:
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
                c.get('name') for c in youtube_cookies 
                if c.get('name') in critical_cookies
            ]
            
            log.info(f"✅ Saved {len(youtube_cookies)} cookies to {COOKIE_FILE}")
            log.info(f"📊 Cookie file size: {COOKIE_FILE.stat().st_size} bytes")
            log.info(f"✅ Critical cookies present: {', '.join(critical_found)}")
            
            # Перевіряємо критичні cookies
            cookie_names = [c.get('name') for c in youtube_cookies]
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
    log.info("   Browser will open, please login manually")
    
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
            await page.goto(YOUTUBE_URL)
            
            log.info("📱 Browser opened. Please:")
            log.info("   1. Login to your YouTube/Google account")
            log.info("   2. Wait until you see your avatar in top right")
            log.info("   3. Press Enter here when done...")
            
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
