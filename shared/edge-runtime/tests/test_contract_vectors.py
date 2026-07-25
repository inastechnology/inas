import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


class SyncContractVectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_dir = Path(__file__).resolve().parents[2] / "contracts" / "sync" / "v1"
        cls.schema = json.loads((cls.contract_dir / "sync.schema.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((cls.contract_dir / "vectors" / "manifest.json").read_text(encoding="utf-8"))

    def test_schema_is_valid_draft_2020_12(self):
        Draft202012Validator.check_schema(self.schema)

    def test_all_manifest_vectors_have_expected_validity(self):
        checked = []
        for entry in self.manifest:
            with self.subTest(vector=entry["file"]):
                document = json.loads((self.contract_dir / "vectors" / entry["file"]).read_text(encoding="utf-8"))
                wrapper = {
                    "$schema": self.schema["$schema"],
                    "$defs": self.schema["$defs"],
                    "$ref": f"#/$defs/{entry['definition']}",
                }
                validator = Draft202012Validator(wrapper, format_checker=FormatChecker())
                errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
                self.assertEqual(not errors, entry["valid"], [error.message for error in errors])
                checked.append(entry["file"])
        self.assertEqual(checked, [entry["file"] for entry in self.manifest])


if __name__ == "__main__":
    unittest.main()
