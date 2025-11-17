"""Tests for the irrigation zone error count sensor."""

import unittest
from unittest.mock import Mock, patch

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData

from custom_components.plant_assistant.sensor import IrrigationZoneErrorCountSensor


def create_state_changed_event(new_state):
    """Create an Event object for state changed callbacks."""
    event_data = EventStateChangedData(
        entity_id="sensor.test",
        old_state=None,
        new_state=new_state,
    )
    return Event("state_changed", event_data)


class TestIrrigationZoneErrorCountSensor(unittest.TestCase):
    """Test cases for IrrigationZoneErrorCountSensor."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.hass = Mock()
        self.entry_id = "test_entry_id"
        self.zone_device_id = ("esphome", "device_123")
        self.zone_name = "Test Zone"
        self.zone_id = "test-zone"

    def _create_sensor(self) -> IrrigationZoneErrorCountSensor:
        """Create a sensor instance for testing."""
        return IrrigationZoneErrorCountSensor(
            self.hass,
            self.entry_id,
            self.zone_device_id,
            self.zone_name,
            self.zone_id,
        )

    def test_handle_last_error_state_change(self) -> None:
        """Test that error count increments when Last Error state changes."""
        sensor = self._create_sensor()
        sensor._state = 0
        sensor._last_error_state = None

        # Create a new state mock (Last Error entity state changed)
        new_error_time = "2025-11-15T10:00:00"
        new_state = Mock()
        new_state.state = new_error_time

        # Call the handler
        with patch.object(sensor, "async_write_ha_state"):
            event = create_state_changed_event(new_state)
            sensor._handle_last_error_state_change(event)

        # Error count should increment
        assert sensor._state == 1
        assert sensor._last_error_state == new_error_time

    def test_handle_last_error_state_change_same_time(self) -> None:
        """Test that error count doesn't increment when Last Error state stays same."""
        sensor = self._create_sensor()
        sensor._state = 1
        sensor._last_error_state = "2025-11-15T10:00:00"

        # Create a state mock with the same error time
        new_state = Mock()
        new_state.state = "2025-11-15T10:00:00"

        # Call the handler
        with patch.object(sensor, "async_write_ha_state"):
            event = create_state_changed_event(new_state)
            sensor._handle_last_error_state_change(event)

        # Error count should NOT increment
        assert sensor._state == 1
        assert sensor._last_error_state == "2025-11-15T10:00:00"

    def test_handle_last_error_state_change_unavailable(self) -> None:
        """Test that error count ignores unavailable Last Error state."""
        sensor = self._create_sensor()
        sensor._state = 0
        sensor._last_error_state = None

        # Create a state mock with unavailable state
        new_state = Mock()
        new_state.state = STATE_UNAVAILABLE

        # Call the handler
        with patch.object(sensor, "async_write_ha_state"):
            event = create_state_changed_event(new_state)
            sensor._handle_last_error_state_change(event)

        # Error count should remain 0
        assert sensor._state == 0
        assert sensor._last_error_state is None

    def test_handle_last_error_state_change_unknown(self) -> None:
        """Test that error count ignores unknown Last Error state."""
        sensor = self._create_sensor()
        sensor._state = 0
        sensor._last_error_state = None

        # Create a state mock with unknown state
        new_state = Mock()
        new_state.state = STATE_UNKNOWN

        # Call the handler
        with patch.object(sensor, "async_write_ha_state"):
            event = create_state_changed_event(new_state)
            sensor._handle_last_error_state_change(event)

        # Error count should remain 0
        assert sensor._state == 0
        assert sensor._last_error_state is None

    def test_handle_last_error_state_change_none(self) -> None:
        """Test that error count ignores None Last Error state."""
        sensor = self._create_sensor()
        sensor._state = 0
        sensor._last_error_state = None

        # Create a state mock with None state
        new_state = Mock()
        new_state.state = None

        # Call the handler
        with patch.object(sensor, "async_write_ha_state"):
            event = create_state_changed_event(new_state)
            sensor._handle_last_error_state_change(event)

        # Error count should remain 0
        assert sensor._state == 0
        assert sensor._last_error_state is None

    def test_reset_error_count(self) -> None:
        """Test that reset_error_count clears the state."""
        sensor = self._create_sensor()
        sensor._state = 5
        sensor._last_error_state = "2025-11-15T10:00:00"
        sensor._attributes = {"event_type": "last_error_state_change"}

        with patch.object(sensor, "async_write_ha_state"):
            sensor.reset_error_count()

        assert sensor._state == 0
        assert sensor._last_error_state is None
        assert sensor._attributes == {}

    def test_error_count_increments_multiple_times(self) -> None:
        """Test that error count increments correctly across multiple state changes."""
        sensor = self._create_sensor()
        sensor._state = 0
        sensor._last_error_state = None

        # First error
        state1 = Mock()
        state1.state = "2025-11-15T10:00:00"
        with patch.object(sensor, "async_write_ha_state"):
            event = create_state_changed_event(state1)
            sensor._handle_last_error_state_change(event)
        assert sensor._state == 1

        # Second error (different time)
        state2 = Mock()
        state2.state = "2025-11-15T11:00:00"
        with patch.object(sensor, "async_write_ha_state"):
            event = create_state_changed_event(state2)
            sensor._handle_last_error_state_change(event)
        assert sensor._state == 2

        # Same time again (should not increment)
        state3 = Mock()
        state3.state = "2025-11-15T11:00:00"
        with patch.object(sensor, "async_write_ha_state"):
            event = create_state_changed_event(state3)
            sensor._handle_last_error_state_change(event)
        assert sensor._state == 2


if __name__ == "__main__":
    unittest.main()
