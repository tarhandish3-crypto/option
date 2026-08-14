# automation/brokers/Omex_khobregan.py
# -*- coding: utf-8 -*-

"""
اتوماسیون ارسال استراتژی اختیار معامله به سامانه خبرگان کارگزاری اومکس (tsetab)

جریان کار:
  1. open_browser()   ← مرورگر باز می‌شود، نام‌کاربری و رمز پر می‌شوند
  2. wait_for_login() ← برنامه منتظر می‌ماند تا کاربر کپچا را حل کرده و login کند
  3. extract_open_positions() ← موقعیت‌های باز از تب «موقعیت های اختیار» استخراج می‌شوند
  4. submit_strategy(positions_str) ← استراتژی در فرم برآورد وارد می‌شود
                                      (پس از چک تعارض موقعیت معکوس)
  5. close_browser()  ← در صورت نیاز

فرمت ورودی submit_strategy:
  "1*ضهرم6045 (Long) + 1*اهرم (Long Stock) + 1*طهرم6045 (Short)"
  یا همان فرمت Positions پنجره اسکنر:
  "اهرم (1xBUY) | ضهرم6045 (1xSELL)"

هر دو فرمت پشتیبانی می‌شوند.
"""

import re
import time
import logging
from typing import List, Dict, Optional

import pandas as pd
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

logger = logging.getLogger("OptionScanner.Automation.OmexKhobregan")


# ─────────────────────────────────────────────────────────────
# ثابت‌ها
# ─────────────────────────────────────────────────────────────

TARGET_URL  = "https://khobregan.tsetab.ir/#/login"
MAX_WAIT    = 15       # ثانیه انتظار برای عناصر صفحه
LOGIN_POLL  = 2        # فاصله پولینگ در انتظار ورود کاربر (ثانیه)
LOGIN_TIMEOUT = 180    # حداکثر زمان انتظار برای ورود کاربر (ثانیه)


# ─────────────────────────────────────────────────────────────
# توابع کمکی (مستقل از کلاس)
# ─────────────────────────────────────────────────────────────

def convert_to_float(value: str) -> float:
    """تبدیل رشته فارسی/انگلیسی به عدد اعشاری"""
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
        logger.warning(f"امکان تبدیل '{value}' به عدد وجود ندارد: {e}")
        return 0.0


def parse_scanner_positions(positions_text: str) -> List[Dict]:
    """
    تبدیل فرمت ستون Positions اسکنر به لیست دیکشنری.

    فرمت اسکنر:  "اهرم (1xBUY) | ضهرم6045 (1xSELL)"
    فرمت استاندارد: "1*ضهرم6045 (Long) + 1*اهرم (Long Stock)"

    هر دو فرمت پشتیبانی می‌شوند.
    خروجی: [{'symbol': 'اهرم', 'quantity': '1', 'direction': 'Long'}, ...]
    """
    positions = []

    # ─── فرمت اسکنر:  نماد (NxSIDE) ───
    scanner_pattern = re.compile(
        r'(\S+)\s*\((\d+)x(BUY|SELL)\)',
        re.IGNORECASE
    )
    scanner_matches = scanner_pattern.findall(positions_text)

    if scanner_matches:
        for symbol, qty, side in scanner_matches:
            direction = 'Long' if side.upper() == 'BUY' else 'Short'
            positions.append({
                'symbol':    symbol.strip(),
                'quantity':  str(int(qty)),
                'direction': direction,
            })
    else:
        # ─── فرمت استاندارد: N*نماد (Long/Short ...) ───
        standard_pattern = re.compile(
            r'([\d.]+)\s*\*\s*(\S+)\s*\(\s*(Long|Short)(?:\s+(?:Stock|Call|Put))?\s*\)',
            re.IGNORECASE
        )
        for part in positions_text.split('+'):
            m = standard_pattern.match(part.strip())
            if not m:
                logger.warning(f"پارت '{part.strip()}' با هیچ الگویی منطبق نشد — رد شد")
                continue
            qty_raw, symbol, direction = m.groups()
            qty_f = float(qty_raw)
            qty = str(int(qty_f)) if qty_f.is_integer() else str(qty_f)
            positions.append({
                'symbol':    symbol.strip(),
                'quantity':  qty,
                'direction': direction.capitalize(),
            })

    # ─── مرتب‌سازی: سهم پایه اول، بعد ض (Call)، بعد ط (Put) ───
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
    existing_positions: List[Dict]
) -> List[Dict]:
    """
    بررسی تعارض موقعیت معکوس.
    خروجی: لیست تعارض‌ها (خالی = بدون تعارض)
    """
    conflicts = []
    for pos in new_positions:
        symbol    = pos['symbol']
        direction = pos['direction']
        existing  = next(
            (p for p in existing_positions if p['نماد'] == symbol), None
        )
        if not existing:
            continue

        buy_pos  = existing.get('موقعیت خرید', 0.0) or 0.0
        sell_pos = existing.get('موقعیت فروش', 0.0) or 0.0

        if direction == 'Long' and sell_pos > 0:
            conflicts.append({
                'symbol':  symbol,
                'message': f"نماد {symbol}: موقعیت فروش از قبل وجود دارد — موقعیت خرید معکوس است",
            })
        elif direction == 'Short' and buy_pos > 0:
            conflicts.append({
                'symbol':  symbol,
                'message': f"نماد {symbol}: موقعیت خرید از قبل وجود دارد — موقعیت فروش معکوس است",
            })
    return conflicts


