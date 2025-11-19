"""Tests for the Master Schedule switch entity."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.plant_assistant.const import DOMAIN
from custom_components.plant_assistant.switch import (
    MasterScheduleSwitch,
    async_setup_entry,
)


@pytest.mark.asyncio
async def test_master_schedule_switch_creation():
    """Test that Master Schedule switch is created for zones with esphome devices."""
    hass = Mock()
    entry = Mock()
    entry.entry_id = "test_entry_id"
    async_add_entities = AsyncMock()

    # Mock hass data structure with irrigation zone having esphome device
    hass.data = {
        DOMAIN: {
            "entries": {
                "test_entry_id": {
                    "irrigation_zones": {
                        "zone-1": {
                            "id": "zone-1",
                            "name": "Front Lawn",
                            "linked_device_id": "esphome_device_1",
                            "locations": {},
                        }
                    }
                }
            }
        }
    }

    # Mock device registry
    device_registry_mock = Mock()
    zone_device_mock = Mock()
    zone_device_mock.id = "esphome_device_1"
    zone_device_mock.identifiers = {("esphome", "device_abc123")}
    device_registry_mock.async_get.return_value = zone_device_mock

    with patch(
        "custom_components.plant_assistant.switch.dr.async_get"
    ) as mock_async_get:
        mock_async_get.return_value = device_registry_mock

        await async_setup_entry(hass, entry, async_add_entities)

    # Verify that async_add_entities was called
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]

    # Verify that ten switches were created (one of each type)
    assert len(entities) == 10
    assert isinstance(entities[0], MasterScheduleSwitch)
    assert entities[0].zone_name == "Front Lawn"


@pytest.mark.asyncio
async def test_master_schedule_switch_not_created_without_esphome():
    """Test that Master Schedule switch is NOT created for zones.

    without esphome devices.
    """
    hass = Mock()
    entry = Mock()
    entry.entry_id = "test_entry_id"
    async_add_entities = AsyncMock()

    # Mock hass data structure with irrigation zone WITHOUT esphome device
    hass.data = {
        DOMAIN: {
            "entries": {
                "test_entry_id": {
                    "irrigation_zones": {
                        "zone-1": {
                            "id": "zone-1",
                            "name": "Front Lawn",
                            "linked_device_id": None,  # No esphome device
                            "locations": {},
                        }
                    }
                }
            }
        }
    }

    device_registry_mock = Mock()
    with patch(
        "custom_components.plant_assistant.switch.dr.async_get"
    ) as mock_async_get:
        mock_async_get.return_value = device_registry_mock

        await async_setup_entry(hass, entry, async_add_entities)

    # Verify that async_add_entities was NOT called
    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_master_schedule_switch_initialization():
    """Test that Master Schedule switch initializes correctly."""
    hass = Mock()

    zone_device_id = ("esphome", "device_abc123")
    zone_name = "Front Lawn"
    zone_device = Mock()

    switch = MasterScheduleSwitch(
        hass=hass,
        entry_id="test_entry_id",
        zone_device_id=zone_device_id,
        zone_name=zone_name,
        _zone_device=zone_device,
    )

    # Verify attributes
    assert switch.zone_name == "Front Lawn"
    assert switch._attr_name == "Front Lawn Schedule"
    assert switch.is_on is False
    assert (
        switch._attr_unique_id
        == f"{DOMAIN}_test_entry_id_esphome_device_abc123_master_schedule"
    )

    # Verify device info
    device_info = switch._attr_device_info
    assert device_info is not None
    # DeviceInfo is a TypedDict, verify it contains identifiers
    assert "identifiers" in device_info
    assert device_info["identifiers"] == {zone_device_id}


@pytest.mark.asyncio
async def test_master_schedule_switch_turn_on_off():
    """Test turning Master Schedule switch on and off."""
    hass = Mock()

    zone_device_id = ("esphome", "device_abc123")
    zone_device = Mock()

    switch = MasterScheduleSwitch(
        hass=hass,
        entry_id="test_entry_id",
        zone_device_id=zone_device_id,
        zone_name="Front Lawn",
        _zone_device=zone_device,
    )

    # Test turning on
    switch.async_write_ha_state = Mock()
    assert switch.is_on is False

    await switch.async_turn_on()
    assert switch.is_on is True
    switch.async_write_ha_state.assert_called()

    # Test turning off
    switch.async_write_ha_state.reset_mock()
    await switch.async_turn_off()
    assert switch.is_on is False
    switch.async_write_ha_state.assert_called()


@pytest.mark.asyncio
async def test_master_schedule_switch_state_restoration_on():
    """Test that Master Schedule switch restores ON state on HA restart."""
    hass = Mock()

    zone_device_id = ("esphome", "device_abc123")
    zone_device = Mock()

    switch = MasterScheduleSwitch(
        hass=hass,
        entry_id="test_entry_id",
        zone_device_id=zone_device_id,
        zone_name="Front Lawn",
        _zone_device=zone_device,
    )

    # Mock the async_get_last_state method
    last_state_mock = Mock()
    last_state_mock.state = STATE_ON
    switch.async_get_last_state = AsyncMock(return_value=last_state_mock)
    switch.async_write_ha_state = Mock()

    # Call async_added_to_hass to trigger restoration
    await switch.async_added_to_hass()

    # Verify state was restored
    assert switch.is_on is True
    assert switch._restored is True


@pytest.mark.asyncio
async def test_master_schedule_switch_state_restoration_off():
    """Test that Master Schedule switch restores OFF state on HA restart."""
    hass = Mock()

    zone_device_id = ("esphome", "device_abc123")
    zone_device = Mock()

    switch = MasterScheduleSwitch(
        hass=hass,
        entry_id="test_entry_id",
        zone_device_id=zone_device_id,
        zone_name="Front Lawn",
        _zone_device=zone_device,
    )

    # Mock the async_get_last_state method
    last_state_mock = Mock()
    last_state_mock.state = STATE_OFF
    switch.async_get_last_state = AsyncMock(return_value=last_state_mock)
    switch.async_write_ha_state = Mock()

    # Call async_added_to_hass to trigger restoration
    await switch.async_added_to_hass()

    # Verify state was restored
    assert switch.is_on is False
    assert switch._restored is True


@pytest.mark.asyncio
async def test_master_schedule_switch_state_restoration_unavailable():
    """Test that Master Schedule switch handles unavailable state on restoration."""
    hass = Mock()

    zone_device_id = ("esphome", "device_abc123")
    zone_device = Mock()

    switch = MasterScheduleSwitch(
        hass=hass,
        entry_id="test_entry_id",
        zone_device_id=zone_device_id,
        zone_name="Front Lawn",
        _zone_device=zone_device,
    )

    # Mock the async_get_last_state method with unavailable state
    last_state_mock = Mock()
    last_state_mock.state = "unavailable"
    switch.async_get_last_state = AsyncMock(return_value=last_state_mock)
    switch.async_write_ha_state = Mock()

    # Call async_added_to_hass to trigger restoration
    await switch.async_added_to_hass()

    # Verify state is set to default (False) when unavailable
    assert switch.is_on is False


@pytest.mark.asyncio
async def test_master_schedule_switch_multiple_zones():
    """Test that Master Schedule switches are created for multiple zones."""
    hass = Mock()
    entry = Mock()
    entry.entry_id = "test_entry_id"
    async_add_entities = AsyncMock()

    # Mock hass data structure with multiple irrigation zones
    hass.data = {
        DOMAIN: {
            "entries": {
                "test_entry_id": {
                    "irrigation_zones": {
                        "zone-1": {
                            "id": "zone-1",
                            "name": "Front Lawn",
                            "linked_device_id": "esphome_device_1",
                            "locations": {},
                        },
                        "zone-2": {
                            "id": "zone-2",
                            "name": "Back Patio",
                            "linked_device_id": "esphome_device_2",
                            "locations": {},
                        },
                        "zone-3": {
                            "id": "zone-3",
                            "name": "Side Garden",
                            "linked_device_id": None,  # This one has no device
                            "locations": {},
                        },
                    }
                }
            }
        }
    }

    # Mock device registry
    device_registry_mock = Mock()

    def mock_async_get_device(device_id):
        if device_id == "esphome_device_1":
            device = Mock()
            device.identifiers = {("esphome", "abc123")}
            return device
        if device_id == "esphome_device_2":
            device = Mock()
            device.identifiers = {("esphome", "def456")}
            return device
        return None

    device_registry_mock.async_get.side_effect = mock_async_get_device

    with patch(
        "custom_components.plant_assistant.switch.dr.async_get"
    ) as mock_async_get:
        mock_async_get.return_value = device_registry_mock

        await async_setup_entry(hass, entry, async_add_entities)

    # Verify that async_add_entities was called with 20 switches (10 per zone)
    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 20
    assert entities[0].zone_name == "Front Lawn"
    assert entities[1].zone_name == "Front Lawn"


@pytest.mark.asyncio
async def test_master_schedule_switch_missing_device():
    """Test handling when zone device cannot be found in registry."""
    hass = Mock()
    entry = Mock()
    entry.entry_id = "test_entry_id"
    async_add_entities = AsyncMock()

    # Mock hass data structure
    hass.data = {
        DOMAIN: {
            "entries": {
                "test_entry_id": {
                    "irrigation_zones": {
                        "zone-1": {
                            "id": "zone-1",
                            "name": "Front Lawn",
                            "linked_device_id": "esphome_device_1",
                            "locations": {},
                        }
                    }
                }
            }
        }
    }

    # Mock device registry that returns None (device not found)
    device_registry_mock = Mock()
    device_registry_mock.async_get.return_value = None

    with patch(
        "custom_components.plant_assistant.switch.dr.async_get"
    ) as mock_async_get:
        mock_async_get.return_value = device_registry_mock

        await async_setup_entry(hass, entry, async_add_entities)

    # Verify that async_add_entities was NOT called
    async_add_entities.assert_not_called()


@pytest.mark.asyncio
async def test_master_schedule_switch_implements_restore_entity():
    """Test that Master Schedule switch implements RestoreEntity."""
    hass = Mock()

    zone_device_id = ("esphome", "device_abc123")
    zone_device = Mock()

    switch = MasterScheduleSwitch(
        hass=hass,
        entry_id="test_entry_id",
        zone_device_id=zone_device_id,
        zone_name="Front Lawn",
        _zone_device=zone_device,
    )

    # Verify that the switch is a RestoreEntity
    assert isinstance(switch, RestoreEntity)
