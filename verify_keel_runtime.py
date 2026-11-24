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
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "keel" / "site"
SHOTS = ROOT / ".verify-keel-ui"
PORT = 8793

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))


ROUTE_MAP = {
    "/login": "/login.html",
    "/new": "/new.html",
    "/app": "/app.html",
    "/download": "/download.html",
    "/privacy": "/privacy.html",
    "/terms": "/terms.html",
    "/notices": "/notices.html",
    "/roadmap": "/roadmap.html",
    "/eula": "/eula.html",
    "/trademark": "/trademark.html",
    "/requirements": "/requirements.html",
}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0].rstrip("/") or "/"
        path = ROUTE_MAP.get(clean, path)
        return super().translate_path(path)


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
            check("landing: auth routes to /login", "/login" in driver.current_url,
                  driver.current_url)
        errs = console_errors(driver)
        check("landing: no console errors", not errs, str(errs[:3]))

        driver.get(base + "/login.html")
        driver.implicitly_wait(3)
        login_text = driver.find_element(By.TAG_NAME, "body").text
        for needle in ["Question what", "Continue with Google", "Continue with Apple",
                       "Explore plans", "Max and Ultra", "Frequently asked questions"]:
            check("login: has " + needle, needle.lower() in login_text.lower())
        check("login: email placeholder",
              "Enter your email" in driver.page_source)
        check("login: no dead # links",
              not driver.execute_script("return [...document.querySelectorAll('a[href=\"#\"]')].length"))
        check("login: 3 plan cards", len(driver.find_elements(
            By.CSS_SELECTOR, ".login-plan-card")) >= 3)
        email_inputs = [e for e in driver.find_elements(By.CSS_SELECTOR, "input")
                        if (e.get_attribute("placeholder") or "").lower().find("email") >= 0
                        or e.get_attribute("type") == "email"]
        check("login: email input", bool(email_inputs))
        if email_inputs:
            email_inputs[0].send_keys("test@example.com")
            submits = driver.find_elements(By.XPATH,
                                           "//button[contains(., 'Continue with email')]")
            if submits:
                submits[0].click()
                try:
                    WebDriverWait(driver, 5).until(
                        lambda d: "/app" in d.current_url)
                    landed = True
                except Exception:
                    landed = False
                check("login: email sign-in goes to /app", landed, driver.current_url)
                check("login: login flag",
                      driver.execute_script("return localStorage.getItem('keel_logged_in')") == "true")
        errs = [e for e in console_errors(driver)
                if "/api/health" not in e.get("message", "")
                and "/api/capabilities/invoke" not in e.get("message", "")]
        check("login: no console errors", not errs, str(errs[:3]))

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
        da = [el for el in driver.find_elements(By.CSS_SELECTOR, "[data-auth-open]")
              if el.is_displayed()]
        check("download: auth triggers", bool(da), str(len(da)))
        if da:
            da[0].click()
            check("download: auth routes to /login", "/login" in driver.current_url,
                  driver.current_url)

        driver.get(base + "/plugins.html")
        driver.implicitly_wait(3)
        pl_text = driver.find_element(By.TAG_NAME, "body").text
        for needle in ["Plugins", "Your plugins", "Most used", "Google Drive",
                       "Popular workflows", "Trending", "Categories",
                       "AI models & agents", "Show all"]:
            check("plugins: has " + needle, needle.lower() in pl_text.lower())
        check("plugins: no dead # links",
              not driver.execute_script("return [...document.querySelectorAll('a[href=\"#\"]')].length"))
        driver.save_screenshot(str(SHOTS / "plugins.png"))

        driver.get(base + "/projects.html")
        driver.implicitly_wait(3)
        pr_text = driver.find_element(By.TAG_NAME, "body").text
        for needle in ["Projects", "Looking to start a project?", "Upload materials",
                       "New project"]:
            check("projects: has " + needle, needle.lower() in pr_text.lower())
        check("projects: no dead # links",
              not driver.execute_script("return [...document.querySelectorAll('a[href=\"#\"]')].length"))
        driver.save_screenshot(str(SHOTS / "projects.png"))

        driver.get(base + "/artifacts.html")
        driver.implicitly_wait(3)
        ar_text = driver.find_element(By.TAG_NAME, "body").text
        for needle in ["Artifacts", "Make something new", "Docs", "Slides",
                       "Design", "GPT-6.2 vs Fable 5.2 Prompts", "Discover Kosovo"]:
            check("artifacts: has " + needle, needle.lower() in ar_text.lower())
        check("artifacts: no dead # links",
              not driver.execute_script("return [...document.querySelectorAll('a[href=\"#\"]')].length"))
        driver.save_screenshot(str(SHOTS / "artifacts.png"))

        driver.get(base + "/new.html")
        driver.implicitly_wait(3)
        new_body = driver.find_element(By.TAG_NAME, "body").text
        check("new: greeting", "You're here" in new_body)
        check("new: recents", "Keel harness build plan" in new_body)
        check("new: sidebar entries",
              all(x in new_body for x in ["New", "Search", "Projects", "Artifacts", "Plugins"]))
        try:
            new_ph = driver.find_element(By.CSS_SELECTOR, "textarea, input[type=text]").get_attribute("placeholder") or ""
        except Exception:
            new_ph = ""
        check("new: composer", "help you today" in new_ph.lower(), new_ph)
        check("new: no dead # links",
              not driver.execute_script("return [...document.querySelectorAll('a[href=\"#\"]')].length"))
        st = [el for el in driver.find_elements(
            By.CSS_SELECTOR,
            "[data-search-trigger], #nav-search, #n-nav-search, button[id$='nav-search']")
              if el.is_displayed()]
        check("new: sidebar search trigger", bool(st))
        if st:
            st[0].click()
            check("palette: opens", visible(driver, ".ksp-root"))
            check("palette: recent rows",
                  len(driver.find_elements(By.CSS_SELECTOR, ".ksp-row")) >= 8)
            check("palette: input present", visible(driver, ".ksp-input"))
            driver.save_screenshot(str(SHOTS / "search-palette.png"))
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            check("palette: closes on Escape", not visible(driver, ".ksp-root"))
        driver.save_screenshot(str(SHOTS / "new.png"))

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
