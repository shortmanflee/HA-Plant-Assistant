"""Tests for temperature above threshold weekly duration sensor."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.plant_assistant.const import DOMAIN
from custom_components.plant_assistant.sensor import (
    TemperatureAboveThresholdHoursSensor,
)

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
        "custom_components.plant_assistant.sensor.er.async_get",
        return_value=registry,
    ):
        yield registry


async def test_temperature_above_threshold_sensor_init(mock_hass):
    """Test initialization of TemperatureAboveThresholdHoursSensor."""
    sensor = TemperatureAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry_123",
        location_device_id="test_location_456",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    assert (
        sensor._attr_name == "Test Garden Temperature Above Threshold Weekly Duration"
    )
    expected = (
        f"{DOMAIN}_test_entry_123_test_garden_"
        "temperature_above_threshold_weekly_duration"
    )
    assert sensor._attr_unique_id == expected
    assert sensor._attr_native_unit_of_measurement == "hours"
    assert sensor._attr_icon == "mdi:thermometer-alert"
    assert sensor._temperature_entity_id == "sensor.test_temperature"


async def test_temperature_above_threshold_sensor_available(mock_hass):
    """Test sensor availability based on temperature entity."""
    sensor = TemperatureAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Test when temperature entity is available
    mock_state = MagicMock()
    mock_state.state = "20.5"
    mock_hass.states.get.return_value = mock_state
    assert sensor.available is True

    # Test when temperature entity is unavailable
    mock_hass.states.get.return_value = None
    assert sensor.available is False


async def test_temperature_above_threshold_no_max_temp_entity(mock_hass):
    """Test calculation when no maximum temperature entity exists."""
    sensor = TemperatureAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # No max temperature entity in registry
    result = await sensor._calculate_hours_above_threshold()
    assert result is None


async def test_temperature_above_threshold_max_temp_unavailable(
    mock_hass, mock_entity_registry
):
    """Test calculation when maximum temperature threshold is unavailable."""
    # Set up mock entity registry with max_temperature entity
    mock_max_temp_entity = MagicMock()
    mock_max_temp_entity.platform = DOMAIN
    mock_max_temp_entity.domain = "sensor"
    mock_max_temp_entity.unique_id = f"{DOMAIN}_test_entry_max_temperature"
    mock_max_temp_entity.entity_id = "sensor.test_garden_max_temperature"
    mock_entity_registry.entities.values.return_value = [mock_max_temp_entity]

    sensor = TemperatureAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Mock max temp state as unavailable
    mock_max_temp_state = MagicMock()
    mock_max_temp_state.state = STATE_UNAVAILABLE
    mock_hass.states.get.return_value = mock_max_temp_state

    result = await sensor._calculate_hours_above_threshold()
    assert result is None


async def test_temperature_above_threshold_no_statistics(
    mock_hass, mock_entity_registry
):
    """Test calculation when no statistics are available."""
    # Set up mock entity registry with max_temperature entity
    mock_max_temp_entity = MagicMock()
    mock_max_temp_entity.platform = DOMAIN
    mock_max_temp_entity.domain = "sensor"
    mock_max_temp_entity.unique_id = f"{DOMAIN}_test_entry_max_temperature"
    mock_max_temp_entity.entity_id = "sensor.test_garden_max_temperature"
    mock_entity_registry.entities.values.return_value = [mock_max_temp_entity]

    sensor = TemperatureAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Mock max temp state
    mock_max_temp_state = MagicMock()
    mock_max_temp_state.state = "25.0"
    mock_hass.states.get.return_value = mock_max_temp_state

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


async def test_temperature_above_threshold_calculation(mock_hass, mock_entity_registry):
    """Test calculation of hours above threshold."""
    # Set up mock entity registry with max_temperature entity
    mock_max_temp_entity = MagicMock()
    mock_max_temp_entity.platform = DOMAIN
    mock_max_temp_entity.domain = "sensor"
    mock_max_temp_entity.unique_id = f"{DOMAIN}_test_entry_max_temperature"
    mock_max_temp_entity.entity_id = "sensor.test_garden_max_temperature"
    mock_entity_registry.entities.values.return_value = [mock_max_temp_entity]

    sensor = TemperatureAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Mock max temp state (threshold is 25°C)
    mock_max_temp_state = MagicMock()
    mock_max_temp_state.state = "25.0"
    mock_hass.states.get.return_value = mock_max_temp_state

    # Mock statistics data
    mock_stats = {
        "sensor.test_temperature": [
            {"mean": 26.0},  # Above threshold
            {"mean": 24.5},  # Below threshold
            {"mean": 28.0},  # Above threshold
            {"mean": 20.0},  # Below threshold
            {"mean": 30.0},  # Above threshold
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
        # Should count 3 hours above threshold (26.0, 28.0, 30.0)
        assert result == 3


async def test_temperature_state_changed_callback(mock_hass, mock_entity_registry):
    """Test temperature state change callback."""
    # Set up mock entity registry with max_temperature entity
    mock_max_temp_entity = MagicMock()
    mock_max_temp_entity.platform = DOMAIN
    mock_max_temp_entity.domain = "sensor"
    mock_max_temp_entity.unique_id = f"{DOMAIN}_test_entry_max_temperature"
    mock_max_temp_entity.entity_id = "sensor.test_garden_max_temperature"
    mock_entity_registry.entities.values.return_value = [mock_max_temp_entity]

    sensor = TemperatureAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
    )

    # Mock async_write_ha_state
    sensor.async_write_ha_state = MagicMock()

    # Mock max temp state (threshold is 25°C)
    mock_max_temp_state = MagicMock()
    mock_max_temp_state.state = "25.0"
    mock_hass.states.get.return_value = mock_max_temp_state

    # Mock statistics data with 2 hours above threshold
    mock_stats = {
        "sensor.test_temperature": [
            {"mean": 26.0},  # Above threshold
            {"mean": 24.0},  # Below threshold
            {"mean": 27.5},  # Above threshold
        ]
    }

    # Mock recorder instance
    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = AsyncMock(return_value=mock_stats)

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

        # Trigger state change with realistic temperature state
        mock_temp_state = MagicMock()
        mock_temp_state.state = "26.5"
        event = create_state_changed_event(mock_temp_state)
        sensor._temperature_state_changed(event)  # type: ignore[arg-type]

        # Verify task was created
        mock_hass.async_create_task.assert_called_once()

        # Execute the task that was created to verify state update
        task_call = mock_hass.async_create_task.call_args[0][0]
        await task_call

        # Verify state was updated
        assert sensor._state == 2
        assert sensor.native_value == 2

        # Verify attributes were set
        assert sensor._attributes["source_entity"] == "sensor.test_temperature"
        assert sensor._attributes["period_days"] == 7

        # Verify async_write_ha_state was called
        sensor.async_write_ha_state.assert_called_once()


async def test_native_value_handling(mock_hass):
    """Test native_value property with different states."""
    sensor = TemperatureAboveThresholdHoursSensor(
        hass=mock_hass,
        entry_id="test_entry",
        location_device_id="test_location",
        location_name="Test Garden",
        temperature_entity_id="sensor.test_temperature",
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
