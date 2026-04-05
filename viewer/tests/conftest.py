"""Playwright conftest — use the pre-installed Chromium binary."""
import os
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

CHROME_BIN = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as p:
        yield p

@pytest.fixture(scope="session")
def browser(playwright_instance):
    b = playwright_instance.chromium.launch(
        headless=True,
        executable_path=CHROME_BIN,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    yield b
    b.close()

@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 820})
    p = ctx.new_page()
    yield p
    ctx.close()
