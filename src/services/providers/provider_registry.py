"""Registry for managing model serving providers."""

from typing import Optional

from .base_provider import BaseProvider, ProviderConfig


class ProviderRegistry:
    """Singleton registry for managing provider classes and instances."""

    _instance: Optional["ProviderRegistry"] = None
    _providers: dict[str, type[BaseProvider]] = {}

    def __new__(cls) -> "ProviderRegistry":
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register_provider(self, name: str, provider_class: type[BaseProvider]) -> None:
        """Register a provider class.

        Args:
        ----
            name: Name to identify the provider
            provider_class: Provider class that extends BaseProvider

        """
        if not issubclass(provider_class, BaseProvider):
            raise TypeError(f"Provider class must extend BaseProvider, got {provider_class}")

        self._providers[name] = provider_class

    def get_provider(self, name: str, config: ProviderConfig) -> BaseProvider:
        """Get an instance of a registered provider.

        Args:
        ----
            name: Name of the provider
            config: Configuration for the provider

        Returns:
        -------
            Configured provider instance

        Raises:
        ------
            ValueError: If provider is not found

        """
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' not found")

        provider_class = self._providers[name]
        return provider_class(config)

    def get_available_providers(self) -> dict[str, type[BaseProvider]]:
        """Get all registered providers.

        Returns
        -------
            Dictionary mapping provider names to provider classes

        """
        return self._providers.copy()

    def provider_exists(self, name: str) -> bool:
        """Check if a provider is registered.

        Args:
        ----
            name: Name of the provider

        Returns:
        -------
            True if provider is registered, False otherwise

        """
        return name in self._providers

    def clear(self) -> None:
        """Clear all registered providers. Useful for testing."""
        self._providers.clear()
