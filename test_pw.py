import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        try:
            print("Launching chrome...")
            browser = await p.chromium.launch(
                headless=False,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled"]
            )
            print("Success!")
            await browser.close()
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(test())
