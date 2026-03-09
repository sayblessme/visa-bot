"""
VFS Global token auto-refresh.

Uses undetected-chromedriver (proven to bypass Cloudflare on VFS Global)
to login, intercept `authorize` / `clientsource` headers from XHR requests,
and store them in Redis for the VFS provider.

If login fails (CAPTCHA / block), sends Telegram alert → admin uses /vfs_token.
"""

import json
import time
import threading

import httpx
import redis
import structlog

from app.config import settings
from app.tasks.celery_app import celery_app

log = structlog.get_logger()

REDIS_KEY_VFS_TOKENS = "vfs:tokens"
TOKEN_TTL_SECONDS = 30 * 60  # 30 min


def _get_redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


def get_vfs_tokens() -> dict | None:
    """Read current VFS tokens from Redis."""
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


@celery_app.task(name="app.tasks.vfs_token_refresh.keepalive_vfs_token")
def keepalive_vfs_token() -> dict:
    """
    Keep VFS token alive by making a lightweight API call every 5 min.
    If token is still valid — extend TTL in Redis.
    If token is dead (403) — notify admin to re-enter via /vfs_token.
    """
    tokens = get_vfs_tokens()
    if not tokens or not tokens.get("authorize"):
        return {"status": "skip", "reason": "no tokens in Redis"}

    route = tokens.get("route", settings.vfs_route or "kaz/ru/aut")
    route_parts = route.split("/")
    origin_code = route_parts[0] if len(route_parts) >= 1 else "kaz"
    dest_code = route_parts[2] if len(route_parts) >= 3 else "aut"

    headers = {
        "authorize": tokens["authorize"],
        "clientsource": tokens.get("clientsource", ""),
        "route": route,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://visa.vfsglobal.com",
        "Referer": "https://visa.vfsglobal.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    cookies = {}
    if tokens.get("cf_clearance"):
        cookies["cf_clearance"] = tokens["cf_clearance"]

    try:
        with httpx.Client(timeout=15, cookies=cookies) as client:
            resp = client.get(
                "https://lift-api.vfsglobal.com/appointment/slots",
                params={
                    "countryCode": origin_code,
                    "missionCode": dest_code,
                    "languageCode": "en-US",
                },
                headers=headers,
            )

        log.info("vfs_keepalive.response", status=resp.status_code, body=resp.text[:200])

        if resp.status_code == 200:
            # Token is alive — extend TTL in Redis
            save_vfs_tokens(
                authorize=tokens["authorize"],
                clientsource=tokens.get("clientsource", ""),
                route=route,
                cf_clearance=tokens.get("cf_clearance", ""),
            )
            log.info("vfs_keepalive.alive", msg="Token extended")
            return {"status": "alive", "ttl_extended": True}

        elif resp.status_code in (401, 403):
            log.warning("vfs_keepalive.token_expired", status=resp.status_code)
            _notify_admin_sync(
                "VFS: токен истёк (403).\n"
                "Обновите через /vfs_token"
            )
            # Delete dead token from Redis
            r = _get_redis()
            r.delete(REDIS_KEY_VFS_TOKENS)
            return {"status": "expired", "code": resp.status_code}

        else:
            log.warning("vfs_keepalive.unexpected", status=resp.status_code)
            return {"status": "unknown", "code": resp.status_code}

    except Exception as exc:
        log.error("vfs_keepalive.error", error=str(exc))
        return {"status": "error", "reason": str(exc)}


@celery_app.task(name="app.tasks.vfs_token_refresh.refresh_vfs_token")
def refresh_vfs_token() -> dict:
    """Celery task: login to VFS via undetected-chromedriver and refresh tokens."""
    if not settings.vfs_email or not settings.vfs_password:
        log.warning("vfs_token_refresh.no_credentials")
        return {"status": "skip", "reason": "no credentials configured"}

    return _refresh_sync()


def _refresh_sync() -> dict:
    """Login to VFS via undetected-chromedriver and capture API tokens."""
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    route = settings.vfs_route or "kaz/ru/aut"
    route_parts = route.split("/")
    origin_code = route_parts[0] if len(route_parts) >= 1 else "kaz"
    lang = route_parts[1] if len(route_parts) >= 2 else "ru"
    dest_code = route_parts[2] if len(route_parts) >= 3 else "aut"

    login_url = f"https://visa.vfsglobal.com/{dest_code}/{lang}/{origin_code}/login"

    captured = {"authorize": "", "clientsource": "", "cf_clearance": ""}

    driver = None
    try:
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=en-US")

        log.info("vfs_token_refresh.starting_browser")
        driver = uc.Chrome(options=options, headless=True, version_main=145)

        # Enable Network domain for request interception via CDP
        driver.execute_cdp_cmd("Network.enable", {})

        # Set up CDP listener to capture XHR headers
        _setup_network_capture(driver, captured)

        log.info("vfs_token_refresh.navigating", url=login_url)
        driver.get(login_url)

        # Wait for Cloudflare challenge to pass (up to 30s)
        log.info("vfs_token_refresh.waiting_cloudflare")
        for i in range(15):
            title = driver.title.lower()
            if "just a moment" in title or "checking" in title:
                time.sleep(2)
            else:
                break
        time.sleep(5)  # Extra wait for Angular SPA to load

        # Check if page loaded
        page_source = driver.page_source
        if "sorry" in page_source.lower() and "progress" in page_source.lower():
            log.warning("vfs_token_refresh.cloudflare_blocked")
            _notify_admin_sync(
                "VFS Token Refresh: Cloudflare заблокировал.\n"
                "Обновите токен вручную: /vfs_token"
            )
            return {"status": "blocked", "reason": "cloudflare"}

        # Wait for login form to appear (Angular needs time)
        log.info("vfs_token_refresh.waiting_for_form")
        try:
            wait = WebDriverWait(driver, 30)
            email_input = wait.until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    '#mat-input-0, '
                    'input[type="email"], '
                    'input[formcontrolname="username"], '
                    'input[name="email"]'
                ))
            )
        except Exception:
            # Save screenshot for debugging
            try:
                driver.save_screenshot("/tmp/vfs_refresh_debug.png")
            except Exception:
                pass
            log.warning("vfs_token_refresh.no_login_form", title=driver.title)
            _notify_admin_sync(
                "VFS Token Refresh: форма логина не загрузилась.\n"
                "Обновите токен вручную: /vfs_token"
            )
            return {"status": "error", "reason": "login form not found"}

        # Dismiss cookie banner if present
        try:
            cookie_btn = driver.find_element(By.CSS_SELECTOR, "#onetrust-accept-btn-handler, button[id*='accept']")
            cookie_btn.click()
            time.sleep(1)
        except Exception:
            pass

        # Fill login form
        log.info("vfs_token_refresh.filling_form")
        email_input.clear()
        email_input.send_keys(settings.vfs_email)
        time.sleep(0.5)

        try:
            password_input = driver.find_element(
                By.CSS_SELECTOR,
                '#mat-input-1, '
                'input[type="password"], '
                'input[formcontrolname="password"]'
            )
            password_input.clear()
            password_input.send_keys(settings.vfs_password)
        except Exception as exc:
            log.error("vfs_token_refresh.password_field_error", error=str(exc))
            return {"status": "error", "reason": "password field not found"}

        time.sleep(1)

        # Check for reCAPTCHA before clicking submit
        captcha_frames = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha'], iframe[src*='captcha']")
        if captcha_frames:
            log.info("vfs_token_refresh.captcha_detected")
            # Try audio CAPTCHA solving
            solved = _try_solve_audio_captcha(driver)
            if not solved:
                _notify_admin_sync(
                    "VFS Token Refresh: обнаружена CAPTCHA, не удалось решить автоматически.\n"
                    "Обновите токен вручную: /vfs_token"
                )
                return {"status": "captcha", "reason": "captcha not solved"}

        # Click sign-in
        try:
            submit = driver.find_element(
                By.CSS_SELECTOR,
                "button[type='submit'], button.mat-raised-button"
            )
            submit.click()
        except Exception:
            log.warning("vfs_token_refresh.submit_not_found")
            return {"status": "error", "reason": "submit button not found"}

        # Wait for login to complete (dashboard redirect or XHR)
        log.info("vfs_token_refresh.waiting_login")
        for i in range(15):
            time.sleep(2)
            if "dashboard" in driver.current_url:
                break
            if captured["authorize"]:
                break

        time.sleep(3)

        # Extract tokens from localStorage if not captured via network
        if not captured["authorize"]:
            try:
                login_response = driver.execute_script(
                    "return localStorage.getItem('loginResponse');"
                )
                if login_response:
                    data = json.loads(login_response)
                    captured["authorize"] = (
                        data.get("authorize")
                        or data.get("token")
                        or data.get("access_token")
                        or ""
                    )
                    log.info("vfs_token_refresh.token_from_localStorage")
            except Exception:
                pass

        # Try to get clientsource from localStorage
        if not captured["clientsource"]:
            try:
                for key in ["clientsource", "clientSource", "client_source"]:
                    val = driver.execute_script(
                        f"return localStorage.getItem('{key}');"
                    )
                    if val:
                        captured["clientsource"] = val
                        break
            except Exception:
                pass

        # Get cf_clearance from cookies
        for cookie in driver.get_cookies():
            if cookie["name"] == "cf_clearance":
                captured["cf_clearance"] = cookie["value"]

        # Evaluate result
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
            save_vfs_tokens(
                authorize=captured["authorize"],
                clientsource=settings.vfs_clientsource,
                route=route,
                cf_clearance=captured["cf_clearance"],
            )
            log.info("vfs_token_refresh.partial", has_clientsource=False)
            return {"status": "partial", "has_authorize": True, "has_clientsource": False}
        else:
            log.warning("vfs_token_refresh.no_tokens_captured")
            _notify_admin_sync(
                "VFS Token Refresh: залогинились, но токены не найдены.\n"
                "Обновите вручную: /vfs_token"
            )
            return {"status": "error", "reason": "no tokens captured"}

    except Exception as exc:
        log.error("vfs_token_refresh.error", error=str(exc))
        _notify_admin_sync(
            f"VFS Token Refresh: ошибка — {str(exc)[:200]}\n"
            "Обновите вручную: /vfs_token"
        )
        return {"status": "error", "reason": str(exc)}
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _setup_network_capture(driver, captured: dict) -> None:
    """Use Selenium CDP to intercept network requests and capture VFS auth headers."""
    try:
        # Use performance log to capture requests
        driver.execute_cdp_cmd("Network.enable", {})

        # Start a background thread to poll for network events
        def _poll_network():
            while not captured.get("_done"):
                try:
                    logs = driver.get_log("performance")
                    for entry in logs:
                        try:
                            msg = json.loads(entry["message"])["message"]
                            if msg["method"] == "Network.requestWillBeSent":
                                url = msg["params"]["request"]["url"]
                                headers = msg["params"]["request"]["headers"]
                                if "lift-api.vfsglobal.com" in url:
                                    if headers.get("authorize"):
                                        captured["authorize"] = headers["authorize"]
                                    if headers.get("clientsource"):
                                        captured["clientsource"] = headers["clientsource"]
                        except (KeyError, json.JSONDecodeError):
                            continue
                except Exception:
                    pass
                time.sleep(1)

        thread = threading.Thread(target=_poll_network, daemon=True)
        thread.start()
    except Exception:
        # Performance logging might not be available — will fall back to localStorage
        pass


