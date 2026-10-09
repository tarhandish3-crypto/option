# automation/brokers/Omex_khobregan.py
# -*- coding: utf-8 -*-

"""
اتوماسیون ارسال استراتژی اختیار معامله به سامانه خبرگان کارگزاری اومکس (tsetab)

روش‌های ارسال:
  A) Selenium  -> open_browser() + wait_for_login() + submit_strategy()
  B) DevTools  -> submit_via_devtools_snippet()  (بدون Selenium)

جریان کار Selenium:
  1. open_browser()   - مرورگر باز می‌شود، نام‌کاربری و رمز پر می‌شوند
  2. wait_for_login() - برنامه منتظر می‌ماند تا کاربر کپچا را حل کرده و login کند
  3. extract_open_positions() - موقعیت‌های باز از تب «موقعیت های اختیار» استخراج می‌شوند
  4. submit_strategy(positions_str) - استراتژی در فرم برآورد وارد می‌شود
  5. close_browser()

جریان کار DevTools Snippet:
  1. get_devtools_snippet_server() - دریافت Singleton سرور
  2. submit_via_devtools_snippet(positions_text) - ارسال به سرور
  3. کاربر در F12 - Console، اسکریپت را اجرا می‌کند
  4. اسکریپت سرور را poll کرده و فرم را پر می‌کند

فرمت ورودی submit_strategy:
  "1*ضهرم6045 (Long) + 1*اهرم (Long Stock) + 1*طهرم6045 (Short)"
  یا همان فرمت Positions پنجره اسکنر:
  "اهرم (1xBUY) | ضهرم6045 (1xSELL)"

هر دو فرمت پشتیبانی می‌شوند.
"""

import re
import time
import uuid
import threading
import logging
from typing import List, Dict, Optional

import pandas as pd

# ─────────────────────────────────────────────────────────────
# WebDriver Imports (Selenium)
# ─────────────────────────────────────────────────────────────

from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    WebDriverException,
)

# ─────────────────────────────────────────────────────────────
# FastAPI Imports (DevTools Snippet Server)
# ─────────────────────────────────────────────────────────────

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import requests


logger = logging.getLogger("OptionScanner.Automation.OmexKhobregan")


# ─────────────────────────────────────────────────────────────
# ثابت‌ها
# ─────────────────────────────────────────────────────────────

TARGET_URL = "https://khobregan.tsetab.ir/#/login"
MAX_WAIT = 15
LOGIN_POLL = 2
LOGIN_TIMEOUT = 180

# DevTools Snippet Server
SNIPPET_HOST = "127.0.0.1"
SNIPPET_PORT = 8000
SNIPPET_URL = f"http://{SNIPPET_HOST}:{SNIPPET_PORT}"
SNIPPET_TIMEOUT = 5


# ═════════════════════════════════════════════════════════════
# بخش ۱: توابع کمکی (مستقل از کلاس)
# ═════════════════════════════════════════════════════════════

def convert_to_float(value: str) -> float:
    """تبدیل رشته فارسی/انگلیسی به عدد اعشاری."""
    if not value or value.strip() in ['-', '', '—', '–', ' ', '\u200c']:
        return 0.0
    try:
        cleaned = value.replace(',', '').replace('٬', '')
        cleaned = cleaned.replace('(', '').replace(')', '')
        cleaned = cleaned.replace('\n', '').replace('\t', '').strip()
        fa_to_en = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
        cleaned = cleaned.translate(fa_to_en)
        return float(cleaned)
    except (ValueError, AttributeError) as e:
        logger.warning("Cannot convert '%s' to number: %s", value, e)
        return 0.0


