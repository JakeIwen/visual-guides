import ast
import json
from pathlib import Path
import unittest

import deploy


ROOT = Path(__file__).resolve().parents[1]


class BackendContractTests(unittest.TestCase):
    def test_contract_table_names_every_external_path_and_real_owner(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        table = text.split("## Contracts", 1)[1].strip().split("\n\n", 1)[0]
        rows = {}
        for line in table.splitlines():
            cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
            if len(cells) == 3 and cells[0] not in {"Path", "---"}:
                rows[cells[0]] = (cells[1], cells[2])
        self.assertEqual(set(rows), {"app.py", "python3 -m local_service", "deploy.py", "hardware_setup.py"})
        expected_owners = {
            "app.py": ("visual_guides_server.py", "visual_guides_cli.py"),
            "python3 -m local_service": ("local_service/__main__.py", "local_service/control.py"),
            "deploy.py": ("deploy.py",),
            "hardware_setup.py": ("hardware_setup.py",),
        }
        for contract, owners in expected_owners.items():
            self.assertTrue(rows[contract][0], contract)
            for owner in owners:
                self.assertIn(owner, rows[contract][1])
                self.assertTrue((ROOT / owner).is_file(), owner)

    def test_stable_entry_is_thin_and_release_contains_its_owners(self):
        entry = ROOT / "app.py"
        self.assertLessEqual(len(entry.read_text(encoding="utf-8").splitlines()), 25)
        artifacts = set(deploy.artifact_paths(ROOT))
        self.assertTrue({"app.py", "visual_guides_cli.py", "visual_guides_server.py"} <= artifacts)

    def test_server_module_does_not_own_argument_or_client_adapters(self):
        tree = ast.parse((ROOT / "visual_guides_server.py").read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertFalse({"argparse", "http.client"} & imports)

    def test_declared_package_and_systemd_targets_exist(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        scripts = package["scripts"]
        self.assertIn("deploy.py", scripts["deploy:check"])
        self.assertIn("deploy.py", scripts["deploy:pi"])
        for name in scripts:
            if name.startswith("service:"):
                self.assertIn("-m local_service", scripts[name])
        unit = (ROOT / "visual-guides.service").read_text(encoding="utf-8")
        self.assertIn("/home/pi/visual-guides/current/app.py", unit)
        for path in ("app.py", "deploy.py", "hardware_setup.py", "local_service/__main__.py"):
            self.assertTrue((ROOT / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
