import os
from io import StringIO
from datetime import datetime, timedelta

from dotenv import load_dotenv
import base64
import urllib.parse
import requests
import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()


def create_driver() -> webdriver.Chrome:
    """Create a Chrome driver with stable defaults and a webdriver-manager fallback."""
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    try:
        return webdriver.Chrome(options=chrome_options)
    except WebDriverException:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)


def attackpoint_login(driver: webdriver.Chrome | None = None) -> webdriver.Chrome:
    """Ensure the driver is logged into AttackPoint and return the driver."""
    if driver is None:
        driver = create_driver()

    wait = WebDriverWait(driver, 20)
    driver.get("https://www.attackpoint.org/login.jsp?returl=https%3A%2F%2Fwww.attackpoint.org%2F")

    name_box = wait.until(EC.presence_of_element_located((By.NAME, "username")))
    name_box.send_keys(os.getenv("ATTACKPOINT_USERNAME"))
    pass_box = wait.until(EC.presence_of_element_located((By.NAME, "password")))
    pass_box.send_keys(os.getenv("ATTACKPOINT_PASSWORD"))
    wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@value='Login']"))).click()
    return driver


# --- Utility helpers used by both pathways ---
def _zero(n: int) -> str:
    return str(n).zfill(2)


def safe_click(driver: webdriver.Chrome, element) -> None:
    """Click an element with a JavaScript fallback if normal click fails."""
    try:
        element.click()
    except Exception:
        driver.execute_script('arguments[0].click();', element)


def go_to_reports_page(driver: webdriver.Chrome) -> None:
    """Navigate to the reports page using a link if present or direct URL fallback."""
    wait = WebDriverWait(driver, 10)
    try:
        wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@href,'reports')]"))).click()
    except Exception:
        driver.get('https://www.attackpoint.org/reports.jsp')


def set_form_date_range(driver: webdriver.Chrome, form, start: dict, end: dict) -> None:
    """Set the from/to date selects inside a given form element."""
    def set_field(name, value):
        try:
            el = form.find_element(By.NAME, name)
            driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el, value)
            return True
        except Exception:
            return False

    set_field('from-day', start['day'])
    set_field('from-month', start['month'])
    set_field('from-year', start['year'])
    set_field('to-day', end['day'])
    set_field('to-month', end['month'])
    set_field('to-year', end['year'])


def ensure_checkbox_checked(driver: webdriver.Chrome, form, name: str) -> None:
    try:
        chk = form.find_element(By.NAME, name)
        if not chk.is_selected():
            driver.execute_script('arguments[0].click();', chk)
    except Exception:
        pass


def collect_form_params(driver: webdriver.Chrome, form) -> dict:
    """Collect named inputs/selects/textarea values from a form into a param dict."""
    params = {}
    elems = form.find_elements(By.CSS_SELECTOR, 'input[name], select[name], textarea[name]')
    for e in elems:
        name = e.get_attribute('name')
        if not name:
            continue
        typ = (e.get_attribute('type') or e.tag_name).lower()
        if typ == 'checkbox':
            if e.is_selected():
                val = e.get_attribute('value') or 'on'
                params[name] = val
        else:
            val = e.get_attribute('value')
            params[name] = '' if val is None else val
    return params


def requests_session_from_driver(driver: webdriver.Chrome) -> requests.Session:
    """Create a requests.Session populated with cookies from the Selenium driver."""
    s = requests.Session()
    for c in driver.get_cookies():
        s.cookies.set(c['name'], c['value'], domain=c.get('domain'), path=c.get('path', '/'))
    return s


# --- Note-writing pathway ---
def _fill_and_submit_description(driver: webdriver.Chrome, description: str) -> None:
    """Low-level: open new note form, set description via JS, and submit."""
    wait = WebDriverWait(driver, 20)
    wait.until(EC.element_to_be_clickable((By.XPATH, '//a[@href="/newtrainingnote.jsp"]'))).click()
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'form[action="/addcomment.jsp"]')))

    result = driver.execute_script(
        "const form = document.querySelector('form[action=\"/addcomment.jsp\"]');"
        "if (!form) return 'missing-form';"
        "const desc = form.querySelector('textarea[name=\"description\"]');"
        "if (!desc) return 'missing-description';"
        "desc.removeAttribute('readonly');"
        "desc.removeAttribute('disabled');"
        "desc.value = arguments[0];"
        "desc.dispatchEvent(new Event('input', { bubbles: true }));"
        "desc.dispatchEvent(new Event('change', { bubbles: true }));"
        "const submit = form.querySelector('input[type=\"submit\"][value=\"Submit\"]');"
        "if (!submit) return 'missing-submit';"
        "submit.click();"
        "return 'submitted';",
        description,
    )

    if result != 'submitted':
        raise RuntimeError(f'Failed to submit form: {result}')


