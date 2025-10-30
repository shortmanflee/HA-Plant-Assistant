"""Tests for Soil Moisture Low Monitor binary sensor."""

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    SoilMoistureLowMonitorBinarySensor,
    SoilMoistureLowMonitorConfig,
)
from custom_components.plant_assistant.const import DOMAIN


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.data = {}
    hass.async_create_task = MagicMock()
    return hass


@pytest.fixture
def mock_entity_registry():
    """Create a mock entity registry."""
    registry = MagicMock()
    registry.entities = MagicMock()
    registry.entities.values = MagicMock(return_value=[])

    with patch(
        "custom_components.plant_assistant.binary_sensor.er.async_get",
        return_value=registry,
    ):
        yield registry


@pytest.fixture
def sensor_config(mock_hass):
    """Create a default sensor configuration."""
    return SoilMoistureLowMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        soil_moisture_entity_id="sensor.test_moisture",
        location_device_id="test_location_456",
    )


class TestSoilMoistureLowMonitorBinarySensorInit:
    """Test initialization of SoilMoistureLowMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = SoilMoistureLowMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Garden Soil Moisture Low Monitor"
        expected_unique_id = (
            f"{DOMAIN}_test_entry_123_test_garden_soil_moisture_low_monitor"
        )
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.soil_moisture_entity_id == "sensor.test_moisture"
        assert sensor.location_name == "Test Garden"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_icon(self, mock_hass):
        """Test that sensor has correct icon."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        assert sensor._attr_icon == "mdi:water-alert"

    def test_sensor_device_info(self, mock_hass):
        """Test that sensor has correct device info."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location_123",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        device_info = sensor.device_info
        assert device_info is not None
        assert device_info.get("identifiers") == {(DOMAIN, "test_location_123")}


class TestSoilMoistureLowMonitorBinarySensorStateLogic:
    """Test state calculation logic."""

    def test_parse_float_with_valid_value(self, mock_hass):
        """Test parsing valid float values."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        assert sensor._parse_float("45.5") == 45.5
        assert sensor._parse_float("0") == 0.0
        assert sensor._parse_float("100") == 100.0

    def test_parse_float_with_invalid_value(self, mock_hass):
        """Test parsing invalid values returns None."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        assert sensor._parse_float("invalid") is None
        assert sensor._parse_float(None) is None
        assert sensor._parse_float(STATE_UNAVAILABLE) is None
        assert sensor._parse_float(STATE_UNKNOWN) is None

    def test_update_state_when_moisture_below_threshold(self, mock_hass):
        """Test that state is ON when moisture is below threshold."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is True

    def test_update_state_when_moisture_above_threshold(self, mock_hass):
        """Test that state is OFF when moisture is above threshold."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = 50.0
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is False

    def test_update_state_when_moisture_equals_threshold(self, mock_hass):
        """Test that state is OFF when moisture equals threshold."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = 30.0
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is False

    def test_update_state_when_moisture_unavailable(self, mock_hass):
        """Test that state is None when moisture is unavailable."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = None
        sensor._min_soil_moisture = 30.0
        sensor._update_state()

        assert sensor._state is None

    def test_update_state_when_threshold_unavailable(self, mock_hass):
        """Test that state is None when threshold is unavailable."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = None
        sensor._update_state()

        assert sensor._state is None


class TestSoilMoistureLowMonitorBinarySensorProperties:
    """Test binary sensor properties."""

    def test_is_on_returns_state(self, mock_hass):
        """Test is_on property returns current state."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._state = True
        assert sensor.is_on is True

        sensor._state = False
        assert sensor.is_on is False

        sensor._state = None
        assert sensor.is_on is None

    def test_extra_state_attributes(self, mock_hass):
        """Test that extra state attributes are set correctly."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0

        attrs = sensor.extra_state_attributes

        # Check required attributes from user request
        assert attrs["type"] == "Critical"
        assert attrs["message"] == "Soil Moisture Low"
        assert attrs["task"] is True
        assert attrs["tags"] == ["test_garden", "zone_a"]

        # Check internal attributes
        assert attrs["current_soil_moisture"] == 25.0
        assert attrs["minimum_soil_moisture_threshold"] == 30.0
        assert attrs["source_entity"] == "sensor.test_moisture"

    def test_available_when_entity_exists(self, mock_hass):
        """Test sensor is available when moisture entity exists."""
        mock_state = MagicMock()
        mock_state.state = "50"
        mock_hass.states.get.return_value = mock_state

        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        assert sensor.available is True

    def test_available_when_entity_missing(self, mock_hass):
        """Test sensor is unavailable when moisture entity is missing."""
        mock_hass.states.get.return_value = None

        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        assert sensor.available is False


