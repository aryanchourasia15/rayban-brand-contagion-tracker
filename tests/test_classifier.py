"""
Unit tests for Heuristic Relevance Classifier (src/data/classifier.py).
"""

import unittest

from src.config import VALID_RELEVANCE_FLAGS
from src.data.classifier import classify_relevance


class TestRelevanceClassifier(unittest.TestCase):
    def test_relevant_classification(self):
        """Articles intersecting Ray-Ban Meta/smart glasses with privacy controversies are classified as 'relevant'."""
        self.assertEqual(
            classify_relevance(
                title="Ray-Ban Meta smart glasses spark privacy controversy over covert recording",
                url="https://example.com/privacy-probe",
            ),
            "relevant",
        )
        self.assertEqual(
            classify_relevance(
                title="Harvard students demonstrate facial recognition stalking with Ray-Ban Meta glasses",
                url="https://example.com/doxxing",
            ),
            "relevant",
        )

    def test_contextual_classification(self):
        """Articles mentioning product without privacy controversy, or privacy without product, are 'contextual'."""
        # Product without privacy
        self.assertEqual(
            classify_relevance(
                title="Ray-Ban Meta smart glasses get new multimodality AI features and sales boost",
                url="https://example.com/tech-review",
            ),
            "contextual",
        )
        # Privacy without product
        self.assertEqual(
            classify_relevance(
                title="EU data protection authorities update biometric surveillance rules",
                url="https://example.com/gdpr-surveillance",
            ),
            "contextual",
        )

    def test_irrelevant_classification(self):
        """Tangential mentions or general non-topic news are classified as 'irrelevant'."""
        self.assertEqual(
            classify_relevance(
                title="Top 10 holiday gifts for tech enthusiasts in 2024",
                url="https://example.com/holiday-gift-guide",
            ),
            "irrelevant",
        )
        self.assertEqual(
            classify_relevance(
                title=None,
                url=None,
                text="",
            ),
            "irrelevant",
        )

    def test_vocabulary_adherence(self):
        """All classifications adhere to VALID_RELEVANCE_FLAGS vocabulary."""
        cases = [
            ("Ray-Ban Meta privacy leak", "https://news.com/1"),
            ("Smart glasses review 2024", "https://news.com/2"),
            ("Cooking recipes for winter", "https://food.com/3"),
        ]
        for title, url in cases:
            flag = classify_relevance(title=title, url=url)
            self.assertIn(flag, VALID_RELEVANCE_FLAGS)


if __name__ == "__main__":
    unittest.main()
