"""
VFS Global token auto-refresh.

Periodically logs into VFS via Playwright + stealth on the server,
intercepts the `authorize` / `clientsource` headers from XHR requests,
and stores them in Redis so the VFS provider can use them for API calls.

If login fails (CAPTCHA / Cloudflare block), sends a Telegram alert
so the admin can paste tokens manually via /vfs_token.
"""

import asyncio
import json

import httpx
import redis
import structlog
from playwright.async_api import async_playwright, Request

from app.config import settings
from app.tasks.celery_app import celery_app

log = structlog.get_logger()

REDIS_KEY_VFS_TOKENS = "vfs:tokens"
TOKEN_TTL_SECONDS = 30 * 60  # 30 min — tokens usually live ~15-30 min


def _get_redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


def get_vfs_tokens() -> dict | None:
    """Read current VFS tokens from Redis. Returns dict with authorize/clientsource/route or None."""
    r = _get_redis()
    raw = r.get(REDIS_KEY_VFS_TOKENS)
    if raw:
        return json.loads(raw)
    return None


def save_vfs_tokens(authorize: str, clientsource: str, route: str, cf_clearance: str = "") -> None:
    """Save VFS tokens to Redis with TTL."""
    r = _get_redis()
    data = {
        "authorize": authorize,
        "clientsource": clientsource,
        "route": route,
        "cf_clearance": cf_clearance,
    }
    r.setex(REDIS_KEY_VFS_TOKENS, TOKEN_TTL_SECONDS, json.dumps(data))
    log.info("vfs_tokens.saved", route=route, ttl=TOKEN_TTL_SECONDS)


@celery_app.task(name="app.tasks.vfs_token_refresh.refresh_vfs_token")
def refresh_vfs_token() -> dict:
    """Celery task: attempt to login to VFS and refresh tokens."""
    if not settings.vfs_email or not settings.vfs_password:
        log.warning("vfs_token_refresh.no_credentials")
        return {"status": "skip", "reason": "no credentials configured"}

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_async_refresh())
    finally:
        loop.close()


