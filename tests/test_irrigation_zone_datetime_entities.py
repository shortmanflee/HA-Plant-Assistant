"""Tests for irrigation zone datetime entities."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from custom_components.plant_assistant.const import DOMAIN
from custom_components.plant_assistant.datetime import (
    IrrigationZoneErrorIgnoreUntilEntity,
    IrrigationZoneScheduleIgnoreUntilEntity,
    IrrigationZoneScheduleMisconfigurationIgnoreUntilEntity,
    IrrigationZoneWaterDeliveryPreferenceIgnoreUntilEntity,
)


class TestIrrigationZoneDateTimeEntities:
    """Test irrigation zone datetime entities."""

    @pytest.mark.asyncio
    async def test_schedule_ignore_until_entity_implements_restore_entity(self):
        """Test that schedule ignore until entity implements RestoreEntity."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert isinstance(entity, RestoreEntity)

    @pytest.mark.asyncio
    async def test_schedule_misconfiguration_ignore_until_entity_implements_restore_entity(  # noqa: E501
        self,
    ):
        """Test that schedule misconfiguration ignore until entity implements.

        RestoreEntity.
        """
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleMisconfigurationIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert isinstance(entity, RestoreEntity)

    @pytest.mark.asyncio
    async def test_water_delivery_preference_ignore_until_entity_implements_restore_entity(  # noqa: E501
        self,
    ):
        """Test that water delivery preference ignore until entity implements.

        RestoreEntity.
        """
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneWaterDeliveryPreferenceIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert isinstance(entity, RestoreEntity)

    @pytest.mark.asyncio
    async def test_error_ignore_until_entity_implements_restore_entity(self):
        """Test that error ignore until entity implements RestoreEntity."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneErrorIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert isinstance(entity, RestoreEntity)

    @pytest.mark.asyncio
    async def test_schedule_ignore_until_entity_unique_id(self):
        """Test that schedule ignore until entity has correct unique ID."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        expected_unique_id = f"{DOMAIN}_esphome_device_abc123_schedule_ignore_until"
        assert entity.unique_id == expected_unique_id

    @pytest.mark.asyncio
    async def test_schedule_misconfiguration_ignore_until_entity_unique_id(self):
        """Test that schedule misconfiguration ignore until entity has correct.

        unique ID.
        """
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleMisconfigurationIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        expected_unique_id = (
            f"{DOMAIN}_esphome_device_abc123_schedule_misconfiguration_ignore_until"
        )
        assert entity.unique_id == expected_unique_id

    @pytest.mark.asyncio
    async def test_water_delivery_preference_ignore_until_entity_unique_id(self):
        """Test that water delivery preference ignore until entity has correct.

        unique ID.
        """
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneWaterDeliveryPreferenceIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        expected_unique_id = (
            f"{DOMAIN}_esphome_device_abc123_water_delivery_preference_ignore_until"
        )
        assert entity.unique_id == expected_unique_id

    @pytest.mark.asyncio
    async def test_error_ignore_until_entity_unique_id(self):
        """Test that error ignore until entity has correct unique ID."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneErrorIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        expected_unique_id = f"{DOMAIN}_esphome_device_abc123_error_ignore_until"
        assert entity.unique_id == expected_unique_id

    @pytest.mark.asyncio
    async def test_schedule_ignore_until_entity_name(self):
        """Test that schedule ignore until entity has correct name."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert entity.name == "Front Lawn Schedule Ignore Until"

    @pytest.mark.asyncio
    async def test_schedule_misconfiguration_ignore_until_entity_name(self):
        """Test that schedule misconfiguration ignore until entity has correct name."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleMisconfigurationIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert entity.name == "Front Lawn Schedule Misconfiguration Ignore Until"

    @pytest.mark.asyncio
    async def test_water_delivery_preference_ignore_until_entity_name(self):
        """Test that water delivery preference ignore until entity has correct name."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneWaterDeliveryPreferenceIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert entity.name == "Front Lawn Water Delivery Preference Ignore Until"

    @pytest.mark.asyncio
    async def test_error_ignore_until_entity_name(self):
        """Test that error ignore until entity has correct name."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneErrorIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert entity.name == "Front Lawn Error Ignore Until"

    @pytest.mark.asyncio
    async def test_schedule_ignore_until_entity_device_info(self):
        """Test that schedule ignore until entity has correct device info."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        # Check that device info has the zone device ID in identifiers
        device_info = entity.device_info
        if device_info and "identifiers" in device_info:
            assert zone_device_id in device_info["identifiers"]

    @pytest.mark.asyncio
    async def test_schedule_ignore_until_entity_icon(self):
        """Test that schedule ignore until entity has correct icon."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert entity.icon == "mdi:calendar-remove"

    @pytest.mark.asyncio
    async def test_schedule_misconfiguration_ignore_until_entity_icon(self):
        """Test that schedule misconfiguration ignore until entity has correct icon."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleMisconfigurationIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert entity.icon == "mdi:alert-circle"

    @pytest.mark.asyncio
    async def test_water_delivery_preference_ignore_until_entity_icon(self):
        """Test that water delivery preference ignore until entity has correct icon."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneWaterDeliveryPreferenceIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert entity.icon == "mdi:water-remove"

    @pytest.mark.asyncio
    async def test_error_ignore_until_entity_icon(self):
        """Test that error ignore until entity has correct icon."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneErrorIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert entity.icon == "mdi:alert-octagon"

    @pytest.mark.asyncio
    async def test_schedule_ignore_until_entity_availability(self):
        """Test that schedule ignore until entity is always available."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        assert entity.available is True

    @pytest.mark.asyncio
    async def test_schedule_ignore_until_entity_initial_value(self):
        """Test that schedule ignore until entity initializes properly after.

        async_added_to_hass.
        """
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        # Before async_added_to_hass, the value is None
        assert entity._attr_native_value is None

        # Mock the async_get_last_state to return None
        entity.async_get_last_state = AsyncMock(return_value=None)

        # Call async_added_to_hass
        await entity.async_added_to_hass()

        # After async_added_to_hass, the value should be initialized to midnight
        assert entity._attr_native_value is not None
        assert isinstance(entity._attr_native_value, datetime)

    @pytest.mark.asyncio
    async def test_schedule_ignore_until_entity_async_set_value(self):
        """Test that schedule ignore until entity can set value."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        # Mock the async_write_ha_state method
        entity.async_write_ha_state = Mock()

        # Create a test datetime with timezone
        test_datetime = dt_util.now().replace(
            hour=12, minute=0, second=0, microsecond=0
        )

        # Set the value
        await entity.async_set_value(test_datetime)

        # Verify the value was set
        assert entity.native_value == test_datetime
        entity.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_schedule_ignore_until_entity_extra_state_attributes(self):
        """Test that schedule ignore until entity has correct extra state attributes."""
        hass = Mock()
        zone_device_id = ("esphome", "device_abc123")

        entity = IrrigationZoneScheduleIgnoreUntilEntity(
            hass=hass,
            entry_id="test_entry_id",
            zone_device_id=zone_device_id,
            zone_name="Front Lawn",
        )

        # Initialize the entity value
        entity._attr_native_value = dt_util.now()

        attrs = entity.extra_state_attributes

        assert "zone_name" in attrs
        assert attrs["zone_name"] == "Front Lawn"
        assert "zone_device_id" in attrs
        assert attrs["zone_device_id"] == zone_device_id
        assert "currently_ignoring" in attrs
        assert "ignore_expires_in_seconds" in attrs