def _try_solve_audio_captcha(driver) -> bool:
    """Attempt to solve reCAPTCHA via audio challenge. Returns True if solved."""
    try:
        from selenium.webdriver.common.by import By

        # Switch to reCAPTCHA iframe
        frames = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
        if not frames:
            return False

        driver.switch_to.frame(frames[0])
        time.sleep(1)

        # Click the reCAPTCHA checkbox
        try:
            checkbox = driver.find_element(By.CSS_SELECTOR, ".recaptcha-checkbox-border")
            checkbox.click()
            time.sleep(2)
        except Exception:
            pass

        driver.switch_to.default_content()

        # Check if challenge appeared
        challenge_frames = driver.find_elements(
            By.CSS_SELECTOR, "iframe[src*='recaptcha'][title*='challenge']"
        )
        if not challenge_frames:
            # Maybe CAPTCHA was solved by just clicking
            return True

        # Switch to challenge frame
        driver.switch_to.frame(challenge_frames[0])
        time.sleep(1)

        # Click audio button
        try:
            audio_btn = driver.find_element(By.CSS_SELECTOR, "#recaptcha-audio-button")
            audio_btn.click()
            time.sleep(3)
        except Exception:
            driver.switch_to.default_content()
            return False

        # Get audio URL
        try:
            audio_source = driver.find_element(By.CSS_SELECTOR, "#audio-source")
            audio_url = audio_source.get_attribute("src")
            if not audio_url:
                driver.switch_to.default_content()
                return False
        except Exception:
            driver.switch_to.default_content()
            return False

        # Transcribe audio (try whisper if available)
        transcription = _transcribe_audio(audio_url)
        if not transcription:
            driver.switch_to.default_content()
            return False

        # Enter the answer
        audio_input = driver.find_element(By.CSS_SELECTOR, "#audio-response")
        audio_input.send_keys(transcription)
        time.sleep(1)

        # Click verify
        verify_btn = driver.find_element(By.CSS_SELECTOR, "#recaptcha-verify-button")
        verify_btn.click()
        time.sleep(3)

        driver.switch_to.default_content()
        return True

    except Exception as exc:
        log.warning("captcha_solve.error", error=str(exc))
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        return False


