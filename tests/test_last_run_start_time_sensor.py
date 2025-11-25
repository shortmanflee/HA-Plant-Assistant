"""Tests for Last Run Start Time sensor."""

from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from custom_components.plant_assistant.sensor import (
    IrrigationZoneLastRunStartTimeSensor,
)


class TestIrrigationZoneLastRunStartTimeSensor:
    """Test IrrigationZoneLastRunStartTimeSensor."""

    def test_extract_zone_start_time_with_device_name(self):
        """Test that zone_name is normalized to extract device data."""
        hass = Mock()
        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="Flower Bed",  # Zone name as displayed
            zone_id="zone-2",  # Still used for unique_id, but not for event extraction
        )

        # Event data uses device names with underscores
        event_data = {
            "trigger": "Zone Deactivated",
            "current_zone": "Flower Bed",
            "lawn_start_time": "2025-11-06T20:24:17+00:00",
            "flower_bed_start_time": "2025-11-06T20:24:17+00:00",
            "flower_bed_duration": "5",
        }

        # Should extract flower_bed_start_time based on zone_name "Flower Bed"
        start_time = sensor._extract_zone_start_time(event_data)
        assert start_time == "2025-11-06T20:24:17+00:00"

    def test_extract_zone_start_time_with_lowercase_device_name(self):
        """Test that zone_name with underscores works correctly."""
        hass = Mock()
        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="lawn",  # Zone name already lowercase
            zone_id="zone_1",  # Still used for unique_id
        )

        event_data = {
            "lawn_start_time": "2025-11-06T20:25:00+00:00",
            "flower_bed_start_time": "2025-11-06T20:24:17+00:00",
        }

        start_time = sensor._extract_zone_start_time(event_data)
        assert start_time == "2025-11-06T20:25:00+00:00"

    def test_extract_zone_start_time_missing_key(self):
        """Test that missing key returns None."""
        hass = Mock()
        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="Planters",
            zone_id="zone-3",
        )

        event_data = {
            "lawn_start_time": "2025-11-06T20:24:17+00:00",
            "flower_bed_start_time": "2025-11-06T20:24:17+00:00",
        }

        # planters_start_time is missing, should return None
        start_time = sensor._extract_zone_start_time(event_data)
        assert start_time is None

    def test_handle_esphome_event_valid_data(self):
        """Test handling of valid esphome event."""
        hass = Mock()
        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="Flower Bed",
            zone_id="zone-2",
        )

        sensor.async_write_ha_state = Mock()

        # Create a mock event with the exact structure from the user's example
        event = Mock()
        event.data = {
            "trigger": "Zone Deactivated",
            "current_zone": "Flower Bed",
            "lawn_start_time": "2025-11-06T20:24:17+00:00",
            "lawn_end_time": "unknown",
            "lawn_duration": "0",
            "flower_bed_start_time": "2025-11-06T20:24:17+00:00",
            "flower_bed_end_time": "unknown",
            "flower_bed_duration": "5",
            "planters_start_time": "unknown",
            "planters_end_time": "unknown",
        }

        sensor._handle_esphome_event(event)

        # Verify the state was updated
        assert sensor._state == "2025-11-06T20:24:17+00:00"
        assert sensor._attributes["zone_name"] == "Flower Bed"
        assert sensor._attributes["zone_key"] == "flower_bed_start_time"
        sensor.async_write_ha_state.assert_called_once()

    def test_handle_esphome_event_unknown_start_time(self):
        """Test handling when start_time is unknown."""
        hass = Mock()
        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="Planters",
            zone_id="zone-3",
        )

        sensor.async_write_ha_state = Mock()
        sensor._state = "2025-11-06T20:00:00+00:00"  # Previous state

        event = Mock()
        event.data = {
            "planters_start_time": "unknown",
        }

        sensor._handle_esphome_event(event)

        # State should not be updated
        assert sensor._state == "2025-11-06T20:00:00+00:00"
        sensor.async_write_ha_state.assert_not_called()

    def test_handle_esphome_event_missing_start_time(self):
        """Test handling when start_time is missing from event."""
        hass = Mock()
        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="Lawn",
            zone_id="zone-1",
        )

        sensor.async_write_ha_state = Mock()

        event = Mock()
        event.data = {
            "trigger": "Zone Deactivated",
            "current_zone": "Flower Bed",
            "flower_bed_start_time": "2025-11-06T20:24:17+00:00",
        }

        sensor._handle_esphome_event(event)

        # State should not be updated since lawn_start_time is missing
        assert sensor._state is None
        sensor.async_write_ha_state.assert_not_called()

    def test_native_value_returns_state(self):
        """Test that native_value returns the current state."""
        hass = Mock()
        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="Test Zone",
            zone_id="zone-1",
        )

        # Test with valid ISO 8601 datetime string
        sensor._state = "2025-11-06T20:24:17+00:00"
        native_value = sensor.native_value
        assert native_value is not None
        # Verify it's a datetime object
        assert hasattr(native_value, "tzinfo")

        # Test with None
        sensor._state = None
        assert sensor.native_value is None

        # Test with unavailable
        sensor._state = STATE_UNAVAILABLE
        assert sensor.native_value is None

        # Test with unknown
        sensor._state = STATE_UNKNOWN
        assert sensor.native_value is None

    def test_native_value_parses_iso_datetime(self):
        """Test that native_value correctly parses ISO 8601 datetime strings."""
        hass = Mock()
        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="Test Zone",
            zone_id="zone-1",
        )

        # Test with various ISO 8601 formats
        test_cases = [
            "2025-11-06T20:24:17+00:00",
            "2025-11-06T20:24:17.000+00:00",
            "2025-11-06T20:24:17Z",
        ]

        for iso_string in test_cases:
            sensor._state = iso_string
            native_value = sensor.native_value
            assert native_value is not None, f"Failed to parse {iso_string}"
            assert hasattr(native_value, "tzinfo"), (
                f"Result is not datetime for {iso_string}"
            )

    def test_extra_state_attributes(self):
        """Test that extra_state_attributes returns the correct data."""
        hass = Mock()
        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="Flower Bed",
            zone_id="zone-2",
        )

        # Set attributes
        sensor._attributes = {
            "event_type": "esphome.irrigation_gateway_update",
            "zone_name": "Flower Bed",
            "zone_key": "flower_bed_start_time",
        }

        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert attrs["event_type"] == "esphome.irrigation_gateway_update"
        assert attrs["zone_name"] == "Flower Bed"
        assert attrs["zone_key"] == "flower_bed_start_time"

    def test_extra_state_attributes_empty(self):
        """Test that extra_state_attributes returns None when empty."""
        hass = Mock()
        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="Test Zone",
            zone_id="zone-1",
        )

        # Empty attributes
        sensor._attributes = {}

        assert sensor.extra_state_attributes is None

    @pytest.mark.asyncio
    async def test_event_listener_setup(self):
        """Test that event listener is set up correctly."""
        hass = Mock()
        hass.bus.async_listen = Mock(return_value=Mock())

        sensor = IrrigationZoneLastRunStartTimeSensor(
            hass=hass,
            entry_id="test_entry",
            zone_device_id=("esphome", "device_123"),
            zone_name="Test Zone",
            zone_id="zone-1",
        )

        # Mock async_get_last_state to return None
        sensor.async_get_last_state = AsyncMock(return_value=None)
        sensor.entity_id = "sensor.test_zone_last_run_start_time"

        # Call async_added_to_hass
        await sensor.async_added_to_hass()

        # Verify event listener was registered
        hass.bus.async_listen.assert_called_once_with(
            "esphome.irrigation_gateway_update",
            sensor._handle_esphome_event,
        )
