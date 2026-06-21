import unittest

from scraping.supplier_discovery import normalize_supplier_candidate_name


class TestSupplierCandidateNormalization(unittest.TestCase):
    def test_converts_sentence_fragments_to_company_names(self):
        examples = {
            "Micron became a major supplier to Apple Inc": "Micron",
            "Fabless manufacturing including Apple Inc": "Apple Inc",
            "Raytheon is a business unit of RTX Corporation": "Raytheon",
            "International with Magna Electronics Corporation": "Magna Electronics Corporation",
        }

        for raw_name, expected in examples.items():
            with self.subTest(raw_name=raw_name):
                self.assertEqual(normalize_supplier_candidate_name(raw_name), expected)

    def test_drops_unidentifiable_organization_fragments(self):
        invalid_names = [
            "Fabless manufacturing",
            "became a supplier to",
            "including",
            "supplier to",
            "company",
            "ThinkPad",
        ]

        for raw_name in invalid_names:
            with self.subTest(raw_name=raw_name):
                self.assertIsNone(normalize_supplier_candidate_name(raw_name))

    def test_drops_target_company_after_normalization(self):
        self.assertIsNone(
            normalize_supplier_candidate_name(
                "Fabless manufacturing including Apple Inc", "Apple"
            )
        )

    def test_removes_repeated_company_prefixes(self):
        examples = {
            "Intel Intel Corporation": "Intel Corporation",
            "GlobalFoundries GlobalFoundries Inc": "GlobalFoundries Inc",
            "Paccar Paccar Inc": "Paccar Inc",
            "IDEX Corporation IDEX Corporation": "IDEX Corporation",
        }

        for raw_name, expected in examples.items():
            with self.subTest(raw_name=raw_name):
                self.assertEqual(normalize_supplier_candidate_name(raw_name), expected)

    def test_repeated_generic_names_are_rejected(self):
        for raw_name in ["Company Company Limited", "Corporation Corporation", "Inc Inc"]:
            with self.subTest(raw_name=raw_name):
                self.assertIsNone(normalize_supplier_candidate_name(raw_name))


if __name__ == "__main__":
    unittest.main()
