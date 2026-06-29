from __future__ import annotations

import os
import tempfile

from reins.features.workmode.url_resolver import infer_search_query_from_message
from reins.features.workmode.workers.browser.config import resolve_browser_launch_config
from reins.features.workmode.workers.browser.research import (
    analyze_source_text,
    build_research_search_url,
    rank_candidates,
)


def test_infer_search_query_from_message_strips_search_words():
    assert infer_search_query_from_message("research community parking policy") == "community parking policy"
    assert infer_search_query_from_message("look up for water leak repair rules") == "water leak repair rules"


def test_rank_candidates_prefers_relevant_sources_and_filters_search_hosts():
    candidates = [
        {
            "title": "Bing cache result",
            "url": "https://www.bing.com/search?q=community+parking+policy",
            "snippet": "search page",
        },
        {
            "title": "Community parking policy guidance",
            "url": (
                "https://www.bing.com/ck/a?"
                "u=a1aHR0cHM6Ly9jaXR5LmV4YW1wbGUuZ292L2NvbW11bml0eS9wYXJraW5nLXBvbGljeQ"
            ),
            "snippet": "Official guidance about community parking policy and enforcement.",
        },
        {
            "title": "Unrelated cooking notes",
            "url": "https://example.com/recipes",
            "snippet": "A page about dinner.",
        },
    ]

    ranked = rank_candidates("community parking policy", candidates, limit=3)

    assert ranked[0]["url"] == "https://city.example.gov/community/parking-policy"
    assert all("bing.com" not in item["url"] for item in ranked)


def test_analyze_source_text_extracts_relevant_facts():
    source = {
        "title": "Water leak repair policy",
        "url": "https://city.example.gov/water-leak-repair",
        "score": 60,
    }
    analysis = analyze_source_text(
        "water leak repair policy",
        source,
        "The water leak repair policy says residents should report pipe leaks within 24 hours. "
        "The property team must inspect the unit and document the repair result.",
    )

    assert analysis["relevant"] is True
    assert analysis["relevance_score"] >= 60
    assert analysis["key_facts"]


def test_build_research_search_url_defaults_to_bing():
    assert build_research_search_url("water leak policy").startswith("https://www.bing.com/search?q=")


def test_browser_launch_config_headless_uses_clean_bundled_browser_by_default():
    old_env = {key: os.environ.get(key) for key in os.environ if key.startswith("WORKMODE_BROWSER_")}
    try:
        for key in list(os.environ):
            if key.startswith("WORKMODE_BROWSER_"):
                os.environ.pop(key)

        config = resolve_browser_launch_config(visible=False)

        assert config.headless is True
        assert config.persistent is False
        assert config.profile_dir is None
    finally:
        for key in list(os.environ):
            if key.startswith("WORKMODE_BROWSER_"):
                os.environ.pop(key)
        for key, value in old_env.items():
            if value is not None:
                os.environ[key] = value


def test_browser_launch_config_uses_dedicated_persistent_profile_when_requested():
    old_env = {key: os.environ.get(key) for key in os.environ if key.startswith("WORKMODE_BROWSER_")}
    try:
        for key in list(os.environ):
            if key.startswith("WORKMODE_BROWSER_"):
                os.environ.pop(key)

        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["WORKMODE_BROWSER_USE_SYSTEM"] = "0"
            os.environ["WORKMODE_BROWSER_CHANNEL"] = "chrome"
            os.environ["WORKMODE_BROWSER_PERSISTENT"] = "1"
            os.environ["WORKMODE_BROWSER_PROFILE_DIR"] = temp_dir

            config = resolve_browser_launch_config(visible=True)

            assert config.headless is False
            assert config.persistent is True
            assert config.channel == "chrome"
            assert config.profile_dir == os.path.realpath(temp_dir)
    finally:
        for key in list(os.environ):
            if key.startswith("WORKMODE_BROWSER_"):
                os.environ.pop(key)
        for key, value in old_env.items():
            if value is not None:
                os.environ[key] = value
