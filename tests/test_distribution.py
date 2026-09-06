from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

from assayer_platform.surface_conformance import inspect_plugin_surface


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "ass_spec"


class DistributionTests(unittest.TestCase):
    def test_distribution_includes_policy_resources(self):
        external = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]
        package_data = external["package-data"]["ass_spec"]
        self.assertIn("*.json", package_data)
        self.assertIn("*.md", package_data)
        self.assertIn("evaluation/*", package_data)
        for name in ("manifest.json", "recognition.json", "policy.json", "checklist.json",
                     "authority.md", "self-check-checklist.md", "quality-standard.md",
                     "spec-template.md", "nfr-catalog.md", "scope.schema.json"):
            self.assertTrue((PACKAGE_ROOT / name).is_file(), name)
        self.assertTrue((PACKAGE_ROOT / "evaluation" / "corpus.json").is_file())


class SurfaceTests(unittest.TestCase):
    def test_imports_stay_within_the_public_sdk_surface(self):
        report = inspect_plugin_surface(ROOT / "src")
        self.assertTrue(report.passed, [issue.as_dict() for issue in report.issues])


if __name__ == "__main__":
    unittest.main()
