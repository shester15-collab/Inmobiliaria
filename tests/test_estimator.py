import json
import tempfile
import unittest
from pathlib import Path
from engine.estimator import load_dataset, unique_candidates, score_property, estimate

ROOT = Path(__file__).resolve().parents[1]

class PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds = load_dataset(ROOT/"data"/"jardines_del_bosque.json")
        cls.props = cls.ds["properties"]

    def test_eleven_publications_preserved(self):
        self.assertEqual(11, len(self.props))

    def test_probable_duplicate_group_counted_once(self):
        self.assertEqual(10, len(unique_candidates(self.props)))

    def test_zero_construction_normalized_to_unknown_and_raw_preserved(self):
        p = next(x for x in self.props if x["id"] == "CASA-04")
        self.assertIsNone(p["construction_m2"])
        self.assertEqual(0, p["raw_data"]["construction_m2"])

    def test_ambiguous_surface_not_assigned_as_land_or_construction(self):
        p = next(x for x in self.props if x["id"] == "CASA-06")
        self.assertIsNone(p["land_m2"])
        self.assertIsNone(p["construction_m2"])
        self.assertEqual(200, p["unknown_surface_m2"])

    def test_bedroom_conflict_preserved(self):
        p = next(x for x in self.props if x["id"] == "CASA-11")
        self.assertEqual(2, p["raw_data"]["description_bedrooms"])
        self.assertEqual(1, p["raw_data"]["structured_bedrooms"])
        self.assertEqual(1, len(p["source_conflicts"]))

    def test_closest_physical_match_scores_well(self):
        target = {"land_m2":120,"construction_m2":90,"bedrooms":2,"bathrooms":1,
                  "parking_spaces":1,"floors":1}
        p = next(x for x in self.props if x["id"] == "CASA-02")
        # Parking is unknown, so coverage now prevents a near-perfect score.
        self.assertGreaterEqual(score_property(target,p)["score"], 85)

    def test_estimator_returns_auditable_output(self):
        target = {"land_m2":120,"construction_m2":90,"bedrooms":2,"bathrooms":1,
                  "parking_spaces":1,"floors":1}
        result = estimate(target,self.props)
        self.assertIn("status",result)
        self.assertIn("comparables",result)
        for c in result["comparables"]:
            self.assertIn("url",c)
            self.assertIn("similarity_score",c)

    def test_complete_match_scores_higher_than_match_with_missing_essential_data(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        complete = {**target}
        missing = {**target, "construction_m2": None, "bedrooms": None}

        self.assertGreater(
            score_property(target, complete)["score"],
            score_property(target, missing)["score"],
        )

    def test_missing_data_is_not_interpreted_as_a_match(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        result = score_property(target, {"land_m2": 120})

        self.assertLess(result["score"], 100)
        self.assertEqual("missing", result["field_reasons"]["construction_m2"])

    def test_invalid_values_and_ambiguous_surfaces_are_safely_excluded(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        invalid = {"land_m2": "120", "construction_m2": -1, "bedrooms": "2",
                   "bathrooms": 1, "parking_spaces": 1, "floors": 1,
                   "unknown_surface_m2": 200}
        result = score_property(target, invalid)

        self.assertIsNone(result["details"]["land_m2"])
        self.assertEqual("invalid_candidate", result["field_reasons"]["land_m2"])
        self.assertEqual("invalid_candidate", result["field_reasons"]["construction_m2"])
        self.assertNotIn("unknown_surface_m2", result["details"])

    def test_estimate_keeps_audit_trail_for_duplicates_and_price_review(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        result = estimate(target, self.props)

        self.assertEqual(11, result["input_publications_count"])
        self.assertEqual(10, result["unique_properties_count"])
        duplicate = next(item for item in result["candidate_audit"] if item["id"] == "CASA-09")
        self.assertEqual("excluded", duplicate["decision"])
        self.assertIn("duplicate", duplicate["reasons"][0])
        self.assertTrue(any("price" in flag for flag in result["price_review_flags"]))

if __name__ == "__main__":
    unittest.main()