def parse_scanner_positions(positions_text: str) -> List[Dict]:
    """
    تبدیل فرمت ستون Positions اسکنر به لیست دیکشنری.

    فرمت اسکنر:  "اهرم (1xBUY) | ضهرم6045 (1xSELL)"
    فرمت استاندارد: "1*ضهرم6045 (Long) + 1*اهرم (Long Stock)"
    """
    positions = []

    # فرمت اسکنر:  نماد (NxSIDE)
    scanner_pattern = re.compile(
        r'(\S+)\s*\((\d+)x(BUY|SELL)\)',
        re.IGNORECASE
    )
    scanner_matches = scanner_pattern.findall(positions_text)

    if scanner_matches:
        for symbol, qty, side in scanner_matches:
            direction = 'Long' if side.upper() == 'BUY' else 'Short'
            positions.append({
                'symbol': symbol.strip(),
                'quantity': str(int(qty)),
                'direction': direction,
            })
    else:
        # فرمت استاندارد: N*نماد (Long/Short ...)
        standard_pattern = re.compile(
            r'([\d.]+)\s*\*\s*(\S+)\s*\(\s*(Long|Short)(?:\s+(?:Stock|Call|Put))?\s*\)',
            re.IGNORECASE
        )
        for part in positions_text.split('+'):
            m = standard_pattern.match(part.strip())
            if not m:
                logger.warning(
                    "Part '%s' did not match any pattern - skipped",
                    part.strip()
                )
                continue
            qty_raw, symbol, direction = m.groups()
            qty_f = float(qty_raw)
            qty = str(int(qty_f)) if qty_f.is_integer() else str(qty_f)
            positions.append({
                'symbol': symbol.strip(),
                'quantity': qty,
                'direction': direction.capitalize(),
            })

    # مرتب‌سازی: سهم پایه اول، بعد ض (Call)، بعد ط (Put)
    def sort_key(x):
        s = x['symbol']
        if s.startswith('ض'):
            g = 1
        elif s.startswith('ط'):
            g = 2
        else:
            g = 0
        return (g, 0 if x['direction'] == 'Long' else 1)

    return sorted(positions, key=sort_key)


def check_position_conflicts(
    new_positions: List[Dict],
    existing_positions: List[Dict]) -> List[Dict]:
    """بررسی تعارض موقعیت معکوس."""
    conflicts = []
    for pos in new_positions:
        symbol = pos['symbol']
        direction = pos['direction']
        existing = next(
            (p for p in existing_positions if p['نماد'] == symbol), None)
        if not existing:
            continue

        buy_pos = existing.get('موقعیت خرید', 0.0) or 0.0
        sell_pos = existing.get('موقعیت فروش', 0.0) or 0.0

        if direction == 'Long' and sell_pos > 0:
            conflicts.append({
                'symbol': symbol,
                'message': f"نماد {symbol}: موقعیت فروش از قبل وجود دارد - موقعیت خرید معکوس است",
            })
        elif direction == 'Short' and buy_pos > 0:
            conflicts.append({
                'symbol': symbol,
                'message': f"نماد {symbol}: موقعیت خرید از قبل وجود دارد - موقعیت فروش معکوس است",
            })
    return conflicts


# ═════════════════════════════════════════════════════════════
# بخش ۲: DevTools Snippet Server
# ═════════════════════════════════════════════════════════════

class _SnippetPayload(BaseModel):
    """مدل Pydantic برای payload سرور Snippet."""
    strategy: str = ""
    underlying: str = ""
    legs: List[Dict] = []


class _AckPayload(BaseModel):
    """مدل Pydantic برای ack."""
    order_id: str = ""


