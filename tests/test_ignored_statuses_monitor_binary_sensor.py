"""Tests for Ignored Statuses Monitor binary sensor."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.binary_sensor import (
    IgnoredStatusesMonitorBinarySensor,
    IgnoredStatusesMonitorConfig,
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
    return IgnoredStatusesMonitorConfig(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_name="Test Garden",
        irrigation_zone_name="Zone A",
        location_device_id="test_location_456",
    )


class TestIgnoredStatusesMonitorBinarySensorInit:
    """Test initialization of IgnoredStatusesMonitorBinarySensor."""

    def test_sensor_init_with_valid_params(self, sensor_config):
        """Test initialization with valid parameters."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)

        assert sensor._attr_name == "Test Garden Ignored Statuses"
        expected_unique_id = f"{DOMAIN}_test_entry_123_test_garden_ignored_statuses"
        assert sensor._attr_unique_id == expected_unique_id
        assert sensor.location_name == "Test Garden"
        assert sensor.irrigation_zone_name == "Zone A"
        assert sensor._ignored_count == 0
        assert sensor._state is None

    def test_sensor_device_class(self, mock_hass):
        """Test that sensor has correct device class."""
        config = IgnoredStatusesMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            location_device_id="test_location",
        )
        sensor = IgnoredStatusesMonitorBinarySensor(config)

        # BinarySensorDeviceClass.PROBLEM has a value of 'problem'
        assert sensor._attr_device_class == "problem"

    def test_sensor_icon_when_no_ignored(self, sensor_config):
        """Test that sensor has correct icon when no statuses are ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)

        sensor._state = False
        assert sensor.icon == "mdi:pause-circle"

    def test_sensor_icon_when_ignored(self, sensor_config):
        """Test that sensor has correct icon when statuses are ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)

        sensor._state = True
        assert sensor.icon == "mdi:pause-circle-outline"

    def test_sensor_is_on_false(self, sensor_config):
        """Test is_on property when no statuses are ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._state = False

        assert sensor.is_on is False

    def test_sensor_is_on_true(self, sensor_config):
        """Test is_on property when statuses are ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._state = True

        assert sensor.is_on is True

    def test_sensor_is_on_none(self, sensor_config):
        """Test is_on property when state is None."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._state = None

        assert sensor.is_on is None


class TestIgnoredStatusesMonitorBinarySensorAttributes:
    """Test extra state attributes of IgnoredStatusesMonitorBinarySensor."""

    def test_extra_state_attributes_no_ignored(self, sensor_config):
        """Test attributes when no statuses are ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._ignored_count = 0
        sensor._state = False

        attrs = sensor.extra_state_attributes

        assert attrs["message"] == "0 Ignored"
        assert attrs["master_tag"] == "test_garden"
        assert attrs["ignored_count"] == 0

    def test_extra_state_attributes_one_ignored(self, sensor_config):
        """Test attributes when one status is ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._ignored_count = 1
        sensor._state = True

        attrs = sensor.extra_state_attributes

        assert attrs["message"] == "1 Ignored"
        assert attrs["master_tag"] == "test_garden"
        assert attrs["ignored_count"] == 1

    def test_extra_state_attributes_multiple_ignored(self, sensor_config):
        """Test attributes when multiple statuses are ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._ignored_count = 3
        sensor._state = True

        attrs = sensor.extra_state_attributes

        assert attrs["message"] == "3 Ignored"
        assert attrs["master_tag"] == "test_garden"
        assert attrs["ignored_count"] == 3

    def test_extra_state_attributes_tags(self, sensor_config):
        """Test that tags are correctly formatted."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)

        attrs = sensor.extra_state_attributes

        assert attrs["master_tag"] == "test_garden"


class TestIgnoredStatusesMonitorBinarySensorCountIgnored:
    """Test counting of ignored statuses."""

    def test_count_ignored_statuses_no_entities(self, sensor_config):
        """Test counting when no ignore_until entities exist."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._ignore_until_entity_ids = []

        count = sensor._count_ignored_statuses()

        assert count == 0

    def test_count_ignored_statuses_none_ignored(self, mock_hass, sensor_config):
        """Test counting when no statuses are currently ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._ignore_until_entity_ids = [
            "datetime.test_garden_soil_moisture_ignore_until",
            "datetime.test_garden_temperature_ignore_until",
        ]

        # Past datetime - not ignored
        past_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        mock_hass.states.get = MagicMock(
            side_effect=lambda _: MagicMock(state=past_time)
        )

        with patch(
            "custom_components.plant_assistant.binary_sensor.dt_util.now",
            return_value=datetime.now(UTC),
        ):
            count = sensor._count_ignored_statuses()

        assert count == 0

    def test_count_ignored_statuses_some_ignored(self, mock_hass, sensor_config):
        """Test counting when some statuses are currently ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._ignore_until_entity_ids = [
            "datetime.test_garden_soil_moisture_ignore_until",
            "datetime.test_garden_temperature_ignore_until",
        ]

        now = datetime.now(UTC)
        future_time = (now + timedelta(hours=1)).isoformat()
        past_time = (now - timedelta(hours=1)).isoformat()

        # Mock states: first entity ignored (future), second not ignored (past)
        states = [
            MagicMock(state=future_time),
            MagicMock(state=past_time),
        ]
        mock_hass.states.get = MagicMock(
            side_effect=lambda _: states.pop(0)
            if states
            else MagicMock(state=past_time)
        )

        with (
            patch(
                "custom_components.plant_assistant.binary_sensor.dt_util.now",
                return_value=now,
            ),
            patch(
                "custom_components.plant_assistant.binary_sensor.dt_util.parse_datetime",
                side_effect=lambda x: datetime.fromisoformat(x),
            ),
        ):
            # Reset the side_effect since we consumed it
            mock_hass.states.get = MagicMock(
                side_effect=[
                    MagicMock(state=future_time),
                    MagicMock(state=past_time),
                ]
            )
            count = sensor._count_ignored_statuses()

        assert count == 1

    def test_count_ignored_statuses_all_ignored(self, mock_hass, sensor_config):
        """Test counting when all statuses are currently ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._ignore_until_entity_ids = [
            "datetime.test_garden_soil_moisture_ignore_until",
            "datetime.test_garden_temperature_ignore_until",
        ]

        now = datetime.now(UTC)
        future_time = (now + timedelta(hours=1)).isoformat()

        # Mock states: all entities ignored (future)
        mock_hass.states.get = MagicMock(return_value=MagicMock(state=future_time))

        with (
            patch(
                "custom_components.plant_assistant.binary_sensor.dt_util.now",
                return_value=now,
            ),
            patch(
                "custom_components.plant_assistant.binary_sensor.dt_util.parse_datetime",
                side_effect=lambda x: datetime.fromisoformat(x),
            ),
        ):
            count = sensor._count_ignored_statuses()

        assert count == 2


class TestIgnoredStatusesMonitorBinarySensorUpdateState:
    """Test state updates."""

    def test_update_state_no_ignored(self, sensor_config):
        """Test state update when no statuses are ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._ignore_until_entity_ids = []

        sensor._update_state()

        assert sensor._state is False
        assert sensor._ignored_count == 0

    def test_update_state_with_ignored(self, mock_hass, sensor_config):
        """Test state update when statuses are ignored."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)
        sensor._ignore_until_entity_ids = [
            "datetime.test_garden_soil_moisture_ignore_until",
        ]

        now = datetime.now(UTC)
        future_time = (now + timedelta(hours=1)).isoformat()

        mock_hass.states.get = MagicMock(return_value=MagicMock(state=future_time))

        with (
            patch(
                "custom_components.plant_assistant.binary_sensor.dt_util.now",
                return_value=now,
            ),
            patch(
                "custom_components.plant_assistant.binary_sensor.dt_util.parse_datetime",
                side_effect=lambda x: datetime.fromisoformat(x),
            ),
        ):
            sensor._update_state()

        assert sensor._state is True
        assert sensor._ignored_count == 1


class TestIgnoredStatusesMonitorBinarySensorDeviceInfo:
    """Test device info property."""

    def test_device_info_with_device_id(self, sensor_config):
        """Test device info when device_id is provided."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)

        device_info = sensor.device_info

        assert device_info is not None
        assert (DOMAIN, "test_location_456") in device_info.get("identifiers", set())

    def test_device_info_without_device_id(self, mock_hass):
        """Test device info when device_id is not provided."""
        config = IgnoredStatusesMonitorConfig(
            hass=mock_hass,
            entry_id="test_entry",
            location_name="Test Garden",
            irrigation_zone_name="Zone A",
            location_device_id=None,
        )
        sensor = IgnoredStatusesMonitorBinarySensor(config)

        device_info = sensor.device_info

        assert device_info is None


class TestIgnoredStatusesMonitorBinarySensorAvailability:
    """Test availability property."""

    def test_sensor_always_available(self, sensor_config):
        """Test that sensor is always available."""
        sensor = IgnoredStatusesMonitorBinarySensor(sensor_config)

        assert sensor.available is True
