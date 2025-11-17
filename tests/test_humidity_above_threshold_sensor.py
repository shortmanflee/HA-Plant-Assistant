"""Tests for humidity above threshold weekly duration sensor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant

from custom_components.plant_assistant.const import DOMAIN
from custom_components.plant_assistant.sensor import (
    HumidityAboveThresholdHoursSensor,
)


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
    return hass


@pytest.fixture
def mock_entity_registry():
    """Create a mock entity registry."""
    registry = MagicMock()
    registry.entities = MagicMock()
    registry.entities.values = MagicMock(return_value=[])

    with patch(
        "custom_components.plant_assistant.sensor.er.async_get",
        return_value=registry,
    ):
        yield registry


async def test_humidity_above_threshold_sensor_init(mock_hass):
    """Test initialization of HumidityAboveThresholdHoursSensor."""
    sensor = HumidityAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_device_id="test_location_456",
        location_name="Test Garden",
        humidity_entity_id="sensor.test_humidity",
    )

    assert sensor._attr_name == "Test Garden Humidity Above Threshold Weekly Duration"
    expected = (
        f"{DOMAIN}_test_entry_123_test_garden_humidity_above_threshold_weekly_duration"
    )
    assert sensor._attr_unique_id == expected
    assert sensor._attr_native_unit_of_measurement == "hours"
    assert sensor._attr_icon == "mdi:water-alert"
    assert sensor._humidity_entity_id == "sensor.test_humidity"


async def test_humidity_above_threshold_sensor_available(mock_hass):
    """Test sensor availability based on humidity entity."""
    sensor = HumidityAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        humidity_entity_id="sensor.test_humidity",
    )

    # Test when humidity entity is available
    mock_state = MagicMock()
    mock_state.state = "65.5"
    mock_hass.states.get.return_value = mock_state
    assert sensor.available is True

    # Test when humidity entity is unavailable
    mock_hass.states.get.return_value = None
    assert sensor.available is False


async def test_humidity_above_threshold_no_max_humidity_entity(mock_hass):
    """Test calculation when no maximum humidity entity exists."""
    sensor = HumidityAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        humidity_entity_id="sensor.test_humidity",
    )

    # No max humidity entity in registry
    result = await sensor._calculate_hours_above_threshold()
    assert result is None


async def test_humidity_above_threshold_max_humidity_unavailable(
    mock_hass, mock_entity_registry
):
    """Test calculation when maximum humidity threshold is unavailable."""
    # Set up mock entity registry with max_humidity entity
    mock_max_humidity_entity = MagicMock()
    mock_max_humidity_entity.platform = DOMAIN
    mock_max_humidity_entity.domain = "sensor"
    mock_max_humidity_entity.unique_id = f"{DOMAIN}_test_entry_max_humidity"
    mock_max_humidity_entity.entity_id = "sensor.test_garden_max_humidity"
    mock_entity_registry.entities.values.return_value = [mock_max_humidity_entity]

    sensor = HumidityAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        humidity_entity_id="sensor.test_humidity",
    )

    # Mock max humidity state as unavailable
    mock_max_humidity_state = MagicMock()
    mock_max_humidity_state.state = STATE_UNAVAILABLE
    mock_hass.states.get.return_value = mock_max_humidity_state

    result = await sensor._calculate_hours_above_threshold()
    assert result is None


async def test_humidity_above_threshold_no_statistics(mock_hass, mock_entity_registry):
    """Test calculation when no statistics are available."""
    # Set up mock entity registry with max_humidity entity
    mock_max_humidity_entity = MagicMock()
    mock_max_humidity_entity.platform = DOMAIN
    mock_max_humidity_entity.domain = "sensor"
    mock_max_humidity_entity.unique_id = f"{DOMAIN}_test_entry_max_humidity"
    mock_max_humidity_entity.entity_id = "sensor.test_garden_max_humidity"
    mock_entity_registry.entities.values.return_value = [mock_max_humidity_entity]

    sensor = HumidityAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        humidity_entity_id="sensor.test_humidity",
    )

    # Mock max humidity state
    mock_max_humidity_state = MagicMock()
    mock_max_humidity_state.state = "75.0"
    mock_hass.states.get.return_value = mock_max_humidity_state

    # Mock recorder instance
    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = AsyncMock(return_value={})

    with (
        patch(
            "custom_components.plant_assistant.sensor.get_instance",
            return_value=mock_recorder,
        ),
        patch(
            "custom_components.plant_assistant.sensor.statistics_during_period"
        ) as mock_stats_fn,
    ):
        mock_stats_fn.return_value = {}
        result = await sensor._calculate_hours_above_threshold()
        assert result is None


async def test_humidity_above_threshold_calculation(mock_hass, mock_entity_registry):
    """Test calculation of hours above threshold."""
    # Set up mock entity registry with max_humidity entity
    mock_max_humidity_entity = MagicMock()
    mock_max_humidity_entity.platform = DOMAIN
    mock_max_humidity_entity.domain = "sensor"
    mock_max_humidity_entity.unique_id = f"{DOMAIN}_test_entry_max_humidity"
    mock_max_humidity_entity.entity_id = "sensor.test_garden_max_humidity"
    mock_entity_registry.entities.values.return_value = [mock_max_humidity_entity]

    sensor = HumidityAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        humidity_entity_id="sensor.test_humidity",
    )

    # Mock max humidity state (threshold is 75%)
    mock_max_humidity_state = MagicMock()
    mock_max_humidity_state.state = "75.0"
    mock_hass.states.get.return_value = mock_max_humidity_state

    # Mock statistics data
    mock_stats = {
        "sensor.test_humidity": [
            {"mean": 78.0},  # Above threshold
            {"mean": 76.5},  # Above threshold
            {"mean": 70.0},  # Below threshold
            {"mean": 82.0},  # Above threshold
            {"mean": 60.0},  # Below threshold
        ]
    }

    # Mock recorder instance
    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = AsyncMock(return_value=mock_stats)

    # Patch both get_instance and statistics_during_period
    with (
        patch(
            "custom_components.plant_assistant.sensor.get_instance",
            return_value=mock_recorder,
        ),
        patch(
            "custom_components.plant_assistant.sensor.statistics_during_period"
        ) as mock_stats_fn,
    ):
        mock_stats_fn.return_value = mock_stats
        result = await sensor._calculate_hours_above_threshold()
        # Should count 3 hours above threshold (78.0, 76.5, 82.0)
        assert result == 3


async def test_humidity_state_changed_callback(mock_hass):
    """Test humidity state change callback."""
    sensor = HumidityAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        humidity_entity_id="sensor.test_humidity",
    )

    # Mock async_create_task
    mock_task = MagicMock()
    mock_hass.async_create_task.return_value = mock_task

    # Trigger state change
    event = create_state_changed_event(MagicMock())
    sensor._humidity_state_changed(event)

    # Verify task was created
    mock_hass.async_create_task.assert_called_once()


async def test_native_value_handling(mock_hass):
    """Test native_value property with different states."""
    sensor = HumidityAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        humidity_entity_id="sensor.test_humidity",
    )

    # Test with valid state
    sensor._state = 10
    assert sensor.native_value == 10

    # Test with unavailable state
    sensor._state = STATE_UNAVAILABLE
    assert sensor.native_value is None

    # Test with unknown state
    sensor._state = STATE_UNKNOWN
    assert sensor.native_value is None

    # Test with None state
    sensor._state = None
    assert sensor.native_value is None
