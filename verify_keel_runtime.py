"""Runtime UI smoke checks for the KEEL site using headless Chrome.

Run from workspace root: python verify_keel_runtime.py
Starts its own static server on port 8765. Screenshots go to .verify-keel-ui/.
"""
from __future__ import annotations

import functools
import http.server
import socketserver
import subprocess
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
PORT = 8791

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
        return [
            e for e in driver.get_log("browser")
            if e.get("level") in ("SEVERE", "ERROR")
        ]
    except Exception:
        return []


def visible(driver, selector: str) -> bool:
    try:
        el = driver.find_element(By.CSS_SELECTOR, selector)
        return el.is_displayed()
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
        # ---------------- landing ----------------
        driver.get(base + "/index.html")
        driver.implicitly_wait(3)
        check("landing: title", "Keel" in driver.title, driver.title)
        check("landing: hero heading",
              visible(driver, "h1") and "Question what" in driver.find_element(By.TAG_NAME, "h1").text)
        check("landing: login card", visible(driver, ".l-login-card"))
        check("landing: pricing cards", len(driver.find_elements(By.CSS_SELECTOR, ".l-plan")) >= 4)
        check("landing: FAQ rows", len(driver.find_elements(By.CSS_SELECTOR, ".l-faq-q")) == 3)
        check("landing: footer help search", visible(driver, "#helpSearch"))
        check("landing: no dead # links",
              not driver.execute_script("return [...document.querySelectorAll('a[href=\"#\"]')].length"))

        # mega menu open / escape
        triggers = driver.find_elements(By.CSS_SELECTOR, ".l-nav-trigger, .kp-nav-trigger")
        check("landing: nav triggers", len(triggers) >= 5, str(len(triggers)))
        if triggers:
            triggers[0].click()
            check("landing: mega opens on click", visible(driver, ".l-mega, .kp-mega"))
            triggers[0].send_keys(Keys.ESCAPE)
            check("landing: mega closes on Escape",
                  not visible(driver, ".l-mega, .kp-mega"))

        # FAQ accordion
        faq = driver.find_elements(By.CSS_SELECTOR, ".l-faq-q")
        if faq:
            faq[0].click()
            check("landing: FAQ expands",
                  faq[0].get_attribute("aria-expanded") == "true")

        # Auth modal
        auth = [el for el in driver.find_elements(By.CSS_SELECTOR, ".js-auth") if el.is_displayed()]
        if auth:
            auth[0].click()
            check("landing: auth modal opens", visible(driver, "#authModal"))
            email = driver.find_element(By.CSS_SELECTOR, "#authEmail")
            email.send_keys("test@example.com")
            driver.find_element(By.CSS_SELECTOR, "#authForm button[type=submit]").click()
            check("landing: auth success view",
                  visible(driver, "#authSuccessView"))
            check("landing: auth leads to /app",
                  bool(driver.find_elements(By.CSS_SELECTOR, '#authSuccessView a[href="/app"]')))
            logged = driver.execute_script("return localStorage.getItem('keel_logged_in')")
            check("landing: login flag stored", logged == "true", str(logged))
            stay = driver.find_elements(By.CSS_SELECTOR, "#authSuccessView [data-modal-close]")
            if stay:
                stay[0].click()

        errs = console_errors(driver)
        check("landing: no console errors", not errs, str(errs[:3]))
        driver.save_screenshot(str(SHOTS / "landing.png"))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        driver.save_screenshot(str(SHOTS / "landing-footer.png"))

        # ---------------- download ----------------
        driver.get(base + "/download.html")
        driver.implicitly_wait(3)
        check("download: title", "Keel" in driver.title, driver.title)
        dtriggers = driver.find_elements(By.CSS_SELECTOR, ".kp-nav-trigger")
        check("download: 5 nav triggers", len(dtriggers) == 5, str(len(dtriggers)))
        check("download: hero heading",
              "Download Keel" in driver.find_element(By.TAG_NAME, "body").text[:1200])
        check("download: no dead # links",
              not driver.execute_script("return [...document.querySelectorAll('a[href=\"#\"]')].length"))
        if dtriggers:
            dtriggers[0].click()
            check("download: mega opens", visible(driver, ".kp-mega"))
            dtriggers[0].send_keys(Keys.ESCAPE)
            check("download: mega closes",
                  not visible(driver, ".kp-mega"))
        errs = console_errors(driver)
        check("download: no console errors", not errs, str(errs[:3]))
        driver.save_screenshot(str(SHOTS / "download.png"))

        # ---------------- app ----------------
        driver.get(base + "/app.html")
        driver.implicitly_wait(3)
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        check("app: has Keel sidebar", "new" in body and "recents" in body)
        try:
            placeholder = driver.find_element(By.CSS_SELECTOR, "#prompt-chat").get_attribute("placeholder")
        except Exception:
            placeholder = ""
        check("app: has composer", "for skills" in (placeholder or ""))
        check("app: has starburst", "starburst" in driver.page_source)
        # The static mirror has no local Python bridge, so its /api/health and
        # /api/capabilities/invoke requests are expected to fail; ignore those.
        errs = [e for e in console_errors(driver)
                if "/api/health" not in e.get("message", "")
                and "/api/capabilities/invoke" not in e.get("message", "")]
        check("app: no fatal console errors", not errs, str(errs[:3]))
        driver.save_screenshot(str(SHOTS / "app.png"))

        # ---------------- mobile ----------------
        driver.set_window_size(390, 844)
        driver.get(base + "/index.html")
        check("mobile: page renders", visible(driver, "h1"))
        driver.save_screenshot(str(SHOTS / "landing-mobile.png"))
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
