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

    def comparable(self, property_id, price_mxn, **changes):
        property_ = {
            "id": property_id, "source": "test", "url": f"https://example.test/{property_id}",
            "price_mxn": price_mxn, "land_m2": 120, "construction_m2": 90,
            "bedrooms": 2, "bathrooms": 1, "parking_spaces": 1, "floors": 1,
            "quality_notes": [], "duplicate_group": None,
        }
        property_.update(changes)
        return property_

    def test_current_dataset_has_numeric_reference_range_and_selected_comparables(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        result = estimate(target, self.props)

        self.assertEqual("orientative", result["status"])
        self.assertEqual(1450000, result["reference_price_mxn"])
        self.assertEqual([531056, 1900000], result["range_mxn"])
        self.assertEqual("low", result["confidence"])
        self.assertIn("no calibrada", result["confidence_note"])
        self.assertEqual(["CASA-01", "CASA-02", "CASA-11", "CASA-10", "CASA-07", "CASA-03"],
                         [item["id"] for item in result["comparables"]])

    def test_zero_or_one_valid_comparable_has_no_numeric_reference(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        for properties, expected_count in (([], 0), ([self.comparable("ONE", 1000000)], 1)):
            with self.subTest(count=expected_count):
                result = estimate(target, properties)
                self.assertEqual("insufficient_comparables", result["status"])
                self.assertIsNone(result["reference_price_mxn"])
                self.assertEqual(expected_count, result["comparables_count"])
                self.assertTrue(result["evidence_reasons"])

    def test_two_to_four_valid_comparables_are_provisional(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        properties = [self.comparable("A", 1000000), self.comparable("B", 1200000)]
        result = estimate(target, properties)

        self.assertEqual("provisional", result["status"])
        self.assertEqual(2, result["comparables_count"])
        self.assertEqual(1000000, result["reference_price_mxn"])
        self.assertIn("limited", result["evidence_reasons"][0])

    def test_minimum_coverage_is_configurable_and_excludes_low_coverage_match(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        sparse = self.comparable("SPARSE", 1000000, construction_m2=None, bedrooms=None,
                                 bathrooms=None, parking_spaces=None, floors=None)
        result = estimate(target, [sparse], min_score=0, min_coverage=.8)

        self.assertEqual(0, result["comparables_count"])
        audit = next(item for item in result["candidate_audit"] if item["id"] == "SPARSE")
        self.assertIn("coverage_below_minimum", audit["reasons"])

    def test_duplicate_representative_is_deterministic_when_prices_differ(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        later = self.comparable("DUP-B", 2000000, duplicate_group="DUP-TEST")
        earlier = self.comparable("DUP-A", 1000000, duplicate_group="DUP-TEST")
        result = estimate(target, [later, earlier])

        self.assertEqual(["DUP-A"], [item["id"] for item in result["comparables"]])
        self.assertIsNone(result["reference_price_mxn"])
        excluded = next(item for item in result["candidate_audit"] if item["id"] == "DUP-B")
        self.assertIn("duplicate", excluded["reasons"][0])

    def test_price_review_flag_does_not_silently_exclude_selected_property(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        result = estimate(target, self.props)

        self.assertIn("CASA-10", [item["id"] for item in result["comparables"]])
        self.assertTrue(any(flag.startswith("CASA-10:") for flag in result["price_review_flags"]))

    def test_current_dataset_reports_exact_descriptive_price_metrics(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        result = estimate(target, self.props)
        metrics = result["price_metrics"]

        self.assertEqual(6, metrics["comparables_count"])
        self.assertEqual(1675000, metrics["median_price_mxn"])
        self.assertAlmostEqual(1818690.1666666667, metrics["mean_price_mxn"])
        self.assertAlmostEqual(1408513.4872184102, metrics["sample_standard_deviation_mxn"])
        self.assertAlmostEqual(.7744658837629078, metrics["sample_coefficient_of_variation"])
        self.assertEqual(760792, metrics["first_quartile_mxn"])
        self.assertEqual(2237500, metrics["third_quartile_mxn"])
        self.assertEqual(1476708, metrics["iqr_mxn"])
        self.assertEqual(431085, metrics["min_price_mxn"])
        self.assertEqual(4250000, metrics["max_price_mxn"])
        self.assertEqual(
            {"high_price_dispersion_heuristic", "price_review_flags_present",
             "selected_comparables_have_missing_fields"},
            {warning["code"] for warning in result["warnings"]},
        )

    def test_zero_and_one_comparable_metrics_mark_undefined_statistics_absent(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        empty = estimate(target, [])
        one = estimate(target, [self.comparable("ONE", 1000000)])

        self.assertEqual(0, empty["price_metrics"]["comparables_count"])
        self.assertIsNone(empty["price_metrics"]["median_price_mxn"])
        self.assertIsNone(empty["price_metrics"]["sample_standard_deviation_mxn"])
        self.assertEqual({"limited_comparable_sample"},
                         {warning["code"] for warning in empty["warnings"]})
        self.assertEqual(1000000, one["price_metrics"]["mean_price_mxn"])
        self.assertIsNone(one["price_metrics"]["sample_standard_deviation_mxn"])
        self.assertIsNone(one["price_metrics"]["sample_coefficient_of_variation"])
        self.assertIsNone(one["price_metrics"]["first_quartile_mxn"])

    def test_inclusive_quartiles_are_interpolated_for_small_samples(self):
        target = {"land_m2": 120, "construction_m2": 90, "bedrooms": 2,
                  "bathrooms": 1, "parking_spaces": 1, "floors": 1}
        result = estimate(target, [self.comparable("A", 1000000), self.comparable("B", 1200000)])
        metrics = result["price_metrics"]

        self.assertEqual(1050000, metrics["first_quartile_mxn"])
        self.assertEqual(1150000, metrics["third_quartile_mxn"])
        self.assertEqual(100000, metrics["iqr_mxn"])
        self.assertEqual("provisional", result["status"])
        self.assertIn("limited_comparable_sample", {warning["code"] for warning in result["warnings"]})

if __name__ == "__main__":
    unittest.main()