def write_note(description: str, driver: webdriver.Chrome | None = None, retries: int = 1) -> None:
    """Public pathway: ensure login, write the note, and clean up.

    Retries once on session errors by default.
    """
    attempt = 0
    while True:
        drv = None
        try:
            drv = driver or create_driver()
            attackpoint_login(drv)
            _fill_and_submit_description(drv, description)
            return
        except InvalidSessionIdException:
            attempt += 1
            if attempt > retries:
                raise
        finally:
            if drv and drv is not driver:
                try:
                    drv.quit()
                except Exception:
                    pass


# --- Report retrieval pathway ---
def parse_attackpoint_csv_text(text: str) -> pd.DataFrame:
    """Parse AttackPoint CSV text into a structured pandas DataFrame.

    Normalizes column names, parses dates, durations, numeric and boolean columns.
    """
    df = pd.read_csv(StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')

    dur_cols = [c for c in df.columns if c.lower() in ('time', 't-intensity') or c.startswith('i')]
    for c in dur_cols:
        try:
            df[c] = pd.to_timedelta(df[c].replace('', pd.NA), errors='coerce')
        except Exception:
            df[c] = pd.to_timedelta(df[c].astype(str), errors='coerce')

    numeric_candidates = ['distance(km)', 'climb(m)', 'ahr', 'mhr', 'rhr', 'sleep', 'weight(kg)']
    for c in numeric_candidates:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].replace('', pd.NA), errors='coerce')

    bool_cols = ['injured', 'sick', 'restday']
    for c in bool_cols:
        if c in df.columns:
            df[c] = df[c].notna() & df[c].astype(str).str.strip().ne('')

    if 'time' in df.columns:
        try:
            df['time_seconds'] = df['time'].dt.total_seconds()
        except Exception:
            df['time_seconds'] = pd.NA

    df.drop(columns=['workout', 'keywords', 'controls', 'spiked', 'rhr', 'sleep', 'weight(kg)', 'shoes', 'route'], errors='ignore', inplace=True)
    return df


def get_report(output_filename: str = 'attackpoint_export.json') -> str:
    """Public pathway: generate a week→today Completed CSV export and save as JSON.

    Returns the path to the saved JSON file.
    """
    driver = create_driver()
    driver = attackpoint_login(driver)
    try:
        go_to_reports_page(driver)

        wait = WebDriverWait(driver, 20)
        form = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'form[action="/printtraining.jsp"]')))

        today = datetime.now()
        week_ago = today - timedelta(days=7)
        start = {'day': _zero(week_ago.day), 'month': _zero(week_ago.month), 'year': str(week_ago.year)}
        end = {'day': _zero(today.day), 'month': _zero(today.month), 'year': str(today.year)}

        set_form_date_range(driver, form, start, end)
        ensure_checkbox_checked(driver, form, 'fromselected')
        ensure_checkbox_checked(driver, form, 'toselected')
        # Completed sessions and CSV output
        try:
            el = form.find_element(By.NAME, 'isplan')
            driver.execute_script("arguments[0].value = '0'; arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el)
        except Exception:
            pass
        try:
            el = form.find_element(By.NAME, 'outtype')
            driver.execute_script("arguments[0].value = 'csv'; arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el)
        except Exception:
            pass

        params = collect_form_params(driver, form)
        session = requests_session_from_driver(driver)

        action = form.get_attribute('action')
        from urllib.parse import urljoin
        url = urljoin(driver.current_url, action)

        resp = session.get(url, params=params, timeout=60)
        resp.raise_for_status()

        content_type = resp.headers.get('Content-Type', '')
        if 'text' in content_type or 'csv' in content_type or resp.encoding:
            text = resp.text
        else:
            encoding = resp.encoding or 'utf-8'
            try:
                text = resp.content.decode(encoding)
            except Exception:
                raise RuntimeError('Export response is not text and could not be decoded')

        df = parse_attackpoint_csv_text(text)
        return df
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == '__main__':
    # Simple CLI via env: if ATTACKPOINT_DESCRIPTION is set, write note; otherwise fetch report
    description = os.getenv('ATTACKPOINT_DESCRIPTION')
    if description:
        write_note(description)
        print('Note submitted')
    else:
        out = get_report('my_export.json')
        print(out)