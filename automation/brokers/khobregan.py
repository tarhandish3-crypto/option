# automation/brokers/khobregan.py
# -*- coding: utf-8 -*-

import pandas as pd
import os
import re
import logging
import time
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, StaleElementReferenceException

# ---------------- تنظیمات logging -----------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)

# ---------------- بخش 1: آماده‌سازی مرورگر -----------------
TARGET_URL = "https://khobregan.tsetab.ir/#/login"

opts = Options()
opts.headless = False
driver = webdriver.Firefox(options=opts)
driver.maximize_window()

driver.get(TARGET_URL)

MAX_WAIT = 15  # seconds
wait = WebDriverWait(driver, MAX_WAIT)  # فقط یک بار تعریف

# پر کردن فیلد یوزرنیم
username = "05-"
password = "Mehdi"

# پیدا کردن فیلد یوزرنیم و پر کردن آن
username_input = wait.until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, "c-k-input-text#account-login-username input.o-inputComponent.u-dir-ltr")))
username_input.clear()
username_input.send_keys(username)

# پیدا کردن فیلد پسورد و پر کردن آن
password_input = wait.until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, "c-k-input-password#sc-accountLoginPassword input.u-dir-ltr")))
password_input.clear()
password_input.send_keys(password)

# حالا مرورگر منتظر کپچا باشد
logger.info("Please solve the captcha manually and click the login button.")

def convert_to_float(value):
    """
    تبدیل متن به عدد
    """
    if not value or value in ['-', '', '—', '–', ' ', '‌']:
        return 0.0
    
    try:
        cleaned = value.replace(',', '').replace('٬', '')
        cleaned = cleaned.replace('(', '').replace(')', '')
        cleaned = cleaned.replace('\n', '').replace('\t', '').strip()
        
        persian_to_english = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
        cleaned = cleaned.translate(persian_to_english)
        
        return float(cleaned)
    except ValueError as e:
        logger.warning(f"امکان تبدیل '{value}' به عدد وجود ندارد: {e}")
        return 0.0
    
def extract_with_advanced_scroll(driver):
    """
    اسکرول پیشرفته با در نظر گرفتن ساختار AG-Grid
    """
    try:
        # کلیک روی تب موقعیت‌ها
        position_tab = wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[contains(@class, 'c-tab') and contains(text(), 'موقعیت های اختیار')]")))
        position_tab.click()
        time.sleep(2)
        
        grid_container = driver.find_element(By.CSS_SELECTOR, ".ag-body-viewport")

        current_pos = 0
        scroll_step = 200
        max_scrolls = 20
        scroll_count = 0
        
        all_rows_data = []
        row_count_set = set()

        # --- 🔹 استخراج اولیه از اولین بخش جدول (بدون اسکرول)
        current_rows = driver.find_elements(By.CSS_SELECTOR, ".ag-center-cols-container .ag-row")
        current_pinned = driver.find_elements(By.CSS_SELECTOR, ".ag-pinned-right-cols-container .ag-row")

        for i in range(min(len(current_rows), len(current_pinned))):
            try:
                symbol_text = current_pinned[i].text.strip()
                center_cells = current_rows[i].find_elements(By.CSS_SELECTOR, ".ag-cell")
                cell_texts = [cell.text.strip() for cell in center_cells if cell.text.strip()]
                
                if len(cell_texts) >= 5 and symbol_text:
                    row_data = {
                        'نماد': symbol_text,
                        'نوع اختیار': cell_texts[0],
                        'موقعیت خرید': convert_to_float(cell_texts[3]),
                        'موقعیت فروش': convert_to_float(cell_texts[4]),
                    }
                    row_hash = hash(f"{symbol_text}{cell_texts[3]}{cell_texts[4]}")
                    if row_hash not in row_count_set:
                        row_count_set.add(row_hash)
                        all_rows_data.append(row_data)
            except Exception:
                continue

        # --- 🔹 ادامه با اسکرول تدریجی
        while scroll_count < max_scrolls:
            current_pos += scroll_step
            driver.execute_script("arguments[0].scrollTop = arguments[1]", grid_container, current_pos)
            time.sleep(0.4)
        
            current_rows = driver.find_elements(By.CSS_SELECTOR, ".ag-center-cols-container .ag-row")
            current_pinned = driver.find_elements(By.CSS_SELECTOR, ".ag-pinned-right-cols-container .ag-row")

            for i in range(min(len(current_rows), len(current_pinned))):
                try:
                    symbol_text = current_pinned[i].text.strip()
                    center_cells = current_rows[i].find_elements(By.CSS_SELECTOR, ".ag-cell")
                    cell_texts = [cell.text.strip() for cell in center_cells if cell.text.strip()]
                    
                    if len(cell_texts) >= 5 and symbol_text:
                        row_data = {
                            'نماد': symbol_text,
                            'نوع اختیار': cell_texts[0],
                            'موقعیت خرید': convert_to_float(cell_texts[3]),
                            'موقعیت فروش': convert_to_float(cell_texts[4]),
                        }
                        row_hash = hash(f"{symbol_text}{cell_texts[3]}{cell_texts[4]}")
                        if row_hash not in row_count_set:
                            row_count_set.add(row_hash)
                            all_rows_data.append(row_data)
                except Exception:
                    continue
            
            new_height = driver.execute_script("return arguments[0].scrollHeight", grid_container)
            if current_pos >= new_height:
                break
                
            scroll_count += 1
        
        return all_rows_data
        
    except Exception as e:
        logger.error(f"خطا در اسکرول پیشرفته: {e}")
        return []
    

