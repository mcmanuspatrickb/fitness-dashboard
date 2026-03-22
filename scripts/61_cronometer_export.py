from pathlib import Path
from datetime import datetime
import os
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DOWNLOAD_DIR = PROJECT_ROOT / os.getenv(
    "CRONOMETER_DOWNLOAD_DIR",
    "data_raw/current/cronometer",
)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

LOGIN_URL = "https://cronometer.com/login/"


def newest_csv_path() -> Path | None:
    csvs = sorted(
        DOWNLOAD_DIR.glob("*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return csvs[0] if csvs else None


def save_debug(page, name: str) -> None:
    path = DOWNLOAD_DIR / name
    page.screenshot(path=str(path), full_page=True)
    print(f"Saved screenshot: {path}")
    print(f"Current URL: {page.url}")
    try:
        print(f"Page title: {page.title()}")
    except Exception:
        pass


def click_first_visible(locator_candidates, label: str, timeout: int = 15000):
    last_error = None
    for locator in locator_candidates:
        try:
            locator.first.wait_for(state="visible", timeout=timeout)
            locator.first.scroll_into_view_if_needed()
            locator.first.click()
            print(f"Clicked: {label}")
            return locator.first
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Could not click: {label}") from last_error


def find_first_visible(locator_candidates, label: str, timeout: int = 15000):
    last_error = None
    for locator in locator_candidates:
        try:
            locator.first.wait_for(state="visible", timeout=timeout)
            locator.first.scroll_into_view_if_needed()
            print(f"Found: {label}")
            return locator.first
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Could not find: {label}") from last_error


def build_target_path() -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d")
    return DOWNLOAD_DIR / f"cronometer_daily_{timestamp}.csv"


def run_export() -> None:
    email = os.getenv("CRONOMETER_EMAIL")
    password = os.getenv("CRONOMETER_PASSWORD")

    if not email or not password:
        raise RuntimeError("Missing CRONOMETER_EMAIL or CRONOMETER_PASSWORD in .env")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            slow_mo=0,
        )
        context = browser.new_context(
            accept_downloads=True,
            viewport={"width": 1440, "height": 1100},
        )
        page = context.new_page()

        try:
            print("Opening login page...")
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.get_by_role("textbox", name="Email").wait_for(timeout=15000)

            print("Logging in...")
            page.get_by_role("textbox", name="Email").fill(email)
            page.get_by_role("textbox", name="Password").fill(password)
            page.get_by_role("button", name="LOG IN").click()

            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(5000)

            print("Opening left sidebar More menu...")
            click_first_visible(
                [
                    page.get_by_role("button", name=" More"),
                    page.get_by_role("button", name="More"),
                    page.locator("button:has-text('More')"),
                    page.locator("[role='button']:has-text('More')"),
                    page.get_by_text("More", exact=True),
                ],
                label="More menu",
            )

            page.wait_for_timeout(1500)

            print("Opening Your Account...")
            click_first_visible(
                [
                    page.get_by_role("link", name="Your Account"),
                    page.get_by_text("Your Account", exact=True),
                    page.locator("a:has-text('Your Account')"),
                    page.locator("[role='menuitem']:has-text('Your Account')"),
                    page.locator("text=/Your\\s*Account/i"),
                ],
                label="Your Account",
            )

            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(3000)

            print("Opening Export Data...")
            click_first_visible(
                [
                    page.get_by_role("button", name="Export Data"),
                    page.get_by_text("Export Data", exact=True),
                    page.locator("button:has-text('Export Data')"),
                    page.locator("[role='button']:has-text('Export Data')"),
                    page.locator("text=/Export\\s*Data/i"),
                ],
                label="Export Data",
            )

            page.wait_for_timeout(2000)

            print("Finding Daily Nutrition export button...")
            export_daily_btn = find_first_visible(
                [
                    page.get_by_role("button", name="Export Daily Nutrition"),
                    page.get_by_text("Export Daily Nutrition", exact=True),
                    page.locator("button:has-text('Export Daily Nutrition')"),
                    page.locator("[role='button']:has-text('Export Daily Nutrition')"),
                    page.locator("text=/Export\\s*Daily\\s*Nutrition/i"),
                    page.locator("text=/Daily\\s*Nutrition/i"),
                ],
                label="Export Daily Nutrition",
            )

            page.wait_for_timeout(1000)

            print("Triggering download...")
            with page.expect_download(timeout=30000) as download_info:
                try:
                    export_daily_btn.click()
                except Exception:
                    export_daily_btn.click(force=True)

            download = download_info.value
            target = build_target_path()
            download.save_as(str(target))
            print(f"Downloaded export to: {target}")

        except PlaywrightTimeoutError as e:
            save_debug(page, "99_timeout.png")
            raise RuntimeError(
                f"Timed out during Cronometer export flow. Current URL: {page.url}"
            ) from e
        except Exception:
            save_debug(page, "98_general_error.png")
            raise
        finally:
            context.close()
            browser.close()


def main_with_retry(retries: int = 3, delay_seconds: int = 5) -> None:
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            print(f"Starting Cronometer export attempt {attempt}/{retries}...")
            run_export()
            print(f"Latest CSV: {newest_csv_path()}")
            return
        except Exception as e:
            last_error = e
            print(f"Attempt {attempt} failed: {e}")
            if attempt < retries:
                print(f"Retrying in {delay_seconds} seconds...")
                time.sleep(delay_seconds)

    raise RuntimeError(f"All {retries} export attempts failed.") from last_error


if __name__ == "__main__":
    main_with_retry()