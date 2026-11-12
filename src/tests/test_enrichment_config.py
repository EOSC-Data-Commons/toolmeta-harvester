from pathlib import Path

from dynaconf import Dynaconf

import toolmeta_harvester.config as config


def test_enrichment_configuration_reads_stage_overrides_and_defaults(monkeypatch):
    monkeypatch.setenv("TOOLMETA_HARVESTER_EGI__LLM_API_KEY", "test-key")
    monkeypatch.setenv(
        "TOOLMETA_HARVESTER_EGI__LLM_API_URL",
        "https://llm.example.test/v1/chat/completions",
    )
    monkeypatch.setenv("TOOLMETA_HARVESTER_EGI__LLM_MODEL", "shared-model")
    monkeypatch.setenv("TOOLMETA_HARVESTER_EGI__EXTRACTION_MODEL", "extraction-model")
    monkeypatch.setenv("TOOLMETA_HARVESTER_EGI__GENERATION_MODEL", "generation-model")
    monkeypatch.setenv(
        "TOOLMETA_HARVESTER_EGI__EMBEDDING_API",
        "https://llm.example.test/v1/embeddings",
    )
    monkeypatch.setenv(
        "TOOLMETA_HARVESTER_EGI__EMBEDDING_MODEL", "test-embedding-model"
    )
    project_root = Path(config.__file__).resolve().parents[2]
    monkeypatch.setattr(
        config,
        "settings",
        Dynaconf(
            envvar_prefix="TOOLMETA_HARVESTER",
            settings_files=[
                str(project_root / "config/config.toml"),
                str(project_root / "config/.secrets.toml"),
            ],
        ),
    )

    assert config.egi_llm_api_key() == "test-key"
    assert config.egi_llm_api_url() == "https://llm.example.test/v1/chat/completions"
    assert config.egi_llm_stage_model("extraction") == "extraction-model"
    assert config.egi_llm_model() == "shared-model"
    assert config.egi_llm_stage_model("generation") == "generation-model"
    assert config.embedding_api() == "https://llm.example.test/v1/embeddings"
    assert config.embedding_model() == "test-embedding-model"
