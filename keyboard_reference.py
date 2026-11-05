#!/usr/bin/env python3
"""Read the public keyboard catalog; standalone, stdlib-only Python 3.9+."""

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
import unicodedata


REFERENCE = Path(__file__).resolve().parent / "static" / "reference"
CATALOG = REFERENCE / "keyboard-shortcuts.json"
SCHEMA = REFERENCE / "keyboard-shortcuts.schema.json"


class CatalogError(ValueError):
    """The catalog cannot safely be presented as verified mappings."""


def validate_value(value, rule, location="catalog"):
    """Validate the JSON Schema keywords used by our shared schema (no coercion)."""
    types = {"object": dict, "array": list, "string": str, "integer": int}
    kind = rule.get("type")
    valid_type = isinstance(value, types[kind])
    if kind == "integer":
        valid_type = ((isinstance(value, int) and not isinstance(value, bool))
                      or (isinstance(value, float) and value.is_integer()))
    if not valid_type:
        raise CatalogError("{}: expected {}".format(location, kind))
    if "const" in rule and value != rule["const"]:
        raise CatalogError("{}: unsupported value {!r}".format(location, value))
    if "enum" in rule and value not in rule["enum"]:
        raise CatalogError("{}: expected one of {}".format(location, rule["enum"]))
    if isinstance(value, dict):
        missing = set(rule.get("required", [])) - value.keys()
        extra = value.keys() - rule.get("properties", {}).keys()
        if missing:
            raise CatalogError("{}: missing {}".format(location, ", ".join(sorted(missing))))
        if extra and rule.get("additionalProperties") is False:
            raise CatalogError("{}: unknown fields {}".format(location, ", ".join(sorted(extra))))
        for key, child in value.items():
            validate_value(child, rule["properties"][key], location + "." + key)
    elif isinstance(value, list):
        if len(value) < rule.get("minItems", 0):
            raise CatalogError("{}: must not be empty".format(location))
        for index, child in enumerate(value):
            validate_value(child, rule["items"], "{}[{}]".format(location, index))
    elif isinstance(value, str):
        if len(value.strip()) < rule.get("minLength", 0):
            raise CatalogError("{}: must not be blank".format(location))
        if "pattern" in rule and re.search(rule["pattern"], value) is None:
            raise CatalogError("{}: invalid format".format(location))
        if any(unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} for char in value):
            raise CatalogError("{}: control/format characters are not allowed".format(location))
        if rule.get("format") == "date":
            try:
                date.fromisoformat(value)
            except ValueError as error:
                raise CatalogError("{}: invalid date".format(location)) from error


def load_catalog(path=CATALOG):
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8-sig"))
        catalog = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as error:
        raise CatalogError("Cannot read keyboard reference: {}".format(error)) from error
    validate_value(catalog, schema)
    ids = set()
    for entry in catalog["entries"]:
        if entry["id"] in ids:
            raise CatalogError("Duplicate mapping id: " + entry["id"])
        ids.add(entry["id"])
        if entry["status"] == "conditional" and not entry["conditions"].strip():
            raise CatalogError(entry["id"] + ": conditional mapping needs conditions")
    return catalog


def select_entries(catalog, search="", include_disabled=False, provider="", scope=""):
    query = search.strip().lower()
    return [entry for entry in catalog["entries"]
            if (include_disabled or entry["status"] != "disabled")
            and (not provider or entry["provider"] == provider)
            and (not scope or entry["scope"] == scope)
            and (not query or query in " ".join(
                " ".join(value) if isinstance(value, list) else value
                for value in entry.values()).lower() + (
                    " " + "".join(entry["keys"]).lower() if len(entry["keys"]) > 1 else ""))]


def format_reference(catalog, entries, include_disabled=False, details=False, notes=False):
    lines = ["Custom keyboard shortcuts"]
    groups = {}
    for entry in entries:
        groups.setdefault((entry["provider"], entry["scope"]), []).append(entry)
    for (provider, scope), mappings in groups.items():
        lines.extend(["", "{} / {}".format(provider, scope)])
        for entry in mappings:
            lines.append("  {} — {} [{}]".format(" then ".join(entry["keys"]),
                                                 entry["action"], entry["status"]))
            if details:
                for key in ("conditions", "limitations"):
                    if entry[key]:
                        lines.append("    {}: {}".format(key.capitalize(), entry[key]))
                lines.append("    Source: " + "; ".join(entry["sources"]))
                lines.append("    Verified: " + entry["verified"])
    if not entries:
        suggestion = "Try a broader search." if include_disabled else "Try a broader search or --all."
        message = ("No matching shortcuts. " + suggestion if catalog["entries"]
                   else "No verified mappings are listed yet. Use --notes for catalog coverage.")
        lines.extend(["", message])
    if not details and any(entry["status"] == "conditional" for entry in entries):
        lines.extend(["", "Conditional mappings have requirements; use --details."])
    lines.extend(["", "{} mapping(s). Disabled mappings are {}.".format(
        len(entries), "included" if include_disabled else "hidden unless --all is supplied")])
    if notes and catalog["notes"]:
        lines.extend(["", "Catalog notes"])
        lines.extend("  " + note for note in catalog["notes"])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("search", nargs="*", help="case-insensitive text search")
    parser.add_argument("--all", action="store_true", help="include disabled mappings")
    parser.add_argument("--provider", default="", help="exact provider name")
    parser.add_argument("--scope", default="", help="exact app/scope name")
    parser.add_argument("--json", action="store_true", help="print complete filtered catalog JSON")
    parser.add_argument("--details", action="store_true", help="show row conditions, limitations and provenance")
    parser.add_argument("--notes", action="store_true", help="show catalog-wide caveats after the results")
    parser.add_argument("--catalog", type=Path, default=CATALOG, help="alternate catalog path")
    args = parser.parse_intermixed_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        entries = select_entries(catalog, " ".join(args.search), args.all,
                                 args.provider, args.scope)
    except CatalogError as error:
        print(str(error), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(dict(catalog, entries=entries), ensure_ascii=False, indent=2))
    else:
        print(format_reference(catalog, entries, args.all, args.details, args.notes), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
