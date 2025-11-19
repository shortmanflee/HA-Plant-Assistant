"""Tests for Master Schedule Status Monitor binary sensor."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    MasterScheduleStatusMonitorBinarySensor,
    MasterScheduleStatusMonitorConfig,
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
    return MasterScheduleStatusMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Zone",
        irrigation_zone_name="Zone A",
        master_schedule_switch_entity_id="switch.test_zone_schedule",
        zone_device_identifier=("plant_assistant", "test_zone_456"),
    )


class TestMasterScheduleStatusMonitorBinarySensorInit:
    """Test initialization of MasterScheduleStatusMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Zone Schedule Status"
        expected_unique_id = f"{DOMAIN}_test_entry_123_test_zone_schedule_status"
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.master_schedule_switch_entity_id == ("switch.test_zone_schedule")
        assert sensor.location_name == "Test Zone"
        assert sensor.irrigation_zone_name == "Zone A"

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = MasterScheduleStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Zone",
            irrigation_zone_name="Zone A",
            master_schedule_switch_entity_id="switch.test_zone_schedule",
            zone_device_identifier=("plant_assistant", "test_zone"),
        )
        sensor = MasterScheduleStatusMonitorBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_initial_state(self, mock_hass, sensor_config):
        """Test that sensor starts with None state."""
        # Mock the states.get to return None so master_schedule_on starts as None
        mock_hass.states.get.return_value = None
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        assert sensor._state is None
        assert sensor._master_schedule_on is None

    def test_sensor_device_info(self, mock_hass):
        """Test that sensor has correct device info."""
        config = MasterScheduleStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Zone",
            irrigation_zone_name="Zone A",
            master_schedule_switch_entity_id="switch.test_zone_schedule",
            zone_device_identifier=("esphome", "test_zone_123"),
        )
        sensor = MasterScheduleStatusMonitorBinarySensor(config)

        device_info = sensor.device_info
        assert device_info is not None
        assert device_info.get("identifiers") == {("esphome", "test_zone_123")}


class TestMasterScheduleStatusMonitorBinarySensorStateLogic:
    """Test state calculation logic."""

    def test_update_state_master_schedule_off(self, sensor_config):
        """Test state update when master schedule is OFF."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = False
        sensor._update_state()

        # When master schedule is OFF, state should be True (problem)
        assert sensor._state is True

    def test_update_state_master_schedule_on(self, sensor_config):
        """Test state update when master schedule is ON."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True
        sensor._update_state()

        # When master schedule is ON, state should be False (no problem)
        assert sensor._state is False

    def test_update_state_master_schedule_unavailable(self, sensor_config):
        """Test state update when master schedule is unavailable."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = None
        sensor._update_state()

        # When master schedule state is unavailable, state should be None
        assert sensor._state is None

    def test_update_state_master_schedule_off_with_ignore_until_active(
        self, sensor_config
    ):
        """Test that ignore_until prevents problem from being raised."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = False

        # Set ignore_until to future time
        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        sensor._update_state()

        # Even though master schedule is OFF, we're ignoring until future, so no problem
        assert sensor._state is False

    def test_update_state_master_schedule_off_with_ignore_until_expired(
        self, sensor_config
    ):
        """Test that expired ignore_until allows problem to be raised."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = False

        # Set ignore_until to past time
        past_time = datetime.now(UTC) - timedelta(hours=1)
        sensor._ignore_until_datetime = past_time

        sensor._update_state()

        # Ignore period is expired, master schedule is OFF, so problem should be raised
        assert sensor._state is True

    def test_update_state_master_schedule_on_with_ignore_until_active(
        self, sensor_config
    ):
        """Test that ignore_until doesn't affect ON state."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = True

        # Set ignore_until to future time
        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        sensor._update_state()

        # Master schedule is ON, so no problem regardless of ignore_until
        assert sensor._state is False