def _transcribe_audio(audio_url: str) -> str | None:
    """Download and transcribe reCAPTCHA audio challenge."""
    import tempfile
    import subprocess

    try:
        # Download audio
        with httpx.Client(timeout=15) as client:
            resp = client.get(audio_url)
            if resp.status_code != 200:
                return None

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(resp.content)
            audio_path = f.name

        # Try whisper CLI (if installed)
        try:
            result = subprocess.run(
                ["whisper", audio_path, "--model", "tiny", "--language", "en", "--output_format", "txt"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                txt_path = audio_path.replace(".mp3", ".txt")
                with open(txt_path) as f:
                    return f.read().strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Try SpeechRecognition library as fallback
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()

            # Convert mp3 to wav first
            wav_path = audio_path.replace(".mp3", ".wav")
            subprocess.run(
                ["ffmpeg", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path, "-y"],
                capture_output=True, timeout=10,
            )

            with sr.AudioFile(wav_path) as source:
                audio = recognizer.record(source)
                return recognizer.recognize_google(audio)
        except Exception:
            pass

        return None
    except Exception:
        return None


def _notify_admin_sync(text: str) -> None:
    """Send a Telegram message to the admin user (sync version)."""
    if not settings.admin_user_id or not settings.bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    try:
        with httpx.Client(timeout=10) as client:
            client.post(url, json={"chat_id": settings.admin_user_id, "text": text})
    except Exception as exc:
        log.error("notify_admin.failed", error=str(exc))
