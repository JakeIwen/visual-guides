"""The web guide and terminal reader consume one validated public catalog."""

import copy
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import keyboard_reference as reference


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "keyboard-shortcuts.json"


# Publication tripwires, not reader policy or proof of privacy: curated review is
# still required. Report locations only, never a possibly private matched value.
PRIVACY_PATTERNS = {
    "URL": re.compile(r"\b[a-z][a-z0-9+.-]*://|\b(?:mailto:|www\.)", re.I),
    "private hostname": re.compile(r"(?<![\w.-])(?:[a-z0-9_-]+\.)+(?:lan|local|ts\.net)\b", re.I),
    "email address": re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+", re.I),
    "private home path": re.compile(r"/(?:Users|home)/[^/\s]+|/root/|[a-z]:\\Users\\", re.I),
}
ACTION_REVIEW_LIMIT = 240


def catalog_strings(value, location="catalog"):
    if isinstance(value, str):
        yield location, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from catalog_strings(child, location + "." + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from catalog_strings(child, "{}[{}]".format(location, index))


def privacy_findings(catalog):
    findings = []
    for location, text in catalog_strings(catalog):
        for label, pattern in PRIVACY_PATTERNS.items():
            if pattern.search(text):
                findings.append((location, label))
        candidates = re.findall(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)", text)
        candidates += [part.rstrip(".") for part in re.findall(r"[0-9a-f:.]+", text, re.I) if ":" in part]
        for candidate in candidates:
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            findings.append((location, "IP address"))
            break
        if location.endswith(".action") and len(text) > ACTION_REVIEW_LIMIT:
            findings.append((location, "long action payload"))
    return findings


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.targets = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.targets.append(dict(attrs).get("href", ""))


class KeyboardReferenceTests(unittest.TestCase):
    def setUp(self):
        self.catalog = reference.load_catalog(FIXTURE)

    def cli(self, *args, catalog=FIXTURE):
        return subprocess.run(
            ["/usr/bin/python3", str(ROOT / "keyboard_reference.py"),
             "--catalog", str(catalog), *args], cwd="/", capture_output=True, text=True)

    def test_catalog_and_page_dependencies(self):
        reference.load_catalog()
        index = Links((ROOT / "static/index.html").read_text())
        self.assertIn("guides/keyboard-shortcuts.html", index.targets)
        page = Links((ROOT / "static/guides/keyboard-shortcuts.html").read_text())
        for name in ("keyboard-shortcuts.json", "keyboard-shortcuts.schema.json"):
            self.assertIn("../reference/" + name, page.targets)
            self.assertTrue((ROOT / "static/reference" / name).is_file())
        self.assertTrue(any("/commits/" in href for href in page.targets))
        self.assertTrue(any("/blob/" in href for href in page.targets))

    def test_default_cli_and_sequence_output_from_unrelated_directory(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        for text in ("Test BTT / Test editor", "Cmd+C", "a then b", "[conditional]",
                     "Conditional mappings have requirements; use --details."):
            self.assertIn(text, result.stdout)
        for text in ("Retired test action", "Editable test field", "fixture-copy.js",
                     "Verified:", "Conditions:", "Limitations:", *self.catalog["notes"]):
            self.assertNotIn(text, result.stdout)
        self.assertNotIn("\x1b", result.stdout)
        direct = subprocess.run(["/usr/bin/python3", str(ROOT / "keyboard_reference.py"),
                                 "--json"], cwd="/", capture_output=True, text=True)
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertEqual(json.loads(direct.stdout)["entries"], reference.select_entries(reference.load_catalog()))

    def test_filter_and_print_parity_with_browser(self):
        result = subprocess.run(["node", str(ROOT / "tests/keyboard_reference_cases.cjs")],
                                cwd="/", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        cases = [{}, {"include_disabled": True}, {"search": "CMD+c"},
                 {"search": "fixture-shell", "include_disabled": True}, {"provider": "Test BTT"},
                 {"scope": "Test terminal", "include_disabled": True}, {"search": "no match"},
                 {"search": " mouse "}, {"provider": "Test zsh"}, {"search": "ab"},
                 {"search": "a b"}]
        actual = []
        for options in cases:
            entries = reference.select_entries(self.catalog, **options)
            actual.append([entry["id"] for entry in entries])
            text = reference.format_reference(self.catalog, entries, options.get("include_disabled", False),
                                              details=True)
            for entry in entries:
                self.assertIn(entry["action"], text)
                self.assertIn(" then ".join(entry["keys"]), text)
                self.assertIn(entry["sources"][0], text)
        self.assertEqual(actual, json.loads(result.stdout))
        self.assertEqual(actual[-2:], [["test-copy", "test-sequence"], ["test-sequence"]])

    def test_production_key_labels_and_group_order(self):
        entries = reference.load_catalog()["entries"]
        for entry in entries:
            for key in entry["keys"]:
                self.assertNotRegex(key, r"\b(?:Cmd|Ctrl|Option|Shift|Fn|Control|Command|Alt|Meta|Super)-")
        order = [(entry["provider"].casefold(), entry["scope"].casefold(),
                  tuple(key.casefold() for key in entry["keys"]), entry["id"]) for entry in entries]
        self.assertEqual(order, sorted(order))
        minus = next(entry for entry in entries if entry["id"] == "iterm-global-2d-100000")
        self.assertEqual(minus["keys"], ["Cmd+-"])

    def test_production_sequence_search_from_cli(self):
        result = self.cli("cosnt", "--json", catalog=reference.CATALOG)
        self.assertEqual(result.returncode, 0, result.stderr)
        entries = json.loads(result.stdout)["entries"]
        self.assertEqual([entry["id"] for entry in entries], ["btt-f8df2b59-10f6-45ea-8c61-8d216dba2593"])
        self.assertEqual(entries[0]["keys"], ["C", "O", "S", "N", "T", "Space"])
        self.assertEqual(entries[0]["action"], "Insert saved text (private).")
        result = self.cli("Cmd+X", "--all", "--json", catalog=reference.CATALOG)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("terminal-clipboard-cut", [entry["id"] for entry in json.loads(result.stdout)["entries"]])

    def test_concise_search_and_explicit_detail_flags(self):
        concise = self.cli("CMD+c")
        self.assertEqual(concise.returncode, 0, concise.stderr)
        self.assertIn("Copy a test line [conditional]", concise.stdout)
        self.assertNotIn("fixture-copy.js", concise.stdout)
        self.assertNotIn("Editable test field", concise.stdout)
        for note in self.catalog["notes"]:
            self.assertNotIn(note, concise.stdout)
        detailed = self.cli("CMD+c", "--details")
        self.assertEqual(detailed.returncode, 0, detailed.stderr)
        for text in ("Conditions: Editable test field", "Limitations: Test mouse selection",
                     "Source: tests/fixture-copy.js", "Verified: 2026-11-04"):
            self.assertIn(text, detailed.stdout)
        for note in self.catalog["notes"]:
            self.assertNotIn(note, detailed.stdout)
        notes = self.cli("CMD+c", "--notes")
        self.assertEqual(notes.returncode, 0, notes.stderr)
        self.assertNotIn("Source:", notes.stdout)
        for note in self.catalog["notes"]:
            self.assertIn(note, notes.stdout)
            self.assertGreater(notes.stdout.index(note), notes.stdout.index("1 mapping(s)."))
        combined = self.cli("CMD+c", "--details", "--notes")
        self.assertEqual(combined.returncode, 0, combined.stderr)
        self.assertIn("Source: tests/fixture-copy.js", combined.stdout)
        self.assertIn(self.catalog["notes"][0], combined.stdout)
        complete = self.cli("--all", "--json", "--details", "--notes")
        self.assertEqual(complete.returncode, 0, complete.stderr)
        self.assertEqual(json.loads(complete.stdout), self.catalog)

    def test_cli_options_and_empty_result(self):
        for args, ids in [(("--all", "--provider", "Test zsh"), ["test-disabled"]),
                          (("--all", "--scope", "Test terminal"), ["test-disabled"]),
                          (("retired", "--all", "test"), ["test-disabled"]),
                          (("test", "retired", "--all"), []),
                          (("CMD+c",), ["test-copy"]), (("not", "found"), [])]:
            result = self.cli("--json", *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([entry["id"] for entry in json.loads(result.stdout)["entries"]], ids)
        self.assertIn("No matching shortcuts", self.cli("not-found").stdout)
        self.assertEqual(self.cli("--help").returncode, 0)
        self.assertEqual(self.cli("--not-an-option").returncode, 2)

    def test_all_status_uses_option_not_matching_rows(self):
        for args in (("--provider", "Test BTT"), ("nomatch",), ("--provider", "absent")):
            result = self.cli("--all", *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Disabled mappings are included.", result.stdout)
            self.assertNotIn("--all", result.stdout)
            self.assertNotIn("hidden", result.stdout)
        self.assertIn("or --all", self.cli("nomatch").stdout)
        empty = dict(self.catalog, entries=[])
        text = reference.format_reference(empty, [], include_disabled=True)
        self.assertIn("No verified mappings", text)
        self.assertIn("Use --notes", text)
        self.assertIn("Disabled mappings are included.", text)

    def test_utf8_bom_catalog_matches_plain_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "catalog.json"
            path.write_text(json.dumps(self.catalog), encoding="utf-8-sig")
            self.assertEqual(reference.load_catalog(path), self.catalog)
            result = self.cli("--json", "--all", catalog=path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), self.catalog)

    def test_unicode_validation_parity(self):
        rejected = ["\ufeff", "text\u202eoverride", "zero\u200bwidth", "join\u200der",
                    "line\u2028separator", "paragraph\u2029separator", "a\x85b", "a\x00b"]
        accepted = ["⌘+C", "1️⃣", "Éditer → sélectionner", "@", "Shift+2 (@ on US layout)"]
        catalogs = []
        expected = []
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "catalog.json"
            for field in ("action", "keys", "notes"):
                for text in rejected + accepted:
                    data = copy.deepcopy(self.catalog)
                    if field == "notes":
                        data["notes"] = [text]
                    else:
                        data["entries"][0][field] = [text] if field == "keys" else text
                    valid = text in accepted
                    catalogs.append(data)
                    expected.append(valid)
                    path.write_text(json.dumps(data), encoding="utf-8")
                    result = self.cli("--json", "--all", catalog=path)
                    self.assertEqual(result.returncode, 0 if valid else 2, (field, repr(text)))
                    if valid:
                        self.assertEqual(json.loads(result.stdout), data)
                    else:
                        self.assertEqual(result.stdout, "")
            node = subprocess.run(["node", str(ROOT / "tests/keyboard_reference_cases.cjs"),
                                   "--validate-catalogs"], input=json.dumps(catalogs),
                                  cwd="/", capture_output=True, text=True)
            self.assertEqual(node.returncode, 0, node.stderr)
            self.assertEqual(json.loads(node.stdout), expected)

    def test_production_catalog_privacy_tripwires(self):
        self.assertEqual(privacy_findings(reference.load_catalog()), [])

    def test_privacy_tripwires_detect_samples_without_banning_at_keys(self):
        samples = {
            "URL": ["https://example.invalid/path", "smb://example.invalid/share", "www.example.invalid"],
            "private hostname": ["fixture.lan", "fixture.local", "fixture.tail000000.ts.net"],
            "email address": ["fixture@example.invalid", "fixture+tag@example.invalid"],
            "IP address": ["192.0.2.123", "[2001:db8::1]", "::ffff:192.0.2.123",
                           "Connect to 192.0.2.123.", "Connect to 2001:db8::1."],
            "private home path": ["/Users/fixture/file", "/home/fixture/file", r"C:\Users\fixture\file"],
            "long action payload": ["x" * (ACTION_REVIEW_LIMIT + 1)],
        }
        for label, values in samples.items():
            for value in values:
                data = copy.deepcopy(self.catalog)
                data["entries"][0]["action"] = value
                self.assertIn(("catalog.entries[0].action", label), privacy_findings(data))
        # Review notes and sources too; the guard is not restricted to actions.
        self.assertIn(("catalog.notes[0]", "URL"), privacy_findings({"notes": ["https://example.invalid"]}))
        self.assertIn(("catalog.sources[0]", "private home path"),
                      privacy_findings({"sources": ["/Users/fixture/source.json"]}))
        safe = copy.deepcopy(self.catalog)
        safe["entries"][0]["keys"] = ["@", "Shift+2 (@ on US layout)"]
        safe["entries"][0]["sources"] = ["~/Library/fixture.json", "tests/fixture.json"]
        self.assertEqual(privacy_findings(safe), [])

    def test_invalid_catalogs_are_refused_instead_of_partially_printed(self):
        changes = [
            lambda data: data["entries"].append(data["entries"][0]),
            lambda data: data["entries"][0].update(status="planned"),
            lambda data: data["entries"][0].update(verified="2026-02-30"),
            lambda data: data["entries"][0].update(keys=[]),
            lambda data: data["entries"][0].update(conditions=""),
            lambda data: data["entries"][0].update(action="\x1b[31m"),
            lambda data: data["entries"][0].update(action=" "),
            lambda data: data["entries"][0].update(private_payload="not allowed"),
            lambda data: data["entries"][0].pop("sources"),
            lambda data: data.update(schema_version=True),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "catalog.json"
            for change in changes:
                data = copy.deepcopy(self.catalog)
                change(data)
                path.write_text(json.dumps(data))
                with self.assertRaises(reference.CatalogError):
                    reference.load_catalog(path)
                result = self.cli(catalog=path)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr)
            for malformed in ("{broken", "null", "[]", '{"schema_version": 1}'):
                path.write_text(malformed)
                result = self.cli(catalog=path)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
            result = self.cli(catalog=Path(temporary) / "missing.json")
            self.assertEqual(result.returncode, 2)
            self.assertIn("Cannot read keyboard reference", result.stderr)


if __name__ == "__main__":
    unittest.main()
