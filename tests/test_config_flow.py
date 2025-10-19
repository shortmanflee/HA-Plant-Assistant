"""Tests for the initial config flow."""

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.plant_assistant.config_flow import ConfigFlow
from custom_components.plant_assistant.const import (
    CONF_LINKED_DEVICE_ID,
    CONF_NAME,
    DOMAIN,
    STEP_DEVICE_SELECTION,
    STEP_MANUAL_NAME,
    STORAGE_VERSION,
)


@pytest.mark.asyncio
async def test_initial_config_flow_with_device():
    """Test the complete initial config flow with device linking."""
    # Create a config flow instance
    flow = ConfigFlow()
    flow.hass = Mock()

    # Mock async_set_unique_id and _abort_if_unique_id_configured
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()

    # Step 1: User starts flow - should show device selection
    result = await flow.async_step_user()
    assert result.get("type") == "form"
    assert result.get("step_id") == STEP_DEVICE_SELECTION

    # Step 2: User selects a device
    device_input = {CONF_LINKED_DEVICE_ID: "test_device_id"}

    # Mock device registry for device validation
    device_registry_mock = Mock()
    device_mock = Mock()
    device_mock.id = "test_device_id"
    device_mock.name = "Garden Sprinkler System"  # This will become the instance name
    device_mock.name_by_user = None
    device_registry_mock.async_get.return_value = device_mock
    dr.async_get = Mock(return_value=device_registry_mock)

    # Mock config_entries to return empty list for _get_all_used_devices
    flow.hass.config_entries = Mock()
    flow.hass.config_entries.async_entries = Mock(return_value=[])

    result = await flow.async_step_device_selection(device_input)
    assert result.get("type") == "create_entry"
    assert (
        result.get("title") == "Garden Sprinkler System"
    )  # Should use device name as title
    assert result.get("data") == {"linked_device_id": "test_device_id"}

    # Check the initial options structure
    options = result.get("options")
    assert options
    assert options["version"] == STORAGE_VERSION
    assert "irrigation_zones" in options
    assert "zone-1" in options["irrigation_zones"]

    zone = options["irrigation_zones"]["zone-1"]
    assert zone["id"] == "zone-1"
    assert zone["name"] == "Garden Sprinkler System"  # Should use device name
    assert zone["linked_device_id"] == "test_device_id"
    assert zone["locations"] == {}


@pytest.mark.asyncio
async def test_initial_config_flow_without_device():
    """Test the config flow without linking a device (manual name entry)."""
    flow = ConfigFlow()
    flow.hass = Mock()

    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()

    # Step 1: User starts flow - should show device selection
    result = await flow.async_step_user()
    assert result.get("type") == "form"
    assert result.get("step_id") == STEP_DEVICE_SELECTION

    # Step 2: User doesn't select device - should go to manual name entry
    device_input = {}
    result = await flow.async_step_device_selection(device_input)
    assert result.get("type") == "form"
    assert result.get("step_id") == STEP_MANUAL_NAME

    # Step 3: User provides manual name
    name_input = {CONF_NAME: "Test Instance"}
    result = await flow.async_step_manual_name(name_input)
    assert result.get("type") == "create_entry"
    assert result.get("title") == "Test Instance"

    # Check the initial zone configuration uses the manual name
    options = result.get("options")
    assert options is not None
    zone = options["irrigation_zones"]["zone-1"]
    assert zone["name"] == "Test Instance"
    assert zone["linked_device_id"] is None


@pytest.mark.asyncio
async def test_initial_config_flow_validation_errors():
    """Test validation errors in the config flow."""
    flow = ConfigFlow()
    flow.hass = Mock()

    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()

    # Test empty manual name
    name_input = {CONF_NAME: ""}
    result = await flow.async_step_manual_name(name_input)
    assert result.get("type") == "form"
    errors = result.get("errors")
    assert errors is not None
    assert errors.get(CONF_NAME) == "name_required"

    # Test invalid device
    device_input = {CONF_LINKED_DEVICE_ID: "invalid_device_id"}

    device_registry_mock = Mock()
    device_registry_mock.async_get.return_value = None  # Device not found
    dr.async_get = Mock(return_value=device_registry_mock)

    result = await flow.async_step_device_selection(device_input)
    assert result.get("type") == "form"
    errors = result.get("errors")
    assert errors is not None
    assert errors.get(CONF_LINKED_DEVICE_ID) == "device_not_found"


@pytest.mark.asyncio
async def test_device_name_precedence():
    """Test that user-defined device name takes precedence over default name."""
    flow = ConfigFlow()
    flow.hass = Mock()

    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()

    device_input = {CONF_LINKED_DEVICE_ID: "test_device_id"}

    # Mock device with both name and name_by_user
    device_registry_mock = Mock()
    device_mock = Mock()
    device_mock.id = "test_device_id"
    device_mock.name = "Default Device Name"
    device_mock.name_by_user = "My Custom Device Name"  # This should be preferred
    device_registry_mock.async_get.return_value = device_mock
    dr.async_get = Mock(return_value=device_registry_mock)

    # Mock config_entries to return empty list for _get_all_used_devices
    flow.hass.config_entries = Mock()
    flow.hass.config_entries.async_entries = Mock(return_value=[])

    result = await flow.async_step_device_selection(device_input)

    # Should prefer name_by_user over name and use it as title and zone name
    assert result.get("title") == "My Custom Device Name"
    options = result.get("options")
    assert options
    zone = options["irrigation_zones"]["zone-1"]
    assert zone["name"] == "My Custom Device Name"


@pytest.mark.asyncio
async def test_unique_id_generation():
    """Test unique ID generation from instance name."""
    flow = ConfigFlow()
    flow.hass = Mock()

    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()

    # Test through manual name flow
    name_input = {CONF_NAME: "My Plant-Assistant Zone"}
    await flow.async_step_manual_name(name_input)

    # Should create unique ID by sanitizing the name
    expected_unique_id = f"{DOMAIN}_my_plant_assistant_zone"
    flow.async_set_unique_id.assert_called_once_with(expected_unique_id)
