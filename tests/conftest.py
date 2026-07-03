import sys
from pathlib import Path

import pytest

# Add custom_components to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load pytest-homeassistant-custom-component fixtures (hass, enable_custom_integrations, …)
pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests that need it."""
    yield
