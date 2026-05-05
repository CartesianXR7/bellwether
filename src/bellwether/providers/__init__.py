"""Provider adapters. One module per provider.

Each adapter satisfies the ProviderAdapter Protocol from bellwether.protocols
and converts provider-specific responses into the common ProviderResponse shape.
finish_reason is normalized to a small vocabulary across providers:
"stop", "length", "content_filter", "tool_use".
"""

from bellwether.providers.anthropic import AnthropicAdapter
from bellwether.providers.google import GoogleAdapter
from bellwether.providers.openai import OpenAIAdapter

__all__ = ["AnthropicAdapter", "GoogleAdapter", "OpenAIAdapter"]
