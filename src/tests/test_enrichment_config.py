from types import SimpleNamespace

from dynaconf import Dynaconf

from toolmeta_harvester import config


def test_generation_and_validation_models_use_configured_values(monkeypatch):
    values = {
        "egi.llm_api_key": "test-key",
        "egi.llm_api_url": "https://llm.test/v1/chat/completions",
        "egi.generation_model": "generation-model",
        "egi.validation_model": "validation-model",
    }
    monkeypatch.setattr(
        config,
        "settings",
        SimpleNamespace(get=lambda key, default=None: values.get(key, default)),
    )
    assert config.egi_llm_api_key() == "test-key"
    assert config.egi_llm_api_url() == "https://llm.test/v1/chat/completions"
    assert config.egi_llm_stage_model("generation") == "generation-model"
    assert config.egi_llm_stage_model("validation") == "validation-model"


def test_extraction_is_not_a_supported_production_stage():
    try:
        config.egi_llm_stage_model("extraction")
    except ValueError as error:
        assert "Unsupported LLM stage" in str(error)
    else:
        raise AssertionError("extraction stage must not be configurable")


def test_dynaconf_toml_default_is_overridden_by_environment(
    tmp_path, monkeypatch
):
    settings_file = tmp_path / "config.toml"
    settings_file.write_text('[egi]\ngeneration_model = "toml-model"\n')
    monkeypatch.setenv(
        "TOOLMETA_HARVESTER_EGI__GENERATION_MODEL", "environment-model"
    )
    monkeypatch.setattr(
        config,
        "settings",
        Dynaconf(
            envvar_prefix="TOOLMETA_HARVESTER",
            settings_files=[str(settings_file)],
            environments=False,
            load_dotenv=False,
        ),
    )

    assert config.egi_llm_stage_model("generation") == "environment-model"


def test_dynaconf_uses_toml_default_without_environment_override(
    tmp_path, monkeypatch
):
    settings_file = tmp_path / "config.toml"
    settings_file.write_text('[egi]\nllm_timeout = 24\n')
    monkeypatch.delenv("TOOLMETA_HARVESTER_EGI__LLM_TIMEOUT", raising=False)
    monkeypatch.setattr(
        config,
        "settings",
        Dynaconf(
            envvar_prefix="TOOLMETA_HARVESTER",
            settings_files=[str(settings_file)],
            environments=False,
            load_dotenv=False,
        ),
    )

    assert config.llm_timeout() == 24


def test_missing_required_secret_fails_clearly(monkeypatch):
    monkeypatch.setattr(
        config,
        "settings",
        SimpleNamespace(get=lambda key, default=None: None),
    )

    try:
        config.egi_llm_api_key()
    except ValueError as error:
        assert "egi.llm_api_key" in str(error)
    else:
        raise AssertionError("missing EGI API key must fail")


def test_invalid_timeout_fails_during_configuration_access(monkeypatch):
    monkeypatch.setattr(
        config,
        "settings",
        SimpleNamespace(get=lambda key, default=None: "not-an-integer"),
    )

    try:
        config.llm_timeout()
    except ValueError:
        pass
    else:
        raise AssertionError("invalid timeout must fail")
