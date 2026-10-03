import struct
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app import create_app
from app.config import Config

ENV = {"ND_URL": "http://nd:4533", "ND_USER": "u", "ND_PASS": "p"}
ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "app" / "static" / "icons"


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", data[16:24])  # width, height from the IHDR chunk


@pytest.fixture
def client():
    app = create_app(Config.from_env(ENV))
    nd = app.extensions["nd"] = MagicMock()
    nd.get_genres.return_value = []
    nd.get_album_list2.return_value = []
    return app.test_client()


def test_manifest_makes_it_an_installable_app_called_play(client):
    r = client.get("/manifest.webmanifest")
    m = r.get_json()
    assert r.status_code == 200 and r.mimetype == "application/manifest+json"
    assert m["name"] == "Play" and m["short_name"] == "Play"
    assert m["display"] == "standalone"            # iOS treats "browser" as a bookmark, not an app
    assert m["start_url"] == "/" and m["scope"] == "/"
    assert m["background_color"] == m["theme_color"] == "#0b0b0d"


def test_manifest_has_any_and_maskable_icons(client):
    icons = client.get("/manifest.webmanifest").get_json()["icons"]
    assert {i["sizes"] for i in icons} >= {"192x192", "512x512"}
    assert {"any", "maskable"} <= {i["purpose"] for i in icons}
    assert all(i["type"] == "image/png" and i["src"].startswith("/static/icons/") for i in icons)


def test_every_icon_the_manifest_lists_exists_at_its_declared_size(client):
    for icon in client.get("/manifest.webmanifest").get_json()["icons"]:
        w, h = (int(n) for n in icon["sizes"].split("x"))
        assert png_size(ICONS / Path(icon["src"]).name) == (w, h), icon["src"]


def test_apple_touch_icon_is_180_square():
    assert png_size(ICONS / "apple-touch-icon.png") == (180, 180)


def test_icons_are_packaged_so_the_docker_image_has_them():
    """Non-Python files only ship if package-data names them (the image had no templates once)."""
    globs = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]["app"]
    assert any(g.startswith("static/icons/") for g in globs)


def test_every_launch_splash_linked_for_ios_exists_and_is_packaged(client):
    import re
    html = client.get("/").text
    links = re.findall(r'<link rel="apple-touch-startup-image" href="([^"]+)" media="([^"]+)"', html)
    assert len(links) == 17
    for href, media in links:
        path = ROOT / "app" / href.lstrip("/")
        assert path.exists(), href
        w, h = png_size(path)
        dpr = 3 if "-webkit-device-pixel-ratio: 3" in media else 2
        css_w, css_h = (int(x) for x in re.findall(r"device-(?:width|height): (\d+)px", media))
        assert (w, h) in {(css_w * dpr, css_h * dpr), (css_h * dpr, css_w * dpr)}, href  # media matches the pixels
    globs = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]["app"]
    assert any(g.startswith("static/splash/") for g in globs)


def test_search_box_is_16px_so_ios_does_not_zoom_on_focus():
    import re
    css = (ROOT / "app" / "static" / "css" / "app.css").read_text()
    search = re.search(r"\n\.search \{(.*?)\}", css, re.S).group(1)
    assert re.search(r"font-size: (\d+)px", search).group(1) == "16"
    room_picker = re.search(r"\n\.panel select \{(.*?)\}", css, re.S).group(1)
    assert re.search(r"font-size: (\d+)px", room_picker).group(1) == "16"  # the album room picker zooms too
    desktop = re.search(r"@media \(min-width: 900px\) \{ \.search \{(.*?)\} \}", css).group(1)
    assert "min-width: 180px" in desktop  # focus rule (150px) must not shrink the wide box


def test_service_worker_is_served_from_the_root_and_registered(client):
    r = client.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.mimetype
    assert r.headers["Cache-Control"] == "no-cache"
    assert 'navigator.serviceWorker.register("/sw.js")' in client.get("/").text


def test_pages_link_the_manifest_and_apple_meta_tags(client):
    html = client.get("/").text
    assert '<link rel="manifest" href="/manifest.webmanifest">' in html
    assert 'rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png"' in html
    assert 'name="apple-mobile-web-app-title" content="Play"' in html
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html
    assert "<title>Play</title>" in html
    assert 'media="(prefers-color-scheme: light)"' in html  # theme-color for both schemes


def test_ipados_detection_runs_before_paint_and_excludes_real_macs(client):
    html = client.get("/").text
    head, body = html.split("<body", 1)
    script = head[head.index('navigator.platform === "MacIntel"') - 40:]
    assert "classList.add(\"ipados\")" in script
    assert "defer" not in script.split("</script>")[0]  # must run before CSS paints, not after
    assert "maxTouchPoints > 1" in script  # a real Mac reports 0; only iPad matches both checks


def test_top_safe_area_has_an_ipados_windowed_chrome_buffer():
    css = (ROOT / "app" / "static" / "css" / "app.css").read_text()
    assert "html.ipados { --top-chrome: 10px; }" in css
    top_rules = [l for l in css.splitlines() if "safe-area-inset-top" in l and not l.lstrip().startswith(("*", "/*"))]
    assert len(top_rules) == 5 and all("var(--top-chrome)" in l for l in top_rules)  # every top usage
    bottom_rules = [l for l in css.splitlines() if "safe-area-inset-bottom" in l]
    assert bottom_rules and not any("top-chrome" in l for l in bottom_rules)  # unaffected
