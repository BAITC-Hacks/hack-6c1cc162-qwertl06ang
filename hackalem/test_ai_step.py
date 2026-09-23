"""Тесты интеграции БЕЗ скачивания модели. Не являются оценкой качества нейросети.
Для реального инференса отдельно запустите prepare_ai.py после установки модели.
"""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import recommender as r
import semantic as s
from app import app

BASE = {
    "city": "Алматы", "event_date": "2026-11-13", "event_type": "свадьба",
    "category": "Фотограф", "budget": 500000, "duration": 4, "language": "русский",
}


class AiIntegrationTests(unittest.TestCase):
    def test_blank_preferences_keep_old_ranking(self):
        with patch.object(r.engine, "score") as score:
            result = r.recommend_contractors({**BASE, "preferences": "   "})
            score.assert_not_called()
        self.assertEqual(result["ranking_mode"], "rules")
        self.assertEqual([p["id"] for p in result["results"]], ["HK-68220", "HK-53108", "HK-91112"])

    def test_missing_model_is_explicit_fallback(self):
        with patch.object(r.engine, "score", side_effect=s.SemanticUnavailable("Модель не установлена")):
            result = r.recommend_contractors({**BASE, "preferences": "Живые эмоции"})
        self.assertEqual(result["ranking_mode"], "rules_fallback")
        self.assertIn("НЕ учтены", result["ranking_note"])
        self.assertEqual(result["count"], 3)
        self.assertTrue(all(p["semantic_similarity"] is None for p in result["results"]))

    def test_filters_before_model_and_quotes_preserved(self):
        by_id = {p["id"]: p for p in r.load_contractors()}
        def scores(profiles, wishes):
            for p in profiles:
                self.assertNotIn(BASE["event_date"], p["busy_dates"])
                self.assertLessEqual(p["price_from_kzt"], BASE["budget"])
                self.assertIn("свадьба", p["event_formats"])
            return {
                p["id"]: {"score": 0.9 if p["id"] == "HK-91112" else 0.2,
                          "evidence": s.split_description(p["description"])[0]}
                for p in profiles
            }
        with patch.object(r.engine, "score", side_effect=scores):
            result = r.recommend_contractors({**BASE, "preferences": "Живые эмоции"})
            again = r.recommend_contractors({**BASE, "preferences": "Живые эмоции"})
        self.assertEqual(result, again)
        self.assertEqual(result["ranking_mode"], "semantic")
        self.assertEqual(result["results"][0]["id"], "HK-91112")
        for card in result["results"]:
            self.assertIn(card["evidence"], by_id[card["id"]]["description"])
            self.assertIn(card["evidence"], card["reason"])

    def test_equal_similarity_uses_price_then_id(self):
        with patch.object(r.engine, "score", side_effect=lambda profiles, wishes: {
            p["id"]: {"score": 0.5, "evidence": ""} for p in profiles
        }):
            result = r.recommend_contractors({**BASE, "preferences": "Тест"})
        self.assertEqual([p["id"] for p in result["results"]], ["HK-68220", "HK-53108", "HK-91112"])

    def test_no_candidates_skips_ai(self):
        with patch.object(r.engine, "score") as score:
            result = r.recommend_contractors({**BASE, "budget": 0, "preferences": "Тест"})
            score.assert_not_called()
        self.assertEqual(result["status"], "no_match")
        self.assertEqual(result["ranking_mode"], "not_applied")

    def test_missing_model_does_not_import_or_download_it(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(s, "MODEL_DIR", Path(folder)):
                engine = s.SemanticEngine()
                self.assertFalse(engine.initialize(r.load_contractors()))
                self.assertFalse(engine.status()["ready"])
                with self.assertRaises(s.SemanticUnavailable):
                    engine.score([], "Тест")

    def test_sentence_fragments_are_original_substrings(self):
        for p in r.load_contractors():
            for fragment in s.split_description(p["description"]):
                self.assertIn(fragment, p["description"])

    def test_long_text_is_chunked_without_losing_tail(self):
        # Stub only checks boundaries; it is not the real multilingual tokenizer.
        def fake_tokenizer(text, **kwargs):
            return {"offset_mapping": [m.span() for m in re.finditer(r"\S+", text)]}
        original = " ".join(f"слово{i}" for i in range(301))
        pieces = s.token_chunks(original, fake_tokenizer, limit=120)
        self.assertEqual(len(pieces), 3)
        self.assertEqual(" ".join(pieces), original)

    def test_api_accepts_preferences_and_rejects_too_long_text(self):
        with TestClient(app) as client:
            with patch.object(r.engine, "score", side_effect=s.SemanticUnavailable("Нет модели")):
                response = client.post("/recommend", json={**BASE, "preferences": "Живые эмоции"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["ranking_mode"], "rules_fallback")
            self.assertEqual(client.post("/recommend", json={**BASE, "preferences": "я" * 501}).status_code, 422)
            self.assertEqual(client.post("/recommend", json={**BASE, "event_date": "2027-01-01"}).status_code, 422)

    def test_ui_and_ai_status_route(self):
        with TestClient(app) as client:
            self.assertIn('id="preferences"', client.get("/").text)
            self.assertIsInstance(client.get("/ai/status").json()["ready"], bool)
            self.assertEqual(client.get("/options").json()["count"], 66)
            self.assertEqual(client.get("/static/script.js").status_code, 200)
            self.assertEqual(client.get("/.env").status_code, 404)
            self.assertEqual(client.get("/static/../data/hackathon%20dataset%20anonymized.csv").status_code, 404)


if __name__ == "__main__":
    unittest.main()