option_positions = extract_with_advanced_scroll(driver)
# df = pd.DataFrame(option_positions)
# # base_path = os.path.dirname(os.path.abspath(__file__))
# base_path = os.getcwd()
# file_path = os.path.join(base_path, 'option-positions.xlsx')
# option_positions = pd.read_excel(file_path)

if not option_positions:
    logger.warning("امکان استخراج موقعیت‌ها از صفحه وجود ندارد.")
else:
    logger.info(f"تعداد {len(option_positions)} موقعیت منحصر به فرد استخراج شد")
    
    # ---------------- بخش 3: پر کردن سطر -----------------
# ---------------- توابع -----------------
def click_button(driver, xpath=None, css=None, description="button"):
    try:
        if css:
            elem = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
        else:
            elem = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        elem.click()
    except (ElementClickInterceptedException, StaleElementReferenceException, TimeoutException):
        logger.warning(f"Normal click failed on {description}, trying JS click ...")
        driver.execute_script("arguments[0].click();", elem)
        logger.info(f"JS click on {description} done.")


def parse_and_sort_positions(input_str):
    positions = []
    parts = [p.strip() for p in input_str.split('+')]
    
    # الگوی بهبود یافته برای پشتیبانی از (Long Stock)، (Short Call)، (Long Put) و ...
    # pattern = r'([\d.]+)\*(\S+)\s+\((Long|Short)\)'
    pattern = r'([\d.]+)\s*\*\s*(\S+)\s*\(\s*(Long|Short)(?:\s+(Stock|Call|Put))?\s*\)'
    

    for part in parts:
        m = re.match(pattern, part)
        if not m:
            logger.warning(f"Text '{part}' does not match pattern and is skipped.")
            continue

        quantity, symbol, direction, opt_type = m.groups()

        # اگر opt_type برابر None بود، یعنی فقط (Long) یا (Short) بوده
        # if opt_type:
        #     direction_full = f"{direction} {opt_type}"
        # else:
        #     direction_full = direction

        # تبدیل quantity به فرمت مناسب (بدون .0)
        quantity_float = float(quantity)
        if quantity_float.is_integer():
            quantity = str(int(quantity_float))  # 1.0 -> 1
        else:
            quantity = str(quantity_float)       # 1.5 -> 1.5

        positions.append({
            'symbol': symbol,
            'quantity': quantity,
            'direction': direction})

    # مرتب‌سازی:
    # اگر با 'ض' یا 'ط' نبود -> 0
    # اگر با 'ض' بود -> 1
    # اگر با 'ط' بود -> 2
    # سپس Long قبل Short
    def sort_key(x):
        if x['symbol'].startswith('ض'):
            group = 1
        elif x['symbol'].startswith('ط'):
            group = 2
        else:
            group = 0
        return (group, 0 if x['direction'] == 'Long' else 1)

    positions_sorted = sorted(positions, key=sort_key)
    
    return positions_sorted
    
def click_new_stimation(driver):
    """کلیک روی دکمه‌ی شروع برآورد جدید"""
    button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.e-btnNew")))
    # button.click()
    driver.execute_script("arguments[0].click();", button)

def add_new_row(driver):
    """افزودن سطر جدید در جدول"""
    XPATH_ADD_ROW_BUTTON = "div.o-item-row > div:nth-child(1) > button"
    click_button(driver, css=XPATH_ADD_ROW_BUTTON, description="Add new row")