class TestSoilMoistureLowMonitorBinarySensorCallbacks:
    """Test state change callbacks."""

    def test_soil_moisture_state_changed_callback(self, mock_hass):
        """Test soil moisture state change callback."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        # Mock async_write_ha_state to avoid Home Assistant runtime dependencies
        sensor.async_write_ha_state = MagicMock()

        sensor._min_soil_moisture = 30.0

        # Simulate moisture dropping below threshold
        old_state = MagicMock()
        old_state.state = "35"
        new_state = MagicMock()
        new_state.state = "25"

        sensor._soil_moisture_state_changed(
            "sensor.test_moisture",
            old_state,
            new_state,
        )

        assert sensor._current_soil_moisture == 25.0
        assert sensor._state is True
        sensor.async_write_ha_state.assert_called_once()

    def test_min_soil_moisture_state_changed_callback(self, mock_hass):
        """Test minimum soil moisture threshold change callback."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        # Mock async_write_ha_state to avoid Home Assistant runtime dependencies
        sensor.async_write_ha_state = MagicMock()

        sensor._current_soil_moisture = 25.0

        # Simulate threshold increasing
        old_state = MagicMock()
        old_state.state = "20"
        new_state = MagicMock()
        new_state.state = "30"

        sensor._min_soil_moisture_state_changed(
            "sensor.min_soil_moisture",
            old_state,
            new_state,
        )

        assert sensor._min_soil_moisture == 30.0
        assert sensor._state is True  # Now below threshold
        sensor.async_write_ha_state.assert_called_once()


class TestSoilMoistureLowMonitorBinarySensorCleanup:
    """Test resource cleanup."""

    async def test_async_will_remove_from_hass(self, mock_hass):
        """Test cleanup when entity is removed."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        # Mock the unsubscribe functions
        mock_unsubscribe = MagicMock()
        mock_unsubscribe_min = MagicMock()

        sensor._unsubscribe = mock_unsubscribe
        sensor._unsubscribe_min = mock_unsubscribe_min

        await sensor.async_will_remove_from_hass()

        # Verify both unsubscribe functions were called
        mock_unsubscribe.assert_called_once()
        mock_unsubscribe_min.assert_called_once()


class TestSoilMoistureLowMonitorBinarySensorIgnoreUntil:
    """Test ignore until datetime functionality."""

    def test_sensor_not_on_when_ignore_until_in_future(self, mock_hass):
        """Test that sensor is OFF when ignore until datetime is in the future."""
        from datetime import datetime, timedelta

        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0

        # Set ignore until to 1 hour in the future
        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        sensor._update_state()

        # Should be False (no problem) even though moisture is below threshold
        assert sensor._state is False

    def test_sensor_on_when_ignore_until_in_past(self, mock_hass):
        """Test that sensor is ON when ignore until datetime is in the past."""
        from datetime import datetime, timedelta

        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0

        # Set ignore until to 1 hour in the past
        past_time = datetime.now(UTC) - timedelta(hours=1)
        sensor._ignore_until_datetime = past_time

        sensor._update_state()

        # Should be True (problem) since ignore period has expired
        assert sensor._state is True

    def test_sensor_on_when_no_ignore_until(self, mock_hass):
        """Test sensor is ON when moisture below threshold and no ignore until."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._ignore_until_datetime = None

        sensor._update_state()

        # Should be True (problem) when no ignore until is set
        assert sensor._state is True

    def test_ignore_until_datetime_state_changed_callback(self, mock_hass):
        """Test ignore until datetime state change callback."""
        from datetime import datetime, timedelta

        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
            location_device_id="test_location",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        # Mock async_write_ha_state to avoid Home Assistant runtime dependencies
        sensor.async_write_ha_state = MagicMock()

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0

        # Initially state should be True (problem)
        sensor._update_state()
        assert sensor._state is True

        # Simulate datetime entity state change to future time
        future_time_str = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        new_state = MagicMock()
        new_state.state = future_time_str

        sensor._soil_moisture_ignore_until_state_changed(
            "datetime.ignore_until",
            None,
            new_state,
        )

        # State should now be False (no problem)
        assert sensor._state is False
        sensor.async_write_ha_state.assert_called_once()

    def test_ignore_until_datetime_cleared_when_unavailable(self, mock_hass):
        """Test that ignore until datetime is cleared when state becomes unavailable."""
        from datetime import datetime, timedelta

        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_device_id="test_location",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        # Mock async_write_ha_state
        sensor.async_write_ha_state = MagicMock()

        # Set initial ignore until datetime
        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0

        # State should be False (no problem) due to ignore until
        sensor._update_state()
        assert sensor._state is False

        # Simulate datetime entity becoming unavailable
        new_state = MagicMock()
        new_state.state = STATE_UNAVAILABLE

        sensor._soil_moisture_ignore_until_state_changed(
            "datetime.ignore_until",
            None,
            new_state,
        )

        # Ignore until should be cleared
        assert sensor._ignore_until_datetime is None

        # State should now be True (problem) since ignore was cleared
        assert sensor._state is True

    def test_extra_state_attributes_includes_ignore_until(self, mock_hass):
        """Test that extra state attributes include ignore until information."""
        from datetime import datetime, timedelta

        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_device_id="test_location",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0

        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        attrs = sensor.extra_state_attributes

        assert "ignore_until" in attrs
        assert "currently_ignoring" in attrs
        assert attrs["currently_ignoring"] is True

    def test_extra_state_attributes_without_ignore_until(self, mock_hass):
        """Test that extra state attributes don't include ignore until when not set."""
        config = SoilMoistureLowMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_device_id="test_location",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            soil_moisture_entity_id="sensor.test_moisture",
        )
        sensor = SoilMoistureLowMonitorBinarySensor(config)

        sensor._current_soil_moisture = 25.0
        sensor._min_soil_moisture = 30.0
        sensor._ignore_until_datetime = None

        attrs = sensor.extra_state_attributes

        assert "ignore_until" not in attrs
        assert "currently_ignoring" not in attrs
