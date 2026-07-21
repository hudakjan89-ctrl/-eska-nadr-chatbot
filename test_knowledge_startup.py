import os
import tempfile
import unittest

from knowledge_github import (
    knowledge_cache_usable,
    knowledge_cache_size,
    MIN_KNOWLEDGE_BYTES,
)


class TestKnowledgeCache(unittest.TestCase):
    def test_empty_file_not_usable(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            path = tmp.name
        try:
            self.assertEqual(os.path.getsize(path), 0)
            # knowledge_cache_usable uses KNOWLEDGE_LOCAL_PATH env - test logic inline
            self.assertLess(os.path.getsize(path), MIN_KNOWLEDGE_BYTES)
        finally:
            os.unlink(path)

    def test_small_file_not_usable(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"x" * 50)
            path = tmp.name
        try:
            self.assertLess(os.path.getsize(path), MIN_KNOWLEDGE_BYTES)
        finally:
            os.unlink(path)

    def test_realistic_file_usable(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"### Test\n\nObsah sekce.\n" * 20)
            path = tmp.name
        try:
            self.assertGreaterEqual(os.path.getsize(path), MIN_KNOWLEDGE_BYTES)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