async def _async_refresh() -> dict:
    """Login to VFS via stealth Playwright browser and capture API tokens."""
    from playwright_stealth import stealth_async

    route = settings.vfs_route or "kaz/ru/aut"
    route_parts = route.split("/")
    origin_code = route_parts[0] if len(route_parts) >= 1 else "kaz"
    lang = route_parts[1] if len(route_parts) >= 2 else "en"
    dest_code = route_parts[2] if len(route_parts) >= 3 else "aut"

    login_url = f"https://visa.vfsglobal.com/{dest_code}/{lang}/{origin_code}/login"

    captured = {"authorize": "", "clientsource": "", "cf_clearance": ""}

    def on_request(request: Request) -> None:
        """Intercept outgoing requests to capture VFS auth headers."""
        url = request.url
        if "lift-api.vfsglobal.com" in url or "vfsglobal.com/api" in url:
            headers = request.headers
            if headers.get("authorize"):
                captured["authorize"] = headers["authorize"]
            if headers.get("clientsource"):
                captured["clientsource"] = headers["clientsource"]

    pw = None
    browser = None
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = await context.new_page()
        await stealth_async(page)

        # Listen for API requests to capture tokens
        page.on("request", on_request)

        log.info("vfs_token_refresh.navigating", url=login_url)
        await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

        # Wait for Cloudflare challenge to pass
        for _ in range(20):
            title = await page.title()
            content = await page.content()
            if "just a moment" in title.lower() or "checking" in title.lower():
                log.info("vfs_token_refresh.cloudflare_wait")
                await asyncio.sleep(2)
            elif len(content) < 200:
                # Empty page — Cloudflare might still be loading
                await asyncio.sleep(2)
            else:
                break

        await asyncio.sleep(3)

        # Check if Cloudflare blocked us
        content = await page.content()
        if "sorry" in content.lower() and "progress" in content.lower():
            log.warning("vfs_token_refresh.cloudflare_blocked")
            await _notify_admin(
                "VFS Token Refresh: Cloudflare заблокировал доступ с сервера.\n"
                "Обновите токен вручную: /vfs_token"
            )
            return {"status": "blocked", "reason": "cloudflare"}

        # Check for CAPTCHA
        captcha_frame = page.locator("iframe[src*='recaptcha'], iframe[src*='turnstile'], iframe[src*='captcha']")
        if await captcha_frame.count() > 0:
            log.warning("vfs_token_refresh.captcha_detected")
            await _notify_admin(
                "VFS Token Refresh: обнаружена CAPTCHA при логине.\n"
                "Обновите токен вручную: /vfs_token"
            )
            return {"status": "captcha", "reason": "captcha required"}

        # Fill login form
        email_input = page.locator(
            '#mat-input-0, '
            'input[type="email"], '
            'input[formcontrolname="username"], '
            'input[placeholder*="mail"], '
            'input[name="email"]'
        )
        try:
            await email_input.first.wait_for(state="visible", timeout=15000)
        except Exception:
            log.warning("vfs_token_refresh.no_login_form", page_title=await page.title())
            await _notify_admin(
                "VFS Token Refresh: не найдена форма логина.\n"
                "Обновите токен вручную: /vfs_token"
            )
            return {"status": "error", "reason": "login form not found"}

        await email_input.first.fill(settings.vfs_email)
        await asyncio.sleep(0.5)

        password_input = page.locator(
            '#mat-input-1, '
            'input[type="password"], '
            'input[formcontrolname="password"]'
        )
        await password_input.first.fill(settings.vfs_password)
        await asyncio.sleep(0.5)

        # Click sign-in
        sign_in = page.locator("button[type='submit'], button:has-text('Sign In'), button:has-text('Войти')")
        await sign_in.first.click()

        # Wait for redirect to dashboard (login success) or API calls
        try:
            await page.wait_for_url("**/dashboard**", timeout=30000)
        except Exception:
            # Even if URL doesn't change, tokens might be captured from XHR
            pass

        await asyncio.sleep(3)

        # Also try to extract from localStorage
        if not captured["authorize"]:
            token_from_storage = await page.evaluate("""
                () => {
                    const lr = localStorage.getItem('loginResponse');
                    if (lr) {
                        try {
                            const data = JSON.parse(lr);
                            return data.authorize || data.token || data.access_token || null;
                        } catch { return null; }
                    }
                    return null;
                }
            """)
            if token_from_storage:
                captured["authorize"] = token_from_storage

        # Get cf_clearance from cookies
        cookies = await context.cookies()
        for cookie in cookies:
            if cookie["name"] == "cf_clearance":
                captured["cf_clearance"] = cookie["value"]

        if captured["authorize"] and captured["clientsource"]:
            save_vfs_tokens(
                authorize=captured["authorize"],
                clientsource=captured["clientsource"],
                route=route,
                cf_clearance=captured["cf_clearance"],
            )
            log.info("vfs_token_refresh.success")
            return {"status": "ok", "has_authorize": True, "has_clientsource": True}
        elif captured["authorize"]:
            # Got authorize but not clientsource — save what we have
            save_vfs_tokens(
                authorize=captured["authorize"],
                clientsource=settings.vfs_clientsource,  # fallback to .env
                route=route,
                cf_clearance=captured["cf_clearance"],
            )
            log.info("vfs_token_refresh.partial", has_clientsource=False)
            return {"status": "partial", "has_authorize": True, "has_clientsource": False}
        else:
            log.warning("vfs_token_refresh.no_tokens_captured")
            await _notify_admin(
                "VFS Token Refresh: не удалось перехватить токены после логина.\n"
                "Обновите токен вручную: /vfs_token"
            )
            return {"status": "error", "reason": "no tokens captured"}

    except Exception as exc:
        log.error("vfs_token_refresh.error", error=str(exc))
        await _notify_admin(
            f"VFS Token Refresh: ошибка — {str(exc)[:200]}\n"
            "Обновите токен вручную: /vfs_token"
        )
        return {"status": "error", "reason": str(exc)}
    finally:
        if browser:
            await browser.close()
        if pw:
            await pw.stop()


async def _notify_admin(text: str) -> None:
    """Send a Telegram message to the admin user."""
    if not settings.admin_user_id or not settings.bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={"chat_id": settings.admin_user_id, "text": text})
    except Exception as exc:
        log.error("notify_admin.failed", error=str(exc))