# ─────────────────────────────────────────────────────────────
# کلاس اصلی
# ─────────────────────────────────────────────────────────────

class OmexKhobreganBroker:
    """
    اتوماسیون ارسال استراتژی به سامانه خبرگان اومکس.

    مثال استفاده:
        broker = OmexKhobreganBroker(username="05-xxx", password="xxxx")
        broker.open_browser()
        # کاربر کپچا را حل می‌کند
        broker.wait_for_login()
        positions = broker.extract_open_positions()
        result = broker.submit_strategy("اهرم (1xBUY) | ضهرم6045 (1xSELL)", positions)
        print(result)
    """

    def __init__(
        self,
        username: str = "",
        password: str = "",
        headless: bool = False,
        max_wait: int = MAX_WAIT,
        chart_range_percentage: int = 80,
    ):
        self.username   = username
        self.password   = password
        self.headless   = headless
        self.max_wait   = max_wait
        self.chart_range_percentage = chart_range_percentage

        self.driver: Optional[webdriver.Firefox] = None
        self.wait:   Optional[WebDriverWait]    = None
        self._logged_in = False

    # ── ۱. مرورگر ──────────────────────────────────────────

    def open_browser(self) -> bool:
        """
        مرورگر را باز می‌کند، به صفحه login می‌رود،
        نام‌کاربری و رمز را پر می‌کند و منتظر کپچا می‌ماند.
        """
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

            logger.info("مرورگر آماده است — لطفاً کپچا را حل کرده و دکمه ورود را بزنید.")
            return True

        except WebDriverException as e:
            logger.error(f"خطا در باز کردن مرورگر: {e}")
            return False

    def wait_for_login(self, timeout: int = LOGIN_TIMEOUT) -> bool:
        """
        منتظر می‌ماند تا URL تغییر کند (نشانه ورود موفق کاربر).
        بعد از login موقعیت‌های باز را استخراج می‌کند.
        """
        if not self.driver:
            logger.error("مرورگر باز نشده است.")
            return False

        elapsed = 0
        logger.info(f"منتظر ورود کاربر (حداکثر {timeout} ثانیه)...")
        while elapsed < timeout:
            try:
                current_url = self.driver.current_url
                if 'login' not in current_url.lower():
                    self._logged_in = True
                    logger.info("✅ ورود موفق — در حال پردازش...")
                    time.sleep(2)
                    return True
            except WebDriverException:
                pass
            time.sleep(LOGIN_POLL)
            elapsed += LOGIN_POLL

        logger.error("⏱️ زمان انتظار برای ورود به پایان رسید.")
        return False

    def close_browser(self) -> None:
        """بستن مرورگر"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self._logged_in = False

    # ── ۲. استخراج موقعیت‌های باز ────────────────────────

    def extract_open_positions(self) -> List[Dict]:
        """
        موقعیت‌های باز را از تب «موقعیت های اختیار» در AG-Grid استخراج می‌کند.
        خروجی: [{'نماد': ..., 'نوع اختیار': ..., 'موقعیت خرید': ..., 'موقعیت فروش': ...}]
        """
        if not self.driver or not self._logged_in:
            logger.error("برای استخراج موقعیت‌ها ابتدا باید وارد سیستم شوید.")
            return []

        try:
            # کلیک روی تب موقعیت‌ها
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
                rows   = self.driver.find_elements(
                    By.CSS_SELECTOR, ".ag-center-cols-container .ag-row")
                pinned = self.driver.find_elements(
                    By.CSS_SELECTOR, ".ag-pinned-right-cols-container .ag-row")
                for i in range(min(len(rows), len(pinned))):
                    try:
                        symbol = pinned[i].text.strip()
                        cells  = rows[i].find_elements(By.CSS_SELECTOR, ".ag-cell")
                        texts  = [c.text.strip() for c in cells if c.text.strip()]
                        if len(texts) >= 5 and symbol:
                            row = {
                                'نماد':         symbol,
                                'نوع اختیار':   texts[0],
                                'موقعیت خرید':  convert_to_float(texts[3]),
                                'موقعیت فروش':  convert_to_float(texts[4]),
                            }
                            h = hash(f"{symbol}{texts[3]}{texts[4]}")
                            if h not in seen:
                                seen.add(h)
                                all_rows.append(row)
                    except Exception:
                        continue

            # خواندن اولیه بدون اسکرول
            _read_visible_rows()

            # اسکرول تدریجی
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

            logger.info(f"✅ {len(all_rows)} موقعیت باز استخراج شد")
            return all_rows

        except Exception as e:
            logger.error(f"خطا در استخراج موقعیت‌های باز: {e}")
            return []

    # ── ۳. ارسال استراتژی ────────────────────────────────

    def submit_strategy(
        self,
        positions_text: str,
        existing_positions: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        استراتژی را در فرم برآورد خبرگان پر می‌کند.

        Args:
            positions_text:      متن Positions (فرمت اسکنر یا استاندارد)
            existing_positions:  لیست موقعیت‌های باز (برای چک تعارض)

        Returns:
            {'success': bool, 'message': str, 'conflicts': list}
        """
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

        # چک تعارض موقعیت معکوس
        existing = existing_positions or []
        conflicts = check_position_conflicts(positions, existing)
        if conflicts:
            msgs = [c['message'] for c in conflicts]
            logger.error("⛔ تعارض موقعیت معکوس شناسایی شد:\n" + "\n".join(msgs))
            return {
                'success': False,
                'message': "تعارض موقعیت معکوس:\n" + "\n".join(msgs),
                'conflicts': conflicts,
            }

        try:
            logger.info(f"🚀 شروع پر کردن {len(positions)} موقعیت در فرم برآورد...")

            # کلیک دکمه «برآورد جدید»
            self._click_new_estimation()

            # پر کردن سطر به سطر
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
                    f"  سطر {i+1}: {pos['symbol']} × {pos['quantity']} — {pos['direction']}"
                )

            # تنظیم بازه نمودار
            self._set_chart_range(self.chart_range_percentage)

            # ساخت و درج عنوان فارسی
            persian_title = self._build_persian_title(positions)
            self._set_strategy_title(persian_title)

            logger.info(f"✅ استراتژی با موفقیت ارسال شد: {persian_title}")
            return {
                'success': True,
                'message': f"استراتژی «{persian_title}» در سامانه ثبت شد.",
                'conflicts': [],
            }

        except Exception as e:
            logger.error(f"❌ خطا در ارسال استراتژی: {e}", exc_info=True)
            return {
                'success': False,
                'message': f"خطا در ارسال: {e}",
                'conflicts': [],
            }

    # ── متدهای داخلی (private) ───────────────────────────

    def _safe_click(self, element, description: str = "element") -> None:
        """کلیک ایمن — در صورت شکست معمولی، از JS استفاده می‌کند"""
        try:
            element.click()
        except (ElementClickInterceptedException, StaleElementReferenceException):
            logger.debug(f"کلیک معمولی روی {description} شکست خورد — تلاش با JS")
            self.driver.execute_script("arguments[0].click();", element)

    def _click_new_estimation(self) -> None:
        """کلیک روی دکمه «برآورد جدید»"""
        btn = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.e-btnNew"))
        )
        self.driver.execute_script("arguments[0].click();", btn)
        time.sleep(1)

    def _add_new_row(self) -> None:
        """افزودن سطر جدید در جدول برآورد"""
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
        row_index: int,
    ) -> None:
        """پر کردن یک سطر در فرم برآورد"""

        # ── انتخاب نماد ──
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

        # ── وارد کردن تعداد ──
        qty_components = self.wait.until(EC.presence_of_all_elements_located((
            By.CSS_SELECTOR, "c-k-input-number[formcontrolname='quantity']"
        )))
        if row_index >= len(qty_components):
            raise RuntimeError(
                f"کامپوننت تعداد برای سطر {row_index} یافت نشد "
                f"(موجود: {len(qty_components)})"
            )
        qty_input = qty_components[row_index].find_element(By.CSS_SELECTOR, "input")
        qty_input.clear()
        qty_input.send_keys(quantity)

        # ── انتخاب Long/Short ──
        side_components = self.wait.until(EC.presence_of_all_elements_located((
            By.CSS_SELECTOR,
            "client-option-strategy-estimation-main-ui-order-side"
        )))
        if row_index >= len(side_components):
            raise RuntimeError(
                f"کامپوننت جهت برای سطر {row_index} یافت نشد"
            )
        side_root = side_components[row_index]
        if direction.lower() == "long":
            btn = side_root.find_element(By.CSS_SELECTOR, "div.buy")
            if "-isActive" not in btn.get_attribute("class"):
                self.driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                btn.click()
        else:
            btn = side_root.find_element(By.CSS_SELECTOR, "div.sell")
            if "-isActive" not in btn.get_attribute("class"):
                self.driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                btn.click()

        # ── قفل قیمت ──
        lock_buttons = self.wait.until(EC.presence_of_all_elements_located((
            By.CSS_SELECTOR,
            "client-option-strategy-estimation-main-ui-lock"
            "[formcontrolname='priceLock'] button"
        )))
        if row_index >= len(lock_buttons):
            raise RuntimeError(
                f"دکمه قفل قیمت برای سطر {row_index} یافت نشد"
            )
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
                logger.warning(f"قیمت سطر {row_index + 1} پر نشد — ادامه می‌دهیم")

    def _set_chart_range(self, value: int) -> None:
        """تنظیم بازه نمودار (درصد)"""
        try:
            inp = self.wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "c-k-input-number[formcontrolname='chartRangePercentage'] input"
            )))
            inp.clear()
            inp.send_keys(str(value))
        except TimeoutException:
            logger.warning("فیلد بازه نمودار یافت نشد — رد شد")

    def _build_persian_title(self, positions: List[Dict]) -> str:
        """ساخت عنوان فارسی استراتژی"""
        mapping = {"long": "خرید", "short": "فروش"}
        parts = [
            f"{mapping.get(p['direction'].lower(), p['direction'])} {p['symbol']}"
            for p in positions
        ]
        return "+".join(parts)

    def _set_strategy_title(self, title: str) -> None:
        """درج عنوان در فیلد عنوان استراتژی"""
        try:
            inp = self.wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "client-option-strategy-estimation-header "
                "input[formcontrolname='title']"
            )))
            inp.clear()
            inp.send_keys(title)
            logger.info(f"عنوان استراتژی تنظیم شد: {title}")
        except TimeoutException:
            logger.warning("فیلد عنوان استراتژی یافت نشد — رد شد")


# ─────────────────────────────────────────────────────────────
# اجرای مستقل (تست دستی بدون UI اسکنر)
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    broker = OmexKhobreganBroker(
        username="05-",
        password="Mehdi",
    )

    if not broker.open_browser():
        print("خطا در باز کردن مرورگر")
        exit(1)

    print("\n>>> کپچا را حل کرده و وارد شوید ...")
    if not broker.wait_for_login():
        print("ورود ناموفق")
        broker.close_browser()
        exit(1)

    positions = broker.extract_open_positions()
    print(f"موقعیت‌های باز: {len(positions)}")

    strategy_input = input(
        "\nاستراتژی را وارد کنید\n"
        "مثال: اهرم (1xBUY) | ضهرم6045 (1xSELL)\n> "
    )

    result = broker.submit_strategy(strategy_input, positions)
    if result['success']:
        print(f"✅ {result['message']}")
    else:
        print(f"❌ {result['message']}")
        if result['conflicts']:
            for c in result['conflicts']:
                print(f"  ⛔ {c['message']}")
