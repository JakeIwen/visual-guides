"""Keep the published guide dependency graph local and owned by its consumers."""

from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import unittest
from urllib.parse import unquote, urlsplit


STATIC = Path(__file__).resolve().parents[1] / "static"
PALETTE = STATIC / "assets" / "palette.css"
CSS_IMPORT = re.compile(r'@import\s+[\'"]([^\'"]+)[\'"]\s*;')
COLOR = re.compile(r'#[\da-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lch|lab)\(')


class PageResources(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.resources = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("src"):
            self.resources.append(attrs["src"])
        if tag == "link" and attrs.get("rel") in {"stylesheet", "icon"}:
            self.resources.append(attrs["href"])


class StaticContractTests(unittest.TestCase):
    def local_resource(self, owner, reference):
        parsed = urlsplit(reference)
        self.assertFalse(parsed.scheme or parsed.netloc, (owner, reference))
        path = unquote(parsed.path)
        target = (STATIC / path.lstrip("/") if path.startswith("/")
                  else owner.parent / path).resolve()
        self.assertTrue(target.is_relative_to(STATIC), (owner, reference))
        self.assertTrue(target.is_file(), f"{owner}: missing {reference}")
        return target

    def dependencies(self, page):
        pending = [(page, value) for value in PageResources(page.read_text()).resources]
        found = set()
        while pending:
            owner, reference = pending.pop()
            target = self.local_resource(owner, reference)
            if target in found:
                continue
            found.add(target)
            if target.suffix == ".css":
                pending.extend((target, value) for value in CSS_IMPORT.findall(target.read_text()))
        return found

    def test_asset_dependencies_exist_and_private_assets_belong_to_their_page(self):
        pages = sorted(STATIC.rglob("*.html"))
        self.assertTrue(pages, "No guide pages discovered")
        consumers = {}
        for page in pages:
            for resource in self.dependencies(page):
                consumers.setdefault(resource, set()).add(page)
        assets = [path for path in STATIC.rglob("*") if path.suffix in {".css", ".js"}]
        self.assertTrue(assets, "No styles or scripts discovered")
        for asset in assets:
            with self.subTest(asset=asset.relative_to(STATIC)):
                self.assertIn(asset, consumers, "Unreferenced asset")
                if len(consumers[asset]) == 1:
                    self.assertEqual(asset.with_suffix(".html"), next(iter(consumers[asset])),
                                     "A private asset belongs beside its page with the same name")
                else:
                    self.assertEqual(asset.parent, STATIC / "assets",
                                     "Shared assets belong in the shared layer")

    def test_colors_and_theme_overrides_have_one_owner(self):
        self.assertTrue(PALETTE.is_file())
        for sheet in STATIC.rglob("*.css"):
            if sheet == PALETTE:
                continue
            with self.subTest(sheet=sheet.relative_to(STATIC)):
                source = re.sub(r"/\*.*?\*/", "", sheet.read_text(), flags=re.S)
                self.assertIsNone(COLOR.search(source), "Use a palette token for CSS colors")
                self.assertNotIn("prefers-color-scheme", source)
                self.assertNotIn("[data-theme", source)

    def test_every_browser_script_parses(self):
        scripts = sorted(STATIC.rglob("*.js"))
        self.assertTrue(scripts, "No browser scripts discovered")
        for script in scripts:
            with self.subTest(script=script.relative_to(STATIC)):
                result = subprocess.run(["node", "--check", str(script)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
