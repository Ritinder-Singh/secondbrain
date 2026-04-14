"""
Connector registry.
Registers all configured connectors and runs them via sync_all().
"""
from config.settings import settings


def _get_connectors() -> list:
    """Return all connectors that are configured in .env."""
    connectors = []

    # Obsidian sync — always available if vault path exists
    from connectors.selfhosted.obsidian_sync import ObsidianSyncConnector
    connectors.append(ObsidianSyncConnector())

    return connectors


def get_connector(name: str):
    """Get a specific connector by class name."""
    for c in _get_connectors():
        if c.__class__.__name__.lower() == name.lower():
            return c
    raise ValueError(f"Connector '{name}' not found or not configured")


def sync_all(dry_run: bool = False) -> list[dict]:
    """Run all configured connectors and return summary results."""
    results = []
    for connector in _get_connectors():
        print(f"\n── {connector.__class__.__name__} ──────────────────────")
        result = connector.sync(dry_run=dry_run)
        results.append(result)
    return results
