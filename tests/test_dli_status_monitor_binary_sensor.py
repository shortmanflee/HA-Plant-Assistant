"""Tests for Daily Light Integral Status Monitor binary sensor."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    DailyLightIntegralStatusMonitorBinarySensor,
    DailyLightIntegralStatusMonitorConfig,
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
    return DailyLightIntegralStatusMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        location_device_id="test_location_456",
    )


class TestDailyLightIntegralStatusMonitorBinarySensorInit:
    """Test initialization of DailyLightIntegralStatusMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Garden Daily Light Integral Status"
        expected_unique_id = f"{DOMAIN}_test_entry_123_test_garden_dli_status"
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.location_name == "Test Garden"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = DailyLightIntegralStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            location_device_id="test_location",
        )
        sensor = DailyLightIntegralStatusMonitorBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_icon_when_dli_above(self, mock_hass):
        """Test that sensor has correct icon when DLI is above threshold."""
        config = DailyLightIntegralStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            location_device_id="test_location",
        )
        sensor = DailyLightIntegralStatusMonitorBinarySensor(config)

        # When problem detected and status is above
        sensor._state = True
        sensor._dli_status = "above"
        assert sensor.icon == "mdi:white-balance-sunny"

    def test_sensor_icon_when_dli_below(self, mock_hass):
        """Test that sensor has correct icon when DLI is below threshold."""
        config = DailyLightIntegralStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            location_device_id="test_location",
        )
        sensor = DailyLightIntegralStatusMonitorBinarySensor(config)

        # When problem detected and status is below
        sensor._state = True
        sensor._dli_status = "below"
        assert sensor.icon == "mdi:sun-compass"

    def test_sensor_icon_when_dli_normal(self, mock_hass):
        """Test that sensor has correct icon when DLI is normal."""
        config = DailyLightIntegralStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            location_device_id="test_location",
        )
        sensor = DailyLightIntegralStatusMonitorBinarySensor(config)

        # When no problem
        sensor._state = False
        sensor._dli_status = "normal"
        assert sensor.icon == "mdi:counter"

        # When state is None (unavailable)
        sensor._state = None
        assert sensor.icon == "mdi:counter"

    def test_sensor_device_info(self, mock_hass):
        """Test that sensor has correct device info."""
        config = DailyLightIntegralStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            location_device_id="test_location_123",
        )
        sensor = DailyLightIntegralStatusMonitorBinarySensor(config)

        device_info = sensor.device_info
        assert device_info is not None


class TestDailyLightIntegralStatusMonitorBinarySensorStateUpdate:
    """Test state update logic of DailyLightIntegralStatusMonitorBinarySensor."""

    def test_update_state_all_none(self, sensor_config):
        """Test state update when all values are None."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        # Explicitly set values to None to test unavailable state
        sensor._weekly_average_dli = None
        sensor._min_dli = None
        sensor._max_dli = None
        sensor._update_state()

        assert sensor._state is None
        assert sensor._dli_status == "normal"

    def test_update_state_dli_below_min(self, sensor_config):
        """Test state update when DLI is below minimum."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._weekly_average_dli = 5.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        sensor._update_state()

        assert sensor._state is True
        assert sensor._dli_status == "below"

    def test_update_state_dli_above_max(self, sensor_config):
        """Test state update when DLI is above maximum."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._weekly_average_dli = 25.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        sensor._update_state()

        assert sensor._state is True
        assert sensor._dli_status == "above"

    def test_update_state_dli_within_range(self, sensor_config):
        """Test state update when DLI is within acceptable range."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._weekly_average_dli = 15.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        sensor._update_state()

        assert sensor._state is False
        assert sensor._dli_status == "normal"

    def test_update_state_dli_at_min_boundary(self, sensor_config):
        """Test state update when DLI is exactly at minimum boundary."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._weekly_average_dli = 10.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        sensor._update_state()

        assert sensor._state is False
        assert sensor._dli_status == "normal"

    def test_update_state_dli_at_max_boundary(self, sensor_config):
        """Test state update when DLI is exactly at maximum boundary."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._weekly_average_dli = 20.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        sensor._update_state()

        assert sensor._state is False
        assert sensor._dli_status == "normal"

    def test_update_state_low_dli_with_active_ignore(self, sensor_config):
        """Test state update when DLI is low but ignore period is active."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._weekly_average_dli = 5.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        # Set ignore until to future time (active)
        now = datetime.now(UTC)
        future_time = now + timedelta(hours=1)
        sensor._low_threshold_ignore_until_datetime = future_time

        sensor._update_state()

        # Should be ignored
        assert sensor._state is False
        assert sensor._dli_status == "normal"

    def test_update_state_low_dli_with_expired_ignore(self, sensor_config):
        """Test state update when DLI is low and ignore period has expired."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._weekly_average_dli = 5.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        # Set ignore until to past time (expired)
        now = datetime.now(UTC)
        past_time = now - timedelta(hours=1)
        sensor._low_threshold_ignore_until_datetime = past_time

        sensor._update_state()

        # Should NOT be ignored
        assert sensor._state is True
        assert sensor._dli_status == "below"

    def test_update_state_high_dli_with_active_ignore(self, sensor_config):
        """Test state update when DLI is high but ignore period is active."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._weekly_average_dli = 25.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        # Set ignore until to future time (active)
        now = datetime.now(UTC)
        future_time = now + timedelta(hours=1)
        sensor._high_threshold_ignore_until_datetime = future_time

        sensor._update_state()

        # Should be ignored
        assert sensor._state is False
        assert sensor._dli_status == "normal"

    def test_update_state_high_dli_with_expired_ignore(self, sensor_config):
        """Test state update when DLI is high and ignore period has expired."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._weekly_average_dli = 25.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        # Set ignore until to past time (expired)
        now = datetime.now(UTC)
        past_time = now - timedelta(hours=1)
        sensor._high_threshold_ignore_until_datetime = past_time

        sensor._update_state()

        # Should NOT be ignored
        assert sensor._state is True
        assert sensor._dli_status == "above"