class TestMasterScheduleStatusMonitorBinarySensorProperties:
    """Test property accessors."""

    def test_is_on_property_when_on(self, sensor_config):
        """Test is_on property when state is True."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = True

        assert sensor.is_on is True

    def test_is_on_property_when_off(self, sensor_config):
        """Test is_on property when state is False."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = False

        assert sensor.is_on is False

    def test_is_on_property_when_unavailable(self, sensor_config):
        """Test is_on property when state is None."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = None

        assert sensor.is_on is None

    def test_icon_when_problem_detected(self, sensor_config):
        """Test icon when problem is detected."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = True

        assert sensor.icon == "mdi:clock-remove"

    def test_icon_when_no_problem(self, sensor_config):
        """Test icon when no problem is detected."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = False

        assert sensor.icon == "mdi:clock-check"

    def test_icon_when_unavailable(self, sensor_config):
        """Test icon when sensor is unavailable."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = None

        assert sensor.icon == "mdi:clock-check"

    def test_availability_when_switch_available(self, mock_hass, sensor_config):
        """Test availability when master schedule switch is available."""
        mock_state = MagicMock()
        mock_state.state = "on"
        mock_hass.states.get.return_value = mock_state

        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)

        assert sensor.available is True

    def test_availability_when_switch_unavailable(self, mock_hass, sensor_config):
        """Test availability when master schedule switch is unavailable."""
        mock_hass.states.get.return_value = None

        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)

        assert sensor.available is False

    def test_extra_state_attributes_when_problem(self, sensor_config):
        """Test extra state attributes when problem is detected."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        sensor._master_schedule_on = False

        attrs = sensor.extra_state_attributes

        assert attrs["type"] == "Warning"
        assert attrs["message"] == "Master Schedule Off"
        assert attrs["task"] is True
        assert attrs["master_schedule_on"] is False
        assert attrs["source_entity"] == "switch.test_zone_schedule"
        assert attrs["tags"] == ["zone_a"]

    def test_extra_state_attributes_when_no_problem(self, sensor_config):
        """Test extra state attributes when no problem is detected."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        sensor._master_schedule_on = True

        attrs = sensor.extra_state_attributes

        assert attrs["type"] == "Warning"
        assert attrs["message"] == "Master Schedule On"
        assert attrs["task"] is True
        assert attrs["master_schedule_on"] is True

    def test_extra_state_attributes_with_ignore_until(self, sensor_config):
        """Test extra state attributes include ignore_until information."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = False

        future_time = datetime.now(UTC) + timedelta(hours=1)
        sensor._ignore_until_datetime = future_time

        attrs = sensor.extra_state_attributes

        assert "ignore_until" in attrs
        assert attrs["ignore_until"] == future_time.isoformat()
        assert attrs["currently_ignoring"] is True


class TestMasterScheduleStatusMonitorBinarySensorCallbacks:
    """Test callback functions."""

    def test_master_schedule_state_changed_to_on(self, sensor_config):
        """Test callback when master schedule changes to ON."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = True
        sensor._master_schedule_on = False
        # Mock the async_write_ha_state method
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = "on"

        event = create_state_changed_event(new_state)
        sensor._master_schedule_state_changed(event)

        assert sensor._master_schedule_on is True
        assert sensor._state is False

    def test_master_schedule_state_changed_to_off(self, sensor_config):
        """Test callback when master schedule changes to OFF."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        sensor._master_schedule_on = True
        # Mock the async_write_ha_state method
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = "off"

        event = create_state_changed_event(new_state)
        sensor._master_schedule_state_changed(event)

        assert sensor._master_schedule_on is False
        assert sensor._state is True

    def test_master_schedule_state_changed_to_unavailable(self, sensor_config):
        """Test callback when master schedule becomes unavailable."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._state = False
        # Mock the async_write_ha_state method
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = STATE_UNAVAILABLE

        event = create_state_changed_event(new_state)
        sensor._master_schedule_state_changed(event)

        assert sensor._master_schedule_on is False
        assert sensor._state is True

    def test_schedule_ignore_until_state_changed(self, sensor_config):
        """Test callback when schedule ignore until datetime changes."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = False
        sensor._state = True
        # Mock the async_write_ha_state method
        sensor.async_write_ha_state = MagicMock()

        future_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        new_state = MagicMock()
        new_state.state = future_time

        event = create_state_changed_event(new_state)
        sensor._schedule_ignore_until_state_changed(event)

        # State should be False (not a problem while ignoring)
        assert sensor._ignore_until_datetime is not None
        assert sensor._state is False

    def test_schedule_ignore_until_state_changed_to_unavailable(self, sensor_config):
        """Test callback when schedule ignore until becomes unavailable."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)
        sensor._master_schedule_on = False
        sensor._ignore_until_datetime = datetime.now(UTC) + timedelta(hours=1)
        # Mock the async_write_ha_state method
        sensor.async_write_ha_state = MagicMock()

        new_state = MagicMock()
        new_state.state = STATE_UNAVAILABLE

        event = create_state_changed_event(new_state)
        sensor._schedule_ignore_until_state_changed(event)

        # Ignore until should be cleared
        assert sensor._ignore_until_datetime is None
        # Now with master schedule OFF and no ignore, should be a problem
        assert sensor._state is True


