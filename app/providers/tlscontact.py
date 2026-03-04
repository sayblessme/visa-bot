"""
TLScontact provider.

Uses Playwright for all interactions — TLScontact has no public API.
Protected by Cloudflare WAF with TLS fingerprinting and IP rate limiting.

URL patterns:
  - Portal: https://visas-{country}.tlscontact.com/
  - Registration: .../registration?issuerId={issuerCode}
  - Workflow: .../workflow/appointment-booking

IssuerID format: {origin_country}{CITY}2{dest_country}
  Example: ruMOW2de = Russia/Moscow -> Germany
"""

import asyncio
import datetime
import json
import re

import structlog
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.providers.base import BaseProvider
from app.providers.schemas import BookingResult, BookingStatus, MonitorCriteria, Slot

log = structlog.get_logger()

# Known TLScontact issuer codes and portals
TLS_PORTALS: dict[str, dict] = {
    "Germany": {
        "domain": "visas-de.tlscontact.com",
        "issuers": {
            "Moscow": "ruMOW2de",
            "Saint Petersburg": "ruLED2de",
            "Novosibirsk": "ruOVB2de",
            "Kaliningrad": "ruKGD2de",
            "Yekaterinburg": "ruSVX2de",
        },
    },
    "France": {
        "domain": "visas-fr.tlscontact.com",
        "issuers": {
            "Moscow": "ruMOW2fr",
            "Saint Petersburg": "ruLED2fr",
        },
    },
    "Italy": {
        "domain": "visas-it.tlscontact.com",
        "issuers": {
            "Moscow": "ruMOW2it",
        },
    },
    "Spain": {
        "domain": "visas-es.tlscontact.com",
        "issuers": {
            "Moscow": "ruMOW2es",
        },
    },
    "Austria": {
        "domain": "visas-at.tlscontact.com",
        "issuers": {
            "Moscow": "ruMOW2at",
        },
    },
    "Czech Republic": {
        "domain": "visas-cz.tlscontact.com",
        "issuers": {
            "Moscow": "ruMOW2cz",
            "Yekaterinburg": "ruSVX2cz",
        },
    },
    "Greece": {
        "domain": "visas-gr.tlscontact.com",
        "issuers": {
            "Moscow": "ruMOW2gr",
        },
    },
    "Portugal": {
        "domain": "visas-pt.tlscontact.com",
        "issuers": {
            "Moscow": "ruMOW2pt",
        },
    },
    "Netherlands": {
        "domain": "visas-nl.tlscontact.com",
        "issuers": {
            "Moscow": "ruMOW2nl",
        },
    },
    "Poland": {
        "domain": "visas-pl.tlscontact.com",
        "issuers": {
            "Moscow": "ruMOW2pl",
        },
    },
}


