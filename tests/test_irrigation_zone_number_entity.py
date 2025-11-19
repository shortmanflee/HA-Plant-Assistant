"""Tests for irrigation zone number entities."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.plant_assistant.const import DOMAIN
from custom_components.plant_assistant.number import (
    FertiliserInjectionDaysNumber,
    async_setup_entry,
)

# List of all number classes to test
NUMBER_CLASSES = (
    (
        FertiliserInjectionDaysNumber,
        "fertiliser_injection_days",
        "Fertiliser Injection Days",
        1,
        30,
        1,
        "days",
        "mdi:calendar-plus",
    ),
)


class TestIrrigationZoneNumberBase:
    """Test the base IrrigationZoneNumber class."""

    @pytest.mark.asyncio
    async def test_number_implements_restore_entity(self):
        """Test that irrigation zone numbers implement RestoreEntity."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        number = FertiliserInjectionDaysNumber(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
            _zone_device=zone_device,
        )

        assert isinstance(number, RestoreEntity)

    @pytest.mark.asyncio
    async def test_number_native_value_property(self):
        """Test the native_value property."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        number = FertiliserInjectionDaysNumber(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
            _zone_device=zone_device,
        )

        assert number.native_value is None
        number._native_value = 15.0
        assert number.native_value == 15.0

    @pytest.mark.asyncio
    async def test_number_initial_value_set_on_first_added(self):
        """Test that initial value is set when added to HA for the first time."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        number = FertiliserInjectionDaysNumber(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
            _zone_device=zone_device,
        )

        # Mock async_get_last_state to return None (no previous state)
        number.async_get_last_state = AsyncMock(return_value=None)
        number.async_write_ha_state = Mock()

        # Call async_added_to_hass
        await number.async_added_to_hass()

        # Verify that initial value was set
        assert number.native_value == 5
        assert number._restored is True


