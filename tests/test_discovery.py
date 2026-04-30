import unittest
from unittest.mock import Mock, patch

from sage.discovery import ModelRef, _check_lm_studio, _check_openai_compat


class DiscoveryTests(unittest.TestCase):
    @patch("sage.discovery.httpx.get")
    def test_openai_compat_preserves_ids_and_formats_labels(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": [
                {"id": "qwen/qwen3.5-9b"},
                {"id": "/models/Qwen3.5-0.8B-Q8_0.gguf"},
            ]
        }
        mock_get.return_value = response

        running, models, error = _check_openai_compat("http://localhost:1234")

        self.assertTrue(running)
        self.assertEqual("", error)
        self.assertEqual(
            [
                ModelRef(id="qwen/qwen3.5-9b", label="qwen3.5-9b"),
                ModelRef(id="/models/Qwen3.5-0.8B-Q8_0.gguf", label="Qwen3.5-0.8B-Q8_0"),
            ],
            models,
        )

    @patch("sage.discovery.httpx.get")
    def test_lm_studio_hides_embedding_models(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": [
                {"id": "qwen3.5-0.8b", "type": "vlm", "state": "loaded"},
                {"id": "qwen/qwen3.5-9b", "type": "vlm", "state": "not-loaded"},
                {"id": "text-embedding-nomic-embed-text-v1.5", "type": "embeddings"},
            ]
        }
        mock_get.return_value = response

        running, models, error = _check_lm_studio("http://localhost:1234")

        self.assertTrue(running)
        self.assertEqual("", error)
        self.assertEqual(
            [
                ModelRef(id="qwen3.5-0.8b", label="qwen3.5-0.8b", loaded=True),
                ModelRef(id="qwen/qwen3.5-9b", label="qwen3.5-9b", loaded=False),
            ],
            models,
        )


if __name__ == "__main__":
    unittest.main()
