"""Tests for Battery Level Status Monitor binary sensor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    BatteryLevelStatusMonitorBinarySensor,
    BatteryLevelStatusMonitorConfig,
)
from custom_components.plant_assistant.const import DOMAIN


def create_state_changed_event(new_state):
    """Create an Event object for state changed callbacks."""
    event_data = EventStateChangedData(
        entity_id="sensor.test",
        old_state=None,
        new_state=new_state,
    )
    return Event("state_changed", event_data)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.data = {}
    hass.async_create_task = MagicMock()
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=lambda: None)
    return hass


@pytest.fixture
def sensor_config(mock_hass):
    """Create a default sensor configuration."""
    return BatteryLevelStatusMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        battery_entity_id="sensor.device_battery",
        location_device_id="test_location_789",
    )


class TestBatteryLevelStatusMonitorBinarySensorInit:
    """Test initialization of BatteryLevelStatusMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Garden Monitor Battery Level Status"
        expected_unique_id = (
            f"{DOMAIN}_test_entry_123_test_garden_monitor_battery_level_status"
        )
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.battery_entity_id == "sensor.device_battery"
        assert sensor.location_name == "Test Garden"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = BatteryLevelStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            battery_entity_id="sensor.device_battery",
            location_device_id="test_location",
        )
        sensor = BatteryLevelStatusMonitorBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_initial_state(self, sensor_config):
        """Test that sensor starts with None state."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        assert sensor._state is None
        assert sensor._current_battery_level is None


class TestBatteryLevelStatusMonitorBinarySensorStateUpdate:
    """Test state update logic for BatteryLevelStatusMonitorBinarySensor."""

    def test_update_state_battery_below_threshold(self, sensor_config):
        """Test state update when battery is below 10% threshold."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 5.0
        sensor._update_state()

        # When battery is below 10%, state should be True (problem)
        assert sensor._state is True

    def test_update_state_battery_at_threshold(self, sensor_config):
        """Test state update when battery is exactly at 10%."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 10.0
        sensor._update_state()

        # When battery is exactly at 10%, state should be False (no problem)
        assert sensor._state is False

    def test_update_state_battery_above_threshold(self, sensor_config):
        """Test state update when battery is above 10%."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 50.0
        sensor._update_state()

        # When battery is above 10%, state should be False (no problem)
        assert sensor._state is False

    def test_update_state_battery_unavailable(self, sensor_config):
        """Test state update when battery level is unavailable."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = None
        sensor._update_state()

        # When battery level is unavailable, state should be None
        assert sensor._state is None

    def test_update_state_battery_high(self, sensor_config):
        """Test state update when battery is fully charged."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 100.0
        sensor._update_state()

        # When battery is fully charged, state should be False (no problem)
        assert sensor._state is False

    def test_update_state_battery_very_low(self, sensor_config):
        """Test state update when battery is critically low."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 0.5
        sensor._update_state()

        # When battery is critically low, state should be True (problem)
        assert sensor._state is True


class TestBatteryLevelStatusMonitorBinarySensorParseFloat:
    """Test float parsing utility method."""

    def test_parse_float_valid_string(self, sensor_config):
        """Test parsing valid float string."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        result = sensor._parse_float("42.5")
        assert result == 42.5

    def test_parse_float_valid_integer(self, sensor_config):
        """Test parsing valid integer string."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        result = sensor._parse_float("100")
        assert result == 100.0

    def test_parse_float_unavailable(self, sensor_config):
        """Test parsing unavailable state."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        result = sensor._parse_float(STATE_UNAVAILABLE)
        assert result is None

    def test_parse_float_unknown(self, sensor_config):
        """Test parsing unknown state."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        result = sensor._parse_float(STATE_UNKNOWN)
        assert result is None

    def test_parse_float_none(self, sensor_config):
        """Test parsing None value."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        result = sensor._parse_float(None)
        assert result is None

    def test_parse_float_invalid_string(self, sensor_config):
        """Test parsing invalid string."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        result = sensor._parse_float("invalid")
        assert result is None


class TestBatteryLevelStatusMonitorBinarySensorProperty:
    """Test properties of BatteryLevelStatusMonitorBinarySensor."""

    def test_is_on_property_when_low(self, sensor_config):
        """Test is_on property when battery is low."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        assert sensor.is_on is True

    def test_is_on_property_when_normal(self, sensor_config):
        """Test is_on property when battery is normal."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        assert sensor.is_on is False

    def test_is_on_property_when_unknown(self, sensor_config):
        """Test is_on property when state is unknown."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = None
        assert sensor.is_on is None

    def test_icon_when_low_battery(self, sensor_config):
        """Test icon when battery is low."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        assert sensor.icon == "mdi:battery-alert"

    def test_icon_when_normal_battery(self, sensor_config):
        """Test icon when battery is normal."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        assert sensor.icon == "mdi:battery"

    def test_icon_when_unknown_state(self, sensor_config):
        """Test icon when state is unknown."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = None
        assert sensor.icon == "mdi:battery"

    def test_available_property_when_battery_available(self, sensor_config):
        """Test that sensor is available when battery entity is available."""
        mock_state = MagicMock()
        mock_state.state = "75"
        sensor_config.hass.states.get.return_value = mock_state

        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        assert sensor.available is True

    def test_available_property_when_battery_unavailable(self, sensor_config):
        """Test that sensor is unavailable when battery entity is unavailable."""
        sensor_config.hass.states.get.return_value = None

        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        assert sensor.available is False

    def test_device_info(self, sensor_config):
        """Test device info property."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        device_info = sensor.device_info

        assert device_info is not None
        assert device_info.get("identifiers") == {(DOMAIN, "test_location_789")}

    def test_device_info_without_location_device_id(self, mock_hass):
        """Test device info when location_device_id is not provided."""
        config = BatteryLevelStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            battery_entity_id="sensor.device_battery",
        )
        sensor = BatteryLevelStatusMonitorBinarySensor(config)
        device_info = sensor.device_info

        assert device_info is None

    def test_extra_state_attributes_when_low(self, sensor_config):
        """Test extra state attributes when battery is low."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        sensor._current_battery_level = 8.0

        attributes = sensor.extra_state_attributes

        assert attributes["type"] == "Critical"
        assert attributes["message"] == "Battery level low (< 10%)"
        assert attributes["task"] is True
        assert attributes["current_battery_level"] == 8.0
        assert attributes["source_entity"] == "sensor.device_battery"
        assert "test_garden" in attributes["tags"]
        assert "zone_a" in attributes["tags"]

    def test_extra_state_attributes_when_normal(self, sensor_config):
        """Test extra state attributes when battery is normal."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        sensor._current_battery_level = 75.0

        attributes = sensor.extra_state_attributes

        assert attributes["type"] == "Normal"
        assert attributes["message"] == "Battery level normal"
        assert attributes["task"] is False
        assert attributes["current_battery_level"] == 75.0
        assert attributes["source_entity"] == "sensor.device_battery"

    def test_extra_state_attributes_tags(self, sensor_config):
        """Test that tags are correctly formatted."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        sensor._current_battery_level = 50.0

        attributes = sensor.extra_state_attributes

        # Tags should be lowercase with underscores
        assert "test_garden" in attributes["tags"]
        assert "zone_a" in attributes["tags"]


class TestBatteryLevelStatusMonitorBinarySensorStateChanges:
    """Test handling of state changes."""

    def test_battery_state_changed_with_valid_value(self, sensor_config):
        """Test handling battery state change with valid value."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = "45.5"

        event = create_state_changed_event(new_state)
        sensor._battery_state_changed(event)

        assert sensor._current_battery_level == 45.5
        assert sensor._state is False  # 45.5 > 10
        sensor.async_write_ha_state.assert_called_once()

    def test_battery_state_changed_low_battery(self, sensor_config):
        """Test handling battery state change when battery goes low."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 50.0
        sensor._state = False
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = "5"

        event = create_state_changed_event(new_state)
        sensor._battery_state_changed(event)

        assert sensor._current_battery_level == 5.0
        assert sensor._state is True  # 5 < 10
        sensor.async_write_ha_state.assert_called_once()

    def test_battery_state_changed_with_none(self, sensor_config):
        """Test handling battery state change with None value."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 50.0
        sensor.async_write_ha_state = MagicMock()

        event = create_state_changed_event(None)
        sensor._battery_state_changed(event)

        assert sensor._current_battery_level is None
        assert sensor._state is None
        sensor.async_write_ha_state.assert_called_once()

    def test_battery_state_changed_with_unavailable(self, sensor_config):
        """Test handling battery state change to unavailable."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 50.0
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = STATE_UNAVAILABLE

        event = create_state_changed_event(new_state)
        sensor._battery_state_changed(event)

        assert sensor._current_battery_level is None
        assert sensor._state is None
        sensor.async_write_ha_state.assert_called_once()


class TestBatteryLevelStatusMonitorBinarySensorAsyncMethods:
    """Test async methods."""

    @pytest.mark.asyncio
    async def test_async_added_to_hass(self, sensor_config):
        """Test async_added_to_hass method."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor.async_write_ha_state = MagicMock()
        sensor.async_get_last_state = AsyncMock(return_value=None)

        # Mock battery state
        mock_state = MagicMock()
        mock_state.state = "75"
        sensor_config.hass.states.get.return_value = mock_state

        # Mock async_track_state_change_event to avoid deprecation warnings in tests
        with patch(
            "custom_components.plant_assistant.binary_sensor.async_track_state_change_event",
            return_value=MagicMock(),
        ):
            await sensor.async_added_to_hass()

        assert sensor._current_battery_level == 75.0
        assert sensor._state is False  # 75 > 10

    @pytest.mark.asyncio
    async def test_async_added_to_hass_no_battery_state(self, sensor_config):
        """Test async_added_to_hass when battery state not available."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor.async_write_ha_state = MagicMock()
        sensor.async_get_last_state = AsyncMock(return_value=None)

        # No battery state available
        sensor_config.hass.states.get.return_value = None

        # Mock async_track_state_change_event to avoid deprecation warnings in tests
        with patch(
            "custom_components.plant_assistant.binary_sensor.async_track_state_change_event",
            return_value=MagicMock(),
        ):
            await sensor.async_added_to_hass()

        assert sensor._current_battery_level is None
        assert sensor._state is None

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass(self, sensor_config):
        """Test async_will_remove_from_hass method."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        mock_unsubscribe = MagicMock()
        sensor._unsubscribe = mock_unsubscribe

        await sensor.async_will_remove_from_hass()

        mock_unsubscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass_no_subscription(self, sensor_config):
        """Test async_will_remove_from_hass when no subscription exists."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._unsubscribe = None

        # Should not raise exception
        await sensor.async_will_remove_from_hass()

    @pytest.mark.asyncio
    async def test_restore_previous_state_from_on(self, sensor_config):
        """Test restoring previous state when it was on."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        last_state = MagicMock()
        last_state.state = "on"

        sensor.async_get_last_state = AsyncMock(return_value=last_state)

        await sensor._restore_previous_state()

        assert sensor._state is True

    @pytest.mark.asyncio
    async def test_restore_previous_state_from_off(self, sensor_config):
        """Test restoring previous state when it was off."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        last_state = MagicMock()
        last_state.state = "off"

        sensor.async_get_last_state = AsyncMock(return_value=last_state)

        await sensor._restore_previous_state()

        assert sensor._state is False

    @pytest.mark.asyncio
    async def test_restore_previous_state_unavailable(self, sensor_config):
        """Test restoring previous state when it was unavailable."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        last_state = MagicMock()
        last_state.state = "unavailable"

        sensor.async_get_last_state = AsyncMock(return_value=last_state)

        await sensor._restore_previous_state()

        # State should remain None since we're restoring from unavailable
        assert sensor._state is None

    @pytest.mark.asyncio
    async def test_restore_previous_state_no_last_state(self, sensor_config):
        """Test restoring previous state when no last state exists."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)

        sensor.async_get_last_state = AsyncMock(return_value=None)

        await sensor._restore_previous_state()

        assert sensor._state is None


class TestBatteryLevelStatusMonitorBinarySensorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_boundary_9_percent(self, sensor_config):
        """Test at 9% (just below threshold)."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 9.0
        sensor._update_state()
        assert sensor._state is True

    def test_boundary_10_1_percent(self, sensor_config):
        """Test at 10.1% (just above threshold)."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 10.1
        sensor._update_state()
        assert sensor._state is False

    def test_boundary_0_percent(self, sensor_config):
        """Test at 0% (completely dead)."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 0.0
        sensor._update_state()
        assert sensor._state is True

    def test_boundary_100_percent(self, sensor_config):
        """Test at 100% (fully charged)."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 100.0
        sensor._update_state()
        assert sensor._state is False

    def test_large_battery_value(self, sensor_config):
        """Test with unusually large battery value (e.g., millivolts)."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 3000.0
        sensor._update_state()
        # Should still be False since it's > 10
        assert sensor._state is False

    def test_negative_battery_value(self, sensor_config):
        """Test with negative battery value (invalid but should handle gracefully)."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = -5.0
        sensor._update_state()
        # Negative value < 10, so should be True
        assert sensor._state is True

    def test_fractional_battery_value(self, sensor_config):
        """Test with fractional battery value."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 9.99
        sensor._update_state()
        assert sensor._state is True

    def test_very_small_fractional_battery_value(self, sensor_config):
        """Test with very small fractional battery value."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 0.01
        sensor._update_state()
        assert sensor._state is True


class TestBatteryLevelStatusMonitorBinarySensorIgnoreUntil:
    """Test ignore until datetime functionality."""

    def test_update_state_with_active_ignore_until(self, sensor_config):
        """Test that state is False when ignore_until is in the future."""
        from datetime import timedelta

        from homeassistant.util import dt as dt_util

        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 5.0  # Low battery

        # Set ignore_until to future
        future_time = dt_util.now() + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        sensor._update_state()

        # Even though battery is low, state should be False due to ignore
        assert sensor._state is False

    def test_update_state_with_expired_ignore_until(self, sensor_config):
        """Test that state respects battery when ignore_until is in the past."""
        from datetime import timedelta

        from homeassistant.util import dt as dt_util

        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._current_battery_level = 5.0  # Low battery

        # Set ignore_until to past
        past_time = dt_util.now() - timedelta(hours=1)
        sensor._ignore_until_datetime = past_time

        sensor._update_state()

        # ignore_until has expired, so state should be True (low battery)
        assert sensor._state is True

    def test_battery_low_ignore_until_state_changed_with_valid_datetime(
        self, sensor_config
    ):
        """Test handling ignore until state change with valid datetime."""
        from datetime import timedelta

        from homeassistant.util import dt as dt_util

        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor.async_write_ha_state = MagicMock()
        sensor._current_battery_level = 5.0  # Low battery

        new_state = MagicMock()
        future_time = dt_util.now() + timedelta(hours=2)
        new_state.state = future_time.isoformat()

        event = create_state_changed_event(new_state)
        sensor._battery_low_ignore_until_state_changed(event)

        assert sensor._ignore_until_datetime is not None
        # State should be False due to active ignore
        assert sensor._state is False
        sensor.async_write_ha_state.assert_called_once()

    def test_battery_low_ignore_until_state_changed_with_unavailable(
        self, sensor_config
    ):
        """Test handling ignore until state change to unavailable."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor.async_write_ha_state = MagicMock()
        sensor._current_battery_level = 5.0  # Low battery

        new_state = MagicMock()
        new_state.state = STATE_UNAVAILABLE

        event = create_state_changed_event(new_state)
        sensor._battery_low_ignore_until_state_changed(event)

        assert sensor._ignore_until_datetime is None
        # Without ignore_until, low battery should trigger
        assert sensor._state is True
        sensor.async_write_ha_state.assert_called_once()

    def test_battery_low_ignore_until_state_changed_with_unknown(self, sensor_config):
        """Test handling ignore until state change to unknown."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor.async_write_ha_state = MagicMock()
        sensor._current_battery_level = 5.0  # Low battery

        new_state = MagicMock()
        new_state.state = STATE_UNKNOWN

        event = create_state_changed_event(new_state)
        sensor._battery_low_ignore_until_state_changed(event)

        assert sensor._ignore_until_datetime is None
        # Without ignore_until, low battery should trigger
        assert sensor._state is True
        sensor.async_write_ha_state.assert_called_once()

    def test_battery_low_ignore_until_state_changed_with_none(self, sensor_config):
        """Test handling ignore until state change to None."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor.async_write_ha_state = MagicMock()
        sensor._current_battery_level = 5.0  # Low battery

        event = create_state_changed_event(None)
        sensor._battery_low_ignore_until_state_changed(event)

        assert sensor._ignore_until_datetime is None
        # Without ignore_until, low battery should trigger
        assert sensor._state is True
        sensor.async_write_ha_state.assert_called_once()

    def test_extra_state_attributes_with_active_ignore_until(self, sensor_config):
        """Test extra state attributes when ignore_until is active."""
        from datetime import timedelta

        from homeassistant.util import dt as dt_util

        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        sensor._current_battery_level = 5.0

        future_time = dt_util.now() + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        attributes = sensor.extra_state_attributes

        assert "ignore_until" in attributes
        assert attributes["currently_ignoring"] is True
        assert "ignore_expires_in_seconds" not in attributes  # Not added to attributes
        assert attributes["ignore_until"] == future_time.isoformat()

    def test_extra_state_attributes_with_expired_ignore_until(self, sensor_config):
        """Test extra state attributes when ignore_until has expired."""
        from datetime import timedelta

        from homeassistant.util import dt as dt_util

        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        sensor._current_battery_level = 5.0

        past_time = dt_util.now() - timedelta(hours=1)
        sensor._ignore_until_datetime = past_time

        attributes = sensor.extra_state_attributes

        assert "ignore_until" in attributes
        assert attributes["currently_ignoring"] is False
        assert attributes["ignore_until"] == past_time.isoformat()

    def test_extra_state_attributes_without_ignore_until(self, sensor_config):
        """Test extra state attributes when no ignore_until is set."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        sensor._current_battery_level = 5.0
        sensor._ignore_until_datetime = None

        attributes = sensor.extra_state_attributes

        assert "ignore_until" not in attributes
        assert "currently_ignoring" not in attributes

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass_with_both_subscriptions(
        self, sensor_config
    ):
        """Test async_will_remove_from_hass with both subscriptions active."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        mock_unsubscribe_battery = MagicMock()
        mock_unsubscribe_ignore_until = MagicMock()
        sensor._unsubscribe = mock_unsubscribe_battery
        sensor._unsubscribe_ignore_until = mock_unsubscribe_ignore_until

        await sensor.async_will_remove_from_hass()

        mock_unsubscribe_battery.assert_called_once()
        mock_unsubscribe_ignore_until.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass_with_only_battery_subscription(
        self, sensor_config
    ):
        """Test async_will_remove_from_hass with only battery subscription."""
        sensor = BatteryLevelStatusMonitorBinarySensor(sensor_config)
        mock_unsubscribe_battery = MagicMock()
        sensor._unsubscribe = mock_unsubscribe_battery
        sensor._unsubscribe_ignore_until = None

        await sensor.async_will_remove_from_hass()

        mock_unsubscribe_battery.assert_called_once()
