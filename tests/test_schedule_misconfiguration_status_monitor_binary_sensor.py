"""Tests for Schedule Misconfiguration Status Monitor binary sensor."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    ScheduleMisconfigurationStatusMonitorBinarySensor,
    ScheduleMisconfigurationStatusMonitorConfig,
)
from custom_components.plant_assistant.const import DOMAIN

from .conftest import create_state_changed_event


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
    return ScheduleMisconfigurationStatusMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Zone",
        irrigation_zone_name="Zone A",
        master_schedule_switch_entity_id="switch.test_zone_schedule",
        sunrise_switch_entity_id="switch.test_zone_sunrise",
        afternoon_switch_entity_id="switch.test_zone_afternoon",
        sunset_switch_entity_id="switch.test_zone_sunset",
        zone_device_identifier=("plant_assistant", "test_zone_456"),
    )


class TestScheduleMisconfigurationStatusMonitorBinarySensorInit:
    """Test initialization of ScheduleMisconfigurationStatusMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Zone Schedule Misconfiguration Status"
        expected_unique_id = (
            f"{DOMAIN}_test_entry_123_test_zone_schedule_misconfiguration_status"
        )
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.master_schedule_switch_entity_id == ("switch.test_zone_schedule")
        assert sensor.sunrise_switch_entity_id == "switch.test_zone_sunrise"
        assert sensor.afternoon_switch_entity_id == "switch.test_zone_afternoon"
        assert sensor.sunset_switch_entity_id == "switch.test_zone_sunset"
        assert sensor.location_name == "Test Zone"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = ScheduleMisconfigurationStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Zone",
            irrigation_zone_name="Zone A",
            master_schedule_switch_entity_id="switch.test_zone_schedule",
            sunrise_switch_entity_id="switch.test_zone_sunrise",
            afternoon_switch_entity_id="switch.test_zone_afternoon",
            sunset_switch_entity_id="switch.test_zone_sunset",
            zone_device_identifier=("plant_assistant", "test_zone"),
        )
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_initial_state(self, mock_hass, sensor_config):
        """Test that sensor starts with None state when switches are unavailable."""
        # Mock the states.get to return None so all switches start as None
        mock_hass.states.get.return_value = None
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        assert sensor._state is None
        assert sensor._master_schedule_on is None
        assert sensor._sunrise_on is None
        assert sensor._afternoon_on is None
        assert sensor._sunset_on is None

    def test_sensor_device_info(self, mock_hass):
        """Test that sensor has correct device info."""
        config = ScheduleMisconfigurationStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Zone",
            irrigation_zone_name="Zone A",
            master_schedule_switch_entity_id="switch.test_zone_schedule",
            sunrise_switch_entity_id="switch.test_zone_sunrise",
            afternoon_switch_entity_id="switch.test_zone_afternoon",
            sunset_switch_entity_id="switch.test_zone_sunset",
            zone_device_identifier=("esphome", "test_zone_123"),
        )
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(config)

        device_info = sensor.device_info
        assert device_info is not None
        assert device_info.get("identifiers") == {("esphome", "test_zone_123")}


