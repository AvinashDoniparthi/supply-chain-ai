import unittest

from scraping.supplier_discovery import supplier_evidence_is_strong


class TestSupplierEvidenceValidation(unittest.TestCase):
    def test_tier_three_rejects_generic_cooccurrence(self):
        evidence = [
            {"snippet": "RTX Corporation is a competitor and industry peer in aerospace."},
            {"snippet": "Raytheon was acquired in a separate context and is an industry peer."},
        ]

        for candidate in ["RTX Corporation", "Raytheon", "Capital Group", "MITRE Corporation"]:
            with self.subTest(candidate=candidate):
                accepted, reason = supplier_evidence_is_strong(evidence, tier=3, confidence=0.92)
                self.assertFalse(accepted)
                self.assertIn("Tier-3", reason)

    def test_tier_three_accepts_direct_supplier_statements(self):
        evidence = [
            {"snippet": "TSMC manufactures chips for Apple under a supply agreement."},
            {"snippet": "Apple sources advanced semiconductors from TSMC."},
        ]

        accepted, reason = supplier_evidence_is_strong(evidence, tier=3, confidence=0.93)
        self.assertTrue(accepted, reason)

    def test_tier_two_rejects_evidence_below_weighted_threshold(self):
        evidence = [
            {"snippet": "A long-running partnership exists between the companies."}
        ]

        accepted, reason = supplier_evidence_is_strong(evidence, tier=2, confidence=0.88)
        self.assertFalse(accepted)
        self.assertIn("Score:", reason)

    def test_globalfoundries_survives_tier_two_weighted_filtering(self):
        evidence = [
            {
                "snippet": (
                    "GlobalFoundries is part of TSMC's semiconductor ecosystem "
                    "and appears in supply-chain report coverage for foundry manufacturing."
                )
            }
        ]

        accepted, reason = supplier_evidence_is_strong(
            evidence, tier=2, confidence=0.88, candidate_name="GlobalFoundries"
        )
        self.assertTrue(accepted, reason)

    def test_umc_survives_tier_two_weighted_filtering(self):
        evidence = [
            {
                "snippet": (
                    "United Microelectronics Corporation is referenced with TSMC "
                    "in semiconductor manufacturing ecosystem coverage and sourcing analysis."
                )
            }
        ]

        accepted, reason = supplier_evidence_is_strong(
            evidence,
            tier=2,
            confidence=0.88,
            candidate_name="United Microelectronics Corporation",
        )
        self.assertTrue(accepted, reason)

    def test_component_specific_display_evidence_is_accepted(self):
        evidence = [
            {
                "title": "Apple iPhone 16 Pro teardown",
                "snippet": "Apple's iPhone 16 Pro uses an OLED panel supplied by Samsung Display.",
            }
        ]

        accepted, reason = supplier_evidence_is_strong(
            evidence,
            tier=1,
            confidence=0.74,
            candidate_name="Samsung Display Co., Ltd.",
            source_company="Apple",
            product_name="iPhone 16 Pro",
            component_name="Display",
        )
        self.assertTrue(accepted, reason)

    def test_component_specific_camera_sensor_evidence_is_accepted(self):
        evidence = [
            {
                "title": "Apple iPhone bill of materials",
                "snippet": "Apple iPhone image sensor components are supplied by Sony Semiconductor Solutions.",
            }
        ]

        accepted, reason = supplier_evidence_is_strong(
            evidence,
            tier=1,
            confidence=0.73,
            candidate_name="Sony Semiconductor Solutions",
            source_company="Apple",
            product_name="iPhone 16 Pro",
            component_name="Camera Sensor",
        )
        self.assertTrue(accepted, reason)


if __name__ == "__main__":
    unittest.main()
