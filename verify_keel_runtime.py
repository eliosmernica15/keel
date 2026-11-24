"""Runtime UI smoke checks for the KEEL site using headless Chrome."""
from __future__ import annotations

import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "keel" / "site"
SHOTS = ROOT / ".verify-keel-ui"
PORT = 8793

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve():
    handler = functools.partial(QuietHandler, directory=str(SITE))
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def console_errors(driver):
    try:
        return [e for e in driver.get_log("browser")
                if e.get("level") in ("SEVERE", "ERROR")]
    except Exception:
        return []


def visible(driver, selector: str) -> bool:
    try:
        return driver.find_element(By.CSS_SELECTOR, selector).is_displayed()
    except Exception:
        return False


def run():
    SHOTS.mkdir(exist_ok=True)
    httpd = serve()
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1440,1000")
    driver = webdriver.Chrome(options=opts)
    base = f"http://127.0.0.1:{PORT}"
    try:
        driver.get(base + "/index.html")
        driver.implicitly_wait(3)
        check("landing: title", "Keel" in driver.title, driver.title)
        check("landing: hero", "Question what" in driver.find_element(By.TAG_NAME, "h1").text)
        check("landing: login card", visible(driver, ".l-login-card"))
        check("landing: 4 plans", len(driver.find_elements(By.CSS_SELECTOR, ".l-plan-card, .l-plan")) >= 4)
        check("landing: FAQ rows", len(driver.find_elements(By.CSS_SELECTOR, ".l-faq-q")) == 3)
        check("landing: help search", visible(driver, "#l-footer-q, #helpSearch"))
        check("landing: no dead # links",
              not driver.execute_script("return [...document.querySelectorAll('a[href=\"#\"]')].length"))
        driver.save_screenshot(str(SHOTS / "landing-top.png"))
        triggers = driver.find_elements(By.CSS_SELECTOR, ".l-nav-trigger")
        check("landing: 5 nav triggers", len(triggers) == 5, str(len(triggers)))
        if triggers:
            triggers[0].click()
            check("landing: mega opens", visible(driver, ".l-mega"))
            triggers[0].send_keys(Keys.ESCAPE)
            check("landing: mega closes", not visible(driver, ".l-mega"))
        faq = driver.find_elements(By.CSS_SELECTOR, ".l-faq-q")
        if faq:
            faq[0].click()
            check("landing: FAQ expands", faq[0].get_attribute("aria-expanded") == "true")
        auth = [el for el in driver.find_elements(
            By.CSS_SELECTOR, "[data-auth-open], .js-auth") if el.is_displayed()]
        check("landing: auth triggers", bool(auth), str(len(auth)))
        if auth:
            auth[0].click()
            check("landing: modal opens", visible(driver, "#l-auth-modal, #authModal"))
            driver.find_element(By.CSS_SELECTOR,
                                "#l-auth-email, #authEmail").send_keys("test@example.com")
            driver.find_element(By.CSS_SELECTOR,
                                "[data-auth-form-view] form button[type=submit], "
                                "#authForm button[type=submit]").click()
            check("landing: success view", visible(driver, "[data-auth-success], #authSuccessView"))
            check("landing: links to /app",
                  bool(driver.find_elements(By.CSS_SELECTOR,
                                            '[data-auth-success] a[href="/app"], '
                                            '#authSuccessView a[href="/app"]')))
            check("landing: login flag",
                  driver.execute_script("return localStorage.getItem('keel_logged_in')") == "true")
            stay = driver.find_elements(By.CSS_SELECTOR,
                                        "[data-auth-success] [data-auth-close], "
                                        "#authSuccessView [data-modal-close]")
            if stay:
                stay[0].click()
        errs = console_errors(driver)
        check("landing: no console errors", not errs, str(errs[:3]))

        driver.get(base + "/download.html")
        driver.implicitly_wait(3)
        dt = driver.find_elements(By.CSS_SELECTOR, ".kp-nav-trigger")
        check("download: 5 nav triggers", len(dt) == 5, str(len(dt)))
        check("download: hero", "Download Keel" in driver.find_element(By.TAG_NAME, "body").text[:1200])
        check("download: no dead # links",
              not driver.execute_script("return [...document.querySelectorAll('a[href=\"#\"]')].length"))
        if dt:
            dt[0].click()
            check("download: mega opens", visible(driver, ".kp-mega"))
            dt[0].send_keys(Keys.ESCAPE)
            check("download: mega closes", not visible(driver, ".kp-mega"))
        errs = console_errors(driver)
        check("download: no console errors", not errs, str(errs[:3]))

        driver.get(base + "/app.html")
        driver.implicitly_wait(3)
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        check("app: sidebar", "new" in body and "recents" in body)
        try:
            ph = driver.find_element(By.CSS_SELECTOR, "#prompt-chat").get_attribute("placeholder") or ""
        except Exception:
            ph = ""
        check("app: composer placeholder", "for skills" in ph)
        check("app: starburst", "starburst" in driver.page_source)
        errs = [e for e in console_errors(driver)
                if "/api/health" not in e.get("message", "")
                and "/api/capabilities/invoke" not in e.get("message", "")]
        check("app: no fatal console errors", not errs, str(errs[:3]))
        driver.save_screenshot(str(SHOTS / "app.png"))

        driver.set_window_size(390, 844)
        driver.get(base + "/index.html")
        check("mobile: renders", visible(driver, "h1"))
    finally:
        driver.quit()
        httpd.shutdown()

    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    print(f"\n{len(results) - len(failed)}/{len(results)} passed. Screenshots: {SHOTS}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    run()