class TestMasterScheduleStatusMonitorBinarySensorAsyncOperations:
    """Test async operations."""

    @pytest.mark.asyncio
    async def test_find_schedule_ignore_until_entity_found(self, mock_hass):
        """Test finding schedule ignore until entity when it exists."""
        config = MasterScheduleStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry_123",
            location_name="Test Zone",
            irrigation_zone_name="Zone A",
            master_schedule_switch_entity_id="switch.test_zone_schedule",
            zone_device_identifier=("plant_assistant", "test_zone_456"),
        )

        sensor = MasterScheduleStatusMonitorBinarySensor(config)

        # Create mock entity with correct unique_id based on zone_device_identifier
        mock_entity = MagicMock()
        mock_entity.platform = DOMAIN
        mock_entity.domain = "datetime"
        mock_entity.unique_id = (
            f"{DOMAIN}_plant_assistant_test_zone_456_schedule_ignore_until"
        )
        mock_entity.entity_id = "datetime.test_zone_schedule_ignore_until"

        mock_registry = MagicMock()
        mock_registry.entities.values.return_value = [mock_entity]

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_registry,
        ):
            result = await sensor._find_schedule_ignore_until_entity()

        assert result == "datetime.test_zone_schedule_ignore_until"

    @pytest.mark.asyncio
    async def test_find_schedule_ignore_until_entity_not_found(self, mock_hass):
        """Test finding schedule ignore until entity when it doesn't exist."""
        config = MasterScheduleStatusMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry_123",
            location_name="Test Zone",
            irrigation_zone_name="Zone A",
            master_schedule_switch_entity_id="switch.test_zone_schedule",
            zone_device_identifier=("plant_assistant", "test_zone_456"),
        )

        sensor = MasterScheduleStatusMonitorBinarySensor(config)

        mock_registry = MagicMock()
        mock_registry.entities.values.return_value = []

        with patch(
            "custom_components.plant_assistant.binary_sensor.er.async_get",
            return_value=mock_registry,
        ):
            result = await sensor._find_schedule_ignore_until_entity()

        assert result is None

    @pytest.mark.asyncio
    async def test_async_added_to_hass(self, sensor_config):
        """Test async_added_to_hass method."""
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)

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
        sensor = MasterScheduleStatusMonitorBinarySensor(sensor_config)

        # Create mock unsubscribe functions
        mock_unsubscribe_switch = MagicMock()
        mock_unsubscribe_ignore = MagicMock()

        sensor._unsubscribe_switch = mock_unsubscribe_switch
        sensor._unsubscribe_ignore_until = mock_unsubscribe_ignore

        await sensor.async_will_remove_from_hass()

        # Verify cleanup was called
        mock_unsubscribe_switch.assert_called_once()
        mock_unsubscribe_ignore.assert_called_once()
