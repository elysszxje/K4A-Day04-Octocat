from providers.openai_provider import OpenAIProvider
from providers.openrouter_provider import OpenRouterProvider
from providers.anthropic_provider import AnthropicProvider
from providers.gemini_provider import GeminiProvider
from providers.demo_provider import DemoProvider
from providers.ninerouter_provider import NineRouterProvider


def make_provider(name: str):
    if name == "openai":
        return OpenAIProvider()
    if name == "openrouter":
        return OpenRouterProvider()
    if name == "anthropic":
        return AnthropicProvider()
    if name == "gemini":
        return GeminiProvider()
    if name == "demo":
        return DemoProvider()
    if name == "ninerouter":
        return NineRouterProvider()
    raise ValueError(f"Unknown provider: {name}")