class TestScheduleMisconfigurationStatusMonitorBinarySensorStateLogic:
    """Test state calculation logic."""

    def test_update_state_all_switches_off(self, sensor_config):
        """Test state when all switches are off (no problem)."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = False
        sensor._sunrise_on = False
        sensor._afternoon_on = False
        sensor._sunset_on = False
        sensor._update_state()

        # Master off, so no problem
        assert sensor._state is False

    def test_update_state_master_on_all_time_switches_off(self, sensor_config):
        """Test state when master is on but all time switches are off (problem)."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._sunrise_on = False
        sensor._afternoon_on = False
        sensor._sunset_on = False
        sensor._update_state()

        # Master on, all time switches off = problem
        assert sensor._state is True

    def test_update_state_master_on_sunrise_on(self, sensor_config):
        """Test state when master is on and sunrise is on (no problem)."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._sunrise_on = True
        sensor._afternoon_on = False
        sensor._sunset_on = False
        sensor._update_state()

        # At least one time switch is on = no problem
        assert sensor._state is False

    def test_update_state_master_on_afternoon_on(self, sensor_config):
        """Test state when master is on and afternoon is on (no problem)."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._sunrise_on = False
        sensor._afternoon_on = True
        sensor._sunset_on = False
        sensor._update_state()

        # At least one time switch is on = no problem
        assert sensor._state is False

    def test_update_state_master_on_sunset_on(self, sensor_config):
        """Test state when master is on and sunset is on (no problem)."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._sunrise_on = False
        sensor._afternoon_on = False
        sensor._sunset_on = True
        sensor._update_state()

        # At least one time switch is on = no problem
        assert sensor._state is False

    def test_update_state_master_on_all_time_switches_on(self, sensor_config):
        """Test state when master and all time switches are on (no problem)."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._sunrise_on = True
        sensor._afternoon_on = True
        sensor._sunset_on = True
        sensor._update_state()

        # At least one time switch is on = no problem
        assert sensor._state is False

    def test_update_state_any_switch_unavailable(self, sensor_config):
        """Test state when any switch is unavailable."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._sunrise_on = None  # Unavailable
        sensor._afternoon_on = False
        sensor._sunset_on = False
        sensor._update_state()

        # Any unavailable switch = state is unavailable
        assert sensor._state is None

    def test_update_state_with_ignore_until_active(self, sensor_config):
        """Test that ignore_until prevents problem from being raised."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._sunrise_on = False
        sensor._afternoon_on = False
        sensor._sunset_on = False

        # Set ignore_until to future time
        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        sensor._update_state()

        # Even though schedule is misconfigured, we're ignoring, so no problem
        assert sensor._state is False

    def test_update_state_with_ignore_until_expired(self, sensor_config):
        """Test that expired ignore_until allows problem to be raised."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._sunrise_on = False
        sensor._afternoon_on = False
        sensor._sunset_on = False

        # Set ignore_until to past time
        past_time = datetime.now(UTC) - timedelta(hours=1)
        sensor._ignore_until_datetime = past_time

        sensor._update_state()

        # Ignore period is expired, schedule is misconfigured, so problem
        assert sensor._state is True


class TestScheduleMisconfigurationStatusMonitorBinarySensorProperties:
    """Test property accessors."""

    def test_is_on_property_when_on(self, sensor_config):
        """Test is_on property when state is True."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._state = True

        assert sensor.is_on is True

    def test_is_on_property_when_off(self, sensor_config):
        """Test is_on property when state is False."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._state = False

        assert sensor.is_on is False

    def test_is_on_property_when_unavailable(self, sensor_config):
        """Test is_on property when state is None."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._state = None

        assert sensor.is_on is None

    def test_icon_when_problem_detected(self, sensor_config):
        """Test icon when problem is detected."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._state = True

        assert sensor.icon == "mdi:clock-alert"

    def test_icon_when_no_problem(self, sensor_config):
        """Test icon when no problem is detected."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._state = False

        assert sensor.icon == "mdi:clock-check"

    def test_availability_all_available(self, mock_hass, sensor_config):
        """Test availability when all switches are available."""
        mock_state = MagicMock()
        mock_state.state = "on"
        mock_hass.states.get.return_value = mock_state

        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)

        assert sensor.available is True

    def test_availability_one_unavailable(self, mock_hass, sensor_config):
        """Test availability when at least one switch is unavailable."""

        def side_effect(entity_id):
            if entity_id == "switch.test_zone_schedule":
                return MagicMock(state="on")
            return None

        mock_hass.states.get.side_effect = side_effect

        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)

        assert sensor.available is False

    def test_extra_state_attributes_when_problem(self, sensor_config):
        """Test extra state attributes when problem is detected."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        sensor._master_schedule_on = True
        sensor._sunrise_on = False
        sensor._afternoon_on = False
        sensor._sunset_on = False

        attrs = sensor.extra_state_attributes

        assert attrs["type"] == "Warning"
        assert attrs["message"] == "Schedule Misconfigured"
        assert attrs["task"] is True
        assert attrs["master_schedule_on"] is True
        assert attrs["sunrise_on"] is False
        assert attrs["afternoon_on"] is False
        assert attrs["sunset_on"] is False
        assert attrs["tags"] == ["zone_a"]

    def test_extra_state_attributes_when_no_problem(self, sensor_config):
        """Test extra state attributes when no problem is detected."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        sensor._master_schedule_on = True
        sensor._sunrise_on = True
        sensor._afternoon_on = False
        sensor._sunset_on = False

        attrs = sensor.extra_state_attributes

        assert attrs["type"] == "Warning"
        assert attrs["message"] == "Schedule OK"
        assert attrs["task"] is True

    def test_extra_state_attributes_with_ignore_until(self, sensor_config):
        """Test extra state attributes include ignore_until information."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._state = False

        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        attrs = sensor.extra_state_attributes

        assert "ignore_until" in attrs
        assert attrs["ignore_until"] == future_time.isoformat()
        assert attrs["currently_ignoring"] is True


class TestScheduleMisconfigurationStatusMonitorBinarySensorCallbacks:
    """Test callback functions."""

    def test_master_schedule_state_changed(self, sensor_config):
        """Test callback when master schedule changes."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = False
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = "on"

        event = create_state_changed_event(new_state)
        sensor._master_schedule_state_changed(event)

        assert sensor._master_schedule_on is True

    def test_sunrise_state_changed(self, sensor_config):
        """Test callback when sunrise switch changes."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._sunrise_on = False
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = "on"

        event = create_state_changed_event(new_state)
        sensor._sunrise_state_changed(event)

        assert sensor._sunrise_on is True

    def test_afternoon_state_changed(self, sensor_config):
        """Test callback when afternoon switch changes."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._afternoon_on = False
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = "on"

        event = create_state_changed_event(new_state)
        sensor._afternoon_state_changed(event)

        assert sensor._afternoon_on is True

    def test_sunset_state_changed(self, sensor_config):
        """Test callback when sunset switch changes."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._sunset_on = False
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = "on"

        event = create_state_changed_event(new_state)
        sensor._sunset_state_changed(event)

        assert sensor._sunset_on is True

    def test_schedule_misconfiguration_ignore_until_state_changed(self, sensor_config):
        """Test callback when ignore until datetime changes."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._sunrise_on = False
        sensor._afternoon_on = False
        sensor._sunset_on = False
        sensor._state = True
        sensor.async_write_ha_state = MagicMock()

        future_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        new_state = MagicMock()
        new_state.state = future_time

        event = create_state_changed_event(new_state)
        sensor._schedule_misconfiguration_ignore_until_state_changed(event)

        # State should be False (not a problem while ignoring)
        assert sensor._ignore_until_datetime is not None
        assert sensor._state is False

    def test_schedule_misconfiguration_ignore_until_state_changed_to_unavailable(
        self, sensor_config
    ):
        """Test callback when ignore until becomes unavailable."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._sunrise_on = False
        sensor._afternoon_on = False
        sensor._sunset_on = False
        sensor._ignore_until_datetime = datetime.now(UTC) + timedelta(hours=1)
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = STATE_UNAVAILABLE

        event = create_state_changed_event(new_state)
        sensor._schedule_misconfiguration_ignore_until_state_changed(event)

        # Ignore until should be cleared
        assert sensor._ignore_until_datetime is None
        # Now with schedule misconfigured and no ignore, should be a problem
        assert sensor._state is True


class TestScheduleMisconfigurationStatusMonitorBinarySensorAsyncOperations:
    """Test async operations."""

    @pytest.mark.asyncio
    async def test_async_added_to_hass(self, sensor_config):
        """Test async_added_to_hass method."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)

        # Mock the parent class method
        sensor.async_get_last_state = AsyncMock(return_value=None)
        sensor.async_write_ha_state = MagicMock()

        # Mock entity registry
        mock_registry = MagicMock()
        mock_registry.entities.values.return_value = []

        with (
            patch(
                "custom_components.plant_assistant.binary_sensor.er.async_get",
                return_value=mock_registry,
            ),
            patch(
                "custom_components.plant_assistant.binary_sensor.async_track_state_change_event"
            ) as mock_track,
        ):
            mock_track.return_value = lambda: None

            await sensor.async_added_to_hass()

            # Verify state was updated
            assert sensor.async_write_ha_state.called

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass(self, sensor_config):
        """Test cleanup when entity is removed."""
        sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(sensor_config)

        # Create mock unsubscribe functions
        mock_unsubscribe_master = MagicMock()
        mock_unsubscribe_sunrise = MagicMock()
        mock_unsubscribe_afternoon = MagicMock()
        mock_unsubscribe_sunset = MagicMock()
        mock_unsubscribe_ignore = MagicMock()

        sensor._unsubscribe_master = mock_unsubscribe_master
        sensor._unsubscribe_sunrise = mock_unsubscribe_sunrise
        sensor._unsubscribe_afternoon = mock_unsubscribe_afternoon
        sensor._unsubscribe_sunset = mock_unsubscribe_sunset
        sensor._unsubscribe_ignore_until = mock_unsubscribe_ignore

        await sensor.async_will_remove_from_hass()

        # Verify cleanup was called
        mock_unsubscribe_master.assert_called_once()
        mock_unsubscribe_sunrise.assert_called_once()
        mock_unsubscribe_afternoon.assert_called_once()
        mock_unsubscribe_sunset.assert_called_once()
        mock_unsubscribe_ignore.assert_called_once()