class TLScontactProvider(BaseProvider):
    """
    TLScontact visa appointment provider.

    Flow:
    1. Login via Playwright (email + password)
    2. Navigate to appointment booking workflow
    3. Parse available dates from the calendar
    4. For booking: select date/time, fill form, handle Cloudflare checks
    5. Human-in-the-loop if any verification is needed

    Rate limit: max 5-6 page loads per day to avoid IP block.
    """

    name: str = "tlscontact"

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._pw = None
        self._browser: Browser | None = None

    async def _ensure_browser(self) -> Browser:
        if self._browser is None or not self._browser.is_connected():
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=self._headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
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
            timezone_id="Europe/Moscow",
        )
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'ru']});
            window.chrome = {runtime: {}};
        """)
        return ctx

    def _resolve_portal(self, country: str, city: str | None) -> tuple[str, str]:
        """Resolve TLScontact domain and issuerID for country/city."""
        portal = TLS_PORTALS.get(country, {})
        domain = portal.get("domain", "visas-de.tlscontact.com")
        issuers = portal.get("issuers", {})

        if city and city in issuers:
            issuer = issuers[city]
        else:
            # Default: first available issuer (usually Moscow)
            issuer = next(iter(issuers.values()), "ruMOW2de")

        return domain, issuer

    # ── Authentication ─────────────────────────────────────────────────

    async def login(self, page: Page, email: str, password: str) -> bool:
        """
        Login to TLScontact account.
        Returns True if login succeeded.
        """
        try:
            # Find and fill email
            email_input = page.locator(
                'input[type="email"], '
                'input[name="email"], '
                'input[placeholder*="mail"], '
                '#email'
            )
            await email_input.wait_for(state="visible", timeout=10000)
            await email_input.fill(email)
            await asyncio.sleep(0.5)

            # Find and fill password
            pass_input = page.locator(
                'input[type="password"], '
                'input[name="password"], '
                '#password'
            )
            await pass_input.fill(password)
            await asyncio.sleep(0.5)

            # Click login button
            login_btn = page.locator(
                'button[type="submit"], '
                'button:has-text("Sign in"), '
                'button:has-text("Log in"), '
                'button:has-text("Login")'
            )
            await login_btn.click()

            # Wait for page to load after login
            await page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(2)

            # Check if we're past the login page
            if "login" not in page.url.lower() and "registration" not in page.url.lower():
                log.info("tls.login.success")
                return True

            log.warning("tls.login.still_on_login_page", url=page.url)
            return False

        except Exception as exc:
            log.error("tls.login.error", error=str(exc))
            return False

    # ── Slot Monitoring ────────────────────────────────────────────────

    async def fetch_availability(self, criteria: MonitorCriteria) -> list[Slot]:
        """
        Navigate to TLScontact calendar and parse available appointment slots.
        """
        country = criteria.country or "Germany"
        city = criteria.city or criteria.center
        domain, issuer_id = self._resolve_portal(country, city)

        ctx = await self._create_context()
        page = await ctx.new_page()
        slots: list[Slot] = []

        try:
            # Navigate to the appointment page
            base_url = f"https://{domain}"
            await page.goto(base_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)

            # Check for Cloudflare challenge
            if await self._is_cloudflare_blocked(page):
                log.warning("tls.fetch.cloudflare_block", domain=domain)
                return []

            # Check for robot landing page
            if await self._is_robot_page(page):
                log.warning("tls.fetch.robot_page", domain=domain)
                return []

            # Try to navigate to appointment booking
            booking_url = f"{base_url}/en/workflow/appointment-booking"
            await page.goto(booking_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # If redirected to login — need credentials
            if "login" in page.url.lower() or "registration" in page.url.lower():
                log.info("tls.fetch.login_required", url=page.url)
                # Try to intercept appointment data from network requests
                slots = await self._intercept_slot_data(page, criteria)
                if not slots:
                    log.info("tls.fetch.need_login", msg="Login required to see slots")
                return slots

            # Parse calendar slots from the page
            slots = await self._parse_calendar_page(page, country, city or "", criteria)

        except Exception as exc:
            log.error("tls.fetch.error", error=str(exc))
        finally:
            await page.close()
            await ctx.close()

        return slots

    async def _parse_calendar_page(
        self, page: Page, country: str, center: str, criteria: MonitorCriteria
    ) -> list[Slot]:
        """Parse available dates from the TLScontact calendar page."""
        slots: list[Slot] = []

        # TLScontact uses various calendar implementations
        # Try multiple selector strategies

        # Strategy 1: Standard date cells (available/clickable)
        selectors = [
            "td.available:not(.disabled)",
            "td[class*='available']",
            ".appointment-table td:not(.unavailable):not(.disabled)",
            ".calendar-day.available",
            "[data-available='true']",
            ".tls-calendar td.open",
            "td.day:not(.off):not(.disabled)",
        ]

        for selector in selectors:
            elements = await page.locator(selector).all()
            if elements:
                log.info("tls.parse.found_elements", selector=selector, count=len(elements))
                for el in elements:
                    try:
                        date_text = (
                            await el.get_attribute("data-date")
                            or await el.get_attribute("aria-label")
                            or await el.inner_text()
                        )
                        dt = self._parse_date(date_text)
                        if dt is None:
                            continue

                        if criteria.date_from and dt.date() < criteria.date_from:
                            continue
                        if criteria.date_to and dt.date() > criteria.date_to:
                            continue

                        slots.append(
                            Slot(
                                provider=self.name,
                                country=country,
                                center=center,
                                datetime_utc=dt,
                                visa_type=criteria.visa_type or "",
                                url=page.url,
                            )
                        )
                    except Exception:
                        continue
                break

        # Strategy 2: Intercept XHR responses with slot data
        if not slots:
            slots = await self._intercept_slot_data(page, criteria)

        return slots

    async def _intercept_slot_data(
        self, page: Page, criteria: MonitorCriteria
    ) -> list[Slot]:
        """Intercept network requests that may contain slot data."""
        slots: list[Slot] = []
        responses: list[dict] = []

        async def on_response(response):
            url = response.url.lower()
            if any(kw in url for kw in ["appointment", "slot", "calendar", "availability"]):
                try:
                    data = await response.json()
                    responses.append({"url": response.url, "data": data})
                except Exception:
                    pass

        page.on("response", on_response)

        # Trigger a reload to capture XHR
        try:
            await page.reload(wait_until="networkidle", timeout=15000)
            await asyncio.sleep(3)
        except Exception:
            pass

        page.remove_listener("response", on_response)

        # Parse any captured responses
        country = criteria.country or "Germany"
        center = criteria.city or criteria.center or ""
        for resp in responses:
            data = resp["data"]
            if isinstance(data, list):
                for item in data:
                    dt = self._extract_datetime_from_item(item)
                    if dt:
                        slots.append(
                            Slot(
                                provider=self.name,
                                country=country,
                                center=center,
                                datetime_utc=dt,
                                visa_type=criteria.visa_type or "",
                                url=resp["url"],
                                raw=item,
                            )
                        )
            elif isinstance(data, dict):
                for key in ("slots", "dates", "appointments", "available", "data"):
                    if key in data and isinstance(data[key], list):
                        for item in data[key]:
                            dt = self._extract_datetime_from_item(item)
                            if dt:
                                slots.append(
                                    Slot(
                                        provider=self.name,
                                        country=country,
                                        center=center,
                                        datetime_utc=dt,
                                        visa_type=criteria.visa_type or "",
                                        url=resp["url"],
                                        raw=item,
                                    )
                                )

        return slots

    @staticmethod
    def _extract_datetime_from_item(item) -> datetime.datetime | None:
        """Try to extract a datetime from a slot data item."""
        if isinstance(item, str):
            try:
                return datetime.datetime.fromisoformat(item.replace("Z", "+00:00"))
            except ValueError:
                return None

        if isinstance(item, dict):
            for key in ("date", "datetime", "slot_date", "appointment_date", "start"):
                val = item.get(key)
                if val:
                    try:
                        if isinstance(val, str):
                            return datetime.datetime.fromisoformat(
                                val.replace("Z", "+00:00")
                            )
                    except ValueError:
                        continue
        return None

    async def _is_cloudflare_blocked(self, page: Page) -> bool:
        """Check if page is showing a Cloudflare challenge."""
        title = await page.title()
        content = await page.content()
        indicators = [
            "Just a moment" in title,
            "Checking your browser" in content,
            "cf-browser-verification" in content,
            "challenge-platform" in content,
        ]
        return any(indicators)

    async def _is_robot_page(self, page: Page) -> bool:
        """Check if TLScontact is showing the robot landing page."""
        content = await page.content()
        indicators = [
            "temporarily blocked" in content.lower(),
            "maximum allowed connections" in content.lower(),
            "unauthorized use" in content.lower(),
        ]
        return any(indicators)

    @staticmethod
    def _parse_date(text: str | None) -> datetime.datetime | None:
        """Parse date from various calendar formats."""
        if not text:
            return None
        text = text.strip()
        for fmt in (
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d.%m.%Y",
            "%B %d, %Y",
            "%d %B %Y",
            "%m/%d/%Y",
        ):
            try:
                return datetime.datetime.strptime(text, fmt).replace(
                    hour=9, minute=0, tzinfo=datetime.UTC
                )
            except ValueError:
                continue
        return None

    # ── Booking ────────────────────────────────────────────────────────

    async def book(self, slot: Slot, user_profile: dict) -> BookingResult:
        """
        Attempt to book a slot on TLScontact via Playwright.
        Human-in-the-loop for any verification steps.
        """
        country = slot.country or "Germany"
        center = slot.center
        domain, issuer_id = self._resolve_portal(country, center)

        ctx = await self._create_context()
        page = await ctx.new_page()

        try:
            base_url = f"https://{domain}"
            await page.goto(base_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Check for blocks
            if await self._is_cloudflare_blocked(page):
                return BookingResult(
                    status=BookingStatus.FAILED,
                    message="Cloudflare заблокировал доступ. Попробуйте позже.",
                    details={"reason": "cloudflare_block"},
                )

            if await self._is_robot_page(page):
                return BookingResult(
                    status=BookingStatus.FAILED,
                    message="TLScontact обнаружил автоматический доступ. Достигнут лимит подключений.",
                    details={"reason": "robot_page"},
                )

            # Check if login needed
            if "login" in page.url.lower() or "registration" in page.url.lower():
                email = user_profile.get("tls_email", "")
                password = user_profile.get("tls_password", "")

                if not email or not password:
                    return BookingResult(
                        status=BookingStatus.NEED_USER_ACTION,
                        message=(
                            "Для бронирования нужны логин и пароль от TLScontact.\n"
                            "Введите их в настройках бота или авторизуйтесь вручную."
                        ),
                        details={"action_type": "login_credentials"},
                    )

                logged_in = await self.login(page, email, password)
                if not logged_in:
                    return BookingResult(
                        status=BookingStatus.NEED_USER_ACTION,
                        message="Не удалось войти в аккаунт TLScontact. Проверьте логин/пароль.",
                        details={"action_type": "login_failed"},
                    )

            # Navigate to appointment booking
            booking_url = f"{base_url}/en/workflow/appointment-booking"
            await page.goto(booking_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # Try to find and click the target date
            target_date_str = slot.datetime_utc.strftime("%Y-%m-%d")
            date_selectors = [
                f'td[data-date="{target_date_str}"]',
                f'[aria-label*="{slot.datetime_utc.strftime("%B")}"][aria-label*="{slot.datetime_utc.day}"]',
                f'td:has-text("{slot.datetime_utc.day}")',
            ]

            date_clicked = False
            for selector in date_selectors:
                el = page.locator(selector)
                if await el.count() > 0:
                    await el.first.click()
                    date_clicked = True
                    await asyncio.sleep(1)
                    break

            if not date_clicked:
                return BookingResult(
                    status=BookingStatus.FAILED,
                    message="Не удалось найти дату на календаре. Слот мог быть уже занят.",
                )

            # Look for time slots
            time_slot = page.locator(
                ".time-slot, "
                "[class*='slot'], "
                "input[type='radio'][name*='time'], "
                "button[class*='slot']"
            )
            if await time_slot.count() > 0:
                await time_slot.first.click()
                await asyncio.sleep(1)

            # Look for confirm/submit button
            confirm = page.locator(
                'button:has-text("Confirm"), '
                'button:has-text("Submit"), '
                'button:has-text("Book"), '
                'button[type="submit"]'
            )
            if await confirm.count() > 0:
                await confirm.first.click()
                await asyncio.sleep(3)

                # Check result
                page_text = await page.inner_text("body")
                if any(kw in page_text.lower() for kw in ["confirmed", "confirmation", "success", "booked"]):
                    return BookingResult(
                        status=BookingStatus.SUCCESS,
                        message="Запись на TLScontact подтверждена!",
                        details={"url": page.url},
                    )

            # If we got here — something needs manual attention
            return BookingResult(
                status=BookingStatus.NEED_USER_ACTION,
                message=(
                    "Дата выбрана, но для завершения бронирования требуется ваше участие.\n"
                    f"Перейдите по ссылке: {page.url}"
                ),
                details={"action_type": "manual_confirm", "url": page.url},
            )

        except Exception as exc:
            log.error("tls.book.error", error=str(exc))
            return BookingResult(
                status=BookingStatus.FAILED,
                message=f"Ошибка при бронировании на TLScontact: {str(exc)}",
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