class DevToolsSnippetServer:
    """
    سرور FastAPI داخلی برای ارتباط با DevTools Snippet.

    این سرور:
    - Thread-Safe (با RLock)
    - فقط یک سفارش در انتظار (State واحد)
    - ۴ endpoint: /health, /select-position, /pending-order, /ack-order
    - قابل شروع/توقف

    نحوه استفاده:
        server = get_devtools_snippet_server()
        server.start()
        # ... ارسال سفارش ...
        server.stop()
    """

    def __init__(self, host: str = SNIPPET_HOST, port: int = SNIPPET_PORT):
        self.host = host
        self.port = port
        self.app = FastAPI(title="Omex DevTools Snippet Bridge")
        self._pending: Optional[dict] = None
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._server: Optional[uvicorn.Server] = None
        self._running = False

        # CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self._setup_routes()
        logger.info("DevToolsSnippetServer initialized on %s:%s", host, port)

    def _setup_routes(self):
        """تنظیم ۴ endpoint سرور."""
        app = self.app

        # ─── ۱. /health ───
        @app.get("/health")
        def health():
            with self._lock:
                return {
                    "status": "ok",
                    "has_pending": self._pending is not None,
                    "running": self._running,
                }

        # ─── ۲. /select-position ───
        @app.post("/select-position")
        def select_position(payload: _SnippetPayload):
            """دریافت موقعیت از UI و ذخیره در State."""
            with self._lock:
                self._pending = {
                    "order_id": str(uuid.uuid4())[:8],
                    "strategy": payload.strategy,
                    "underlying": payload.underlying,
                    "legs": payload.legs,
                    "timestamp": time.time(),
                }
                logger.info(
                    "Position queued: id=%s strategy=%s underlying=%s legs=%d",
                    self._pending["order_id"],
                    self._pending["strategy"],
                    self._pending["underlying"],
                    len(self._pending["legs"]),
                )
                return {
                    "status": "ok",
                    "order_id": self._pending["order_id"],
                }

        # ─── ۳. /pending-order ───
        @app.get("/pending-order")
        def get_pending_order():
            """Snippet این را poll می‌کند."""
            with self._lock:
                return {"pending_order": self._pending}

        # ─── ۴. /ack-order ───
        @app.post("/ack-order")
        def ack_order(payload: _AckPayload):
            """Snippet بعد از پر کردن فرم."""
            with self._lock:
                order_id = payload.order_id
                if self._pending and self._pending.get("order_id") == order_id:
                    self._pending = None
                    logger.info("Order acknowledged: id=%s", order_id)
                    return {"status": "acked"}
                return {"status": "not_found"}

    def start(self):
        """شروع سرور در Thread جداگانه."""
        if self._running:
            logger.info("DevToolsSnippetServer already running")
            return

        self._running = True

        def _run():
            config = uvicorn.Config(
                self.app,
                host=self.host,
                port=self.port,
                log_level="warning",
            )
            self._server = uvicorn.Server(config)
            self._server.run()

        self._thread = threading.Thread(
            target=_run,
            daemon=True,
            name="DevToolsSnippetServer",
        )
        self._thread.start()

        # صبر کوتاه برای راه‌اندازی
        time.sleep(0.3)
        logger.info("DevToolsSnippetServer started on %s:%s", self.host, self.port)

    def stop(self):
        """توقف سرور."""
        if not self._running:
            return

        self._running = False
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("DevToolsSnippetServer stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def has_pending(self) -> bool:
        with self._lock:
            return self._pending is not None


# ─── Singleton ───

_devtools_snippet_server: Optional[DevToolsSnippetServer] = None
_devtools_lock = threading.Lock()


def get_devtools_snippet_server() -> DevToolsSnippetServer:
    """دریافت نمونه Singleton از DevToolsSnippetServer."""
    global _devtools_snippet_server
    if _devtools_snippet_server is None:
        with _devtools_lock:
            if _devtools_snippet_server is None:
                _devtools_snippet_server = DevToolsSnippetServer()
    return _devtools_snippet_server


# ═════════════════════════════════════════════════════════════
# بخش ۳: کلاس اصلی Broker
# ═════════════════════════════════════════════════════════════

class OmexKhobreganBroker:
    """
    اتوماسیون ارسال استراتژی به سامانه خبرگان اومکس.

    دو روش پشتیبانی می‌شود:
    1. Selenium (روش سنتی)
    2. DevTools Snippet (روش جدید)

    مثال Selenium:
        broker = OmexKhobreganBroker(username="05-xxx", password="xxxx")
        broker.open_browser()
        broker.wait_for_login()
        positions = broker.extract_open_positions()
        result = broker.submit_strategy("...", positions)

    مثال DevTools Snippet:
        broker = OmexKhobreganBroker()
        result = broker.submit_via_devtools_snippet("اهرم (1xBUY) | ضهرم6045 (1xSELL)")
    """

    def __init__(
        self,
        username: str = "",
        password: str = "",
        headless: bool = False,
        max_wait: int = MAX_WAIT,
        chart_range_percentage: int = 80,):
        self.username = username
        self.password = password
        self.headless = headless
        self.max_wait = max_wait
        self.chart_range_percentage = chart_range_percentage

        # Selenium
        self.driver: Optional[webdriver.Firefox] = None
        self.wait: Optional[WebDriverWait] = None
        self._logged_in = False

        # DevTools Snippet
        self._snippet_running = False

    # ═══════════════════════════════════════════════════════
    # روش ۱: Selenium
    # ═══════════════════════════════════════════════════════

    def open_browser(self) -> bool:
        """مرورگر را باز می‌کند و به صفحه login می‌رود."""
        try:
            opts = FirefoxOptions()
            opts.headless = self.headless
            self.driver = webdriver.Firefox(options=opts)
            self.driver.maximize_window()
            self.wait = WebDriverWait(self.driver, self.max_wait)

            self.driver.get(TARGET_URL)

            # پر کردن یوزرنیم
            username_input = self.wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "c-k-input-text#account-login-username input.o-inputComponent.u-dir-ltr"
            )))
            username_input.clear()
            username_input.send_keys(self.username)

            # پر کردن پسورد
            password_input = self.wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "c-k-input-password#sc-accountLoginPassword input.u-dir-ltr"
            )))
            password_input.clear()
            password_input.send_keys(self.password)

            logger.info("Browser ready - please solve captcha and click login.")
            return True

        except WebDriverException as e:
            logger.error("Error opening browser: %s", e)
            return False

    def wait_for_login(self, timeout: int = LOGIN_TIMEOUT) -> bool:
        """منتظر ورود کاربر می‌ماند."""
        if not self.driver:
            logger.error("Browser not opened.")
            return False

        elapsed = 0
        logger.info("Waiting for user login (max %d seconds)...", timeout)
        while elapsed < timeout:
            try:
                current_url = self.driver.current_url
                if 'login' not in current_url.lower():
                    self._logged_in = True
                    logger.info("Login successful - processing...")
                    time.sleep(2)
                    return True
            except WebDriverException:
                pass
            time.sleep(LOGIN_POLL)
            elapsed += LOGIN_POLL

        logger.error("Login timeout reached.")
        return False

    def close_browser(self) -> None:
        """بستن مرورگر."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self._logged_in = False

    def extract_open_positions(self) -> List[Dict]:
        """استخراج موقعیت‌های باز از AG-Grid."""
        if not self.driver or not self._logged_in:
            logger.error("Please login first to extract positions.")
            return []

        try:
            position_tab = self.wait.until(EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(@class, 'c-tab') and contains(text(), 'موقعیت های اختیار')]"
            )))
            position_tab.click()
            time.sleep(2)

            grid_container = self.driver.find_element(
                By.CSS_SELECTOR, ".ag-body-viewport"
            )

            all_rows: List[Dict] = []
            seen: set = set()
            current_pos = 0
            scroll_step = 200
            max_scrolls = 20

            def _read_visible_rows():
                rows = self.driver.find_elements(
                    By.CSS_SELECTOR, ".ag-center-cols-container .ag-row")
                pinned = self.driver.find_elements(
                    By.CSS_SELECTOR, ".ag-pinned-right-cols-container .ag-row")
                for i in range(min(len(rows), len(pinned))):
                    try:
                        symbol = pinned[i].text.strip()
                        cells = rows[i].find_elements(
                            By.CSS_SELECTOR, ".ag-cell")
                        texts = [c.text.strip()
                                 for c in cells if c.text.strip()]
                        if len(texts) >= 5 and symbol:
                            row = {
                                'نماد': symbol,
                                'نوع اختیار': texts[0],
                                'موقعیت خرید': convert_to_float(texts[3]),
                                'موقعیت فروش': convert_to_float(texts[4]),
                            }
                            h = hash(f"{symbol}{texts[3]}{texts[4]}")
                            if h not in seen:
                                seen.add(h)
                                all_rows.append(row)
                    except Exception:
                        continue

            _read_visible_rows()

            for _ in range(max_scrolls):
                current_pos += scroll_step
                self.driver.execute_script(
                    "arguments[0].scrollTop = arguments[1]",
                    grid_container, current_pos
                )
                time.sleep(0.4)
                _read_visible_rows()
                scroll_height = self.driver.execute_script(
                    "return arguments[0].scrollHeight", grid_container
                )
                if current_pos >= scroll_height:
                    break

            logger.info("%d open positions extracted.", len(all_rows))
            return all_rows

        except Exception as e:
            logger.error("Error extracting open positions: %s", e)
            return []

    def submit_strategy(
        self,
        positions_text: str,
        existing_positions: Optional[List[Dict]] = None,) -> Dict:
        """ارسال استراتژی با Selenium."""
        if not self.driver or not self._logged_in:
            return {
                'success': False,
                'message': "ابتدا باید وارد سیستم شوید.",
                'conflicts': [],
            }

        positions = parse_scanner_positions(positions_text)
        if not positions:
            return {
                'success': False,
                'message': "هیچ موقعیت معتبری در متن ورودی یافت نشد.",
                'conflicts': [],
            }

        existing = existing_positions or []
        conflicts = check_position_conflicts(positions, existing)
        if conflicts:
            msgs = [c['message'] for c in conflicts]
            logger.error("Position conflict detected:\n%s", "\n".join(msgs))
            return {
                'success': False,
                'message': "تعارض موقعیت معکوس:\n" + "\n".join(msgs),
                'conflicts': conflicts,
            }

        try:
            logger.info("Starting to fill %d positions in estimation form...",
                        len(positions))

            self._click_new_estimation()

            for i, pos in enumerate(positions):
                if i > 0:
                    self._add_new_row()
                self._fill_estimation_row(
                    symbol=pos['symbol'],
                    quantity=pos['quantity'],
                    direction=pos['direction'],
                    row_index=i,
                )
                logger.info(
                    "Row %d: %s x %s - %s",
                    i + 1, pos['symbol'], pos['quantity'], pos['direction']
                )

            self._set_chart_range(self.chart_range_percentage)

            persian_title = self._build_persian_title(positions)
            self._set_strategy_title(persian_title)

            logger.info("Strategy submitted successfully: %s", persian_title)
            return {
                'success': True,
                'message': f"استراتژی «{persian_title}» در سامانه ثبت شد.",
                'conflicts': [],
            }

        except Exception as e:
            logger.error("Error submitting strategy: %s", e, exc_info=True)
            return {
                'success': False,
                'message': f"خطا در ارسال: {e}",
                'conflicts': [],
            }

    # ── متدهای داخلی Selenium ──

    def _safe_click(self, element, description: str = "element") -> None:
        try:
            element.click()
        except (ElementClickInterceptedException, StaleElementReferenceException):
            logger.debug("Normal click failed on %s - trying JS", description)
            self.driver.execute_script("arguments[0].click();", element)

    def _click_new_estimation(self) -> None:
        btn = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.e-btnNew")))
        self.driver.execute_script("arguments[0].click();", btn)
        time.sleep(1)

    def _add_new_row(self) -> None:
        btn = self.wait.until(EC.element_to_be_clickable((
            By.CSS_SELECTOR, "div.o-item-row > div:nth-child(1) > button"
        )))
        self._safe_click(btn, "add-row")
        time.sleep(0.5)

    def _fill_estimation_row(
        self,
        symbol: str,
        quantity: str,
        direction: str,
        row_index: int,) -> None:
        # انتخاب نماد
        container = self.wait.until(EC.element_to_be_clickable((
            By.CSS_SELECTOR, "client-instrument-search div.ng-select-container"
        )))
        container.click()
        time.sleep(1.5)

        inp = self.wait.until(EC.element_to_be_clickable((
            By.CSS_SELECTOR, "client-instrument-search input[type='text']"
        )))
        inp.clear()
        inp.send_keys(symbol)
        time.sleep(1)

        first_opt = self.wait.until(EC.element_to_be_clickable((
            By.CSS_SELECTOR, "div.ng-option.ng-star-inserted"
        )))
        first_opt.click()

        # وارد کردن تعداد
        qty_components = self.wait.until(EC.presence_of_all_elements_located((
            By.CSS_SELECTOR, "c-k-input-number[formcontrolname='quantity']"
        )))
        if row_index >= len(qty_components):
            raise RuntimeError(
                f"Quantity component for row {row_index} not found "
                f"(available: {len(qty_components)})"
            )
        qty_input = qty_components[row_index].find_element(
            By.CSS_SELECTOR, "input")
        qty_input.clear()
        qty_input.send_keys(quantity)

        # انتخاب Long/Short
        side_components = self.wait.until(EC.presence_of_all_elements_located((
            By.CSS_SELECTOR,
            "client-option-strategy-estimation-main-ui-order-side"
        )))
        if row_index >= len(side_components):
            raise RuntimeError(f"Side component for row {row_index} not found")
        side_root = side_components[row_index]
        if direction.lower() == "long":
            btn = side_root.find_element(By.CSS_SELECTOR, "div.buy")
            if "-isActive" not in btn.get_attribute("class"):
                self.driver.execute_script(
                    "arguments[0].scrollIntoView(true);", btn)
                btn.click()
        else:
            btn = side_root.find_element(By.CSS_SELECTOR, "div.sell")
            if "-isActive" not in btn.get_attribute("class"):
                self.driver.execute_script(
                    "arguments[0].scrollIntoView(true);", btn)
                btn.click()

        # قفل قیمت
        lock_buttons = self.wait.until(EC.presence_of_all_elements_located((
            By.CSS_SELECTOR,
            "client-option-strategy-estimation-main-ui-lock"
            "[formcontrolname='priceLock'] button"
        )))
        if row_index >= len(lock_buttons):
            raise RuntimeError(f"Lock button for row {row_index} not found")
        lock_btn = lock_buttons[row_index]
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center',behavior:'smooth'});",
            lock_btn
        )
        time.sleep(0.3)
        lock_btn.click()

        # انتظار پر شدن فیلد قیمت
        price_inputs = self.driver.find_elements(
            By.CSS_SELECTOR,
            "c-k-input-number[formcontrolname='price'] input"
        )
        if row_index < len(price_inputs):
            price_inp = price_inputs[row_index]
            try:
                WebDriverWait(self.driver, 5).until(
                    lambda d: price_inp.get_attribute('value') not in ('', None)
                )
            except TimeoutException:
                logger.warning("Price for row %d not filled - continuing",
                               row_index + 1)

    def _set_chart_range(self, value: int) -> None:
        try:
            inp = self.wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "c-k-input-number[formcontrolname='chartRangePercentage'] input"
            )))
            inp.clear()
            inp.send_keys(str(value))
        except TimeoutException:
            logger.warning("Chart range field not found - skipped")

    def _build_persian_title(self, positions: List[Dict]) -> str:
        mapping = {"long": "خرید", "short": "فروش"}
        parts = [
            f"{mapping.get(p['direction'].lower(), p['direction'])} {p['symbol']}"
            for p in positions
        ]
        return "+".join(parts)

    def _set_strategy_title(self, title: str) -> None:
        try:
            inp = self.wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "client-option-strategy-estimation-header "
                "input[formcontrolname='title']"
            )))
            inp.clear()
            inp.send_keys(title)
            logger.info("Strategy title set: %s", title)
        except TimeoutException:
            logger.warning("Strategy title field not found - skipped")

    # ═══════════════════════════════════════════════════════
    # روش ۲: DevTools Snippet
    # ═══════════════════════════════════════════════════════

    def start_snippet_server(self) -> bool:
        """شروع سرور DevTools Snippet."""
        try:
            server = get_devtools_snippet_server()
            if not server.is_running:
                server.start()
            self._snippet_running = server.is_running
            return self._snippet_running
        except Exception as e:
            logger.error("Failed to start DevTools snippet server: %s", e)
            return False

    def stop_snippet_server(self) -> None:
        """توقف سرور DevTools Snippet."""
        try:
            server = get_devtools_snippet_server()
            if server.is_running:
                server.stop()
            self._snippet_running = False
        except Exception as e:
            logger.error("Failed to stop DevTools snippet server: %s", e)

    def is_snippet_server_running(self) -> bool:
        """آیا سرور Snippet در حال اجراست؟"""
        try:
            server = get_devtools_snippet_server()
            return server.is_running
        except Exception:
            return False

    def submit_via_devtools_snippet(
        self,
        positions_text: str,
        strategy_name: str = "",
        underlying: str = "",) -> Dict:
        """
        ارسال موقعیت از طریق DevTools Snippet (بدون Selenium).

        Args:
            positions_text: متن موقعیت (فرمت اسکنر)
            strategy_name: نام استراتژی (اختیاری، برای لاگ)
            underlying: نماد پایه (اختیاری، برای لاگ)

        Returns:
            dict: {'success': bool, 'message': str, 'order_id': str}
        """
        # ۱. بررسی سرور
        server = get_devtools_snippet_server()
        if not server.is_running:
            if not self.start_snippet_server():
                return {
                    'success': False,
                    'message': "سرور DevTools Snippet اجرا نشد.",
                    'order_id': '',
                }

        # ۲. پارس موقعیت‌ها
        try:
            positions = parse_scanner_positions(positions_text)
        except Exception as e:
            logger.error("Failed to parse positions: %s", e)
            return {
                'success': False,
                'message': f"خطا در پارس موقعیت‌ها: {e}",
                'order_id': '',
            }

        if not positions:
            return {
                'success': False,
                'message': "هیچ موقعیت معتبری در متن ورودی یافت نشد.",
                'order_id': '',
            }

        # ۳. ساخت payload
        legs_payload = [
            {
                "symbol": p['symbol'],
                "side": p['direction'].lower(),
                "quantity": int(p['quantity']),
                "direction": p['direction'],
            }
            for p in positions
        ]

        payload = {
            "strategy": strategy_name,
            "underlying": underlying,
            "legs": legs_payload,}

        # ۴. ارسال به سرور
        try:
            r = requests.post(
                f"{SNIPPET_URL}/select-position",
                json=payload,
                timeout=SNIPPET_TIMEOUT,
            )

            if r.status_code != 200:
                return {
                    'success': False,
                    'message': f"خطای سرور: HTTP {r.status_code}",
                    'order_id': '',
                }

            result = r.json()
            order_id = result.get("order_id", "?")

            logger.info("Position sent via DevTools Snippet: id=%s legs=%d",
                        order_id, len(legs_payload))

            return {
                'success': True,
                'message': (
                    f"موقعیت به DevTools Snippet ارسال شد.\n"
                    f"شناسه سفارش: {order_id}\n\n"
                    f"حالا در مرورگر کارگزاری، Snippet فرم را پر می‌کند."
                ),
                'order_id': order_id,
            }

        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to Snippet server")
            return {
                'success': False,
                'message': "اتصال به سرور Snippet برقرار نیست.",
                'order_id': '',
            }
        except Exception as e:
            logger.error("DevTools Snippet submit failed: %s", e, exc_info=True)
            return {
                'success': False,
                'message': f"خطا در ارسال: {e}",
                'order_id': '',
            }


# ─────────────────────────────────────────────────────────────
# اجرای مستقل (تست دستی)
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    broker = OmexKhobreganBroker(
        username="05-",
        password="Mehdi",
    )

    if not broker.open_browser():
        logger.error("Failed to open browser")
        exit(1)

    logger.info("Please solve captcha and login...")
    if not broker.wait_for_login():
        logger.error("Login failed")
        broker.close_browser()
        exit(1)

    positions = broker.extract_open_positions()
    logger.info("Open positions: %d", len(positions))

    strategy_input = input(
        "\nEnter strategy:\n"
        "Example: اهرم (1xBUY) | ضهرم6045 (1xSELL)\n> "
    )

    result = broker.submit_strategy(strategy_input, positions)
    if result['success']:
        logger.info("Success: %s", result['message'])
    else:
        logger.error("Failed: %s", result['message'])
        if result['conflicts']:
            for c in result['conflicts']:
                logger.error("Conflict: %s", c['message'])