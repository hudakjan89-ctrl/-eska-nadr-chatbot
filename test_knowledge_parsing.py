import os
import tempfile
import unittest

os.environ["QDRANT_PATH"] = tempfile.mkdtemp(prefix="qdrant-knowledge-test-")

from database import _parse_knowledge_sections, upsert_knowledge_content  # noqa: E402


class TestKnowledgeParsing(unittest.TestCase):
    def test_triple_hash_sections(self):
        content = "### Sekce A\nText A.\n\n### Sekce B\nText B."
        items = _parse_knowledge_sections(content)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Sekce A")

    def test_double_hash_sections(self):
        content = "## Sekce A\nText A.\n\n## Sekce B\nText B."
        items = _parse_knowledge_sections(content)
        self.assertEqual(len(items), 2)

    def test_seed_file_has_sections(self):
        seed_path = os.path.join(os.path.dirname(__file__), "knowledge_seed.md")
        with open(seed_path, encoding="utf-8") as handle:
            content = handle.read()
        items = _parse_knowledge_sections(content)
        self.assertGreaterEqual(len(items), 10)

    def test_upsert_seed(self):
        from database import init_db
        init_db()
        seed_path = os.path.join(os.path.dirname(__file__), "knowledge_seed.md")
        with open(seed_path, encoding="utf-8") as handle:
            content = handle.read()
        count = upsert_knowledge_content(content)
        self.assertGreaterEqual(count, 10)


if __name__ == "__main__":
    unittest.main()
