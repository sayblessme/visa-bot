"""
VFS Global provider.

Uses Playwright for login (to get JWT token) and the VFS Lift API for slot monitoring.
Booking is done via Playwright browser automation with human-in-the-loop for captchas.

URL patterns:
  - Portal: https://visa.vfsglobal.com/{dest_country}/{lang}/{origin_country}/
  - Login: .../login
  - Book: .../book-an-appointment
  - Slots API: https://lift-api.vfsglobal.com/appointment/slots
"""

import asyncio
import datetime
import json
import re

import httpx
import structlog
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.providers.base import BaseProvider
from app.providers.schemas import BookingResult, BookingStatus, MonitorCriteria, Slot
from app.utils.crypto import decrypt_data, encrypt_data

log = structlog.get_logger()


class _TokenCfg:
    """Lightweight wrapper so Redis tokens can be used where settings cfg is expected."""

    def __init__(self, data: dict) -> None:
        self.vfs_authorize = data.get("authorize", "")
        self.vfs_clientsource = data.get("clientsource", "")
        self.vfs_route = data.get("route", "")
        self.vfs_cf_clearance = data.get("cf_clearance", "")

# Known VFS center codes (expandable)
VFS_CENTERS: dict[str, dict] = {
    "Germany": {
        "country_code": "deu",
        "centers": {
            "Berlin": "DEBL",
            "Munich": "DEMN",
            "Frankfurt": "DEFR",
            "Hamburg": "DEHM",
            "Dusseldorf": "DEDS",
        },
    },
    "France": {
        "country_code": "fra",
        "centers": {
            "Paris": "FRPR",
            "Lyon": "FRLY",
            "Marseille": "FRML",
        },
    },
    "Italy": {
        "country_code": "ita",
        "centers": {"Rome": "ITRM", "Milan": "ITML"},
    },
    "Spain": {
        "country_code": "esp",
        "centers": {"Madrid": "ESMD", "Barcelona": "ESBC"},
    },
    "Netherlands": {
        "country_code": "nld",
        "centers": {"The Hague": "NLTH", "Amsterdam": "NLAM"},
    },
    "Austria": {
        "country_code": "aut",
        "centers": {"Vienna": "ATVN"},
    },
    "Poland": {
        "country_code": "pol",
        "centers": {"Warsaw": "PLWW", "Krakow": "PLKR"},
    },
    "Czech Republic": {
        "country_code": "cze",
        "centers": {"Prague": "CZPR"},
    },
    "Greece": {
        "country_code": "grc",
        "centers": {"Athens": "GRAT", "Thessaloniki": "GRTH"},
    },
    "Portugal": {
        "country_code": "prt",
        "centers": {"Lisbon": "PTLS"},
    },
}


