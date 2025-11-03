"""Tests for irrigation zone switches."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.plant_assistant.const import DOMAIN
from custom_components.plant_assistant.switch import (
    AfternoonScheduleSwitch,
    AllowFertiliserInjectionSwitch,
    AllowRainWaterDeliverySwitch,
    AllowWaterMainDeliverySwitch,
    IgnoreAreaOccupancySwitch,
    IgnoreRainSwitch,
    IgnoreSensorsSwitch,
    MasterScheduleSwitch,
    SunriseScheduleSwitch,
    SunsetScheduleSwitch,
    async_setup_entry,
)

# List of all switch classes to test
SWITCH_CLASSES = (
    (MasterScheduleSwitch, "master_schedule", "Master Schedule"),
    (SunriseScheduleSwitch, "sunrise_schedule", "Sunrise Schedule"),
    (AfternoonScheduleSwitch, "afternoon_schedule", "Afternoon Schedule"),
    (SunsetScheduleSwitch, "sunset_schedule", "Sunset Schedule"),
    (IgnoreAreaOccupancySwitch, "ignore_area_occupancy", "Ignore Area Occupancy"),
    (IgnoreSensorsSwitch, "ignore_sensors", "Ignore Sensors"),
    (IgnoreRainSwitch, "ignore_rain", "Ignore Rain"),
    (
        AllowRainWaterDeliverySwitch,
        "allow_rain_water_delivery",
        "Allow Rain Water Delivery",
    ),
    (
        AllowWaterMainDeliverySwitch,
        "allow_water_main_delivery",
        "Allow Water Main Delivery",
    ),
    (
        AllowFertiliserInjectionSwitch,
        "allow_fertiliser_injection",
        "Allow Fertiliser Injection",
    ),
)


class TestIrrigationZoneSwitchBase:
    """Test the base IrrigationZoneSwitch class."""

    @pytest.mark.asyncio
    async def test_switch_implements_restore_entity(self):
        """Test that irrigation zone switches implement RestoreEntity."""
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

        assert isinstance(switch, RestoreEntity)

    @pytest.mark.asyncio
    async def test_switch_is_on_property(self):
        """Test the is_on property."""
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

        assert switch.is_on is False
        switch._is_on = True
        assert switch.is_on is True


@pytest.mark.parametrize(
    ("switch_class", "switch_type", "switch_suffix"), SWITCH_CLASSES
)
class TestIrrigationZoneSwitches:
    """Parametrized tests for all irrigation zone switches."""

    @pytest.mark.asyncio
    async def test_switch_initialization(
        self, switch_class, switch_type, switch_suffix
    ):
        """Test that switch initializes correctly."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_name = "Front Lawn"
        zone_device = Mock()

        switch = switch_class(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name=zone_name,
            _zone_device=zone_device,
        )

        # Verify attributes
        assert switch.zone_name == "Front Lawn"
        assert switch._attr_name == f"Front Lawn {switch_suffix}"
        assert switch.is_on is False
        assert (
            switch._attr_unique_id
            == f"{DOMAIN}_test_entry_id_esphome_device_abc123_{switch_type}"
        )

        # Verify device info
        device_info = switch._attr_device_info
        assert device_info is not None
        assert "identifiers" in device_info
        assert device_info["identifiers"] == {zone_device_id}

    @pytest.mark.asyncio
    async def test_switch_turn_on_off(
        self,
        switch_class,
        switch_type,  # noqa: ARG002
        switch_suffix,  # noqa: ARG002
    ):
        """Test turning switch on and off."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        switch = switch_class(
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
    async def test_switch_state_restoration_on(
        self,
        switch_class,
        switch_type,  # noqa: ARG002
        switch_suffix,  # noqa: ARG002
    ):
        """Test that switch restores ON state on HA restart."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        switch = switch_class(
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
    async def test_switch_state_restoration_off(
        self,
        switch_class,
        switch_type,  # noqa: ARG002
        switch_suffix,  # noqa: ARG002
    ):
        """Test that switch restores OFF state on HA restart."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        switch = switch_class(
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
    async def test_switch_state_restoration_unavailable(
        self,
        switch_class,
        switch_type,  # noqa: ARG002
        switch_suffix,  # noqa: ARG002
    ):
        """Test that switch handles unavailable state on restoration."""
        hass = Mock()

        zone_device_id = ("esphome", "device_abc123")
        zone_device = Mock()

        switch = switch_class(
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


class TestAsyncSetupEntry:
    """Test the async_setup_entry function."""

    @pytest.mark.asyncio
    async def test_all_switches_created_for_single_zone(self):
        """Test that all 10 switches are created for a single zone."""
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

        # Verify that 10 switches were created
        assert len(entities) == 10

        # Verify each switch type
        expected_types = [
            "master_schedule",
            "sunrise_schedule",
            "afternoon_schedule",
            "sunset_schedule",
            "ignore_area_occupancy",
            "ignore_sensors",
            "ignore_rain",
            "allow_rain_water_delivery",
            "allow_water_main_delivery",
            "allow_fertiliser_injection",
        ]

        for i, expected_type in enumerate(expected_types):
            assert entities[i]._switch_type == expected_type
            assert entities[i].zone_name == "Front Lawn"

    @pytest.mark.asyncio
    async def test_switches_created_for_multiple_zones(self):
        """Test that switches are created for multiple zones."""
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
            "custom_components.plant_assistant.switch.dr.async_get"
        ) as mock_async_get:
            mock_async_get.return_value = device_registry_mock

            await async_setup_entry(hass, entry, async_add_entities)

        # Verify that async_add_entities was called with 20 switches (10 per zone)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 20

        # Verify zones
        zone_1_entities = [e for e in entities if e.zone_name == "Front Lawn"]
        zone_2_entities = [e for e in entities if e.zone_name == "Back Patio"]
        assert len(zone_1_entities) == 10
        assert len(zone_2_entities) == 10

    @pytest.mark.asyncio
    async def test_switches_not_created_without_esphome(self):
        """Test that switches are NOT created for zones without esphome devices."""
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
    async def test_switches_not_created_with_missing_device(self):
        """Test that switches are NOT created when zone device cannot be found."""
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
    async def test_switches_mixed_zones_with_and_without_devices(self):
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
            "custom_components.plant_assistant.switch.dr.async_get"
        ) as mock_async_get:
            mock_async_get.return_value = device_registry_mock

            await async_setup_entry(hass, entry, async_add_entities)

        # Verify that async_add_entities was called with 20 switches (10 per zone
        # with devices)
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 20

        # Verify only zones with devices have switches
        zone_1_entities = [e for e in entities if e.zone_name == "Front Lawn"]
        zone_3_entities = [e for e in entities if e.zone_name == "Side Garden"]
        assert len(zone_1_entities) == 10
        assert len(zone_3_entities) == 10