def fill_estimation_row(driver, symbol, quantity, direction, row_index=0):
    # کلیک روی ng-select container
    container = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "client-instrument-search div.ng-select-container")))
    container.click()
    time.sleep(2)
    
    # وارد کردن متن نماد
    input_field = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "client-instrument-search input[type='text']")))
    input_field.clear()
    input_field.send_keys(symbol)
    time.sleep(1)
    
    # انتخاب اولین گزینه
    first_option = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "div.ng-option.ng-star-inserted")))
    first_option.click()
    
    # پیدا کردن فیلد تعداد برای سطر مورد نظر
    quantity_components = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "c-k-input-number[formcontrolname='quantity']")))

    if row_index < len(quantity_components):
        # پیدا کردن input داخل کامپوننت
        quantity_component = quantity_components[row_index]
        input_qty = quantity_component.find_element(By.CSS_SELECTOR, "input")
        
        input_qty.clear()
        input_qty.send_keys(quantity)
    else:
        raise Exception(f"Quantity component for row {row_index} not found")

    # انتخاب موقعیت Long/Short بر اساس index سطر و direction
    side_components = wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "client-option-strategy-estimation-main-ui-order-side")))

    if row_index < len(side_components):
        side_root = side_components[row_index]
        if direction.lower() == "long":
            buy_div = side_root.find_element(By.CSS_SELECTOR, "div.buy")
            if "-isActive" not in buy_div.get_attribute("class"):
                driver.execute_script("arguments[0].scrollIntoView(true);", buy_div)
                buy_div.click()
        else:
            sell_div = side_root.find_element(By.CSS_SELECTOR, "div.sell")
            if "-isActive" not in sell_div.get_attribute("class"):
                driver.execute_script("arguments[0].scrollIntoView(true);", sell_div)
                sell_div.click()
    else:
        raise Exception(f"Order side component for row {row_index} not found")

    # فعال‌سازی قفل قیمت و انتظار پر شدن مقدار قیمت
    lock_buttons = wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "client-option-strategy-estimation-main-ui-lock[formcontrolname='priceLock'] button")))
    if row_index >= len(lock_buttons):
        raise Exception(f"Price lock button for row {row_index} not found; only {len(lock_buttons)} present.")

    lock_button = lock_buttons[row_index]
    current_state = lock_button.find_element(By.CSS_SELECTOR, "c-k-icon").get_attribute("class")
    is_locked = "-is-locked" in current_state or "active" in current_state.lower()

    driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", lock_button)
    time.sleep(0.3)
    lock_button.click()

    price_inputs = driver.find_elements(By.CSS_SELECTOR, "c-k-input-number[formcontrolname='price'] input")
    if row_index < len(price_inputs):
        price_input = price_inputs[row_index]
        wait.until(lambda d: price_input.get_attribute('value') != "")
        price_value = price_input.get_attribute("value")
    else:
        logger.warning(f"Price input not found for row {row_index + 1}")

    
def check_position_conflicts(positions, extracted_positions):
    conflicts = []
    
    for pos in positions:
        symbol = pos['symbol']
        direction = pos['direction']    # 'Long' یا 'Short'
        
        # پیدا کردن موقعیت موجود برای این نماد
        existing_position = next((p for p in extracted_positions if p['نماد'] == symbol), None)
        
        if existing_position:
            buy_position = existing_position['موقعیت خرید']
            sell_position = existing_position['موقعیت فروش']
            
            # حالت ۱: کاربر می‌خواهد Long بگیرد، اما از قبل Short دارد
            if direction == 'Long' and not pd.isna(sell_position) and sell_position > 0:
                conflicts.append({
                    'symbol': symbol,
                    'message': f" نماد {symbol} موقعیت فروش از قبل وجود دارد و شما در حال موقعیت معکوس خرید هستید"})
            
            # حالت ۲: کاربر می‌خواهد Short بگیرد، اما از قبل Long دارد
            elif direction == 'Short' and not pd.isna(buy_position) and buy_position > 0:
                conflicts.append({
                    'symbol': symbol,
                    'message': f" نماد {symbol} موقعیت خرید از قبل وجود دارد و شما در حال موقعیت معکوس فروش هستید"})
    
    return conflicts


# ---------------- بخش 4: پر کردن چند سطر -----------------
# ورودی کاربر
user_input = input("Enter strategy input (e.g., '1.0*Symbol1 (Long) + 1.0*Symbol2 (Short)'):\n")
# user_input = '1.0*ضهرم7037 (Long) + 1.0*طهرم7037 (Short) + 1.0*ضهرم7038 (Short) + 1.0*طهرم7038 (Long)'
positions = parse_and_sort_positions(user_input)

conflicts = check_position_conflicts(positions, option_positions)

if conflicts:
    logger.error("هشدار: موقعیت معکوس شناسایی شد!")
    for conflict in conflicts:
        logger.error(conflict['message'])  # فقط پیغام را چاپ کن
    logger.error("فرآیند متوقف شد.")
    
else:
    logger.info("شروع پر کردن") 
    click_new_stimation(driver)
    for i, pos in enumerate(positions):
        if i > 0:
            add_new_row(driver)
        fill_estimation_row(driver, pos['symbol'], pos['quantity'], pos['direction'], row_index=i)

    # ==============================
    # تنظیم مقدار تکست‌باکس عددی به 80
    # ==============================
    days_input = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "c-k-input-number[formcontrolname='chartRangePercentage'] input")))
    days_input.clear()
    days_input.send_keys("80")

    # ==============================
    # افزودن نام استراتژی در فیلد عنوان
    # ==============================
    mapping = {"long": "خرید", "short": "فروش"}

    # ساخت رشته فارسی از لیست مرتب‌شده
    persian_parts = [f"{mapping.get(p['direction'].lower())} {p['symbol']}" for p in positions]
    persian_title = "+".join(persian_parts)

    # درج در فیلد عنوان
    title_input = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "client-option-strategy-estimation-header input[formcontrolname='title']")))
    title_input.clear()
    title_input.send_keys(persian_title )
    logger.info(f"Strategy title set to: {persian_title }")


