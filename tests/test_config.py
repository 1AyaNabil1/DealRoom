from src.config import DEFAULT_MODEL, get_settings


def test_defaults_without_any_configuration():
    settings = get_settings({})
    assert settings.google_api_key is None
    assert settings.llm_configured is False
    assert settings.model == DEFAULT_MODEL
    assert settings.chunks_per_analysis == 20
    assert settings.llm_max_attempts == 2
    assert settings.session_file == "session_store.json"
    assert settings.cors_origins == ("*",)


def test_blank_api_key_counts_as_not_configured():
    # `uvicorn --env-file .env` turns "GOOGLE_API_KEY=" into an empty string.
    assert get_settings({"GOOGLE_API_KEY": "   "}).llm_configured is False


def test_values_are_read_from_the_environment():
    settings = get_settings({
        "GOOGLE_API_KEY": "k",
        "DEALROOM_MODEL": "gemini-x",
        "DEALROOM_LLM_TIMEOUT_S": "2.5",
        "DEALROOM_LLM_MAX_ATTEMPTS": "3",
        "DEALROOM_CHUNKS_PER_ANALYSIS": "4",
        "DEALROOM_SESSION_FILE": "/tmp/s.json",
        "DEALROOM_CORS_ORIGINS": "https://a.example, https://b.example",
    })
    assert settings.llm_configured is True
    assert settings.model == "gemini-x"
    assert settings.llm_timeout_s == 2.5
    assert settings.llm_max_attempts == 3
    assert settings.chunks_per_analysis == 4
    assert settings.session_file == "/tmp/s.json"
    assert settings.cors_origins == ("https://a.example", "https://b.example")


def test_invalid_numbers_fall_back_to_defaults():
    settings = get_settings({
        "DEALROOM_LLM_TIMEOUT_S": "fast",
        "DEALROOM_LLM_MAX_ATTEMPTS": "0",
        "DEALROOM_CHUNKS_PER_ANALYSIS": "-5",
    })
    assert settings.llm_timeout_s == 15.0
    assert settings.llm_max_attempts == 2
    assert settings.chunks_per_analysis == 20
