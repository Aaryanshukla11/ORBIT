"""Unit tests for EnvironmentProviderRegistry and Environment Providers."""

import os
import tempfile
import pytest

from orbit.runtime.agent.contracts import AbstractAction, AbstractActionType
from orbit.runtime.environment.registry import (
    EnvironmentProviderRegistry,
    get_default_environment_registry,
)
from orbit.runtime.environment.spreadsheet_providers import CsvSpreadsheetProvider
from orbit.runtime.environment.browser_providers import SystemDefaultBrowserProvider


@pytest.mark.asyncio
async def test_csv_spreadsheet_write_and_read():
    provider = CsvSpreadsheetProvider()
    assert await provider.is_available() is True

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "test_output.csv")
        
        # Test WRITE
        write_action = AbstractAction(
            action_type=AbstractActionType.SPREADSHEET_WRITE,
            parameters={
                "path": csv_path,
                "headers": ["Model", "Price", "RAM"],
                "rows": [
                    ["Laptop A", "50000", "16GB"],
                    ["Laptop B", "55000", "8GB"],
                ],
            },
            expected_effect="Write rows to CSV",
        )
        assert await provider.check_permissions(write_action) is True
        write_result = await provider.execute(write_action)
        assert write_result.success is True
        assert os.path.exists(csv_path)

        # Test READ
        read_action = AbstractAction(
            action_type=AbstractActionType.SPREADSHEET_READ,
            parameters={"path": csv_path},
            expected_effect="Read CSV",
        )
        read_result = await provider.execute(read_action)
        assert read_result.success is True
        rows = read_result.output["rows"]
        assert len(rows) == 3  # Header + 2 data rows
        assert rows[0] == ["Model", "Price", "RAM"]
        assert rows[1] == ["Laptop A", "50000", "16GB"]


@pytest.mark.asyncio
async def test_system_default_browser_provider():
    provider = SystemDefaultBrowserProvider()
    assert await provider.is_available() is True

    valid_action = AbstractAction(
        action_type=AbstractActionType.BROWSER_NAVIGATE,
        parameters={"url": "https://www.google.com"},
        expected_effect="Navigate browser",
    )
    assert await provider.check_permissions(valid_action) is True

    invalid_action = AbstractAction(
        action_type=AbstractActionType.BROWSER_NAVIGATE,
        parameters={"url": "invalid_url_without_scheme"},
        expected_effect="Navigate browser",
    )
    assert await provider.check_permissions(invalid_action) is False


@pytest.mark.asyncio
async def test_registry_fallback_and_resolution():
    registry = get_default_environment_registry()

    # SPREADSHEET_WRITE should resolve to an available provider (Excel or CSV fallback)
    provider = await registry.resolve_provider(AbstractActionType.SPREADSHEET_WRITE)
    assert provider is not None
    assert provider.provider_id in ("excel_com_provider", "csv_fallback_provider")

    # BROWSER_NAVIGATE should resolve to an available provider
    b_provider = await registry.resolve_provider(AbstractActionType.BROWSER_NAVIGATE)
    assert b_provider is not None

    # Availability map
    avail_map = await registry.get_availability_map()
    assert "SPREADSHEET_WRITE" in avail_map
    assert "BROWSER_NAVIGATE" in avail_map
