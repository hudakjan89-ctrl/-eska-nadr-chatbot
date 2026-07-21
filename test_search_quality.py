import os
import tempfile
import unittest

os.environ["QDRANT_PATH"] = tempfile.mkdtemp(prefix="qdrant-test-")

from database import (  # noqa: E402
    normalize_volume_query,
    expand_search_query,
    detect_query_intent,
    detect_product_purpose,
    rerank_products,
    _lexical_score,
    _normalize_text,
)
from xml_parser import detect_placement, detect_construction_type  # noqa: E402


class TestVolumeNormalization(unittest.TestCase):
    def test_10m_to_10m3(self):
        self.assertIn("10m3", normalize_volume_query("retenční nádrž 10m"))

    def test_deset_kubiku(self):
        normalized = normalize_volume_query("retenční nádrž deset kubíků")
        self.assertTrue("10m3" in normalized or "10 m3" in normalized)

    def test_10m3_unchanged(self):
        self.assertIn("10m3", normalize_volume_query("10m3 podzemní nádrž"))


class TestQueryExpansion(unittest.TestCase):
    def test_retencni_maps_to_pozarni(self):
        expanded = expand_search_query("retenční nádrž 10m3")
        self.assertIn("požární", expanded.lower())

    def test_podzemni_expansion(self):
        expanded = expand_search_query("podzemní")
        self.assertIn("samonosná", expanded.lower())
        self.assertIn("dvouplášťová", expanded.lower())

    def test_hlasic_expansion(self):
        expanded = expand_search_query("hlásič naplnění")
        self.assertIn("hlásič", expanded.lower())

    def test_cerpadlo_expansion(self):
        expanded = expand_search_query("kalové čerpadlo s plovákem")
        self.assertIn("čerpadlo", expanded.lower())


class TestPlacementDetection(unittest.TestCase):
    def test_samonosna_is_podzemni(self):
        self.assertEqual(
            detect_placement("Samonosná kruhová nádrž na vodu - 10m3"),
            "podzemni",
        )

    def test_dvouplastova_is_podzemni(self):
        self.assertEqual(
            detect_placement("Dvouplášťová kruhová nádrž na vodu - 10m3"),
            "podzemni",
        )

    def test_nadzemni(self):
        self.assertEqual(
            detect_placement("Nadzemní nádrž 10m3"),
            "nadzemni",
        )


class TestConstructionType(unittest.TestCase):
    def test_dvouplastova(self):
        self.assertEqual(
            detect_construction_type("Dvouplášťová kruhová nádrž na vodu - 10m3"),
            "dvouplastova",
        )

    def test_obetonovani(self):
        self.assertEqual(
            detect_construction_type("Kruhová nádrž na vodu k obetonování - 10m3"),
            "obetonovani",
        )


class TestProductPurpose(unittest.TestCase):
    def test_destovka(self):
        prod = {
            "name": "Samonosná kruhová nádrž na vodu - 10m3",
            "category": "Nádrže na dešťovou vodu",
            "url": "https://www.ceskanadrz.cz/10m3-samonosna-kruhova-nadrz-na-vodu/",
        }
        self.assertEqual(detect_product_purpose(prod), "destovka")

    def test_pitna(self):
        prod = {
            "name": "Samonosná nádrž na pitnou vodu - 10m3",
            "category": "Nádrže na pitnou vodu",
            "url": "https://www.ceskanadrz.cz/10m3-samonosna/",
        }
        self.assertEqual(detect_product_purpose(prod), "pitna")


class TestReranking(unittest.TestCase):
    def _products(self):
        return [
            {
                "name": "Česká nádrž - Nadzemní nádrž 10m3",
                "url": "https://www.ceskanadrz.cz/nadzemni-10m3/",
                "category": "Nadzemní",
                "placement": "nadzemni",
                "construction_type": "nadzemni",
            },
            {
                "name": "Česká nádrž - Samonosná kruhová nádrž na vodu - 10m3",
                "url": "https://www.ceskanadrz.cz/10m3-samonosna-kruhova-nadrz-na-vodu/",
                "category": "Nádrže na dešťovou vodu",
                "placement": "podzemni",
                "construction_type": "samonosna",
            },
            {
                "name": "Česká nádrž - Kruhová nádrž na vodu k obetonování - 10m3",
                "url": "https://www.ceskanadrz.cz/10m3-kruhova-nadrz-na-vodu-k-obetonovani/",
                "category": "Nádrže na dešťovou vodu",
                "placement": "podzemni",
                "construction_type": "obetonovani",
            },
            {
                "name": "Česká nádrž - Dvouplášťová kruhová nádrž na vodu - 10m3",
                "url": "https://www.ceskanadrz.cz/10m3-dvouplastova-kruhova-nadrz-na-vodu/",
                "category": "Nádrže na dešťovou vodu",
                "placement": "podzemni",
                "construction_type": "dvouplastova",
            },
        ]

    def test_podzemni_prefers_underground(self):
        ranked = rerank_products(self._products(), "10m3 podzemní nádrž")
        top = ranked[0]
        self.assertEqual(top["placement"], "podzemni")
        self.assertNotIn("nadzem", top["name"].lower())

    def test_destovka_prefers_rainwater(self):
        ranked = rerank_products(self._products(), "nádrž na dešťovou vodu 10m3")
        self.assertIn("destov", _normalize_text(ranked[0]["category"]))

    def test_accessory_query(self):
        products = self._products() + [{
            "name": "Hlásič naplnění jímky, nádrže či septiku",
            "url": "https://www.ceskanadrz.cz/hlasic-naplneni-jimky--nadrze-ci-septiku-2/",
            "category": "Příslušenství",
            "placement": "neznamo",
            "construction_type": "neznamo",
        }]
        ranked = rerank_products(products, "hlásič naplnění jímky")
        self.assertIn("hlasic", ranked[0]["url"])

    def test_lexical_score_underground_penalizes_aboveground(self):
        intent = detect_query_intent("podzemní nádrž 10m3")
        underground = self._products()[1]
        aboveground = self._products()[0]
        self.assertGreater(
            _lexical_score(underground, "podzemní nádrž 10m3", intent),
            _lexical_score(aboveground, "podzemní nádrž 10m3", intent),
        )


if __name__ == "__main__":
    unittest.main()
