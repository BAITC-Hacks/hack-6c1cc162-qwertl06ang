"""Функциональные проверки именно CSV, приложенного к этому обновлению."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import recommender as r


BASE = {
    "city": "Алматы", "event_date": "2026-11-13", "event_type": "свадьба",
    "category": "Фотограф", "budget": 500000, "duration": 4, "language": "русский",
}


class CsvUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = r.load_contractors()
        cls.by_id = {item["id"]: item for item in cls.profiles}

    def query(self, **changes):
        return r.recommend_contractors({**BASE, **changes})

    def test_catalog_count_and_unique_ids(self):
        self.assertEqual(len(self.profiles), 66)
        self.assertEqual(len(self.by_id), 66)
        self.assertFalse(any(item["id"].startswith("demo_") for item in self.profiles))

    def test_flag_types_and_counts(self):
        for item in self.profiles:
            for key in ("synthetic", "city_imputed", "price_imputed"):
                self.assertIs(type(item[key]), bool)
        self.assertEqual(sum(item["synthetic"] for item in self.profiles), 13)
        self.assertEqual(sum(item["city_imputed"] for item in self.profiles), 8)
        self.assertEqual(sum(item["price_imputed"] for item in self.profiles), 18)
        self.assertIs(self.by_id["HK-39372"]["synthetic"], False)
        self.assertIs(self.by_id["HK-90001"]["synthetic"], True)

    def test_lists_and_multiple_categories(self):
        for item in self.profiles:
            for key in ("categories", "event_formats", "languages", "busy_dates"):
                self.assertIsInstance(item[key], list)
                self.assertTrue(all(isinstance(value, str) for value in item[key]))
        halls = [item for item in self.profiles if "Банкетный зал" in item["categories"]]
        self.assertEqual(len(halls), 8)
        self.assertTrue(any(len(item["categories"]) > 1 for item in halls))

    def test_numbers_and_null_hours(self):
        self.assertEqual(sum(item["max_hours"] is None for item in self.profiles), 9)
        for item in self.profiles:
            self.assertIs(type(item["price_from_kzt"]), int)
            self.assertTrue(item["max_hours"] is None or item["max_hours"] > 0)

    def test_base_selection(self):
        result = self.query()
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["total_matches"], 4)
        self.assertEqual(result["count"], 3)
        self.assertEqual([item["id"] for item in result["results"]],
                         ["HK-68220", "HK-53108", "HK-91112"])

    def test_date_changes_selection(self):
        result = self.query(event_date="2026-11-14")
        self.assertEqual(result["total_matches"], 3)
        self.assertEqual([item["id"] for item in result["results"]],
                         ["HK-68220", "HK-76268", "HK-91112"])
        self.assertIn("заняты на выбранную дату", result["message"])
        for item in result["results"]:
            self.assertNotIn("2026-11-14", self.by_id[item["id"]]["busy_dates"])

    def test_rare_category_and_null_hours(self):
        result = self.query(category="Флорист", duration=24)
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["count"], 2)
        self.assertEqual([item["id"] for item in result["results"]], ["HK-39372", "HK-90001"])
        self.assertTrue(all("не привязана" in item["reason"] for item in result["results"]))

    def test_budget_no_match(self):
        result = self.query(budget=100000)
        self.assertEqual(result["status"], "no_match")
        self.assertEqual(result["results"], [])
        self.assertIn("начальная цена выше бюджета", result["message"])

    def test_city_category_absent(self):
        result = self.query(city="Астана", category="Декоратор")
        self.assertEqual(result["status"], "no_category")
        self.assertEqual(result["results"], [])

    def test_optional_fields(self):
        result = self.query(duration=None, language=None)
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["total_matches"], 4)

    def test_deterministic(self):
        self.assertEqual(self.query(), self.query())

    def test_source_text_preserved(self):
        with r.DATA_FILE.open(encoding="utf-8-sig", newline="") as file:
            for original in csv.DictReader(file):
                converted = self.by_id[original["id"]]
                for key in ("id", "anon_name", "city", "description"):
                    self.assertEqual(converted[key], original[key])

    def test_missing_file_is_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(r, "DATA_FILE", Path(folder) / "absent.csv"):
                with self.assertRaises(FileNotFoundError):
                    r.load_contractors()

    def test_invalid_flag_is_error(self):
        with r.DATA_FILE.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            headers = reader.fieldnames
            row = next(reader)
        row["synthetic"] = "unknown"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            with path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=headers)
                writer.writeheader()
                writer.writerow(row)
            with patch.object(r, "DATA_FILE", path):
                with self.assertRaisesRegex(ValueError, "synthetic"):
                    r.load_contractors()


if __name__ == "__main__":
    unittest.main()
