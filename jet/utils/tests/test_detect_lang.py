import pytest
from jet.utils.language import detect_lang, DetectLangResult
from jet.utils.string_utils import remove_non_alpha_numeric


class TestDetectLang:
    def test_detect_english_text(self):
        # Given: A simple English text input
        input_text = "Hello, this is a test."
        expected: DetectLangResult = {"lang": "en", "score": 0.999}

        # When: Calling detect_lang with English text
        result = detect_lang(input_text)

        # Then: The result should match the expected language and approximate score
        assert result["lang"] == expected["lang"]
        assert pytest.approx(result["score"], rel=0.1) == expected["score"]

    def test_detect_spanish_text(self):
        # Given: A simple Spanish text input
        input_text = "Hola, esto es una prueba."
        expected: DetectLangResult = {"lang": "es", "score": 0.999}

        # When: Calling detect_lang with Spanish text
        result = detect_lang(input_text)

        # Then: The result should match the expected language and approximate score
        assert result["lang"] == expected["lang"]
        assert pytest.approx(result["score"], rel=0.1) == expected["score"]

    def test_non_alphanumeric_cleaning(self):
        # Given: Text with special characters
        input_text = "Hello!!! This@#$ is a ^&* test."
        expected: DetectLangResult = {"lang": "en", "score": 0.999}

        # When: Calling detect_lang with text containing special characters
        result = detect_lang(input_text)

        # Then: The result should match the expected language and approximate score
        assert result["lang"] == expected["lang"]
        assert pytest.approx(result["score"], rel=0.1) == expected["score"]

    def test_empty_text(self):
        # Given: An empty string
        input_text = ""
        expected: DetectLangResult = {"lang": "en", "score": 0.1245}

        # When: Calling detect_lang with empty text
        result = detect_lang(input_text)

        # Then: The result should indicate English language with the observed score
        assert result["lang"] == expected["lang"]
        assert pytest.approx(result["score"], rel=0.1) == expected["score"]

    def test_short_text(self):
        # Given: A very short text input
        input_text = "Hi"
        expected: DetectLangResult = {"lang": "en", "score": 0.1}

        # When: Calling detect_lang with short text
        result = detect_lang(input_text)

        # Then: The result should match the expected language with a reasonable score
        assert result["lang"] == expected["lang"]
        assert result["score"] >= 0.1  # Short text has lower confidence

    def teardown_method(self):
        # Clean up any resources if needed (none in this case)
        pass
