"""Playwright conftest — works on Mac and Linux."""
import os
import sys
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

# On Linux CI we use a pre-installed binary; on Mac let Playwright find it.
_LINUX_BIN = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
_USE_CUSTOM_BIN = sys.platform == "linux" and os.path.exists(_LINUX_BIN)

@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as p:
        yield p

@pytest.fixture(scope="session")
def browser(playwright_instance):
    kwargs = dict(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    if _USE_CUSTOM_BIN:
        kwargs["executable_path"] = _LINUX_BIN
    b = playwright_instance.chromium.launch(**kwargs)
    yield b
    b.close()

@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 820})
    p = ctx.new_page()
    yield p
    ctx.close()
