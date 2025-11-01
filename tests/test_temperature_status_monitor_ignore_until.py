"""Tests for Temperature Status Monitor binary sensor ignore until functionality."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.plant_assistant.binary_sensor import (
    TemperatureStatusMonitorBinarySensor,
    TemperatureStatusMonitorConfig,
)


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
    return TemperatureStatusMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        temperature_entity_id="sensor.test_temperature",
        location_device_id="test_location_456",
    )


class TestTemperatureStatusMonitorIgnoreUntilFunctionality:
    """Test ignore until functionality for temperature status monitor."""

    def test_high_threshold_ignore_until_prevents_alarm(self, mock_hass):
        """Test that high threshold ignore until datetime prevents alarm."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)

        # Set up thresholds exceeding 2 hours for "above" status
        sensor._above_threshold_hours = 3.0
        sensor._below_threshold_hours = 0.5

        # Set ignore until datetime to a time in the future
        now = dt_util.now()
        future_time = now + timedelta(hours=1)
        sensor._high_threshold_ignore_until_datetime = future_time

        # Update state - should not trigger alarm due to ignore until
        sensor._update_state()

        assert sensor._state is False
        assert sensor._temperature_status == "normal"

    def test_low_threshold_ignore_until_prevents_alarm(self, mock_hass):
        """Test that low threshold ignore until datetime prevents alarm."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)

        # Set up thresholds exceeding 2 hours for "below" status
        sensor._above_threshold_hours = 0.5
        sensor._below_threshold_hours = 3.0

        # Set ignore until datetime to a time in the future
        now = dt_util.now()
        future_time = now + timedelta(hours=2)
        sensor._low_threshold_ignore_until_datetime = future_time

        # Update state - should not trigger alarm due to ignore until
        sensor._update_state()

        assert sensor._state is False
        assert sensor._temperature_status == "normal"

    def test_expired_high_threshold_ignore_until_allows_alarm(self, mock_hass):
        """Test that expired high threshold ignore until datetime allows alarm."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)

        # Set up thresholds exceeding 2 hours for "above" status
        sensor._above_threshold_hours = 3.0
        sensor._below_threshold_hours = 0.5

        # Set ignore until datetime to a time in the past
        now = dt_util.now()
        past_time = now - timedelta(hours=1)
        sensor._high_threshold_ignore_until_datetime = past_time

        # Update state - should trigger alarm since ignore until has expired
        sensor._update_state()

        assert sensor._state is True
        assert sensor._temperature_status == "above"

    def test_expired_low_threshold_ignore_until_allows_alarm(self, mock_hass):
        """Test that expired low threshold ignore until datetime allows alarm."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)

        # Set up thresholds exceeding 2 hours for "below" status
        sensor._above_threshold_hours = 0.5
        sensor._below_threshold_hours = 3.0

        # Set ignore until datetime to a time in the past
        now = dt_util.now()
        past_time = now - timedelta(hours=1)
        sensor._low_threshold_ignore_until_datetime = past_time

        # Update state - should trigger alarm since ignore until has expired
        sensor._update_state()

        assert sensor._state is True
        assert sensor._temperature_status == "below"

    def test_high_threshold_ignore_until_callback(self, mock_hass):
        """Test high threshold ignore until datetime state changed callback."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)
        sensor.async_write_ha_state = MagicMock()

        # Create a mock new_state with datetime string
        future_time = dt_util.now() + timedelta(hours=1)
        mock_new_state = MagicMock()
        mock_new_state.state = future_time.isoformat()

        sensor._high_threshold_ignore_until_state_changed(
            "entity_id", None, mock_new_state
        )

        assert sensor._high_threshold_ignore_until_datetime is not None
        assert sensor._high_threshold_ignore_until_datetime.replace(
            microsecond=0
        ) == future_time.replace(microsecond=0)

    def test_low_threshold_ignore_until_callback(self, mock_hass):
        """Test low threshold ignore until datetime state changed callback."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)
        sensor.async_write_ha_state = MagicMock()

        # Create a mock new_state with datetime string
        future_time = dt_util.now() + timedelta(hours=2)
        mock_new_state = MagicMock()
        mock_new_state.state = future_time.isoformat()

        sensor._low_threshold_ignore_until_state_changed(
            "entity_id", None, mock_new_state
        )

        assert sensor._low_threshold_ignore_until_datetime is not None
        assert sensor._low_threshold_ignore_until_datetime.replace(
            microsecond=0
        ) == future_time.replace(microsecond=0)

    def test_high_threshold_ignore_until_callback_with_none(self, mock_hass):
        """Test high threshold ignore until callback with None state."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)
        sensor.async_write_ha_state = MagicMock()

        sensor._high_threshold_ignore_until_state_changed("entity_id", None, None)

        assert sensor._high_threshold_ignore_until_datetime is None

    def test_low_threshold_ignore_until_callback_with_none(self, mock_hass):
        """Test low threshold ignore until callback with None state."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)
        sensor.async_write_ha_state = MagicMock()

        sensor._low_threshold_ignore_until_state_changed("entity_id", None, None)

        assert sensor._low_threshold_ignore_until_datetime is None

    def test_high_threshold_ignore_until_callback_with_unavailable(self, mock_hass):
        """Test high threshold ignore until callback with unavailable state."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)
        sensor.async_write_ha_state = MagicMock()

        # Create a mock new_state with unavailable
        mock_new_state = MagicMock()
        mock_new_state.state = STATE_UNAVAILABLE

        sensor._high_threshold_ignore_until_state_changed(
            "entity_id", None, mock_new_state
        )

        assert sensor._high_threshold_ignore_until_datetime is None

    def test_extra_state_attributes_with_high_ignore_until(self, mock_hass):
        """Test extra state attributes includes high ignore until info."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)

        future_time = dt_util.now() + timedelta(hours=1)
        sensor._high_threshold_ignore_until_datetime = future_time

        attrs = sensor.extra_state_attributes

        assert "high_threshold_ignore_until" in attrs
        assert "currently_ignoring_high" in attrs
        assert attrs["currently_ignoring_high"] is True

    def test_extra_state_attributes_with_low_ignore_until(self, mock_hass):
        """Test extra state attributes includes low ignore until info."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)

        future_time = dt_util.now() + timedelta(hours=2)
        sensor._low_threshold_ignore_until_datetime = future_time

        attrs = sensor.extra_state_attributes

        assert "low_threshold_ignore_until" in attrs
        assert "currently_ignoring_low" in attrs
        assert attrs["currently_ignoring_low"] is True

    def test_extra_state_attributes_with_expired_high_ignore_until(self, mock_hass):
        """Test extra state attributes with expired high ignore until."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)

        past_time = dt_util.now() - timedelta(hours=1)
        sensor._high_threshold_ignore_until_datetime = past_time

        attrs = sensor.extra_state_attributes

        assert "high_threshold_ignore_until" in attrs
        assert "currently_ignoring_high" in attrs
        assert attrs["currently_ignoring_high"] is False

    def test_both_high_and_low_ignore_until_only_high_applies(self, mock_hass):
        """Test that when both ignore until are set, only relevant one applies."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)

        # Set above threshold hours to exceed limit
        sensor._above_threshold_hours = 3.0
        sensor._below_threshold_hours = 0.5

        # Set high ignore until to future (should prevent alarm)
        future_time = dt_util.now() + timedelta(hours=1)
        sensor._high_threshold_ignore_until_datetime = future_time

        # Set low ignore until to past (should not matter for this case)
        past_time = dt_util.now() - timedelta(hours=1)
        sensor._low_threshold_ignore_until_datetime = past_time

        sensor._update_state()

        # Should not alarm because high ignore until is active
        assert sensor._state is False
        assert sensor._temperature_status == "normal"

    def test_both_high_and_low_ignore_until_only_low_applies(self, mock_hass):
        """Test that when both ignore until are set, only relevant one applies."""
        config = TemperatureStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            temperature_entity_id="sensor.test_temperature",
            location_device_id="test_location",
        )
        sensor = TemperatureStatusMonitorBinarySensor(config)

        # Set below threshold hours to exceed limit
        sensor._above_threshold_hours = 0.5
        sensor._below_threshold_hours = 3.0

        # Set low ignore until to future (should prevent alarm)
        future_time = dt_util.now() + timedelta(hours=2)
        sensor._low_threshold_ignore_until_datetime = future_time

        # Set high ignore until to past (should not matter for this case)
        past_time = dt_util.now() - timedelta(hours=1)
        sensor._high_threshold_ignore_until_datetime = past_time

        sensor._update_state()

        # Should not alarm because low ignore until is active
        assert sensor._state is False
        assert sensor._temperature_status == "normal"
