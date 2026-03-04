"""
BLS Spain (BLS International) provider for Spanish visa appointments.

URL: https://spain-russia.blsspainglobal.com/
BLS International handles visa processing for Spain in Russia and other countries.

Uses Playwright for all interactions — no public API.
"""

import asyncio
import datetime
import re

import structlog
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.providers.base import BaseProvider
from app.providers.schemas import BookingResult, BookingStatus, MonitorCriteria, Slot

log = structlog.get_logger()

BLS_PORTALS: dict[str, dict] = {
    "Spain": {
        "domain": "spain-russia.blsspainglobal.com",
        "cities": {
            "Moscow": "moscow",
            "Saint Petersburg": "saint-petersburg",
        },
    },
}


class BLSSpainProvider(BaseProvider):
    """
    BLS Spain visa appointment provider.

    Flow:
    1. Login via Playwright (email + password)
    2. Navigate to appointment scheduling
    3. Parse calendar for available dates
    4. Book with human-in-the-loop for captcha
    """

    name: str = "bls_spain"

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
                ],
            )
        return self._browser

    async def _create_context(self) -> BrowserContext:
        browser = await self._ensure_browser()
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return ctx

    async def fetch_availability(self, criteria: MonitorCriteria) -> list[Slot]:
        """Navigate to BLS Spain and parse available appointment slots."""
        portal = BLS_PORTALS.get("Spain", {})
        domain = portal.get("domain", "spain-russia.blsspainglobal.com")

        ctx = await self._create_context()
        page = await ctx.new_page()
        slots: list[Slot] = []

        try:
            url = f"https://{domain}"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)

            # Try to find appointment/booking link
            book_link = page.locator(
                'a:has-text("Book Appointment"), '
                'a:has-text("Schedule"), '
                'a[href*="appointment"], '
                'a[href*="booking"]'
            )
            if await book_link.count() > 0:
                await book_link.first.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(2)

            # Check if login required
            if await self._needs_login(page):
                log.info("bls.fetch.login_required")
                return []

            # Parse calendar / available dates
            slots = await self._parse_slots(page, criteria)

            # Also try intercepting XHR
            if not slots:
                slots = await self._intercept_api(page, criteria)

        except Exception as exc:
            log.error("bls.fetch.error", error=str(exc))
        finally:
            await page.close()
            await ctx.close()

        return slots

    async def _needs_login(self, page: Page) -> bool:
        login_indicators = page.locator(
            'input[type="email"], input[name="email"], '
            'form[action*="login"], #loginForm'
        )
        return await login_indicators.count() > 0

    async def _parse_slots(
        self, page: Page, criteria: MonitorCriteria
    ) -> list[Slot]:
        slots: list[Slot] = []

        selectors = [
            "td.available:not(.disabled)",
            "td[class*='available']",
            ".calendar td:not(.unavailable):not(.booked)",
            "[data-available='true']",
            ".slot-available",
            ".day-cell.open",
        ]

        for selector in selectors:
            elements = await page.locator(selector).all()
            if elements:
                log.info("bls.parse.found", selector=selector, count=len(elements))
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
                                country="Spain",
                                center=criteria.city or criteria.center or "",
                                datetime_utc=dt,
                                visa_type=criteria.visa_type or "Schengen C",
                                url=page.url,
                            )
                        )
                    except Exception:
                        continue
                break

        return slots

    async def _intercept_api(
        self, page: Page, criteria: MonitorCriteria
    ) -> list[Slot]:
        """Intercept XHR responses with appointment data."""
        slots: list[Slot] = []
        responses: list[dict] = []

        async def on_response(response):
            url = response.url.lower()
            if any(kw in url for kw in ["appointment", "slot", "calendar", "available"]):
                try:
                    data = await response.json()
                    responses.append({"url": response.url, "data": data})
                except Exception:
                    pass

        page.on("response", on_response)
        try:
            await page.reload(wait_until="networkidle", timeout=15000)
            await asyncio.sleep(3)
        except Exception:
            pass
        page.remove_listener("response", on_response)

        for resp in responses:
            data = resp["data"]
            items = data if isinstance(data, list) else data.get("slots", data.get("data", []))
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    date_str = item.get("date") or item.get("slotDate") or ""
                    if date_str:
                        try:
                            dt = datetime.datetime.fromisoformat(
                                date_str.replace("Z", "+00:00")
                            )
                            slots.append(
                                Slot(
                                    provider=self.name,
                                    country="Spain",
                                    center=criteria.city or "",
                                    datetime_utc=dt,
                                    visa_type=criteria.visa_type or "Schengen C",
                                    url=resp["url"],
                                    raw=item,
                                )
                            )
                        except ValueError:
                            continue

        return slots

    @staticmethod
    def _parse_date(text: str | None) -> datetime.datetime | None:
        if not text:
            return None
        text = text.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%B %d, %Y", "%d %B %Y"):
            try:
                return datetime.datetime.strptime(text, fmt).replace(
                    hour=9, minute=0, tzinfo=datetime.UTC
                )
            except ValueError:
                continue
        return None

    async def book(self, slot: Slot, user_profile: dict) -> BookingResult:
        """Attempt to book via Playwright with human-in-the-loop."""
        ctx = await self._create_context()
        page = await ctx.new_page()

        try:
            url = slot.url or "https://spain-russia.blsspainglobal.com"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            if await self._needs_login(page):
                email = user_profile.get("bls_email", "")
                password = user_profile.get("bls_password", "")

                if not email or not password:
                    return BookingResult(
                        status=BookingStatus.NEED_USER_ACTION,
                        message=(
                            "Для бронирования нужны логин/пароль от BLS Spain.\n"
                            "Задайте их через 'Учётные данные' в меню."
                        ),
                        details={"action_type": "login_credentials"},
                    )

                # Fill login form
                await page.locator('input[type="email"], input[name="email"]').first.fill(email)
                await page.locator('input[type="password"]').first.fill(password)
                await page.locator('button[type="submit"]').first.click()
                await page.wait_for_load_state("networkidle", timeout=15000)
                await asyncio.sleep(2)

            # Try to select date
            target = slot.datetime_utc.strftime("%Y-%m-%d")
            date_cell = page.locator(f'[data-date="{target}"], td:has-text("{slot.datetime_utc.day}")')
            if await date_cell.count() > 0:
                await date_cell.first.click()
                await asyncio.sleep(1)
            else:
                return BookingResult(
                    status=BookingStatus.FAILED,
                    message="Дата не найдена на календаре. Слот мог быть занят.",
                )

            # Check for captcha
            captcha = page.locator("iframe[src*='recaptcha'], [class*='captcha']")
            if await captcha.count() > 0:
                return BookingResult(
                    status=BookingStatus.NEED_USER_ACTION,
                    message="Обнаружена капча. Решите её и нажмите 'Продолжить'.",
                    details={"action_type": "captcha", "url": page.url},
                )

            # Try confirm
            confirm = page.locator(
                "button:has-text('Confirm'), button:has-text('Submit'), button:has-text('Book')"
            )
            if await confirm.count() > 0:
                await confirm.first.click()
                await asyncio.sleep(3)

                page_text = await page.inner_text("body")
                if any(kw in page_text.lower() for kw in ["confirmed", "success", "booked"]):
                    return BookingResult(
                        status=BookingStatus.SUCCESS,
                        message="Запись на BLS Spain подтверждена!",
                    )

            return BookingResult(
                status=BookingStatus.NEED_USER_ACTION,
                message=f"Требуется ручное подтверждение.\nСсылка: {page.url}",
                details={"action_type": "manual_confirm", "url": page.url},
            )

        except Exception as exc:
            log.error("bls.book.error", error=str(exc))
            return BookingResult(
                status=BookingStatus.FAILED,
                message=f"Ошибка бронирования: {str(exc)}",
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