class TestIrrigationZoneNumbers:
    """Tests for all irrigation zone numbers."""

    @pytest.mark.asyncio
    async def test_number_initialization(self):
        """Test that number initializes correctly."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_name = "Front Lawn"
        zone_device = Mock()

        number = FertiliserInjectionDaysNumber(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name=zone_name,
            _zone_device=zone_device,
        )

        # Verify attributes
        assert number.zone_name == "Front Lawn"
        assert number._attr_name == "Front Lawn Fertiliser Injection Days"
        assert number.native_value is None
        assert (
            number._attr_unique_id
            == f"{DOMAIN}_test_entry_id_esphome_device_abc123_fertiliser_injection_days"
        )

        # Verify number-specific attributes
        assert number._attr_native_min_value == 1
        assert number._attr_native_max_value == 30
        assert number._attr_native_step == 1
        assert number._attr_native_unit_of_measurement == "days"
        assert number._attr_icon == "mdi:calendar-plus"

        # Verify device info
        device_info = number._attr_device_info
        assert device_info is not None
        assert "identifiers" in device_info
        assert device_info["identifiers"] == {zone_device_id}

    @pytest.mark.asyncio
    async def test_number_set_native_value(self):
        """Test setting native value."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        number = FertiliserInjectionDaysNumber(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
            _zone_device=zone_device,
        )

        # Test setting value
        number.async_write_ha_state = Mock()
        assert number.native_value is None

        await number.async_set_native_value(15.0)
        assert number.native_value == 15.0
        number.async_write_ha_state.assert_called()

        # Test setting different value
        number.async_write_ha_state.reset_mock()
        await number.async_set_native_value(25.0)
        assert number.native_value == 25.0
        number.async_write_ha_state.assert_called()

    @pytest.mark.asyncio
    async def test_number_state_restoration(self):
        """Test that number restores state on HA restart."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        number = FertiliserInjectionDaysNumber(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
            _zone_device=zone_device,
        )

        # Mock the async_get_last_state method
        last_state_mock = Mock()
        last_state_mock.state = "18.5"
        number.async_get_last_state = AsyncMock(return_value=last_state_mock)
        number.async_write_ha_state = Mock()

        # Call async_added_to_hass to trigger restoration
        await number.async_added_to_hass()

        # Verify state was restored
        assert number.native_value == 18.5
        assert number._restored is True

    @pytest.mark.asyncio
    async def test_number_state_restoration_integer(self):
        """Test that number restores integer state on HA restart."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        number = FertiliserInjectionDaysNumber(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
            _zone_device=zone_device,
        )

        # Mock the async_get_last_state method with integer state
        last_state_mock = Mock()
        last_state_mock.state = "20"
        number.async_get_last_state = AsyncMock(return_value=last_state_mock)
        number.async_write_ha_state = Mock()

        # Call async_added_to_hass to trigger restoration
        await number.async_added_to_hass()

        # Verify state was restored
        assert number.native_value == 20.0
        assert number._restored is True

    @pytest.mark.asyncio
    async def test_number_state_restoration_unavailable(self):
        """Test that number handles unavailable state on restoration."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        number = FertiliserInjectionDaysNumber(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
            _zone_device=zone_device,
        )

        # Mock the async_get_last_state method with unavailable state
        last_state_mock = Mock()
        last_state_mock.state = "unavailable"
        number.async_get_last_state = AsyncMock(return_value=last_state_mock)
        number.async_write_ha_state = Mock()

        # Call async_added_to_hass to trigger restoration
        await number.async_added_to_hass()

        # Verify state is set to initial value when unavailable
        assert number.native_value == 5

    @pytest.mark.asyncio
    async def test_number_state_restoration_unknown(self):
        """Test that number handles unknown state on restoration."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        number = FertiliserInjectionDaysNumber(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
            _zone_device=zone_device,
        )

        # Mock the async_get_last_state method with unknown state
        last_state_mock = Mock()
        last_state_mock.state = "unknown"
        number.async_get_last_state = AsyncMock(return_value=last_state_mock)
        number.async_write_ha_state = Mock()

        # Call async_added_to_hass to trigger restoration
        await number.async_added_to_hass()

        # Verify state is set to initial value when unknown
        assert number.native_value == 5

    @pytest.mark.asyncio
    async def test_number_state_restoration_invalid(self):
        """Test that number handles invalid state on restoration."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        number = FertiliserInjectionDaysNumber(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
            _zone_device=zone_device,
        )

        # Mock the async_get_last_state method with invalid state
        last_state_mock = Mock()
        last_state_mock.state = "not_a_number"
        number.async_get_last_state = AsyncMock(return_value=last_state_mock)
        number.async_write_ha_state = Mock()

        # Call async_added_to_hass to trigger restoration
        await number.async_added_to_hass()

        # Verify state is set to initial value when invalid
        assert number.native_value == 5


class TestAsyncSetupEntry:
    """Test the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_all_numbers_created_for_single_zone(self):
        """Test that all number entities are created for a single zone."""
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
            "custom_components.plant_assistant.number.dr.async_get"
        ) as mock_async_get:
            mock_async_get.return_value = device_registry_mock

            await async_setup_entry(hass, entry, async_add_entities)

        # Verify that async_add_entities was called
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]

        # Verify that 1 number entity was created
        assert len(entities) == 1

        # Verify the number entity type
        assert entities[0]._number_type == "fertiliser_injection_days"
        assert entities[0].zone_name == "Front Lawn"

    @pytest.mark.asyncio
    async def test_numbers_created_for_multiple_zones(self):
        """Test that numbers are created for multiple zones."""
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
            "custom_components.plant_assistant.number.dr.async_get"
        ) as mock_async_get:
            mock_async_get.return_value = device_registry_mock

            await async_setup_entry(hass, entry, async_add_entities)

        # Verify that async_add_entities was called with 2 number entities (1 per zone)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 2

        # Verify zones
        zone_1_entities = [e for e in entities if e.zone_name == "Front Lawn"]
        zone_2_entities = [e for e in entities if e.zone_name == "Back Patio"]
        assert len(zone_1_entities) == 1
        assert len(zone_2_entities) == 1

    @pytest.mark.asyncio
    async def test_numbers_not_created_without_esphome(self):
        """Test that numbers are NOT created for zones without esphome devices."""
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
            "custom_components.plant_assistant.number.dr.async_get"
        ) as mock_async_get:
            mock_async_get.return_value = device_registry_mock

            await async_setup_entry(hass, entry, async_add_entities)

        # Verify that async_add_entities was NOT called
        async_add_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_numbers_not_created_with_missing_device(self):
        """Test that numbers are NOT created when zone device cannot be found."""
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
            "custom_components.plant_assistant.number.dr.async_get"
        ) as mock_async_get:
            mock_async_get.return_value = device_registry_mock

            await async_setup_entry(hass, entry, async_add_entities)

        # Verify that async_add_entities was NOT called
        async_add_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_numbers_mixed_zones_with_and_without_devices(self):
        """Test creation with some zones having devices and others not."""
        hass = Mock()
        entry = Mock()
        entry.entry_id = "test_entry_id"
        async_add_entities = AsyncMock()

        # Mock hass data structure with mixed zones
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
                                "linked_device_id": None,  # No device
                                "locations": {},
                            },
                            "zone-3": {
                                "id": "zone-3",
                                "name": "Side Garden",
                                "linked_device_id": "esphome_device_2",
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
            "custom_components.plant_assistant.number.dr.async_get"
        ) as mock_async_get:
            mock_async_get.return_value = device_registry_mock

            await async_setup_entry(hass, entry, async_add_entities)

        # Verify that async_add_entities was called with 2 number entities (1 per zone
        # with devices)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 2

        # Verify only zones with devices have numbers
        zone_1_entities = [e for e in entities if e.zone_name == "Front Lawn"]
        zone_3_entities = [e for e in entities if e.zone_name == "Side Garden"]
        assert len(zone_1_entities) == 1
        assert len(zone_3_entities) == 1