class TestDailyLightIntegralStatusMonitorBinarySensorAttributes:
    """Test state attributes of DailyLightIntegralStatusMonitorBinarySensor."""

    def test_extra_state_attributes_normal(self, sensor_config):
        """Test state attributes when DLI is normal."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._state = False
        sensor._dli_status = "normal"
        sensor._weekly_average_dli = 15.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        attrs = sensor.extra_state_attributes

        assert attrs["dli_status"] == "normal"
        assert attrs["weekly_average_dli"] == 15.0
        assert attrs["minimum_dli_threshold"] == 10.0
        assert attrs["maximum_dli_threshold"] == 20.0
        assert attrs["type"] == "Critical"
        assert "task" in attrs

    def test_extra_state_attributes_low_dli(self, sensor_config):
        """Test state attributes when DLI is below threshold."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._state = True
        sensor._dli_status = "below"
        sensor._weekly_average_dli = 5.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        attrs = sensor.extra_state_attributes

        assert attrs["dli_status"] == "below"
        assert attrs["weekly_average_dli"] == 5.0
        assert attrs["message"] == "Daily Light Integral Below"

    def test_extra_state_attributes_high_dli(self, sensor_config):
        """Test state attributes when DLI is above threshold."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._state = True
        sensor._dli_status = "above"
        sensor._weekly_average_dli = 25.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        attrs = sensor.extra_state_attributes

        assert attrs["dli_status"] == "above"
        assert attrs["weekly_average_dli"] == 25.0
        assert attrs["message"] == "Daily Light Integral Above"

    def test_extra_state_attributes_with_ignore_periods(self, sensor_config):
        """Test state attributes include ignore period information."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._state = False
        sensor._dli_status = "normal"
        sensor._weekly_average_dli = 15.0
        sensor._min_dli = 10.0
        sensor._max_dli = 20.0

        now = datetime.now(UTC)
        future_high = now + timedelta(hours=2)
        future_low = now + timedelta(hours=3)

        sensor._high_threshold_ignore_until_datetime = future_high
        sensor._low_threshold_ignore_until_datetime = future_low

        attrs = sensor.extra_state_attributes

        assert "high_threshold_ignore_until" in attrs
        assert "low_threshold_ignore_until" in attrs
        assert attrs["currently_ignoring_high"] is True
        assert attrs["currently_ignoring_low"] is True


class TestDailyLightIntegralStatusMonitorBinarySensorParsing:
    """Test parsing utilities of DailyLightIntegralStatusMonitorBinarySensor."""

    def test_parse_float_valid_string(self, sensor_config):
        """Test parsing valid float string."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        result = sensor._parse_float("15.5")

        assert result == 15.5

    def test_parse_float_valid_int(self, sensor_config):
        """Test parsing valid integer."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        result = sensor._parse_float(20)

        assert result == 20.0

    def test_parse_float_none(self, sensor_config):
        """Test parsing None."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        result = sensor._parse_float(None)

        assert result is None

    def test_parse_float_unavailable(self, sensor_config):
        """Test parsing unavailable state."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        result = sensor._parse_float(STATE_UNAVAILABLE)

        assert result is None

    def test_parse_float_unknown(self, sensor_config):
        """Test parsing unknown state."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        result = sensor._parse_float(STATE_UNKNOWN)

        assert result is None

    def test_parse_float_invalid_string(self, sensor_config):
        """Test parsing invalid string."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        result = sensor._parse_float("invalid")

        assert result is None


class TestDailyLightIntegralStatusMonitorBinarySensorIsOn:
    """Test is_on property of DailyLightIntegralStatusMonitorBinarySensor."""

    def test_is_on_true(self, sensor_config):
        """Test is_on when state is True."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._state = True

        assert sensor.is_on is True

    def test_is_on_false(self, sensor_config):
        """Test is_on when state is False."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._state = False

        assert sensor.is_on is False

    def test_is_on_none(self, sensor_config):
        """Test is_on when state is None."""
        sensor = DailyLightIntegralStatusMonitorBinarySensor(sensor_config)

        sensor._state = None

        assert sensor.is_on is None
