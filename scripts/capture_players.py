"""Capture actual rendered video elements from public camera pages.

No credentials, origin spoofing, challenge-solving, or TLS exceptions. Only a
ready video (or an explicitly configured camera-image frame) may be captured.
"""
import asyncio
from collections import defaultdict
import re
from playwright.async_api import async_playwright
from build_snapshots import public_url, write_snapshot


async def descendant_frames(frame):
    yield frame
    for child in frame.child_frames:
        async for descendant in descendant_frames(child):
            yield descendant


async def selected_frames(page, config):
    if config.get("frameMatch"):
        match = config["frameMatch"]
        for frame in page.frames:
            if match in frame.url:
                return [frame]
        return []
    if config.get("label"):
        label = re.compile(r"^" + re.escape(config["label"]) + r"$", re.I)
        text = page.get_by_text(label).first
        if not await text.count():
            return []
        parent = text
        for _ in range(7):
            parent = parent.locator("xpath=..")
            iframe = parent.locator("iframe")
            count = await iframe.count()
            if count == 1:
                element = await iframe.element_handle()
                frame = await element.content_frame()
                return [frame] if frame else []
            if count > 1:
                return []  # Ambiguous mapping must not show a different camera.
        return []
    return [page.main_frame]


async def capture_view(page, config):
    for _ in range(10):
        for root in await selected_frames(page, config):
            async for frame in descendant_frames(root):
                for video in await frame.locator("video").all():
                    if not await video.is_visible():
                        continue
                    ready = await video.evaluate("v => v.readyState >= 2 && v.videoWidth >= 160 && v.videoHeight >= 90")
                    if ready:
                        return await video.screenshot(type="jpeg", quality=85, timeout=6000)
                if config.get("imageFrame"):
                    for image in await frame.locator("img").all():
                        ready = await image.evaluate("i => i.complete && i.naturalWidth >= 160 && i.naturalHeight >= 90 && !new URL(i.currentSrc).username")
                        if ready and await image.is_visible():
                            return await image.screenshot(type="jpeg", quality=85, timeout=6000)
        await asyncio.sleep(1)
    raise ValueError("No ready camera image or video")


async def run(cameras, configs, output, previous):
    groups = defaultdict(list)
    for camera in cameras:
        config = configs.get(camera["id"], {})
        # Direct players for image-backed sources are not needed for first rollout.
        if camera.get("previewSrc") or camera["provider"] == "image":
            continue
        url = config.get("page", camera["src"] if camera["provider"] == "iframe" else camera["source"])
        groups[public_url(url)].append((camera, config))
    entries = {}
    semaphore = asyncio.Semaphore(3)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        async def group(url, items):
            async with semaphore:
                context = await browser.new_context(viewport={"width": 1280, "height": 900}, locale="en-US")
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=40000)
                    # Ordinary cookie choices, when present, enable camera frames.
                    for label in ["Accept All Cookies", "Accept all cookies", "Accept All"]:
                        button = page.get_by_role("button", name=label, exact=True)
                        if await button.count() and await button.first.is_visible():
                            await button.first.click(timeout=3000)
                            break
                    for camera, config in items:
                        try:
                            if config.get("frameMatch"):
                                selector = 'iframe[src*="' + config["frameMatch"] + '"], iframe[data-src*="' + config["frameMatch"] + '"]'
                                target = page.locator(selector).first
                                if await target.count():
                                    await target.scroll_into_view_if_needed(timeout=6000)
                            body = await capture_view(page, config)
                            entries[camera["id"]] = write_snapshot(output, camera["id"], body, previous.get(camera["id"]), method="rendered-camera")
                            print("Captured player: " + camera["id"], flush=True)
                        except Exception:
                            print("Player not ready: " + camera["id"], flush=True)
                except Exception:
                    print("Camera page unavailable: " + items[0][0]["resort"], flush=True)
                finally:
                    await context.close()
        await asyncio.gather(*(group(url, items) for url, items in groups.items()))
        await browser.close()
    return entries


def capture_players(cameras, configs, output, previous):
    return asyncio.run(run(cameras, configs, output, previous))
