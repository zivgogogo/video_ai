import pytest

from app.ai.interface import AIProvider
from app.ai.factory import create_ai_provider


def test_interface_is_abstract():
    with pytest.raises(TypeError):
        AIProvider()


def test_factory_creates_claude():
    p = create_ai_provider("claude", "claude-sonnet-4-6")
    assert isinstance(p, AIProvider)
    assert "claude" in p.model_name()


def test_factory_creates_openai():
    p = create_ai_provider("openai", "gpt-4o")
    assert isinstance(p, AIProvider)
    assert p.model_name() == "gpt-4o"


def test_factory_creates_local():
    p = create_ai_provider("local", "qwen")
    assert isinstance(p, AIProvider)


def test_factory_raises_on_unknown():
    with pytest.raises(ValueError, match="Unknown"):
        create_ai_provider("unknown")