class VFSGlobalProvider(BaseProvider):
    """
    VFS Global visa appointment provider.

    Flow:
    1. Login via Playwright to obtain JWT token
    2. Use JWT to query lift-api.vfsglobal.com/appointment/slots
    3. Parse available slots from API response
    4. Booking via Playwright with human-in-the-loop for captcha
    """

    name: str = "vfs_global"

    SLOTS_API = "https://lift-api.vfsglobal.com/appointment/slots"
    BASE_URL = "https://visa.vfsglobal.com"

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._pw = None
        self._browser: Browser | None = None
        self._jwt_token: str | None = None

    async def _ensure_browser(self) -> Browser:
        if self._browser is None or not self._browser.is_connected():
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=self._headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
        return self._browser

    async def _create_context(self, storage_state: dict | None = None) -> BrowserContext:
        browser = await self._ensure_browser()
        ctx = await browser.new_context(
            storage_state=storage_state,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        # Remove webdriver flag
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return ctx

    # ── Authentication ─────────────────────────────────────────────────

    async def login(
        self,
        email: str,
        password: str,
        dest_country_code: str = "deu",
        origin_country_code: str = "rus",
    ) -> str | None:
        """
        Login to VFS Global via Playwright browser.
        Returns JWT token if successful, None otherwise.

        If captcha appears, this will wait for human intervention.
        """
        ctx = await self._create_context()
        page = await ctx.new_page()

        login_url = f"{self.BASE_URL}/{dest_country_code}/en/{origin_country_code}/login"
        log.info("vfs.login", url=login_url)

        try:
            # Use domcontentloaded — networkidle hangs on VFS due to continuous XHR
            await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

            # Wait for Cloudflare Waiting Room to pass (up to 30s)
            for _ in range(15):
                title = await page.title()
                if "just a moment" in title.lower() or "checking" in title.lower():
                    log.info("vfs.login.cloudflare_wait")
                    await asyncio.sleep(2)
                else:
                    break
            await asyncio.sleep(3)

            # Fill email — try multiple selectors
            email_input = page.locator(
                '#mat-input-0, '
                'input[type="email"], '
                'input[formcontrolname="username"], '
                'input[placeholder*="mail"], '
                'input[name="email"]'
            )
            await email_input.first.wait_for(state="visible", timeout=20000)
            await email_input.first.fill(email)
            await asyncio.sleep(0.5)

            # Fill password
            password_input = page.locator(
                '#mat-input-1, '
                'input[type="password"], '
                'input[formcontrolname="password"]'
            )
            await password_input.first.fill(password)

            # Handle reCAPTCHA — wait for human to solve if present
            captcha = page.locator("iframe[src*='recaptcha']")
            if await captcha.count() > 0:
                log.info("vfs.login.captcha_detected", msg="Waiting for human to solve captcha")
                # Wait up to 5 minutes for captcha to be solved
                try:
                    await page.wait_for_selector(
                        "#g-recaptcha-response[value]:not([value=''])",
                        timeout=300000,
                    )
                except Exception:
                    log.warning("vfs.login.captcha_timeout")

            # Click sign-in button
            sign_in = page.locator("button[type='submit'], button:has-text('Sign In')")
            await sign_in.click()

            # Wait for navigation after login
            await page.wait_for_url("**/dashboard**", timeout=30000)

            # Extract JWT from localStorage or cookies
            token = await self._extract_jwt(page)
            if token:
                self._jwt_token = token
                log.info("vfs.login.success")
            else:
                log.warning("vfs.login.no_jwt")

            return token
        except Exception as exc:
            log.error("vfs.login.error", error=str(exc))
            return None
        finally:
            await page.close()
            await ctx.close()

    async def _extract_jwt(self, page: Page) -> str | None:
        """Extract JWT token from browser storage."""
        # Try localStorage
        token = await page.evaluate("""
            () => {
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    const value = localStorage.getItem(key);
                    if (value && value.startsWith('eyJ')) return value;
                }
                return null;
            }
        """)
        if token:
            return token

        # Try cookies
        cookies = await page.context.cookies()
        for cookie in cookies:
            if cookie["value"].startswith("eyJ"):
                return cookie["value"]

        # Try intercepting from network
        return None

    # ── Slot Monitoring ────────────────────────────────────────────────

    async def fetch_availability(self, criteria: MonitorCriteria) -> list[Slot]:
        """
        Fetch available slots from VFS Global API.
        Priority: 1) Redis tokens (auto-refreshed)  2) .env tokens  3) Playwright browser fallback.
        """
        from app.config import settings as cfg
        from app.tasks.vfs_token_refresh import get_vfs_tokens

        # 1) Try Redis tokens (set by auto-refresh or /vfs_token command)
        redis_tokens = get_vfs_tokens()
        if redis_tokens and redis_tokens.get("authorize"):
            log.info("vfs.fetch.redis_tokens", route=redis_tokens.get("route", ""))
            return await self._fetch_via_direct_api(criteria, _TokenCfg(redis_tokens))

        # 2) Fallback to .env tokens
        if cfg.vfs_authorize and cfg.vfs_clientsource:
            log.info("vfs.fetch.env_tokens", route=cfg.vfs_route)
            return await self._fetch_via_direct_api(criteria, cfg)

        # 3) Last resort: browser-based fetch
        log.warning("vfs.fetch.no_token", msg="No API token available, using browser fallback")
        return await self._fetch_via_browser(criteria)

    async def _fetch_via_direct_api(
        self, criteria: MonitorCriteria, cfg
    ) -> list[Slot]:
        """Fetch slots using the VFS Lift API with authorize/clientsource headers."""
        # Parse route: "kaz/ru/aut" → origin=kaz, dest=aut
        route_parts = cfg.vfs_route.split("/") if cfg.vfs_route else []
        origin_code = route_parts[0] if len(route_parts) >= 1 else "kaz"
        dest_code = route_parts[2] if len(route_parts) >= 3 else "aut"

        country = criteria.country or "Austria"
        city = criteria.city or criteria.center

        headers = {
            "authorize": cfg.vfs_authorize,
            "clientsource": cfg.vfs_clientsource,
            "route": cfg.vfs_route,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://visa.vfsglobal.com",
            "Referer": "https://visa.vfsglobal.com/",
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/18.5 Mobile/15E148 Safari/604.1"
            ),
        }

        # Add Cloudflare cookies if available
        cookies = {}
        if cfg.vfs_cf_clearance:
            cookies["cf_clearance"] = cfg.vfs_cf_clearance

        slots: list[Slot] = []

        try:
            async with httpx.AsyncClient(timeout=20, cookies=cookies) as client:
                # GET /appointment/slots — use codes matching the route
                params = {
                    "countryCode": origin_code,
                    "missionCode": dest_code,
                    "centerCode": "",
                    "loginUser": "",
                    "visaCategoryCode": self._visa_type_to_code(criteria.visa_type),
                    "languageCode": "en-US",
                    "applicantsCount": str(criteria.applicants_count),
                    "days": "90",
                    "slotType": "appointment",
                }
                resp = await client.get(self.SLOTS_API, params=params, headers=headers)
                log.info("vfs.api.slots", status=resp.status_code, body=resp.text[:500])

                if resp.status_code == 200:
                    data = resp.json()
                    slots = self._parse_api_slots(data, country, city or "", criteria)
                elif resp.status_code in (401, 403):
                    log.warning("vfs.api.auth_error", status=resp.status_code)

                # Also try POST /appointment/application
                if not slots:
                    app_resp = await client.post(
                        "https://lift-api.vfsglobal.com/appointment/application",
                        headers=headers,
                        json={
                            "countryCode": origin_code,
                            "missionCode": dest_code,
                        },
                    )
                    log.info("vfs.api.application", status=app_resp.status_code, body=app_resp.text[:500])

                    if app_resp.status_code == 200:
                        data = app_resp.json()
                        slots = self._parse_api_slots(data, country, city or "", criteria)

        except Exception as exc:
            log.error("vfs.api.request_error", error=str(exc))

        return slots

    def _parse_api_slots(
        self, data: dict | list, country: str, center: str, criteria: MonitorCriteria
    ) -> list[Slot]:
        """Parse slots from VFS API JSON response."""
        slots: list[Slot] = []

        # API response format may vary; handle both list and dict
        items = data if isinstance(data, list) else data.get("slots", data.get("data", []))
        if not isinstance(items, list):
            items = [items] if items else []

        for item in items:
            try:
                # Try multiple date field names
                date_str = (
                    item.get("date")
                    or item.get("slotDate")
                    or item.get("appointmentDate")
                    or ""
                )
                time_str = item.get("time") or item.get("slotTime") or "09:00"

                if not date_str:
                    continue

                # Parse datetime
                if "T" in date_str:
                    dt = datetime.datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                else:
                    dt = datetime.datetime.strptime(
                        f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
                    ).replace(tzinfo=datetime.UTC)

                # Apply date filters
                if criteria.date_from and dt.date() < criteria.date_from:
                    continue
                if criteria.date_to and dt.date() > criteria.date_to:
                    continue

                slots.append(
                    Slot(
                        provider=self.name,
                        country=country,
                        center=center or item.get("centerName", ""),
                        datetime_utc=dt,
                        visa_type=criteria.visa_type or item.get("visaCategory", ""),
                        url=f"{self.BASE_URL}/book-an-appointment",
                        raw=item,
                    )
                )
            except (ValueError, KeyError) as exc:
                log.debug("vfs.parse_slot.skip", error=str(exc))
                continue

        return slots

    async def _fetch_via_browser(self, criteria: MonitorCriteria) -> list[Slot]:
        """Fallback: fetch slots by navigating the VFS website with Playwright."""
        country = criteria.country or "Germany"
        country_info = VFS_CENTERS.get(country, {})
        country_code = country_info.get("country_code", "deu")

        ctx = await self._create_context()
        page = await ctx.new_page()
        slots: list[Slot] = []

        try:
            url = f"{self.BASE_URL}/{country_code}/en/rus/book-an-appointment"
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Wait for Cloudflare
            for _ in range(15):
                title = await page.title()
                if "just a moment" in title.lower():
                    await asyncio.sleep(2)
                else:
                    break
            await asyncio.sleep(3)

            # Try to find green (available) date cells in the calendar
            available_dates = await page.locator(
                ".mat-calendar-body-cell:not(.mat-calendar-body-disabled), "
                "[class*='available'], "
                "[style*='green'], "
                ".day-available"
            ).all()

            for el in available_dates:
                try:
                    date_text = await el.get_attribute("aria-label") or await el.inner_text()
                    # Try to parse the date
                    dt = self._parse_calendar_date(date_text)
                    if dt:
                        if criteria.date_from and dt.date() < criteria.date_from:
                            continue
                        if criteria.date_to and dt.date() > criteria.date_to:
                            continue
                        slots.append(
                            Slot(
                                provider=self.name,
                                country=country,
                                center=criteria.center or criteria.city or "",
                                datetime_utc=dt,
                                visa_type=criteria.visa_type or "",
                                url=url,
                            )
                        )
                except Exception:
                    continue

        except Exception as exc:
            log.error("vfs.browser_fetch.error", error=str(exc))
        finally:
            await page.close()
            await ctx.close()

        return slots

    @staticmethod
    def _parse_calendar_date(text: str) -> datetime.datetime | None:
        """Attempt to parse a date from calendar cell text."""
        text = text.strip()
        for fmt in ("%B %d, %Y", "%d %B %Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.datetime.strptime(text, fmt).replace(
                    hour=9, minute=0, tzinfo=datetime.UTC
                )
            except ValueError:
                continue
        # Try extracting just the day number if in a month view
        match = re.search(r"\d+", text)
        if match:
            day = int(match.group())
            now = datetime.datetime.now(datetime.UTC)
            return now.replace(day=day, hour=9, minute=0, second=0, microsecond=0)
        return None

    @staticmethod
    def _visa_type_to_code(visa_type: str | None) -> str:
        """Map visa type string to VFS category code."""
        mapping = {
            "schengen c": "002",
            "national d": "003",
            "tourist": "002",
            "business": "004",
            "student": "005",
        }
        if visa_type:
            return mapping.get(visa_type.lower(), "002")
        return "002"

    # ── Booking ────────────────────────────────────────────────────────

    async def book(self, slot: Slot, user_profile: dict) -> BookingResult:
        """
        Book a slot via Playwright.
        Returns NEED_USER_ACTION if captcha/verification is required.
        """
        ctx = await self._create_context()
        page = await ctx.new_page()

        try:
            # Navigate to booking page
            url = slot.url or f"{self.BASE_URL}/book-an-appointment"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Check if login is needed
            if "/login" in page.url:
                return BookingResult(
                    status=BookingStatus.NEED_USER_ACTION,
                    message=(
                        "Необходимо войти в аккаунт VFS Global.\n"
                        "Перейдите по ссылке, авторизуйтесь и нажмите 'Продолжить'."
                    ),
                    details={"action_type": "login", "url": page.url},
                )

            # Try to select the date on the calendar
            target_date = slot.datetime_utc.strftime("%B %-d, %Y")
            date_cell = page.locator(f'[aria-label="{target_date}"], td:has-text("{slot.datetime_utc.day}")')

            if await date_cell.count() > 0:
                await date_cell.first.click()
                await asyncio.sleep(1)
            else:
                return BookingResult(
                    status=BookingStatus.FAILED,
                    message="Не удалось найти выбранную дату на календаре. Слот мог быть занят.",
                )

            # Check for time slot selection
            time_slots = page.locator("[class*='time-slot'], [class*='slot-time']")
            if await time_slots.count() > 0:
                await time_slots.first.click()
                await asyncio.sleep(1)

            # Check for captcha
            captcha = page.locator(
                "iframe[src*='recaptcha'], "
                "app-cloudflare-captcha-container, "
                "[class*='captcha']"
            )
            if await captcha.count() > 0:
                return BookingResult(
                    status=BookingStatus.NEED_USER_ACTION,
                    message=(
                        "Обнаружена капча на странице бронирования.\n"
                        "Пожалуйста, решите капчу и нажмите 'Продолжить'."
                    ),
                    details={
                        "action_type": "captcha",
                        "url": page.url,
                        "page_title": await page.title(),
                    },
                )

            # Try to confirm booking
            confirm_btn = page.locator(
                "button:has-text('Confirm'), "
                "button:has-text('Submit'), "
                "button:has-text('Book')"
            )
            if await confirm_btn.count() > 0:
                await confirm_btn.first.click()
                await asyncio.sleep(3)

                # Check for success indicators
                success = page.locator(
                    "[class*='success'], "
                    "[class*='confirmation'], "
                    ":has-text('confirmed'), "
                    ":has-text('reference number')"
                )
                if await success.count() > 0:
                    confirmation_text = await success.first.inner_text()
                    return BookingResult(
                        status=BookingStatus.SUCCESS,
                        message=f"Бронирование подтверждено!\n{confirmation_text}",
                    )

            return BookingResult(
                status=BookingStatus.NEED_USER_ACTION,
                message=(
                    "Слот выбран, но требуется ручное подтверждение.\n"
                    "Проверьте браузерную сессию и завершите бронирование."
                ),
                details={"action_type": "confirm", "url": page.url},
            )

        except Exception as exc:
            log.error("vfs.book.error", error=str(exc))
            return BookingResult(
                status=BookingStatus.FAILED,
                message=f"Ошибка при бронировании: {str(exc)}",
            )
        finally:
            await page.close()
            await ctx.close()

    async def close(self) -> None:
        if self._browser and self._browser.is_connected():
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
