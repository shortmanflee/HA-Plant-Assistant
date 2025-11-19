"""
Binary sensors for the Plant Assistant integration.

This module provides binary sensors that monitor plant health conditions,
such as soil moisture levels falling below configured thresholds.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .sensor import _resolve_entity_id, find_device_entities_by_pattern

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

# Battery level threshold (percentage) for low battery alert
BATTERY_LEVEL_THRESHOLD = 10

# Error count threshold for problem status
ERROR_COUNT_THRESHOLD = 3

# Time constants
SECONDS_IN_24_HOURS = 86400  # 24 hours in seconds
WATERING_RECENT_CHANGE_THRESHOLD = (
    10.0  # Percent change threshold for watering detection
)


@dataclass
class SoilMoistureLowMonitorConfig:
    """Configuration for SoilMoistureLowMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_moisture_entity_id: str
    location_device_id: str | None = None
    soil_moisture_entity_unique_id: str | None = None


@dataclass
class SoilMoistureHighMonitorConfig:
    """Configuration for SoilMoistureHighMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_moisture_entity_id: str
    location_device_id: str | None = None
    soil_moisture_entity_unique_id: str | None = None
    has_esphome_device: bool = False


@dataclass
class SoilMoistureHighOverrideMonitorConfig:
    """Configuration for SoilMoistureHighOverrideMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_moisture_entity_id: str
    location_device_id: str | None = None


@dataclass
class SoilMoistureWaterSoonMonitorConfig:
    """Configuration for SoilMoistureWaterSoonMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_moisture_entity_id: str
    location_device_id: str | None = None


@dataclass
class SoilConductivityLowMonitorConfig:
    """Configuration for SoilConductivityLowMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_conductivity_entity_id: str
    soil_moisture_entity_id: str
    location_device_id: str | None = None


@dataclass
class SoilConductivityHighMonitorConfig:
    """Configuration for SoilConductivityHighMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_conductivity_entity_id: str
    location_device_id: str | None = None
    has_esphome_device: bool = False


@dataclass
class SoilConductivityHighOverrideMonitorConfig:
    """Configuration for SoilConductivityHighOverrideMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_conductivity_entity_id: str
    location_device_id: str | None = None


@dataclass
class SoilConductivityStatusMonitorConfig:
    """Configuration for SoilConductivityStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_conductivity_entity_id: str
    soil_conductivity_entity_unique_id: str | None = None
    location_device_id: str | None = None
    has_esphome_device: bool = False


@dataclass
class SoilMoistureStatusMonitorConfig:
    """Configuration for SoilMoistureStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_moisture_entity_id: str
    soil_moisture_entity_unique_id: str | None = None
    location_device_id: str | None = None
    has_esphome_device: bool = False


@dataclass
class TemperatureStatusMonitorConfig:
    """Configuration for TemperatureStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    temperature_entity_id: str
    temperature_entity_unique_id: str | None = None
    location_device_id: str | None = None


@dataclass
class HumidityStatusMonitorConfig:
    """Configuration for HumidityStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    humidity_entity_id: str
    humidity_entity_unique_id: str | None = None
    location_device_id: str | None = None


@dataclass
class LinkMonitorConfig:
    """Configuration for LinkMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    monitoring_device_id: str
    location_device_id: str | None = None


@dataclass
class BatteryLevelStatusMonitorConfig:
    """Configuration for BatteryLevelStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    battery_entity_id: str
    battery_entity_unique_id: str | None = None
    location_device_id: str | None = None


@dataclass
class DailyLightIntegralStatusMonitorConfig:
    """Configuration for DailyLightIntegralStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    location_device_id: str | None = None


@dataclass
class PlantCountStatusMonitorConfig:
    """Configuration for PlantCountStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    plant_count: int
    location_device_id: str | None = None


@dataclass
class IgnoredStatusesMonitorConfig:
    """Configuration for IgnoredStatusesMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    location_device_id: str | None = None


@dataclass
class StatusMonitorConfig:
    """Configuration for StatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    location_device_id: str | None = None


@dataclass
class MasterScheduleStatusMonitorConfig:
    """Configuration for MasterScheduleStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    master_schedule_switch_entity_id: str
    zone_device_identifier: tuple[str, str]
    master_schedule_switch_unique_id: str | None = None


@dataclass
class ScheduleMisconfigurationStatusMonitorConfig:
    """Configuration for ScheduleMisconfigurationStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    master_schedule_switch_entity_id: str
    sunrise_switch_entity_id: str
    afternoon_switch_entity_id: str
    sunset_switch_entity_id: str
    zone_device_identifier: tuple[str, str]
    master_schedule_switch_unique_id: str | None = None
    sunrise_switch_unique_id: str | None = None
    afternoon_switch_unique_id: str | None = None
    sunset_switch_unique_id: str | None = None


@dataclass
class WaterDeliveryPreferenceStatusMonitorConfig:
    """Configuration for WaterDeliveryPreferenceStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    master_schedule_switch_entity_id: str
    allow_rain_water_delivery_switch_entity_id: str
    allow_water_main_delivery_switch_entity_id: str
    zone_device_identifier: tuple[str, str]
    master_schedule_switch_unique_id: str | None = None
    allow_rain_water_delivery_switch_unique_id: str | None = None
    allow_water_main_delivery_switch_unique_id: str | None = None


@dataclass
class ErrorStatusMonitorConfig:
    """Configuration for ErrorStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    error_count_entity_id: str
    zone_device_identifier: tuple[str, str]
    error_count_entity_unique_id: str | None = None


@dataclass
class ESPHomeRunningStatusMonitorConfig:
    """Configuration for ESPHomeRunningStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    monitoring_device_id: str
    zone_device_identifier: tuple[str, str]


@dataclass
class IrrigationZoneStatusMonitorConfig:
    """Configuration for IrrigationZoneStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    zone_id: str
    zone_device_identifier: tuple[str, str]


@dataclass
class RecentlyWateredBinarySensorConfig:
    """Configuration for RecentlyWateredBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_device_id: str
    location_name: str
    recent_change_entity_id: str


class PlantCountStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors plant count status for a location.

    This sensor turns ON (problem detected) when the plant count is 0,
    indicating that no plants are assigned to the location's slots.
    """

    def __init__(self, config: PlantCountStatusMonitorConfig) -> None:
        """
        Initialize the Plant Count Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self._plant_count = config.plant_count

        # Set entity attributes
        self._attr_name = f"{self.location_name} Plant Count Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_plant_count_status_monitor"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._unsubscribe: Any = None

    def _update_state(self) -> None:
        """Update binary sensor state based on plant count."""
        # Check if we're in an ignore period
        is_ignoring = self._is_currently_ignoring()

        # Binary sensor is ON (problem) when plant count is 0 and NOT ignoring
        self._state = self._plant_count == 0 and not is_ignoring

    def _is_currently_ignoring(self) -> bool:
        """
        Check if plant count status is currently being ignored.

        Check if plant count status is currently being ignored until a
        certain datetime.
        """
        # Try to get the plant count ignore until entity state
        ignore_until_entity_id = (
            f"datetime.{self.location_name.lower().replace(' ', '_')}"
            f"_plant_count_ignore_until"
        )

        state = self.hass.states.get(ignore_until_entity_id)
        if state and state.state not in ("unknown", "unavailable", None):
            try:
                # Parse the ignore until datetime
                ignore_until = dt_util.parse_datetime(state.state)
                if ignore_until:
                    now = dt_util.now()
                    # Check if current time is before the ignore until time
                    return now < ignore_until
            except (ValueError, TypeError):
                # If we can't parse the datetime, don't ignore
                pass

        return False

    @property
    def is_on(self) -> bool | None:
        """Return True if plant count is 0 (problem detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:flower-tulip-outline"
        return "mdi:flower-tulip"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs: dict[str, Any] = {
            "type": "Warning",
            "message": "No Plants Assigned",
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "plant_count": self._plant_count,
            "currently_ignoring": self._is_currently_ignoring(),
        }
        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored plant count status for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def async_added_to_hass(self) -> None:
        """Add entity to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IgnoredStatusesMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors if any status sensors are being ignored.

    This sensor turns ON (problem detected) when one or more of the other
    Status binary sensors are currently being ignored (within their
    ignore_until period). The Message attribute shows "X Ignored" where X
    is the count of ignored statuses.
    """

    def __init__(self, config: IgnoredStatusesMonitorConfig) -> None:
        """
        Initialize the Ignored Statuses Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name

        # Set entity attributes
        self._attr_name = f"{self.location_name} Ignored Statuses"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_ignored_statuses"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._ignored_count: int = 0
        # List of ignore_until entity IDs and unique_ids to track
        self._ignore_until_entity_ids: list[str] = []
        self._ignore_until_entity_unique_ids: dict[
            str, str
        ] = {}  # entity_id -> unique_id mapping
        self._unsubscribe_handlers: list[Any] = []

    def _get_entity_unique_id(self, entity_id: str) -> str | None:
        """Get unique_id for an entity_id."""
        try:
            entity_reg = er.async_get(self.hass)
            if entity_reg is not None:
                entity_entry = entity_reg.async_get(entity_id)
                if entity_entry and entity_entry.unique_id:
                    return entity_entry.unique_id
        except (TypeError, AttributeError, ValueError):
            pass
        return None

    async def _find_ignore_until_entities(self) -> list[str]:
        """
        Find all ignore_until datetime entities for this location.

        Returns a list of entity_ids for all ignore_until entities.
        """
        ignore_until_entities: list[str] = []
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    ignore_until_entities.append(entity.entity_id)
                    # Store unique_id mapping for resilient tracking
                    self._ignore_until_entity_unique_ids[entity.entity_id] = (
                        entity.unique_id
                    )
                    _LOGGER.debug(
                        "Found ignore_until datetime entity for %s: %s (unique_id: %s)",
                        self.location_name,
                        entity.entity_id,
                        entity.unique_id,
                    )

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding ignore_until entities: %s", exc)

        return ignore_until_entities

    def _count_ignored_statuses(self) -> int:
        """
        Count how many status sensors are currently being ignored.

        Returns the count of status sensors within their ignore_until period.
        """
        ignored_count = 0
        now = dt_util.now()

        for entity_id in self._ignore_until_entity_ids:
            state = self.hass.states.get(entity_id)
            if state and state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
                "unknown",
            ):
                try:
                    ignore_until = dt_util.parse_datetime(state.state)
                    if ignore_until:
                        # Ensure timezone info
                        if ignore_until.tzinfo is None:
                            ignore_until = ignore_until.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        # Check if current time is before the ignore until time
                        if now < ignore_until:
                            ignored_count += 1
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing ignore_until datetime for %s: %s",
                        entity_id,
                        exc,
                    )

        return ignored_count

    def _update_state(self) -> None:
        """Update binary sensor state based on count of ignored statuses."""
        self._ignored_count = self._count_ignored_statuses()
        # Binary sensor is ON (problem) when one or more statuses are ignored
        self._state = self._ignored_count > 0

    @callback
    def _ignore_until_state_changed(self, _event: Event[EventStateChangedData]) -> None:
        """Handle ignore_until datetime changes."""
        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if any status sensors are being ignored."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:pause-circle-outline"
        return "mdi:pause-circle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs: dict[str, Any] = {
            "message": f"{self._ignored_count} Ignored",
            "master_tag": self.location_name.lower().replace(" ", "_"),
            "ignored_count": self._ignored_count,
        }
        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                self._ignored_count = last_state.attributes.get("ignored_count", 0)
                _LOGGER.info(
                    "Restored ignored statuses monitor for %s: %s (%d ignored)",
                    self.location_name,
                    self._state,
                    self._ignored_count,
                )
            except (AttributeError, ValueError):
                pass

    async def async_added_to_hass(self) -> None:
        """Add entity to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Find all ignore_until entities
        self._ignore_until_entity_ids = await self._find_ignore_until_entities()

        # Resolve all entity IDs with fallback to unique_id for resilience
        resolved_entity_ids = []
        for entity_id in self._ignore_until_entity_ids:
            unique_id = self._ignore_until_entity_unique_ids.get(entity_id)
            resolved_entity_id = _resolve_entity_id(self.hass, entity_id, unique_id)
            if resolved_entity_id:
                if resolved_entity_id != entity_id:
                    _LOGGER.debug(
                        "Resolved ignore_until entity ID: %s -> %s",
                        entity_id,
                        resolved_entity_id,
                    )
                    # Update mapping if entity was renamed
                    if unique_id:
                        self._ignore_until_entity_unique_ids[resolved_entity_id] = (
                            unique_id
                        )
                        del self._ignore_until_entity_unique_ids[entity_id]
                resolved_entity_ids.append(resolved_entity_id)
            else:
                resolved_entity_ids.append(
                    entity_id
                )  # Keep original if resolution failed
        self._ignore_until_entity_ids = resolved_entity_ids

        # Subscribe to state changes for all ignore_until entities
        for entity_id in self._ignore_until_entity_ids:
            unsubscribe = async_track_state_change_event(
                self.hass,
                entity_id,
                self._ignore_until_state_changed,
            )
            self._unsubscribe_handlers.append(unsubscribe)

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        for unsubscribe in self._unsubscribe_handlers:
            if unsubscribe:
                unsubscribe()
        self._unsubscribe_handlers.clear()


class StatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors overall status of all other status sensors.

    This sensor turns ON (problem detected) when any of the other status
    binary sensors (Plant Count, Soil Moisture, Soil Conductivity, Temperature,
    Humidity, Battery Level, or Daily Light Integral) are ON. The Ignored
    Statuses sensor is not considered. The message attribute shows the count
    of monitored sensors that currently have a problem (e.g., "2 Issues").
    """

    def __init__(self, config: StatusMonitorConfig) -> None:
        """
        Initialize the Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name

        # Set entity attributes
        self._attr_name = f"{self.location_name} Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{self.entry_id}_{location_name_safe}_status"

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._status_sensors: dict[str, bool | None] = {}
        self._status_entity_ids: dict[str, str] = {}
        self._status_entity_unique_ids: dict[
            str, str
        ] = {}  # entity_id -> unique_id mapping
        self._unsubscribe_handlers: list[Any] = []

    def _get_entity_unique_id(self, entity_id: str) -> str | None:
        """Get unique_id for an entity_id."""
        try:
            entity_reg = er.async_get(self.hass)
            if entity_reg is not None:
                entity_entry = entity_reg.async_get(entity_id)
                if entity_entry and entity_entry.unique_id:
                    return entity_entry.unique_id
        except (TypeError, AttributeError, ValueError):
            pass
        return None

    async def _find_status_sensors(self) -> dict[str, str]:
        """
        Find all status sensor entities for this location.

        Returns a dictionary mapping sensor display name to entity_id.
        Status sensors that are found:
        - Plant Count Status
        - Soil Moisture Status
        - Soil Conductivity Status
        - Temperature Status
        - Humidity Status
        - Battery Level Status
        - Daily Light Integral Status
        """
        status_sensors: dict[str, str] = {}
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "binary_sensor"
                    and entity.unique_id
                    and self.entry_id in entity.unique_id
                    and location_name_safe in entity.unique_id
                ):
                    # Check if this is a status monitor entity
                    # (but NOT ignored statuses)
                    unique_id = entity.unique_id
                    is_status_sensor = False
                    sensor_name = ""

                    if "plant_count_status" in unique_id:
                        is_status_sensor = True
                        sensor_name = "Plant Count Status"
                    elif "soil_moisture_status" in unique_id:
                        is_status_sensor = True
                        sensor_name = "Soil Moisture Status"
                    elif "soil_conductivity_status" in unique_id:
                        is_status_sensor = True
                        sensor_name = "Soil Conductivity Status"
                    elif "temperature_status" in unique_id:
                        is_status_sensor = True
                        sensor_name = "Temperature Status"
                    elif "humidity_status" in unique_id:
                        is_status_sensor = True
                        sensor_name = "Humidity Status"
                    elif (
                        "battery_level_status" in unique_id
                        or "monitor_battery_level" in unique_id
                    ):
                        is_status_sensor = True
                        sensor_name = "Battery Level Status"
                    elif "dli_status" in unique_id:
                        is_status_sensor = True
                        sensor_name = "Daily Light Integral Status"

                    # Exclude ignored statuses sensor
                    if is_status_sensor and "ignored_statuses" not in unique_id:
                        status_sensors[sensor_name] = entity.entity_id
                        # Store unique_id mapping for resilient tracking
                        self._status_entity_unique_ids[entity.entity_id] = unique_id
                        _LOGGER.debug(
                            "Found status sensor for %s: %s -> %s (unique_id: %s)",
                            self.location_name,
                            sensor_name,
                            entity.entity_id,
                            unique_id,
                        )

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding status sensors: %s", exc)

        return status_sensors

    def _update_state(self) -> None:
        """Update binary sensor state based on all status sensors."""
        # Check if any status sensor is ON (problem detected)
        any_problem = False
        problem_sensors = []

        for sensor_name, is_on in self._status_sensors.items():
            if is_on is True:
                any_problem = True
                problem_sensors.append(sensor_name)

        self._state = any_problem

    @callback
    def _status_sensor_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle status sensor state changes."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        # Find which sensor this is
        for sensor_name, sensor_entity_id in self._status_entity_ids.items():
            if sensor_entity_id == entity_id:
                if new_state is None:
                    self._status_sensors[sensor_name] = None
                else:
                    self._status_sensors[sensor_name] = new_state.state == "on"
                break

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if any status sensor has a problem."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:alert-circle-outline"
        return "mdi:check-circle-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        # Build list of active problems
        problem_sensors = [
            name for name, is_on in self._status_sensors.items() if is_on is True
        ]

        # Create message with issue count
        issue_count = len(problem_sensors)
        message = (
            f"{issue_count} Issue" if issue_count == 1 else f"{issue_count} Issues"
        )

        attrs: dict[str, Any] = {
            "message": message,
            "problem_sensors": problem_sensors,
            "total_sensors_monitored": len(self._status_sensors),
            "master_tag": self.irrigation_zone_name,
        }
        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Available if we have found at least one status sensor
        return len(self._status_sensors) > 0

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored status monitor for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def async_added_to_hass(self) -> None:
        """Add entity to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Find all status sensor entities
        self._status_entity_ids = await self._find_status_sensors()

        # Resolve all entity IDs with fallback to unique_id for resilience
        resolved_status_entity_ids = {}
        for sensor_name, entity_id in self._status_entity_ids.items():
            unique_id = self._status_entity_unique_ids.get(entity_id)
            resolved_entity_id = _resolve_entity_id(self.hass, entity_id, unique_id)
            if resolved_entity_id:
                if resolved_entity_id != entity_id:
                    _LOGGER.debug(
                        "Resolved status sensor entity ID: %s -> %s",
                        entity_id,
                        resolved_entity_id,
                    )
                    # Update mapping if entity was renamed
                    if unique_id:
                        self._status_entity_unique_ids[resolved_entity_id] = unique_id
                        del self._status_entity_unique_ids[entity_id]
                resolved_status_entity_ids[sensor_name] = resolved_entity_id
            else:
                resolved_status_entity_ids[sensor_name] = entity_id  # Keep original
        self._status_entity_ids = resolved_status_entity_ids

        # Initialize status tracking dictionary
        for sensor_name in self._status_entity_ids:
            self._status_sensors[sensor_name] = None

        # Subscribe to state changes for all status sensors
        for sensor_name, entity_id in self._status_entity_ids.items():
            # Get initial state
            if state := self.hass.states.get(entity_id):
                self._status_sensors[sensor_name] = state.state == "on"

            # Subscribe to changes
            unsubscribe = async_track_state_change_event(
                self.hass,
                entity_id,
                self._status_sensor_state_changed,
            )
            self._unsubscribe_handlers.append(unsubscribe)

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        for unsubscribe in self._unsubscribe_handlers:
            if unsubscribe:
                unsubscribe()
        self._unsubscribe_handlers.clear()


class MasterScheduleStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors master schedule status for an irrigation zone.

    This sensor turns ON (problem detected) when the master schedule switch
    for an irrigation zone associated with an esphome device has been turned off.
    The sensor respects the Schedule Ignore Until datetime entity - if the current
    time is before the ignore until datetime, the problem is not raised.
    """

    def __init__(self, config: MasterScheduleStatusMonitorConfig) -> None:
        """
        Initialize the Master Schedule Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.zone_device_identifier = config.zone_device_identifier
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.master_schedule_switch_entity_id = config.master_schedule_switch_entity_id
        self._master_schedule_switch_unique_id = config.master_schedule_switch_unique_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Schedule Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_schedule_status"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={self.zone_device_identifier},
        )

        self._state: bool | None = None
        self._master_schedule_on: bool | None = None
        self._ignore_until_datetime: Any = None
        self._unsubscribe_switch: Any = None
        self._unsubscribe_ignore_until: Any = None

        # Initialize with current state of master schedule switch entity
        if switch_state := self.hass.states.get(self.master_schedule_switch_entity_id):
            self._master_schedule_on = switch_state.state == "on"

    def _update_state(self) -> None:
        """Update binary sensor state based on master schedule switch status."""
        # If master schedule switch state is unavailable, set state to None
        if self._master_schedule_on is None:
            self._state = None
            return

        # Check if we're currently in the ignore period
        if self._ignore_until_datetime is not None:
            try:
                now = dt_util.now()
                if now < self._ignore_until_datetime:
                    # Current time is before ignore until datetime, no problem
                    self._state = False
                    return
            except (TypeError, AttributeError) as exc:
                _LOGGER.debug("Error checking ignore until datetime: %s", exc)

        # Binary sensor is ON (problem) when master schedule switch is OFF
        self._state = not self._master_schedule_on

    async def _find_schedule_ignore_until_entity(self) -> str | None:
        """
        Find schedule ignore until datetime entity for this irrigation zone.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            # Build the expected unique_id pattern based on zone device identifier
            zone_device_domain = self.zone_device_identifier[0]
            zone_device_id = self.zone_device_identifier[1]

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "schedule_ignore_until" in entity.unique_id
                    and zone_device_domain in entity.unique_id
                    and zone_device_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found schedule ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding schedule ignore until entity: %s", exc)

        return None

    @callback
    def _master_schedule_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle master schedule switch state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._master_schedule_on = None
        else:
            self._master_schedule_on = new_state.state == "on"

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _schedule_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle schedule ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._ignore_until_datetime = parsed_datetime
                else:
                    self._ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug("Error parsing schedule ignore until datetime: %s", exc)
                self._ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if master schedule is off (problem detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:clock-remove"
        return "mdi:clock-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            "type": "Warning",
            "message": "Master Schedule Off" if self._state else "Master Schedule On",
            "task": True,
            "tags": [
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "master_schedule_on": self._master_schedule_on,
            "source_entity": self.master_schedule_switch_entity_id,
        }

        # Add ignore until information if available
        if self._ignore_until_datetime:
            now = dt_util.now()
            attrs["ignore_until"] = self._ignore_until_datetime.isoformat()
            attrs["currently_ignoring"] = now < self._ignore_until_datetime

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        switch_state = self.hass.states.get(self.master_schedule_switch_entity_id)
        return switch_state is not None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored master schedule status for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_schedule_ignore_until_subscription(self) -> None:
        """Find and subscribe to schedule ignore until datetime entity."""
        ignore_until_entity_id = await self._find_schedule_ignore_until_entity()
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing schedule ignore until datetime: %s", exc
                    )

            try:
                self._unsubscribe_ignore_until = async_track_state_change_event(
                    self.hass,
                    ignore_until_entity_id,
                    self._schedule_ignore_until_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to schedule ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to schedule ignore until entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Schedule ignore until datetime not found for zone %s",
                self.irrigation_zone_name,
            )

    async def _setup_master_schedule_subscription(self) -> None:
        """Subscribe to master schedule switch entity state changes."""
        # Re-resolve entity_id immediately before subscription to handle any
        # renames that occurred during initialization
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        self.master_schedule_switch_entity_id = (
            _resolve_entity_id(
                self.hass,
                self.master_schedule_switch_entity_id,
                self._master_schedule_switch_unique_id,
            )
            or self.master_schedule_switch_entity_id
        )
        try:
            self._unsubscribe_switch = async_track_state_change_event(
                self.hass,
                self.master_schedule_switch_entity_id,
                self._master_schedule_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to master schedule switch: %s",
                self.master_schedule_switch_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to master schedule entity %s: %s",
                self.master_schedule_switch_entity_id,
                exc,
            )

    async def _resolve_entity_references(self) -> None:
        """Resolve entity references using unique_id if entity_id not found."""
        # Import helper at runtime to avoid circular imports
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        # Resolve master schedule switch
        resolved_entity_id = _resolve_entity_id(
            self.hass,
            self.master_schedule_switch_entity_id,
            self._master_schedule_switch_unique_id,
        )
        if (
            resolved_entity_id
            and resolved_entity_id != self.master_schedule_switch_entity_id
        ):
            _LOGGER.info(
                "Resolved master_schedule_switch for %s: %s -> %s",
                self.location_name,
                self.master_schedule_switch_entity_id,
                resolved_entity_id,
            )
            self.master_schedule_switch_entity_id = resolved_entity_id

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Resolve entity references before subscriptions
        await self._resolve_entity_references()

        # Set up subscriptions
        await self._setup_schedule_ignore_until_subscription()
        await self._setup_master_schedule_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe_switch:
            self._unsubscribe_switch()
        if (
            hasattr(self, "_unsubscribe_ignore_until")
            and self._unsubscribe_ignore_until
        ):
            self._unsubscribe_ignore_until()


class ScheduleMisconfigurationStatusMonitorBinarySensor(
    BinarySensorEntity, RestoreEntity
):
    """
    Binary sensor that monitors schedule misconfiguration for an irrigation zone.

    This sensor turns ON (problem detected) when the master schedule switch is on,
    but all three time-based switches (sunrise, afternoon, sunset) are off, indicating
    a schedule misconfiguration. The sensor respects the Schedule Misconfiguration
    Ignore Until datetime entity - if the current time is before the ignore until
    datetime, the problem is not raised.
    """

    def __init__(self, config: ScheduleMisconfigurationStatusMonitorConfig) -> None:
        """
        Initialize the Schedule Misconfiguration Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.zone_device_identifier = config.zone_device_identifier
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.master_schedule_switch_entity_id = config.master_schedule_switch_entity_id
        self.sunrise_switch_entity_id = config.sunrise_switch_entity_id
        self.afternoon_switch_entity_id = config.afternoon_switch_entity_id
        self.sunset_switch_entity_id = config.sunset_switch_entity_id
        self._master_schedule_switch_unique_id = config.master_schedule_switch_unique_id
        self._sunrise_switch_unique_id = config.sunrise_switch_unique_id
        self._afternoon_switch_unique_id = config.afternoon_switch_unique_id
        self._sunset_switch_unique_id = config.sunset_switch_unique_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Schedule Misconfiguration Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_"
            "schedule_misconfiguration_status"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={self.zone_device_identifier},
        )

        self._state: bool | None = None
        self._master_schedule_on: bool | None = None
        self._sunrise_on: bool | None = None
        self._afternoon_on: bool | None = None
        self._sunset_on: bool | None = None
        self._ignore_until_datetime: Any = None
        self._unsubscribe_master: Any = None
        self._unsubscribe_sunrise: Any = None
        self._unsubscribe_afternoon: Any = None
        self._unsubscribe_sunset: Any = None
        self._unsubscribe_ignore_until: Any = None

        # Initialize with current state of switch entities
        if master_state := self.hass.states.get(self.master_schedule_switch_entity_id):
            self._master_schedule_on = master_state.state == "on"
        if sunrise_state := self.hass.states.get(self.sunrise_switch_entity_id):
            self._sunrise_on = sunrise_state.state == "on"
        if afternoon_state := self.hass.states.get(self.afternoon_switch_entity_id):
            self._afternoon_on = afternoon_state.state == "on"
        if sunset_state := self.hass.states.get(self.sunset_switch_entity_id):
            self._sunset_on = sunset_state.state == "on"

    def _update_state(self) -> None:
        """Update binary sensor state based on schedule switch status."""
        # If any switch state is unavailable, set state to None
        if (
            self._master_schedule_on is None
            or self._sunrise_on is None
            or self._afternoon_on is None
            or self._sunset_on is None
        ):
            self._state = None
            return

        # Check if we're currently in the ignore period
        if self._ignore_until_datetime is not None:
            try:
                now = dt_util.now()
                if now < self._ignore_until_datetime:
                    # Current time is before ignore until datetime, no problem
                    self._state = False
                    return
            except (TypeError, AttributeError) as exc:
                _LOGGER.debug("Error checking ignore until datetime: %s", exc)

        # Binary sensor is ON (problem) when:
        # - Master schedule switch is ON AND
        # - All three time-based switches (sunrise, afternoon, sunset) are OFF
        all_time_switches_off = (
            not self._sunrise_on and not self._afternoon_on and not self._sunset_on
        )
        self._state = self._master_schedule_on and all_time_switches_off

    async def _find_schedule_misconfiguration_ignore_until_entity(self) -> str | None:
        """
        Find schedule misconfiguration ignore until datetime entity for this zone.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            # Build the expected unique_id pattern based on zone device identifier
            zone_device_domain = self.zone_device_identifier[0]
            zone_device_id = self.zone_device_identifier[1]

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "schedule_misconfiguration_ignore_until" in entity.unique_id
                    and zone_device_domain in entity.unique_id
                    and zone_device_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found schedule misconfiguration ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Error finding schedule misconfiguration ignore until entity: %s", exc
            )

        return None

    @callback
    def _master_schedule_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle master schedule switch state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._master_schedule_on = None
        else:
            self._master_schedule_on = new_state.state == "on"

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _sunrise_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle sunrise switch state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._sunrise_on = None
        else:
            self._sunrise_on = new_state.state == "on"

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _afternoon_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle afternoon switch state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._afternoon_on = None
        else:
            self._afternoon_on = new_state.state == "on"

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _sunset_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle sunset switch state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._sunset_on = None
        else:
            self._sunset_on = new_state.state == "on"

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _schedule_misconfiguration_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle schedule misconfiguration ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._ignore_until_datetime = parsed_datetime
                else:
                    self._ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing schedule misconfiguration ignore until datetime: %s",
                    exc,
                )
                self._ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if schedule is misconfigured (problem detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:clock-alert"
        return "mdi:clock-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            "type": "Warning",
            "message": ("Schedule Misconfigured" if self._state else "Schedule OK"),
            "task": True,
            "tags": [
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "master_schedule_on": self._master_schedule_on,
            "sunrise_on": self._sunrise_on,
            "afternoon_on": self._afternoon_on,
            "sunset_on": self._sunset_on,
            "source_entity_master": self.master_schedule_switch_entity_id,
            "source_entity_sunrise": self.sunrise_switch_entity_id,
            "source_entity_afternoon": self.afternoon_switch_entity_id,
            "source_entity_sunset": self.sunset_switch_entity_id,
        }

        # Add ignore until information if available
        if self._ignore_until_datetime:
            now = dt_util.now()
            attrs["ignore_until"] = self._ignore_until_datetime.isoformat()
            attrs["currently_ignoring"] = now < self._ignore_until_datetime

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        master_state = self.hass.states.get(self.master_schedule_switch_entity_id)
        sunrise_state = self.hass.states.get(self.sunrise_switch_entity_id)
        afternoon_state = self.hass.states.get(self.afternoon_switch_entity_id)
        sunset_state = self.hass.states.get(self.sunset_switch_entity_id)

        # Entity is available if all switches exist and are not unavailable/unknown
        for state in [master_state, sunrise_state, afternoon_state, sunset_state]:
            if state is None:
                return False
            if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return False

        return True

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored schedule misconfiguration status for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_schedule_misconfiguration_ignore_until_subscription(self) -> None:
        """Find and subscribe to schedule misconfiguration ignore until entity."""
        ignore_until_entity_id = (
            await self._find_schedule_misconfiguration_ignore_until_entity()
        )
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing schedule misconfiguration ignore until "
                        "datetime: %s",
                        exc,
                    )

            try:
                self._unsubscribe_ignore_until = async_track_state_change_event(
                    self.hass,
                    ignore_until_entity_id,
                    self._schedule_misconfiguration_ignore_until_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to schedule misconfiguration ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to schedule misconfiguration ignore until "
                    "entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Schedule misconfiguration ignore until datetime not found for zone %s",
                self.irrigation_zone_name,
            )

    async def _setup_master_schedule_subscription(self) -> None:
        """Subscribe to master schedule switch entity state changes."""
        try:
            self._unsubscribe_master = async_track_state_change_event(
                self.hass,
                self.master_schedule_switch_entity_id,
                self._master_schedule_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to master schedule switch: %s",
                self.master_schedule_switch_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to master schedule entity %s: %s",
                self.master_schedule_switch_entity_id,
                exc,
            )

    async def _setup_sunrise_subscription(self) -> None:
        """Subscribe to sunrise switch entity state changes."""
        # Re-resolve entity_id immediately before subscription to handle any
        # renames that occurred during initialization
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        self.sunrise_switch_entity_id = (
            _resolve_entity_id(
                self.hass,
                self.sunrise_switch_entity_id,
                self._sunrise_switch_unique_id,
            )
            or self.sunrise_switch_entity_id
        )
        try:
            self._unsubscribe_sunrise = async_track_state_change_event(
                self.hass,
                self.sunrise_switch_entity_id,
                self._sunrise_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to sunrise switch: %s",
                self.sunrise_switch_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to sunrise switch entity %s: %s",
                self.sunrise_switch_entity_id,
                exc,
            )

    async def _setup_afternoon_subscription(self) -> None:
        """Subscribe to afternoon switch entity state changes."""
        # Re-resolve entity_id immediately before subscription to handle any
        # renames that occurred during initialization
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        self.afternoon_switch_entity_id = (
            _resolve_entity_id(
                self.hass,
                self.afternoon_switch_entity_id,
                self._afternoon_switch_unique_id,
            )
            or self.afternoon_switch_entity_id
        )
        try:
            self._unsubscribe_afternoon = async_track_state_change_event(
                self.hass,
                self.afternoon_switch_entity_id,
                self._afternoon_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to afternoon switch: %s",
                self.afternoon_switch_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to afternoon switch entity %s: %s",
                self.afternoon_switch_entity_id,
                exc,
            )

    async def _setup_sunset_subscription(self) -> None:
        """Subscribe to sunset switch entity state changes."""
        # Re-resolve entity_id immediately before subscription to handle any
        # renames that occurred during initialization
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        self.sunset_switch_entity_id = (
            _resolve_entity_id(
                self.hass,
                self.sunset_switch_entity_id,
                self._sunset_switch_unique_id,
            )
            or self.sunset_switch_entity_id
        )
        try:
            self._unsubscribe_sunset = async_track_state_change_event(
                self.hass,
                self.sunset_switch_entity_id,
                self._sunset_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to sunset switch: %s",
                self.sunset_switch_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to sunset switch entity %s: %s",
                self.sunset_switch_entity_id,
                exc,
            )

    async def _resolve_entity_references(self) -> None:
        """Resolve entity references using unique_id if entity_id not found."""
        # Import helper at runtime to avoid circular imports
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        # Resolve master schedule switch
        resolved_entity_id = _resolve_entity_id(
            self.hass,
            self.master_schedule_switch_entity_id,
            self._master_schedule_switch_unique_id,
        )
        if (
            resolved_entity_id
            and resolved_entity_id != self.master_schedule_switch_entity_id
        ):
            _LOGGER.info(
                "Resolved master_schedule_switch for %s: %s -> %s",
                self.location_name,
                self.master_schedule_switch_entity_id,
                resolved_entity_id,
            )
            self.master_schedule_switch_entity_id = resolved_entity_id

        # Resolve sunrise switch
        resolved_entity_id = _resolve_entity_id(
            self.hass, self.sunrise_switch_entity_id, self._sunrise_switch_unique_id
        )
        if resolved_entity_id and resolved_entity_id != self.sunrise_switch_entity_id:
            _LOGGER.info(
                "Resolved sunrise_switch for %s: %s -> %s",
                self.location_name,
                self.sunrise_switch_entity_id,
                resolved_entity_id,
            )
            self.sunrise_switch_entity_id = resolved_entity_id

        # Resolve afternoon switch
        resolved_entity_id = _resolve_entity_id(
            self.hass, self.afternoon_switch_entity_id, self._afternoon_switch_unique_id
        )
        if resolved_entity_id and resolved_entity_id != self.afternoon_switch_entity_id:
            _LOGGER.info(
                "Resolved afternoon_switch for %s: %s -> %s",
                self.location_name,
                self.afternoon_switch_entity_id,
                resolved_entity_id,
            )
            self.afternoon_switch_entity_id = resolved_entity_id

        # Resolve sunset switch
        resolved_entity_id = _resolve_entity_id(
            self.hass, self.sunset_switch_entity_id, self._sunset_switch_unique_id
        )
        if resolved_entity_id and resolved_entity_id != self.sunset_switch_entity_id:
            _LOGGER.info(
                "Resolved sunset_switch for %s: %s -> %s",
                self.location_name,
                self.sunset_switch_entity_id,
                resolved_entity_id,
            )
            self.sunset_switch_entity_id = resolved_entity_id

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Resolve entity references before subscriptions
        await self._resolve_entity_references()

        # Set up subscriptions
        await self._setup_schedule_misconfiguration_ignore_until_subscription()
        await self._setup_master_schedule_subscription()
        await self._setup_sunrise_subscription()
        await self._setup_afternoon_subscription()
        await self._setup_sunset_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe_master:
            self._unsubscribe_master()
        if self._unsubscribe_sunrise:
            self._unsubscribe_sunrise()
        if self._unsubscribe_afternoon:
            self._unsubscribe_afternoon()
        if self._unsubscribe_sunset:
            self._unsubscribe_sunset()
        if (
            hasattr(self, "_unsubscribe_ignore_until")
            and self._unsubscribe_ignore_until
        ):
            self._unsubscribe_ignore_until()


class WaterDeliveryPreferenceStatusMonitorBinarySensor(
    BinarySensorEntity, RestoreEntity
):
    """
    Binary sensor that monitors water delivery preference status for an irrigation zone.

    This sensor turns ON (problem detected) when the master schedule switch is on,
    but both the Allow Rain Water Delivery and Allow Water Main Delivery switches
    are off, indicating no water delivery methods are available. The sensor respects
    the Water Delivery Preference Ignore Until datetime entity - if the current time
    is before the ignore until datetime, the problem is not raised.
    """

    def __init__(self, config: WaterDeliveryPreferenceStatusMonitorConfig) -> None:
        """
        Initialize the Water Delivery Preference Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.zone_device_identifier = config.zone_device_identifier
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.master_schedule_switch_entity_id = config.master_schedule_switch_entity_id
        self.allow_rain_water_delivery_switch_entity_id = (
            config.allow_rain_water_delivery_switch_entity_id
        )
        self.allow_water_main_delivery_switch_entity_id = (
            config.allow_water_main_delivery_switch_entity_id
        )
        self._master_schedule_switch_unique_id = config.master_schedule_switch_unique_id
        self._allow_rain_water_delivery_switch_unique_id = (
            config.allow_rain_water_delivery_switch_unique_id
        )
        self._allow_water_main_delivery_switch_unique_id = (
            config.allow_water_main_delivery_switch_unique_id
        )

        # Set entity attributes
        self._attr_name = f"{self.location_name} Water Delivery Preference Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_"
            "water_delivery_preference_status"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={self.zone_device_identifier},
        )

        self._state: bool | None = None
        self._master_schedule_on: bool | None = None
        self._allow_rain_water_delivery_on: bool | None = None
        self._allow_water_main_delivery_on: bool | None = None
        self._ignore_until_datetime: Any = None
        self._unsubscribe_master: Any = None
        self._unsubscribe_rain_delivery: Any = None
        self._unsubscribe_main_delivery: Any = None
        self._unsubscribe_ignore_until: Any = None

        # Initialize with current state of switch entities
        if master_state := self.hass.states.get(self.master_schedule_switch_entity_id):
            self._master_schedule_on = master_state.state == "on"
        if rain_state := self.hass.states.get(
            self.allow_rain_water_delivery_switch_entity_id
        ):
            self._allow_rain_water_delivery_on = rain_state.state == "on"
        if main_state := self.hass.states.get(
            self.allow_water_main_delivery_switch_entity_id
        ):
            self._allow_water_main_delivery_on = main_state.state == "on"

    def _update_state(self) -> None:
        """Update binary sensor state based on delivery preference switch status."""
        # If any switch state is unavailable, set state to None
        if (
            self._master_schedule_on is None
            or self._allow_rain_water_delivery_on is None
            or self._allow_water_main_delivery_on is None
        ):
            self._state = None
            return

        # Check if we're currently in the ignore period
        if self._ignore_until_datetime is not None:
            try:
                now = dt_util.now()
                if now < self._ignore_until_datetime:
                    # Current time is before ignore until datetime, no problem
                    self._state = False
                    return
            except (TypeError, AttributeError) as exc:
                _LOGGER.debug("Error checking ignore until datetime: %s", exc)

        # Binary sensor is ON (problem) when:
        # - Master schedule switch is ON AND
        # - Both delivery preference switches are OFF
        both_delivery_methods_off = (
            not self._allow_rain_water_delivery_on
            and not self._allow_water_main_delivery_on
        )
        self._state = self._master_schedule_on and both_delivery_methods_off

    async def _find_water_delivery_preference_ignore_until_entity(
        self,
    ) -> str | None:
        """
        Find water delivery preference ignore until datetime entity for this zone.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            # Build the expected unique_id pattern based on zone device identifier
            zone_device_domain = self.zone_device_identifier[0]
            zone_device_id = self.zone_device_identifier[1]

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "water_delivery_preference_ignore_until" in entity.unique_id
                    and zone_device_domain in entity.unique_id
                    and zone_device_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found water delivery preference ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Error finding water delivery preference ignore until entity: %s", exc
            )

        return None

    @callback
    def _master_schedule_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle master schedule switch state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._master_schedule_on = None
        else:
            self._master_schedule_on = new_state.state == "on"

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _allow_rain_water_delivery_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle allow rain water delivery switch state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._allow_rain_water_delivery_on = None
        else:
            self._allow_rain_water_delivery_on = new_state.state == "on"

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _allow_water_main_delivery_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle allow water main delivery switch state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._allow_water_main_delivery_on = None
        else:
            self._allow_water_main_delivery_on = new_state.state == "on"

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _water_delivery_preference_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle water delivery preference ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._ignore_until_datetime = parsed_datetime
                else:
                    self._ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing water delivery preference ignore until datetime: %s",
                    exc,
                )
                self._ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if water delivery preference misconfigured (problem)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:water-alert"
        return "mdi:water-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            "type": "Warning",
            "message": (
                "Water Delivery Unset" if self._state else "Water Delivery Available"
            ),
            "task": True,
            "tags": [
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "master_schedule_on": self._master_schedule_on,
            "allow_rain_water_delivery_on": self._allow_rain_water_delivery_on,
            "allow_water_main_delivery_on": self._allow_water_main_delivery_on,
            "source_entity_master": self.master_schedule_switch_entity_id,
            "source_entity_rain_delivery": (
                self.allow_rain_water_delivery_switch_entity_id
            ),
            "source_entity_main_delivery": (
                self.allow_water_main_delivery_switch_entity_id
            ),
        }

        # Add ignore until information if available
        if self._ignore_until_datetime:
            now = dt_util.now()
            attrs["ignore_until"] = self._ignore_until_datetime.isoformat()
            attrs["currently_ignoring"] = now < self._ignore_until_datetime

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        master_state = self.hass.states.get(self.master_schedule_switch_entity_id)
        rain_state = self.hass.states.get(
            self.allow_rain_water_delivery_switch_entity_id
        )
        main_state = self.hass.states.get(
            self.allow_water_main_delivery_switch_entity_id
        )

        # Entity is available if all switches exist and are not unavailable/unknown
        for state in [master_state, rain_state, main_state]:
            if state is None:
                return False
            if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                return False

        return True

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored water delivery preference status for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_water_delivery_preference_ignore_until_subscription(
        self,
    ) -> None:
        """Find and subscribe to water delivery preference ignore until entity."""
        ignore_until_entity_id = (
            await self._find_water_delivery_preference_ignore_until_entity()
        )
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing water delivery preference ignore until "
                        "datetime: %s",
                        exc,
                    )

            try:
                self._unsubscribe_ignore_until = async_track_state_change_event(
                    self.hass,
                    ignore_until_entity_id,
                    self._water_delivery_preference_ignore_until_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to water delivery preference ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to water delivery preference ignore until "
                    "entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Water delivery preference ignore until datetime not found for zone %s",
                self.irrigation_zone_name,
            )

    async def _setup_master_schedule_subscription(self) -> None:
        """Subscribe to master schedule switch entity state changes."""
        try:
            self._unsubscribe_master = async_track_state_change_event(
                self.hass,
                self.master_schedule_switch_entity_id,
                self._master_schedule_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to master schedule switch: %s",
                self.master_schedule_switch_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to master schedule entity %s: %s",
                self.master_schedule_switch_entity_id,
                exc,
            )

    async def _setup_allow_rain_water_delivery_subscription(self) -> None:
        """Subscribe to allow rain water delivery switch entity state changes."""
        # Re-resolve entity_id immediately before subscription to handle any
        # renames that occurred during initialization
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        self.allow_rain_water_delivery_switch_entity_id = (
            _resolve_entity_id(
                self.hass,
                self.allow_rain_water_delivery_switch_entity_id,
                self._allow_rain_water_delivery_switch_unique_id,
            )
            or self.allow_rain_water_delivery_switch_entity_id
        )
        try:
            self._unsubscribe_rain_delivery = async_track_state_change_event(
                self.hass,
                self.allow_rain_water_delivery_switch_entity_id,
                self._allow_rain_water_delivery_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to allow rain water delivery switch: %s",
                self.allow_rain_water_delivery_switch_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to allow rain water delivery entity %s: %s",
                self.allow_rain_water_delivery_switch_entity_id,
                exc,
            )

    async def _setup_allow_water_main_delivery_subscription(self) -> None:
        """Subscribe to allow water main delivery switch entity state changes."""
        # Re-resolve entity_id immediately before subscription to handle any
        # renames that occurred during initialization
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        self.allow_water_main_delivery_switch_entity_id = (
            _resolve_entity_id(
                self.hass,
                self.allow_water_main_delivery_switch_entity_id,
                self._allow_water_main_delivery_switch_unique_id,
            )
            or self.allow_water_main_delivery_switch_entity_id
        )
        try:
            self._unsubscribe_main_delivery = async_track_state_change_event(
                self.hass,
                self.allow_water_main_delivery_switch_entity_id,
                self._allow_water_main_delivery_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to allow water main delivery switch: %s",
                self.allow_water_main_delivery_switch_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to allow water main delivery entity %s: %s",
                self.allow_water_main_delivery_switch_entity_id,
                exc,
            )

    async def _resolve_entity_references(self) -> None:
        """Resolve entity references using unique_id if entity_id not found."""
        # Import helper at runtime to avoid circular imports
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        # Resolve master schedule switch
        resolved_entity_id = _resolve_entity_id(
            self.hass,
            self.master_schedule_switch_entity_id,
            self._master_schedule_switch_unique_id,
        )
        if (
            resolved_entity_id
            and resolved_entity_id != self.master_schedule_switch_entity_id
        ):
            _LOGGER.info(
                "Resolved master_schedule_switch for %s: %s -> %s",
                self.location_name,
                self.master_schedule_switch_entity_id,
                resolved_entity_id,
            )
            self.master_schedule_switch_entity_id = resolved_entity_id

        # Resolve allow rain water delivery switch
        resolved_entity_id = _resolve_entity_id(
            self.hass,
            self.allow_rain_water_delivery_switch_entity_id,
            self._allow_rain_water_delivery_switch_unique_id,
        )
        if (
            resolved_entity_id
            and resolved_entity_id != self.allow_rain_water_delivery_switch_entity_id
        ):
            _LOGGER.info(
                "Resolved allow_rain_water_delivery_switch for %s: %s -> %s",
                self.location_name,
                self.allow_rain_water_delivery_switch_entity_id,
                resolved_entity_id,
            )
            self.allow_rain_water_delivery_switch_entity_id = resolved_entity_id

        # Resolve allow water main delivery switch
        resolved_entity_id = _resolve_entity_id(
            self.hass,
            self.allow_water_main_delivery_switch_entity_id,
            self._allow_water_main_delivery_switch_unique_id,
        )
        if (
            resolved_entity_id
            and resolved_entity_id != self.allow_water_main_delivery_switch_entity_id
        ):
            _LOGGER.info(
                "Resolved allow_water_main_delivery_switch for %s: %s -> %s",
                self.location_name,
                self.allow_water_main_delivery_switch_entity_id,
                resolved_entity_id,
            )
            self.allow_water_main_delivery_switch_entity_id = resolved_entity_id

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Resolve entity references before subscriptions
        await self._resolve_entity_references()

        # Set up subscriptions
        await self._setup_water_delivery_preference_ignore_until_subscription()
        await self._setup_master_schedule_subscription()
        await self._setup_allow_rain_water_delivery_subscription()
        await self._setup_allow_water_main_delivery_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe_master:
            self._unsubscribe_master()
        if self._unsubscribe_rain_delivery:
            self._unsubscribe_rain_delivery()
        if self._unsubscribe_main_delivery:
            self._unsubscribe_main_delivery()
        if (
            hasattr(self, "_unsubscribe_ignore_until")
            and self._unsubscribe_ignore_until
        ):
            self._unsubscribe_ignore_until()


class ErrorStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors error count status for an irrigation zone.

    This sensor turns ON (problem detected) when the error count reaches 3 or more,
    indicating that the irrigation zone has accumulated multiple errors.
    """

    def __init__(self, config: ErrorStatusMonitorConfig) -> None:
        """
        Initialize the Error Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.zone_device_identifier = config.zone_device_identifier
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.error_count_entity_id = config.error_count_entity_id
        self.error_count_entity_unique_id = config.error_count_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Error Status"

        # Generate unique_id
        zone_device_domain = config.zone_device_identifier[0]
        zone_device_id = config.zone_device_identifier[1]
        unique_id_parts = (
            DOMAIN,
            self.entry_id,
            zone_device_domain,
            zone_device_id,
            "error_status",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={self.zone_device_identifier},
        )

        self._state: bool | None = None
        self._error_count: int = 0
        self._unsubscribe = None

        # Resolve error count entity ID using resilient lookup
        resolved_entity_id = _resolve_entity_id(
            self.hass, self.error_count_entity_id, self.error_count_entity_unique_id
        )
        if resolved_entity_id and resolved_entity_id != self.error_count_entity_id:
            _LOGGER.debug(
                "Resolved error count entity ID: %s -> %s",
                self.error_count_entity_id,
                resolved_entity_id,
            )
            self.error_count_entity_id = resolved_entity_id

        # Capture unique_id if not already stored
        if not self.error_count_entity_unique_id:
            self.error_count_entity_unique_id = self._get_entity_unique_id(
                self.error_count_entity_id
            )

        # Initialize with current state of error count entity
        if error_count_state := self.hass.states.get(self.error_count_entity_id):
            try:
                self._error_count = int(error_count_state.state)
            except (ValueError, TypeError):
                self._error_count = 0

    def _get_entity_unique_id(self, entity_id: str) -> str | None:
        """Get unique_id for an entity_id."""
        try:
            entity_reg = er.async_get(self.hass)
            if entity_reg is not None:
                entity_entry = entity_reg.async_get(entity_id)
                if entity_entry and entity_entry.unique_id:
                    return entity_entry.unique_id
        except (TypeError, AttributeError, ValueError):
            pass
        return None

    def _update_state(self) -> None:
        """Update binary sensor state based on error count."""
        # Binary sensor is ON (problem) when error count >= ERROR_COUNT_THRESHOLD
        self._state = self._error_count >= ERROR_COUNT_THRESHOLD

    @callback
    def _error_count_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle error count sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._error_count = 0
        else:
            try:
                self._error_count = int(new_state.state)
            except (ValueError, TypeError):
                self._error_count = 0

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if error count is 3 or more (problem detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:alert-circle-outline"
        return "mdi:check-circle-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        error_label = "Error" if self._error_count == 1 else "Errors"
        return {
            "type": "Warning",
            "message": f"{self._error_count} {error_label}",
            "task": True,
            "tags": [
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "error_count": self._error_count,
            "error_threshold": ERROR_COUNT_THRESHOLD,
            "source_entity": self.error_count_entity_id,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        error_count_state = self.hass.states.get(self.error_count_entity_id)
        return error_count_state is not None and error_count_state.state not in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        )

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                self._error_count = last_state.attributes.get("error_count", 0)
                _LOGGER.info(
                    "Restored error status monitor for %s: %s (error_count=%d)",
                    self.location_name,
                    self._state,
                    self._error_count,
                )
            except (AttributeError, ValueError):
                pass

    async def async_update_source_entity(self, new_entity_id: str) -> None:
        """Update the error count entity ID when it is renamed."""
        _LOGGER.info(
            "Updating ErrorStatusMonitor %s error count entity from %s to %s",
            self.entity_id,
            self.error_count_entity_id,
            new_entity_id,
        )

        # Unsubscribe from old entity
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

        # Update the entity ID
        self.error_count_entity_id = new_entity_id

        # Capture new unique_id
        self.error_count_entity_unique_id = self._get_entity_unique_id(new_entity_id)

        # Re-subscribe to new entity
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.error_count_entity_id,
                self._error_count_state_changed,
            )
            _LOGGER.debug(
                "Re-subscribed to error count sensor: %s",
                self.error_count_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to re-subscribe to error count entity %s: %s",
                self.error_count_entity_id,
                exc,
            )

        # Update state from new entity
        if error_count_state := self.hass.states.get(self.error_count_entity_id):
            try:
                self._error_count = int(error_count_state.state)
            except (ValueError, TypeError):
                self._error_count = 0
        else:
            self._error_count = 0

        self._update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Resolve error count entity ID with fallback to unique_id
        resolved_entity_id = _resolve_entity_id(
            self.hass,
            self.error_count_entity_id,
            self.error_count_entity_unique_id,
        )
        if resolved_entity_id and resolved_entity_id != self.error_count_entity_id:
            _LOGGER.debug(
                "Resolved error count entity ID: %s -> %s",
                self.error_count_entity_id,
                resolved_entity_id,
            )
            self.error_count_entity_id = resolved_entity_id

        # Subscribe to error count sensor state changes
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.error_count_entity_id,
                self._error_count_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to error count sensor: %s",
                self.error_count_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to error count entity %s: %s",
                self.error_count_entity_id,
                exc,
            )

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class ESPHomeRunningStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors ESPHome binary sensor with 'running' device class.

    This sensor turns ON when the ESPHome device associated with an irrigation zone
    has a binary sensor with device_class='running' that is ON, indicating the
    device is currently running/active.
    """

    def __init__(self, config: ESPHomeRunningStatusMonitorConfig) -> None:
        """
        Initialize the ESPHome Running Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.zone_device_identifier = config.zone_device_identifier
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.monitoring_device_id = config.monitoring_device_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Irrigation Status"

        # Generate unique_id
        zone_device_domain = config.zone_device_identifier[0]
        zone_device_id = config.zone_device_identifier[1]
        unique_id_parts = (
            DOMAIN,
            self.entry_id,
            zone_device_domain,
            zone_device_id,
            "irrigation_status",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.RUNNING

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={self.zone_device_identifier},
        )

        self._state: bool | None = None
        self._running_sensor_entity_id: str | None = None
        self._running_sensor_entity_unique_id: str | None = None
        self._unsubscribe = None

    def _get_entity_unique_id(self, entity_id: str) -> str | None:
        """Get unique_id for an entity_id."""
        try:
            entity_reg = er.async_get(self.hass)
            if entity_reg is not None:
                entity_entry = entity_reg.async_get(entity_id)
                if entity_entry and entity_entry.unique_id:
                    return entity_entry.unique_id
        except (TypeError, AttributeError, ValueError):
            pass
        return None

    def _find_running_binary_sensor(self) -> str | None:
        """
        Find binary sensor with device_class='running' on monitoring device.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            # Find all binary sensor entities associated with the monitoring device
            for entity in ent_reg.entities.values():
                if (
                    entity.device_id == self.monitoring_device_id
                    and entity.domain == "binary_sensor"
                ):
                    # Get the entity's state to check device_class attribute
                    entity_state = self.hass.states.get(entity.entity_id)
                    if entity_state:
                        device_class = entity_state.attributes.get("device_class")
                        if device_class == "running":
                            _LOGGER.debug(
                                "Found running binary sensor on device %s: %s",
                                self.monitoring_device_id,
                                entity.entity_id,
                            )
                            return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding running binary sensor: %s", exc)

        return None

    def _update_state(self) -> None:
        """Update binary sensor state based on running sensor state."""
        # If no running sensor found, set state to None (sensor unavailable)
        if self._running_sensor_entity_id is None:
            self._state = None
            return

        # Get the current state of the running sensor
        running_sensor_state = self.hass.states.get(self._running_sensor_entity_id)
        if running_sensor_state is None:
            self._state = None
            return

        # Binary sensor is ON (problem) when running sensor is ON
        self._state = running_sensor_state.state == "on"

    @callback
    def _running_sensor_state_changed(
        self, _event: Event[EventStateChangedData]
    ) -> None:
        """Handle running sensor state changes."""
        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if device is running."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:play-circle-outline"
        return "mdi:stop-circle-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return {
            "type": "Warning",
            "message": "Device Running" if self._state else "Device Stopped",
            "task": self._state is True,
            "tags": [
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "device_id": self.monitoring_device_id,
            "running_sensor_entity": self._running_sensor_entity_id,
            "source_entity": self._running_sensor_entity_id,
            "source_unique_id": self._running_sensor_entity_unique_id,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Entity is available if we found a running sensor
        return self._running_sensor_entity_id is not None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored esphome running status for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def async_update_source_entity(self, new_entity_id: str) -> None:
        """Update the running sensor entity ID when it is renamed."""
        _LOGGER.info(
            "Updating ESPHomeRunningStatusMonitor %s running sensor from %s to %s",
            self.entity_id,
            self._running_sensor_entity_id,
            new_entity_id,
        )

        # Unsubscribe from old entity
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

        # Update the entity ID
        self._running_sensor_entity_id = new_entity_id

        # Capture new unique_id
        self._running_sensor_entity_unique_id = self._get_entity_unique_id(
            new_entity_id
        )

        # Re-subscribe to new entity
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self._running_sensor_entity_id,
                self._running_sensor_state_changed,
            )
            _LOGGER.debug(
                "Re-subscribed to running sensor: %s",
                self._running_sensor_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to re-subscribe to running sensor %s: %s",
                self._running_sensor_entity_id,
                exc,
            )

        # Update state from new entity
        self._update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to running sensor state changes."""
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Find the running binary sensor
        self._running_sensor_entity_id = self._find_running_binary_sensor()

        # Capture unique_id for resilient tracking
        if self._running_sensor_entity_id:
            self._running_sensor_entity_unique_id = self._get_entity_unique_id(
                self._running_sensor_entity_id
            )

            # Resolve entity ID with fallback to unique_id
            resolved_entity_id = _resolve_entity_id(
                self.hass,
                self._running_sensor_entity_id,
                self._running_sensor_entity_unique_id,
            )
            if (
                resolved_entity_id
                and resolved_entity_id != self._running_sensor_entity_id
            ):
                _LOGGER.debug(
                    "Resolved running sensor entity ID: %s -> %s",
                    self._running_sensor_entity_id,
                    resolved_entity_id,
                )
                self._running_sensor_entity_id = resolved_entity_id

        if self._running_sensor_entity_id:
            # Subscribe to running sensor state changes
            try:
                self._unsubscribe = async_track_state_change_event(
                    self.hass,
                    self._running_sensor_entity_id,
                    self._running_sensor_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to running sensor: %s",
                    self._running_sensor_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to running sensor %s: %s",
                    self._running_sensor_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Running binary sensor not found for device %s",
                self.monitoring_device_id,
            )

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors overall status of an irrigation zone.

    This sensor turns ON (problem detected) when any of the zone's problem
    binary sensors are ON, OR when any plant location within the zone has
    its Status sensor ON. This provides a comprehensive view of the entire
    irrigation zone's health including all associated plant locations.
    """

    def __init__(self, config: IrrigationZoneStatusMonitorConfig) -> None:
        """
        Initialize the Irrigation Zone Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.zone_device_identifier = config.zone_device_identifier
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.zone_id = config.zone_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Status"

        # Generate unique_id
        zone_device_domain = config.zone_device_identifier[0]
        zone_device_id = config.zone_device_identifier[1]
        unique_id_parts = (
            DOMAIN,
            self.entry_id,
            zone_device_domain,
            zone_device_id,
            "status",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={self.zone_device_identifier},
        )

        self._state: bool | None = None
        self._zone_problem_sensors: dict[str, bool | None] = {}
        self._location_status_sensors: dict[str, bool | None] = {}
        self._zone_problem_entity_ids: dict[str, str] = {}
        self._location_status_entity_ids: dict[str, str] = {}
        self._zone_problem_entity_unique_ids: dict[str, str] = {}
        self._location_status_entity_unique_ids: dict[str, str] = {}
        self._unsubscribe_handlers: list[Any] = []

    def _get_entity_unique_id(self, entity_id: str) -> str | None:
        """Get unique_id for an entity_id."""
        try:
            entity_reg = er.async_get(self.hass)
            if entity_reg is not None:
                entity_entry = entity_reg.async_get(entity_id)
                if entity_entry and entity_entry.unique_id:
                    return entity_entry.unique_id
        except (TypeError, AttributeError, ValueError):
            pass
        return None

    async def _find_zone_problem_sensors(self) -> dict[str, str]:
        """
        Find all problem sensor entities for this irrigation zone.

        Returns a dictionary mapping sensor display name to entity_id.
        Zone problem sensors that are found:
        - Schedule Status (master schedule off)
        - Schedule Misconfiguration Status
        - Water Delivery Preference Status
        - Error Status (error count >= 3)
        - Irrigation Status (ESPHome running)
        """
        problem_sensors: dict[str, str] = {}
        try:
            ent_reg = er.async_get(self.hass)
            zone_device_domain = self.zone_device_identifier[0]
            zone_device_id = self.zone_device_identifier[1]

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "binary_sensor"
                    and entity.unique_id
                    and self.entry_id in entity.unique_id
                    and zone_device_domain in entity.unique_id
                    and zone_device_id in entity.unique_id
                ):
                    unique_id = entity.unique_id
                    is_problem_sensor = False
                    sensor_name = ""

                    if "schedule_status" in unique_id:
                        is_problem_sensor = True
                        sensor_name = "Schedule Status"
                    elif "schedule_misconfiguration" in unique_id:
                        is_problem_sensor = True
                        sensor_name = "Schedule Misconfiguration"
                    elif "water_delivery_preference" in unique_id:
                        is_problem_sensor = True
                        sensor_name = "Water Delivery Preference"
                    elif "error_status" in unique_id:
                        is_problem_sensor = True
                        sensor_name = "Error Status"
                    elif "irrigation_status" in unique_id:
                        is_problem_sensor = True
                        sensor_name = "Irrigation Status"

                    # Exclude the overall status sensor itself
                    # by checking if the unique_id ends with just
                    # "status" (not "schedule_status", etc.)
                    if is_problem_sensor and not unique_id.endswith(
                        f"{zone_device_id}_status"
                    ):
                        problem_sensors[sensor_name] = entity.entity_id
                        self._zone_problem_entity_unique_ids[entity.entity_id] = (
                            unique_id
                        )
                        _LOGGER.debug(
                            "Found zone problem sensor for %s: %s -> %s"
                            " (unique_id: %s)",
                            self.location_name,
                            sensor_name,
                            entity.entity_id,
                            unique_id,
                        )

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding zone problem sensors: %s", exc)

        return problem_sensors

    async def _find_location_status_sensors(self) -> dict[str, str]:
        """
        Find all plant location Status sensors for this irrigation zone.

        Returns a dictionary mapping location name to status sensor entity_id.
        """
        status_sensors: dict[str, str] = {}
        try:
            ent_reg = er.async_get(self.hass)

            # Get the parent config entry to access its subentries
            parent_entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if not parent_entry:
                _LOGGER.warning(
                    "Could not find parent entry with ID: %s", self.entry_id
                )
                return status_sensors

            if not parent_entry.subentries:
                _LOGGER.debug("Parent entry %s has no subentries", self.entry_id)
                return status_sensors

            _LOGGER.debug(
                "Found parent entry %s with %d subentries",
                self.entry_id,
                len(parent_entry.subentries),
            )

            # Build a set of subentry IDs that belong to this zone
            zone_subentry_ids = set()
            for subentry_id, subentry in parent_entry.subentries.items():
                zone_id = subentry.data.get("zone_id")
                location_name = subentry.data.get("name", "Unknown")
                _LOGGER.debug(
                    "Checking subentry %s: zone_id=%s, location=%s (target zone=%s)",
                    subentry_id,
                    zone_id,
                    location_name,
                    self.zone_id,
                )
                if zone_id == self.zone_id:
                    zone_subentry_ids.add(subentry_id)
                    _LOGGER.debug(
                        "Matched subentry %s for zone %s (location: %s)",
                        subentry_id,
                        self.zone_id,
                        location_name,
                    )

            _LOGGER.debug(
                "Found %d subentries for zone %s: %s",
                len(zone_subentry_ids),
                self.zone_id,
                zone_subentry_ids,
            )

            # Look through all binary sensors to find status sensors
            # that belong to our zone's subentries
            # Note: We check if the subentry_id is in the unique_id because
            # all entities are registered with the parent entry's config_entry_id
            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "binary_sensor"
                    and entity.unique_id
                    and entity.unique_id.endswith("_status")
                ):
                    # Check if this entity belongs to any of our zone's subentries
                    # by checking if the subentry_id appears in the unique_id
                    for subentry_id in zone_subentry_ids:
                        if subentry_id in entity.unique_id:
                            # This is a status sensor for a plant location in our zone
                            # Get the subentry to extract the location name
                            subentry = parent_entry.subentries.get(subentry_id)
                            if subentry is not None:
                                location_name = subentry.data.get(
                                    "name", "Unknown Location"
                                )
                                status_sensors[location_name] = entity.entity_id
                                self._location_status_entity_unique_ids[
                                    entity.entity_id
                                ] = entity.unique_id
                                _LOGGER.info(
                                    "Found location status sensor for zone %s: "
                                    "%s -> %s (unique_id: %s, subentry_id: %s)",
                                    self.location_name,
                                    location_name,
                                    entity.entity_id,
                                    entity.unique_id,
                                    subentry_id,
                                )
                            break  # Found a match, no need to check other subentries

        except (AttributeError, KeyError, ValueError):
            _LOGGER.exception("Error finding location status sensors")

        _LOGGER.info(
            "Irrigation zone %s found %d location status sensors: %s",
            self.location_name,
            len(status_sensors),
            list(status_sensors.keys()),
        )

        return status_sensors

    async def _refresh_location_status_sensors(self) -> None:
        """Refresh location status sensors and subscribe to their state changes."""
        # Find all location status sensors
        new_location_status_entity_ids = await self._find_location_status_sensors()

        # Resolve all location status entity IDs
        resolved_location_status_entity_ids = {}
        for location_name, entity_id in new_location_status_entity_ids.items():
            unique_id = self._location_status_entity_unique_ids.get(entity_id)
            resolved_entity_id = _resolve_entity_id(self.hass, entity_id, unique_id)
            if resolved_entity_id:
                if resolved_entity_id != entity_id:
                    _LOGGER.debug(
                        "Resolved location status sensor entity ID: %s -> %s",
                        entity_id,
                        resolved_entity_id,
                    )
                    if unique_id:
                        self._location_status_entity_unique_ids[resolved_entity_id] = (
                            unique_id
                        )
                        del self._location_status_entity_unique_ids[entity_id]
                resolved_location_status_entity_ids[location_name] = resolved_entity_id
            else:
                resolved_location_status_entity_ids[location_name] = entity_id

        # Update the entity IDs
        self._location_status_entity_ids = resolved_location_status_entity_ids

        # Initialize tracking dictionary
        for location_name in self._location_status_entity_ids:
            self._location_status_sensors[location_name] = None

        # Subscribe to state changes for all location status sensors
        for location_name, entity_id in self._location_status_entity_ids.items():
            if state := self.hass.states.get(entity_id):
                self._location_status_sensors[location_name] = state.state == "on"

            unsubscribe = async_track_state_change_event(
                self.hass,
                entity_id,
                self._sensor_state_changed,
            )
            self._unsubscribe_handlers.append(unsubscribe)

        # Update state after finding new sensors
        self._update_state()
        self.async_write_ha_state()

        _LOGGER.info(
            "Refreshed location status sensors for zone %s: found %d sensors",
            self.location_name,
            len(self._location_status_entity_ids),
        )

    def _update_state(self) -> None:
        """Update binary sensor state based on all monitored sensors."""
        # Check if any zone problem sensor is ON
        zone_problems = [
            name for name, is_on in self._zone_problem_sensors.items() if is_on is True
        ]

        # Check if any location status sensor is ON
        location_problems = [
            name
            for name, is_on in self._location_status_sensors.items()
            if is_on is True
        ]

        # Overall status is problem if ANY monitored sensor has a problem
        self._state = len(zone_problems) > 0 or len(location_problems) > 0

    @callback
    def _sensor_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle monitored sensor state changes."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")

        # Check if it's a zone problem sensor
        for sensor_name, sensor_entity_id in self._zone_problem_entity_ids.items():
            if sensor_entity_id == entity_id:
                if new_state is None:
                    self._zone_problem_sensors[sensor_name] = None
                else:
                    self._zone_problem_sensors[sensor_name] = new_state.state == "on"
                break

        # Check if it's a location status sensor
        for location_name, sensor_entity_id in self._location_status_entity_ids.items():
            if sensor_entity_id == entity_id:
                if new_state is None:
                    self._location_status_sensors[location_name] = None
                else:
                    self._location_status_sensors[location_name] = (
                        new_state.state == "on"
                    )
                break

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if any monitored sensor has a problem."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:alert-circle-outline"
        return "mdi:check-circle-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        # Build list of zone problems
        zone_problems = [
            name for name, is_on in self._zone_problem_sensors.items() if is_on is True
        ]

        # Build list of location problems
        location_problems = [
            name
            for name, is_on in self._location_status_sensors.items()
            if is_on is True
        ]

        # Total issue count
        total_issues = len(zone_problems) + len(location_problems)
        message = (
            f"{total_issues} Issue" if total_issues == 1 else f"{total_issues} Issues"
        )

        attrs: dict[str, Any] = {
            "message": message,
            "zone_problems": zone_problems,
            "location_problems": location_problems,
            "total_zone_sensors_monitored": len(self._zone_problem_sensors),
            "total_location_sensors_monitored": len(self._location_status_sensors),
        }
        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Available if we have found at least one sensor to monitor
        return (
            len(self._zone_problem_sensors) > 0
            or len(self._location_status_sensors) > 0
        )

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored irrigation zone status monitor for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def async_added_to_hass(self) -> None:
        """Add entity to hass."""
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Find all zone problem sensors
        self._zone_problem_entity_ids = await self._find_zone_problem_sensors()

        # Resolve all zone problem entity IDs
        resolved_zone_problem_entity_ids = {}
        for sensor_name, entity_id in self._zone_problem_entity_ids.items():
            unique_id = self._zone_problem_entity_unique_ids.get(entity_id)
            resolved_entity_id = _resolve_entity_id(self.hass, entity_id, unique_id)
            if resolved_entity_id:
                if resolved_entity_id != entity_id:
                    _LOGGER.debug(
                        "Resolved zone problem sensor entity ID: %s -> %s",
                        entity_id,
                        resolved_entity_id,
                    )
                    if unique_id:
                        self._zone_problem_entity_unique_ids[resolved_entity_id] = (
                            unique_id
                        )
                        del self._zone_problem_entity_unique_ids[entity_id]
                resolved_zone_problem_entity_ids[sensor_name] = resolved_entity_id
            else:
                resolved_zone_problem_entity_ids[sensor_name] = entity_id
        self._zone_problem_entity_ids = resolved_zone_problem_entity_ids

        # Initialize tracking dictionaries for zone problem sensors
        for sensor_name in self._zone_problem_entity_ids:
            self._zone_problem_sensors[sensor_name] = None

        # Subscribe to state changes for all zone problem sensors
        for sensor_name, entity_id in self._zone_problem_entity_ids.items():
            if state := self.hass.states.get(entity_id):
                self._zone_problem_sensors[sensor_name] = state.state == "on"

            unsubscribe = async_track_state_change_event(
                self.hass,
                entity_id,
                self._sensor_state_changed,
            )
            self._unsubscribe_handlers.append(unsubscribe)

        # Schedule a delayed refresh to find location status sensors
        # This is necessary because location status sensors may not be
        # registered in the entity registry yet when this sensor is added
        async def _delayed_refresh() -> None:
            """Refresh location status sensors after a delay."""
            await asyncio.sleep(2)  # Wait for other entities to be registered
            await self._refresh_location_status_sensors()

        self.hass.async_create_task(_delayed_refresh())

        # Update initial state (will update again after delayed refresh)
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        for unsubscribe in self._unsubscribe_handlers:
            if unsubscribe:
                unsubscribe()
        self._unsubscribe_handlers.clear()


class SoilMoistureLowMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors soil moisture levels against minimum threshold.

    This sensor turns ON (problem detected) when soil moisture reading falls
    below the minimum soil moisture threshold, indicating the plant may need watering.
    """

    def __init__(self, config: SoilMoistureLowMonitorConfig) -> None:
        """
        Initialize the Soil Moisture Low Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.soil_moisture_entity_id = config.soil_moisture_entity_id
        self._soil_moisture_entity_unique_id = config.soil_moisture_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Soil Moisture Low Monitor"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_soil_moisture_low_monitor"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._min_soil_moisture: float | None = None
        self._current_soil_moisture: float | None = None
        self._ignore_until_datetime: Any = None
        self._unsubscribe: Any = None
        self._unsubscribe_min: Any = None
        self._unsubscribe_ignore_until: Any = None

        # Initialize with current state of soil moisture entity
        if soil_moisture_state := self.hass.states.get(self.soil_moisture_entity_id):
            self._current_soil_moisture = self._parse_float(soil_moisture_state.state)

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _update_state(self) -> None:
        """Update binary sensor state based on current moisture and threshold."""
        # If either value is unavailable, set state to None (sensor unavailable)
        if self._current_soil_moisture is None or self._min_soil_moisture is None:
            self._state = None
            return

        # Check if we're currently in the ignore period
        if self._ignore_until_datetime is not None:
            try:
                now = dt_util.now()
                if now < self._ignore_until_datetime:
                    # Current time is before ignore until datetime, no problem
                    self._state = False
                    return
            except (TypeError, AttributeError) as exc:
                _LOGGER.debug("Error checking ignore until datetime: %s", exc)

        # Binary sensor is ON (problem) when current moisture < minimum threshold
        self._state = self._current_soil_moisture < self._min_soil_moisture

    async def _find_min_soil_moisture_sensor(self) -> str | None:
        """
        Find the min soil moisture aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_min_soil_moisture" in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found min soil moisture sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding min soil moisture sensor: %s", exc)

        return None

    async def _find_soil_moisture_ignore_until_entity(self) -> str | None:
        """
        Find soil moisture low threshold ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "soil_moisture_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found soil moisture ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding soil moisture ignore until entity: %s", exc)

        return None

    @callback
    def _soil_moisture_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle soil moisture sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._current_soil_moisture = None
        else:
            self._current_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_moisture_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle minimum soil moisture threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._min_soil_moisture = None
        else:
            self._min_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _soil_moisture_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle soil moisture ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._ignore_until_datetime = parsed_datetime
                else:
                    self._ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing soil moisture ignore until datetime: %s", exc
                )
                self._ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if soil moisture is below threshold (problem detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:water-minus"
        return "mdi:water-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            "type": "Critical",
            "message": "Soil Moisture Low",
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "current_soil_moisture": self._current_soil_moisture,
            "minimum_soil_moisture_threshold": self._min_soil_moisture,
            "source_entity": self.soil_moisture_entity_id,
        }

        # Add ignore until information if available
        if self._ignore_until_datetime:
            now = dt_util.now()
            attrs["ignore_until"] = self._ignore_until_datetime.isoformat()
            attrs["currently_ignoring"] = now < self._ignore_until_datetime

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        soil_moisture_state = self.hass.states.get(self.soil_moisture_entity_id)
        return soil_moisture_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored soil moisture low monitor state for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_min_soil_moisture_subscription(self) -> None:
        """Find and subscribe to min soil moisture sensor."""
        min_moisture_entity_id = await self._find_min_soil_moisture_sensor()
        if min_moisture_entity_id:
            if min_moisture_state := self.hass.states.get(min_moisture_entity_id):
                self._min_soil_moisture = self._parse_float(min_moisture_state.state)

            try:
                self._unsubscribe_min = async_track_state_change_event(
                    self.hass,
                    min_moisture_entity_id,
                    self._min_soil_moisture_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to min soil moisture sensor: %s",
                    min_moisture_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to min soil moisture sensor %s: %s",
                    min_moisture_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Min soil moisture sensor not found for location %s",
                self.location_name,
            )

    async def _setup_ignore_until_subscription(self) -> None:
        """Find and subscribe to soil moisture ignore until datetime entity."""
        ignore_until_entity_id = await self._find_soil_moisture_ignore_until_entity()
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing soil moisture ignore until datetime: %s", exc
                    )

            try:
                self._unsubscribe_ignore_until = async_track_state_change_event(
                    self.hass,
                    ignore_until_entity_id,
                    self._soil_moisture_ignore_until_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to soil moisture ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to soil moisture ignore until entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Soil moisture ignore until datetime not found for location %s",
                self.location_name,
            )

    async def _setup_soil_moisture_subscription(self) -> None:
        """Subscribe to soil moisture entity state changes."""
        # Re-resolve entity_id immediately before subscription to handle any
        # renames that occurred during initialization
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        self.soil_moisture_entity_id = (
            _resolve_entity_id(
                self.hass,
                self.soil_moisture_entity_id,
                self._soil_moisture_entity_unique_id,
            )
            or self.soil_moisture_entity_id
        )
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.soil_moisture_entity_id,
                self._soil_moisture_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to soil moisture sensor: %s",
                self.soil_moisture_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to soil moisture entity %s: %s",
                self.soil_moisture_entity_id,
                exc,
            )

    async def _resolve_entity_references(self) -> None:
        """Resolve entity references using unique_id if entity_id not found."""
        # Import helper at runtime to avoid circular imports
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        # Resolve soil moisture entity
        resolved_entity_id = _resolve_entity_id(
            self.hass,
            self.soil_moisture_entity_id,
            self._soil_moisture_entity_unique_id,
        )
        if resolved_entity_id and resolved_entity_id != self.soil_moisture_entity_id:
            _LOGGER.info(
                "Resolved soil_moisture_entity for %s: %s -> %s",
                self.location_name,
                self.soil_moisture_entity_id,
                resolved_entity_id,
            )
            self.soil_moisture_entity_id = resolved_entity_id

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Resolve entity references before subscriptions
        await self._resolve_entity_references()

        # Set up subscriptions
        await self._setup_min_soil_moisture_subscription()
        await self._setup_ignore_until_subscription()
        await self._setup_soil_moisture_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_min") and self._unsubscribe_min:
            self._unsubscribe_min()
        if (
            hasattr(self, "_unsubscribe_ignore_until")
            and self._unsubscribe_ignore_until
        ):
            self._unsubscribe_ignore_until()


class SoilMoistureHighMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors soil moisture levels against maximum threshold.

    This sensor turns ON (problem detected) when soil moisture reading exceeds
    the maximum soil moisture threshold, indicating potential overwatering or
    flooding issues.
    """

    def __init__(self, config: SoilMoistureHighMonitorConfig) -> None:
        """
        Initialize the Soil Moisture High Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.soil_moisture_entity_id = config.soil_moisture_entity_id
        self._soil_moisture_entity_unique_id = config.soil_moisture_entity_unique_id
        self.has_esphome_device = config.has_esphome_device

        # Set entity attributes
        self._attr_name = f"{self.location_name} Soil Moisture High Monitor"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_soil_moisture_high_monitor"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._max_soil_moisture: float | None = None
        self._current_soil_moisture: float | None = None
        self._ignore_until_datetime: Any = None
        self._last_watered_entity_id: str | None = None
        self._unsubscribe: Any = None
        self._unsubscribe_max: Any = None
        self._unsubscribe_ignore_until: Any = None

        # Initialize with current state of soil moisture entity
        if soil_moisture_state := self.hass.states.get(self.soil_moisture_entity_id):
            self._current_soil_moisture = self._parse_float(soil_moisture_state.state)

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _was_watered_recently(self) -> bool:
        """
        Check if plant was watered in the last 24 hours.

        This check is only performed for zones WITHOUT ESPHome devices,
        as ESPHome zones get direct watering data from irrigation events.

        Returns True if watered within last 24 hours, False otherwise.
        """
        # Skip this check if zone has ESPHome device - they have direct watering data
        if self.has_esphome_device:
            return False

        if not self._last_watered_entity_id:
            return False

        last_watered_state = self.hass.states.get(self._last_watered_entity_id)
        if not last_watered_state or last_watered_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            return False

        try:
            last_watered_time = dt_util.parse_datetime(last_watered_state.state)
            if not last_watered_time:
                return False

            now = dt_util.now()
            time_since_watering = (now - last_watered_time).total_seconds()

            # Check if within 24 hours
            if time_since_watering < SECONDS_IN_24_HOURS:
                return True

        except (ValueError, TypeError, AttributeError) as exc:
            _LOGGER.debug("Error checking last watered time: %s", exc)

        return False

    def _update_state(self) -> None:
        """Update binary sensor state based on current moisture and threshold."""
        # If either value is unavailable, set state to None (sensor unavailable)
        if self._current_soil_moisture is None or self._max_soil_moisture is None:
            self._state = None
            return

        # Check if we're currently in the ignore period
        if self._ignore_until_datetime is not None:
            try:
                now = dt_util.now()
                if now < self._ignore_until_datetime:
                    # Current time is before ignore until datetime, no problem
                    self._state = False
                    return
            except (TypeError, AttributeError) as exc:
                _LOGGER.debug("Error checking ignore until datetime: %s", exc)

        # For non-ESPHome zones, suppress if watered in last 24 hours
        if not self.has_esphome_device and self._was_watered_recently():
            self._state = False
            return

        # Binary sensor is ON (problem) when current moisture > maximum threshold
        self._state = self._current_soil_moisture > self._max_soil_moisture

    async def _find_max_soil_moisture_sensor(self) -> str | None:
        """
        Find the max soil moisture aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_max_soil_moisture" in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found max soil moisture sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding max soil moisture sensor: %s", exc)

        return None

    async def _find_soil_moisture_ignore_until_entity(self) -> str | None:
        """
        Find soil moisture high threshold ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "soil_moisture_high_threshold_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found soil moisture high ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Error finding soil moisture high ignore until entity: %s", exc
            )

        return None

    async def _find_last_watered_sensor(self) -> str | None:
        """
        Find the last watered timestamp sensor for this location.

        Only searches for non-ESPHome zones as ESPHome zones have
        direct watering data from irrigation events.

        Returns the entity_id if found, None otherwise.
        """
        # Skip for ESPHome zones
        if self.has_esphome_device:
            return None

        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_last_watered" in entity.unique_id
                ):
                    _LOGGER.debug("Found last watered sensor: %s", entity.entity_id)
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding last watered sensor: %s", exc)

        return None

    @callback
    def _soil_moisture_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle soil moisture sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._current_soil_moisture = None
        else:
            self._current_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_soil_moisture_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle maximum soil moisture threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._max_soil_moisture = None
        else:
            self._max_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _soil_moisture_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle soil moisture ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._ignore_until_datetime = parsed_datetime
                else:
                    self._ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing soil moisture ignore until datetime: %s", exc
                )
                self._ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if soil moisture is above threshold (problem detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:water-plus"
        return "mdi:water-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            "type": "Critical",
            "message": "Soil Moisture High",
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "current_soil_moisture": self._current_soil_moisture,
            "maximum_soil_moisture_threshold": self._max_soil_moisture,
            "source_entity": self.soil_moisture_entity_id,
        }

        # Add ignore until information if available
        if self._ignore_until_datetime:
            now = dt_util.now()
            attrs["ignore_until"] = self._ignore_until_datetime.isoformat()
            attrs["currently_ignoring"] = now < self._ignore_until_datetime

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        soil_moisture_state = self.hass.states.get(self.soil_moisture_entity_id)
        return soil_moisture_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored soil moisture high monitor state for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_max_soil_moisture_subscription(self) -> None:
        """Find and subscribe to max soil moisture sensor."""
        max_moisture_entity_id = await self._find_max_soil_moisture_sensor()
        if max_moisture_entity_id:
            if max_moisture_state := self.hass.states.get(max_moisture_entity_id):
                self._max_soil_moisture = self._parse_float(max_moisture_state.state)

            try:
                self._unsubscribe_max = async_track_state_change_event(
                    self.hass,
                    max_moisture_entity_id,
                    self._max_soil_moisture_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to max soil moisture sensor: %s",
                    max_moisture_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to max soil moisture sensor %s: %s",
                    max_moisture_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Max soil moisture sensor not found for location %s",
                self.location_name,
            )

    async def _setup_ignore_until_subscription(self) -> None:
        """Find and subscribe to soil moisture ignore until datetime entity."""
        ignore_until_entity_id = await self._find_soil_moisture_ignore_until_entity()
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing soil moisture ignore until datetime: %s", exc
                    )

            try:
                self._unsubscribe_ignore_until = async_track_state_change_event(
                    self.hass,
                    ignore_until_entity_id,
                    self._soil_moisture_ignore_until_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to soil moisture high ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to soil moisture high ignore until "
                    "entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Soil moisture high ignore until datetime not found for location %s",
                self.location_name,
            )

    async def _setup_last_watered_subscription(self) -> None:
        """Find last watered sensor for non-ESPHome zones."""
        # Only look for last watered sensor if zone doesn't have ESPHome device
        if self.has_esphome_device:
            _LOGGER.debug(
                "Skipping last watered sensor lookup for %s - zone has ESPHome device",
                self.location_name,
            )
            return

        last_watered_entity_id = await self._find_last_watered_sensor()
        if last_watered_entity_id:
            self._last_watered_entity_id = last_watered_entity_id
            _LOGGER.debug(
                "Found last watered sensor for %s: %s",
                self.location_name,
                last_watered_entity_id,
            )
        else:
            _LOGGER.debug(
                "Last watered sensor not found for location %s (will be created later)",
                self.location_name,
            )

    async def _setup_soil_moisture_subscription(self) -> None:
        """Subscribe to soil moisture entity state changes."""
        # Re-resolve entity_id immediately before subscription to handle any
        # renames that occurred during initialization
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        self.soil_moisture_entity_id = (
            _resolve_entity_id(
                self.hass,
                self.soil_moisture_entity_id,
                self._soil_moisture_entity_unique_id,
            )
            or self.soil_moisture_entity_id
        )
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.soil_moisture_entity_id,
                self._soil_moisture_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to soil moisture sensor: %s",
                self.soil_moisture_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to soil moisture entity %s: %s",
                self.soil_moisture_entity_id,
                exc,
            )

    async def _resolve_entity_references(self) -> None:
        """Resolve entity references using unique_id if entity_id not found."""
        # Import helper at runtime to avoid circular imports
        from .sensor import _resolve_entity_id  # noqa: PLC0415

        # Resolve soil moisture entity
        resolved_entity_id = _resolve_entity_id(
            self.hass,
            self.soil_moisture_entity_id,
            self._soil_moisture_entity_unique_id,
        )
        if resolved_entity_id and resolved_entity_id != self.soil_moisture_entity_id:
            _LOGGER.info(
                "Resolved soil_moisture_entity for %s: %s -> %s",
                self.location_name,
                self.soil_moisture_entity_id,
                resolved_entity_id,
            )
            self.soil_moisture_entity_id = resolved_entity_id

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Resolve entity references before subscriptions
        await self._resolve_entity_references()

        # Set up subscriptions
        await self._setup_max_soil_moisture_subscription()
        await self._setup_ignore_until_subscription()
        await self._setup_last_watered_subscription()
        await self._setup_soil_moisture_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_max") and self._unsubscribe_max:
            self._unsubscribe_max()
        if (
            hasattr(self, "_unsubscribe_ignore_until")
            and self._unsubscribe_ignore_until
        ):
            self._unsubscribe_ignore_until()


class SoilMoistureHighOverrideMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Informational binary sensor showing when high moisture warnings are suppressed.

    This sensor turns ON when the plant was recently watered (within 24 hours)
    AND the soil moisture is above the maximum threshold. It indicates that the
    high moisture condition exists but warnings are being suppressed because
    watering was detected.

    This sensor is only created for non-ESPHome zones where watering detection
    is inferred from moisture spikes rather than direct irrigation events.
    """

    def __init__(self, config: SoilMoistureHighOverrideMonitorConfig) -> None:
        """
        Initialize the Soil Moisture High Override Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.soil_moisture_entity_id = config.soil_moisture_entity_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Soil Moisture High Override"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_soil_moisture_high_override"
        )

        # Set binary sensor properties - this is informational, not a problem
        self._attr_device_class = None
        self._attr_icon = "mdi:water-check-outline"
        self._attr_entity_category = None  # Make it visible, not diagnostic

        # Set device info to associate with the location device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.location_device_id)},
        )

        self._state: bool | None = None
        self._soil_moisture: float | None = None
        self._max_soil_moisture: float | None = None
        self._last_watered_time: Any = None
        self._unsubscribe: Any = None
        self._unsubscribe_max: Any = None
        self._unsubscribe_last_watered: Any = None
        self._last_watered_entity_id: str | None = None

    def _was_watered_recently(self) -> bool:
        """
        Check if the plant was watered within the last 24 hours.

        Returns:
            True if watered within last 24 hours, False otherwise.

        """
        if self._last_watered_time is None:
            return False

        try:
            # Parse the last watered timestamp
            last_watered_dt = None
            if isinstance(self._last_watered_time, str):
                last_watered_dt = dt_util.parse_datetime(self._last_watered_time)
            else:
                last_watered_dt = self._last_watered_time

            if last_watered_dt is None:
                return False

            # Check if within 24 hours
            now = dt_util.now()
            time_since_watering = (now - last_watered_dt).total_seconds()

            if time_since_watering < SECONDS_IN_24_HOURS:
                return True

        except (ValueError, TypeError, AttributeError) as exc:
            _LOGGER.debug(
                "Error checking last watered time for %s: %s",
                self.location_name,
                exc,
            )

        return False

    def _update_state(self) -> None:
        """Update binary sensor state based on conditions."""
        # Sensor is unavailable if required data is missing
        if self._soil_moisture is None or self._max_soil_moisture is None:
            self._state = None
            return

        # Binary sensor is ON when:
        # 1. Plant was watered recently (within 24 hours)
        # 2. AND soil moisture is above maximum threshold
        is_above_max = self._soil_moisture > self._max_soil_moisture
        was_watered_recently = self._was_watered_recently()

        self._state = is_above_max and was_watered_recently

    async def _find_last_watered_sensor(self) -> str | None:
        """
        Find the last watered sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")
            expected_unique_id = (
                f"{DOMAIN}_{self.entry_id}_{location_name_safe}_last_watered"
            )

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id == expected_unique_id
                ):
                    _LOGGER.debug(
                        "Found last watered sensor: %s for location %s",
                        entity.entity_id,
                        self.location_name,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding last watered sensor: %s", exc)

        return None

    @callback
    def _soil_moisture_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle soil moisture sensor state changes."""
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._soil_moisture = None
        else:
            try:
                self._soil_moisture = float(new_state.state)
            except (ValueError, TypeError):
                _LOGGER.debug(
                    "Could not convert soil moisture to float: %s",
                    new_state.state,
                )
                self._soil_moisture = None

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_soil_moisture_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle max soil moisture threshold sensor state changes."""
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._max_soil_moisture = None
        else:
            try:
                self._max_soil_moisture = float(new_state.state)
            except (ValueError, TypeError):
                _LOGGER.debug(
                    "Could not convert max soil moisture to float: %s",
                    new_state.state,
                )
                self._max_soil_moisture = None

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _last_watered_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle last watered sensor state changes."""
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._last_watered_time = None
        else:
            self._last_watered_time = new_state.state

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            "soil_moisture": self._soil_moisture,
            "max_soil_moisture": self._max_soil_moisture,
            "last_watered": self._last_watered_time,
            "was_watered_recently": self._was_watered_recently(),
            "suppression_period_hours": 24,
        }

    async def _restore_previous_state(self) -> None:
        """Restore previous state from last state."""
        if not (last_state := await self.async_get_last_state()):
            return

        if last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state == "on"

        if last_state.attributes:
            if (moisture := last_state.attributes.get("soil_moisture")) is not None:
                with contextlib.suppress(ValueError, TypeError):
                    self._soil_moisture = float(moisture)

            if (
                max_moist := last_state.attributes.get("max_soil_moisture")
            ) is not None:
                with contextlib.suppress(ValueError, TypeError):
                    self._max_soil_moisture = float(max_moist)

            self._last_watered_time = last_state.attributes.get("last_watered")

        _LOGGER.debug(
            "Restored soil moisture high override sensor %s with state: %s",
            self.entity_id,
            self._state,
        )

    async def _setup_last_watered_listener(self) -> None:
        """Set up listener for last watered sensor."""
        self._last_watered_entity_id = await self._find_last_watered_sensor()
        if not self._last_watered_entity_id:
            return

        if (
            initial_state := self.hass.states.get(self._last_watered_entity_id)
        ) and initial_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._last_watered_time = initial_state.state

        self._unsubscribe_last_watered = async_track_state_change_event(
            self.hass,
            [self._last_watered_entity_id],
            self._last_watered_state_changed,
        )

    async def _setup_max_moisture_listener(self) -> None:
        """Set up listener for max soil moisture threshold sensor."""
        location_name_safe = self.location_name.lower().replace(" ", "_")
        max_entity_id = f"number.{location_name_safe}_max_soil_moisture"

        if not self.hass.states.get(max_entity_id):
            return

        if (
            initial_state := self.hass.states.get(max_entity_id)
        ) and initial_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            with contextlib.suppress(ValueError, TypeError):
                self._max_soil_moisture = float(initial_state.state)

        self._unsubscribe_max = async_track_state_change_event(
            self.hass,
            [max_entity_id],
            self._max_soil_moisture_state_changed,
        )

    async def _setup_moisture_listener(self) -> None:
        """Set up listener for soil moisture sensor."""
        try:
            if (
                initial_state := self.hass.states.get(self.soil_moisture_entity_id)
            ) and initial_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                with contextlib.suppress(ValueError, TypeError):
                    self._soil_moisture = float(initial_state.state)

            self._unsubscribe = async_track_state_change_event(
                self.hass,
                [self.soil_moisture_entity_id],
                self._soil_moisture_state_changed,
            )
            _LOGGER.debug(
                "Set up state listener for %s tracking %s",
                self.location_name,
                self.soil_moisture_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up state listener for %s: %s",
                self.location_name,
                exc,
            )

    async def async_added_to_hass(self) -> None:
        """Set up state listeners when entity is added to hass."""
        await super().async_added_to_hass()

        await self._restore_previous_state()
        await self._setup_last_watered_listener()
        await self._setup_max_moisture_listener()
        await self._setup_moisture_listener()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_max") and self._unsubscribe_max:
            self._unsubscribe_max()
        if (
            hasattr(self, "_unsubscribe_last_watered")
            and self._unsubscribe_last_watered
        ):
            self._unsubscribe_last_watered()


class SoilMoistureWaterSoonMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors soil moisture approaching minimum threshold.

    This sensor turns ON (problem detected) when soil moisture reading falls
    within a warning zone (low threshold to low threshold + 5%), indicating
    the plant will soon need watering but hasn't reached critical levels yet.
    It will not show a problem if the low threshold has already been reached.
    """

    def __init__(self, config: SoilMoistureWaterSoonMonitorConfig) -> None:
        """
        Initialize the Soil Moisture Water Soon Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.soil_moisture_entity_id = config.soil_moisture_entity_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Soil Moisture Water Soon Monitor"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}"
            "_soil_moisture_water_soon_monitor"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._min_soil_moisture: float | None = None
        self._current_soil_moisture: float | None = None
        self._unsubscribe: Any = None
        self._unsubscribe_min: Any = None

        # Initialize with current state of soil moisture entity
        if soil_moisture_state := self.hass.states.get(self.soil_moisture_entity_id):
            self._current_soil_moisture = self._parse_float(soil_moisture_state.state)

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _update_state(self) -> None:
        """Update binary sensor state based on current moisture and threshold."""
        # If either value is unavailable, set state to None (sensor unavailable)
        if self._current_soil_moisture is None or self._min_soil_moisture is None:
            self._state = None
            return

        # Water Soon threshold is low threshold + 5 percentage points
        water_soon_threshold = self._min_soil_moisture + 5

        # Binary sensor is ON (problem) when:
        # current moisture <= water_soon_threshold AND current moisture >= low_threshold
        # This means the plant doesn't have a critical problem yet, but water soon
        self._state = (
            self._current_soil_moisture <= water_soon_threshold
            and self._current_soil_moisture >= self._min_soil_moisture
        )

    async def _find_min_soil_moisture_sensor(self) -> str | None:
        """
        Find the min soil moisture aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_min_soil_moisture" in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found min soil moisture sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding min soil moisture sensor: %s", exc)

        return None

    @callback
    def _soil_moisture_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle soil moisture sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._current_soil_moisture = None
        else:
            self._current_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_moisture_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle minimum soil moisture threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._min_soil_moisture = None
        else:
            self._min_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if soil moisture is in water soon zone (warning detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:watering-can"
        return "mdi:water-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            "type": "Warning",
            "message": "Soil Moisture Water Soon",
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "current_soil_moisture": self._current_soil_moisture,
            "minimum_soil_moisture_threshold": self._min_soil_moisture,
            "source_entity": self.soil_moisture_entity_id,
        }

        # Add water soon threshold information
        if self._min_soil_moisture is not None:
            water_soon_threshold = self._min_soil_moisture + 5
            attrs["water_soon_threshold"] = water_soon_threshold

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        soil_moisture_state = self.hass.states.get(self.soil_moisture_entity_id)
        return soil_moisture_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored soil moisture water soon monitor state for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_min_soil_moisture_subscription(self) -> None:
        """Find and subscribe to min soil moisture sensor."""
        min_moisture_entity_id = await self._find_min_soil_moisture_sensor()
        if min_moisture_entity_id:
            if min_moisture_state := self.hass.states.get(min_moisture_entity_id):
                self._min_soil_moisture = self._parse_float(min_moisture_state.state)

            try:
                self._unsubscribe_min = async_track_state_change_event(
                    self.hass,
                    min_moisture_entity_id,
                    self._min_soil_moisture_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to min soil moisture sensor: %s",
                    min_moisture_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to min soil moisture sensor %s: %s",
                    min_moisture_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Min soil moisture sensor not found for location %s",
                self.location_name,
            )

    async def _setup_soil_moisture_subscription(self) -> None:
        """Subscribe to soil moisture entity state changes."""
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.soil_moisture_entity_id,
                self._soil_moisture_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to soil moisture sensor: %s",
                self.soil_moisture_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to soil moisture entity %s: %s",
                self.soil_moisture_entity_id,
                exc,
            )

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Set up subscriptions
        await self._setup_min_soil_moisture_subscription()
        await self._setup_soil_moisture_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_min") and self._unsubscribe_min:
            self._unsubscribe_min()


class SoilConductivityLowMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors soil conductivity levels against minimum threshold.

    This sensor turns ON (problem detected) when soil conductivity reading falls
    below the minimum soil conductivity threshold. Additionally, soil moisture must
    be at least 10 percentage points above the soil moisture low threshold to raise
    a problem, indicating insufficient nutrient levels only when soil has adequate
    moisture.
    """

    def __init__(self, config: SoilConductivityLowMonitorConfig) -> None:
        """
        Initialize the Soil Conductivity Low Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.soil_conductivity_entity_id = config.soil_conductivity_entity_id
        self.soil_moisture_entity_id = config.soil_moisture_entity_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Soil Conductivity Low Monitor"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_"
            "soil_conductivity_low_monitor"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._min_soil_conductivity: float | None = None
        self._current_soil_conductivity: float | None = None
        self._min_soil_moisture: float | None = None
        self._current_soil_moisture: float | None = None
        self._unsubscribe: Any = None
        self._unsubscribe_conductivity_min: Any = None
        self._unsubscribe_moisture: Any = None
        self._unsubscribe_moisture_min: Any = None

        # Initialize with current state of soil conductivity entity
        if conductivity_state := self.hass.states.get(self.soil_conductivity_entity_id):
            self._current_soil_conductivity = self._parse_float(
                conductivity_state.state
            )

        # Initialize with current state of soil moisture entity
        if moisture_state := self.hass.states.get(self.soil_moisture_entity_id):
            self._current_soil_moisture = self._parse_float(moisture_state.state)

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _update_state(self) -> None:
        """Update binary sensor state based on conductivity and moisture levels."""
        # If any required value is unavailable, set state to None (sensor unavailable)
        if (
            self._current_soil_conductivity is None
            or self._min_soil_conductivity is None
            or self._current_soil_moisture is None
            or self._min_soil_moisture is None
        ):
            self._state = None
            return

        # Problem is raised when:
        # 1. Soil conductivity is below the low threshold AND
        # 2. Soil moisture is at least 10 percentage points above the low threshold
        conductivity_below_threshold = (
            self._current_soil_conductivity < self._min_soil_conductivity
        )
        moisture_above_threshold = (
            self._current_soil_moisture >= self._min_soil_moisture + 10
        )

        self._state = conductivity_below_threshold and moisture_above_threshold

    async def _find_min_soil_conductivity_sensor(self) -> str | None:
        """
        Find the min soil conductivity aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_min_soil_conductivity"
                    in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found min soil conductivity sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding min soil conductivity sensor: %s", exc)

        return None

    async def _find_min_soil_moisture_sensor(self) -> str | None:
        """
        Find the min soil moisture aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_min_soil_moisture" in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found min soil moisture sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding min soil moisture sensor: %s", exc)

        return None

    @callback
    def _soil_conductivity_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle soil conductivity sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._current_soil_conductivity = None
        else:
            self._current_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_conductivity_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle minimum soil conductivity threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._min_soil_conductivity = None
        else:
            self._min_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _soil_moisture_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle soil moisture sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._current_soil_moisture = None
        else:
            self._current_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_moisture_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle minimum soil moisture threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._min_soil_moisture = None
        else:
            self._min_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if soil conductivity is below threshold (problem detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:flash-off"
        return "mdi:flash-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = {
            "type": "Critical",
            "message": "Soil Conductivity Low",
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "current_soil_conductivity": self._current_soil_conductivity,
            "minimum_soil_conductivity_threshold": self._min_soil_conductivity,
            "current_soil_moisture": self._current_soil_moisture,
            "minimum_soil_moisture_threshold": self._min_soil_moisture,
            "source_entity": self.soil_conductivity_entity_id,
            "moisture_source_entity": self.soil_moisture_entity_id,
        }

        # Add derived attributes for monitoring conditions
        if self._min_soil_moisture is not None:
            attrs["soil_moisture_threshold_for_conductivity_check"] = (
                self._min_soil_moisture + 10
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        conductivity_state = self.hass.states.get(self.soil_conductivity_entity_id)
        moisture_state = self.hass.states.get(self.soil_moisture_entity_id)
        return conductivity_state is not None and moisture_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored soil conductivity low monitor state for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_soil_conductivity_subscription(self) -> None:
        """Subscribe to soil conductivity entity state changes."""
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.soil_conductivity_entity_id,
                self._soil_conductivity_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to soil conductivity sensor: %s",
                self.soil_conductivity_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to soil conductivity entity %s: %s",
                self.soil_conductivity_entity_id,
                exc,
            )

    async def _setup_soil_moisture_subscription(self) -> None:
        """Subscribe to soil moisture entity state changes."""
        try:
            self._unsubscribe_moisture = async_track_state_change_event(
                self.hass,
                self.soil_moisture_entity_id,
                self._soil_moisture_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to soil moisture sensor: %s",
                self.soil_moisture_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to soil moisture entity %s: %s",
                self.soil_moisture_entity_id,
                exc,
            )

    async def _setup_min_soil_conductivity_subscription(self) -> None:
        """Find and subscribe to min soil conductivity sensor."""
        min_conductivity_entity_id = await self._find_min_soil_conductivity_sensor()
        if min_conductivity_entity_id:
            if min_conductivity_state := self.hass.states.get(
                min_conductivity_entity_id
            ):
                self._min_soil_conductivity = self._parse_float(
                    min_conductivity_state.state
                )

            try:
                self._unsubscribe_conductivity_min = async_track_state_change_event(
                    self.hass,
                    min_conductivity_entity_id,
                    self._min_soil_conductivity_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to min soil conductivity sensor: %s",
                    min_conductivity_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to min soil conductivity sensor %s: %s",
                    min_conductivity_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Min soil conductivity sensor not found for location %s",
                self.location_name,
            )

    async def _setup_min_soil_moisture_subscription(self) -> None:
        """Find and subscribe to min soil moisture sensor."""
        min_moisture_entity_id = await self._find_min_soil_moisture_sensor()
        if min_moisture_entity_id:
            if min_moisture_state := self.hass.states.get(min_moisture_entity_id):
                self._min_soil_moisture = self._parse_float(min_moisture_state.state)

            try:
                self._unsubscribe_moisture_min = async_track_state_change_event(
                    self.hass,
                    min_moisture_entity_id,
                    self._min_soil_moisture_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to min soil moisture sensor: %s",
                    min_moisture_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to min soil moisture sensor %s: %s",
                    min_moisture_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Min soil moisture sensor not found for location %s",
                self.location_name,
            )

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Set up subscriptions
        await self._setup_soil_conductivity_subscription()
        await self._setup_soil_moisture_subscription()
        await self._setup_min_soil_conductivity_subscription()
        await self._setup_min_soil_moisture_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_moisture") and self._unsubscribe_moisture:
            self._unsubscribe_moisture()
        if (
            hasattr(self, "_unsubscribe_conductivity_min")
            and self._unsubscribe_conductivity_min
        ):
            self._unsubscribe_conductivity_min()
        if (
            hasattr(self, "_unsubscribe_moisture_min")
            and self._unsubscribe_moisture_min
        ):
            self._unsubscribe_moisture_min()


class SoilConductivityHighMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors soil conductivity levels against maximum threshold.

    This sensor turns ON (problem detected) when soil conductivity reading exceeds
    the maximum soil conductivity threshold, indicating potential salt accumulation
    or over-fertilization.
    """

    def __init__(self, config: SoilConductivityHighMonitorConfig) -> None:
        """
        Initialize the Soil Conductivity High Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.soil_conductivity_entity_id = config.soil_conductivity_entity_id
        self.has_esphome_device = config.has_esphome_device

        # Set entity attributes
        self._attr_name = f"{self.location_name} Soil Conductivity High Monitor"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_"
            "soil_conductivity_high_monitor"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._max_soil_conductivity: float | None = None
        self._current_soil_conductivity: float | None = None
        self._last_watered_entity_id: str | None = None
        self._unsubscribe: Any = None
        self._unsubscribe_conductivity_max: Any = None

        # Initialize with current state of soil conductivity entity
        if conductivity_state := self.hass.states.get(self.soil_conductivity_entity_id):
            self._current_soil_conductivity = self._parse_float(
                conductivity_state.state
            )

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _was_watered_recently(self) -> bool:
        """
        Check if plant was watered in the last 24 hours.

        This check is only performed for zones WITHOUT ESPHome devices,
        as ESPHome zones get direct watering data from irrigation events.

        Returns True if watered within last 24 hours, False otherwise.
        """
        # Skip this check if zone has ESPHome device - they have direct watering data
        if self.has_esphome_device:
            return False

        if not self._last_watered_entity_id:
            return False

        last_watered_state = self.hass.states.get(self._last_watered_entity_id)
        if not last_watered_state or last_watered_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            return False

        try:
            last_watered_time = dt_util.parse_datetime(last_watered_state.state)
            if not last_watered_time:
                return False

            now = dt_util.now()
            time_since_watering = (now - last_watered_time).total_seconds()

            # Check if within 24 hours
            if time_since_watering < SECONDS_IN_24_HOURS:
                return True

        except (ValueError, TypeError, AttributeError) as exc:
            _LOGGER.debug("Error checking last watered time: %s", exc)

        return False

    def _update_state(self) -> None:
        """Update binary sensor state based on conductivity and maximum threshold."""
        # If either value is unavailable, set state to None (sensor unavailable)
        if (
            self._current_soil_conductivity is None
            or self._max_soil_conductivity is None
        ):
            self._state = None
            return

        # For non-ESPHome zones, suppress if watered recently
        if not self.has_esphome_device and self._was_watered_recently():
            self._state = False
            return

        # Binary sensor is ON (problem) when current conductivity > maximum threshold
        self._state = self._current_soil_conductivity > self._max_soil_conductivity

    async def _find_max_soil_conductivity_sensor(self) -> str | None:
        """
        Find the max soil conductivity aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_max_soil_conductivity"
                    in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found max soil conductivity sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding max soil conductivity sensor: %s", exc)

        return None

    async def _find_last_watered_sensor(self) -> str | None:
        """
        Find the last watered timestamp sensor for this location.

        Only searches for non-ESPHome zones as ESPHome zones have
        direct watering data from irrigation events.

        Returns the entity_id if found, None otherwise.
        """
        # Skip for ESPHome zones
        if self.has_esphome_device:
            return None

        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_last_watered" in entity.unique_id
                ):
                    _LOGGER.debug("Found last watered sensor: %s", entity.entity_id)
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding last watered sensor: %s", exc)

        return None

    @callback
    def _soil_conductivity_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle soil conductivity sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._current_soil_conductivity = None
        else:
            self._current_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_soil_conductivity_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle maximum soil conductivity threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._max_soil_conductivity = None
        else:
            self._max_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if soil conductivity is above threshold (problem detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:flash-alert"
        return "mdi:flash-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return {
            "type": "Critical",
            "message": "Soil Conductivity High",
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "current_soil_conductivity": self._current_soil_conductivity,
            "maximum_soil_conductivity_threshold": self._max_soil_conductivity,
            "source_entity": self.soil_conductivity_entity_id,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        conductivity_state = self.hass.states.get(self.soil_conductivity_entity_id)
        return conductivity_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored soil conductivity high monitor state for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_soil_conductivity_subscription(self) -> None:
        """Subscribe to soil conductivity entity state changes."""
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.soil_conductivity_entity_id,
                self._soil_conductivity_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to soil conductivity sensor: %s",
                self.soil_conductivity_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to soil conductivity entity %s: %s",
                self.soil_conductivity_entity_id,
                exc,
            )

    async def _setup_max_soil_conductivity_subscription(self) -> None:
        """Find and subscribe to max soil conductivity sensor."""
        max_conductivity_entity_id = await self._find_max_soil_conductivity_sensor()
        if max_conductivity_entity_id:
            if max_conductivity_state := self.hass.states.get(
                max_conductivity_entity_id
            ):
                self._max_soil_conductivity = self._parse_float(
                    max_conductivity_state.state
                )

            try:
                self._unsubscribe_conductivity_max = async_track_state_change_event(
                    self.hass,
                    max_conductivity_entity_id,
                    self._max_soil_conductivity_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to max soil conductivity sensor: %s",
                    max_conductivity_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to max soil conductivity sensor %s: %s",
                    max_conductivity_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Max soil conductivity sensor not found for location %s",
                self.location_name,
            )

    async def _setup_last_watered_subscription(self) -> None:
        """Find last watered sensor for non-ESPHome zones."""
        # Only look for last watered sensor if zone doesn't have ESPHome device
        if self.has_esphome_device:
            _LOGGER.debug(
                "Skipping last watered sensor lookup for %s - zone has ESPHome device",
                self.location_name,
            )
            return

        last_watered_entity_id = await self._find_last_watered_sensor()
        if last_watered_entity_id:
            self._last_watered_entity_id = last_watered_entity_id
            _LOGGER.debug(
                "Found last watered sensor for %s: %s",
                self.location_name,
                last_watered_entity_id,
            )
        else:
            _LOGGER.debug(
                "Last watered sensor not found for location %s (will be created later)",
                self.location_name,
            )

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Set up subscriptions
        await self._setup_soil_conductivity_subscription()
        await self._setup_max_soil_conductivity_subscription()
        await self._setup_last_watered_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if (
            hasattr(self, "_unsubscribe_conductivity_max")
            and self._unsubscribe_conductivity_max
        ):
            self._unsubscribe_conductivity_max()


class SoilConductivityHighOverrideMonitorBinarySensor(
    BinarySensorEntity, RestoreEntity
):
    """
    Informational binary sensor showing when high conductivity warnings are suppressed.

    This sensor turns ON when the plant was recently watered (within 24 hours)
    AND the soil conductivity is above the maximum threshold. It indicates that the
    high conductivity condition exists but warnings are being suppressed because
    watering was detected.

    This sensor is only created for non-ESPHome zones where watering detection
    is inferred from moisture spikes rather than direct irrigation events.
    """

    def __init__(self, config: SoilConductivityHighOverrideMonitorConfig) -> None:
        """
        Initialize the Soil Conductivity High Override Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.soil_conductivity_entity_id = config.soil_conductivity_entity_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Soil Conductivity High Override"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}"
            "_soil_conductivity_high_override"
        )

        # Set binary sensor properties - this is informational, not a problem
        self._attr_device_class = None
        self._attr_icon = "mdi:sprout-outline"
        self._attr_entity_category = None  # Make it visible, not diagnostic

        # Set device info to associate with the location device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.location_device_id)},
        )

        self._state: bool | None = None
        self._soil_conductivity: float | None = None
        self._max_soil_conductivity: float | None = None
        self._last_watered_time: Any = None
        self._unsubscribe: Any = None
        self._unsubscribe_max: Any = None
        self._unsubscribe_last_watered: Any = None
        self._last_watered_entity_id: str | None = None

    def _was_watered_recently(self) -> bool:
        """
        Check if the plant was watered within the last 24 hours.

        Returns:
            True if watered within last 24 hours, False otherwise.

        """
        if self._last_watered_time is None:
            return False

        try:
            # Parse the last watered timestamp
            last_watered_dt = None
            if isinstance(self._last_watered_time, str):
                last_watered_dt = dt_util.parse_datetime(self._last_watered_time)
            else:
                last_watered_dt = self._last_watered_time

            if last_watered_dt is None:
                return False

            # Check if within 24 hours
            now = dt_util.now()
            time_since_watering = (now - last_watered_dt).total_seconds()

            if time_since_watering < SECONDS_IN_24_HOURS:
                return True

        except (ValueError, TypeError, AttributeError) as exc:
            _LOGGER.debug(
                "Error checking last watered time for %s: %s",
                self.location_name,
                exc,
            )

        return False

    def _update_state(self) -> None:
        """Update binary sensor state based on conditions."""
        # Sensor is unavailable if required data is missing
        if self._soil_conductivity is None or self._max_soil_conductivity is None:
            self._state = None
            return

        # Binary sensor is ON when:
        # 1. Plant was watered recently (within 24 hours)
        # 2. AND soil conductivity is above maximum threshold
        is_above_max = self._soil_conductivity > self._max_soil_conductivity
        was_watered_recently = self._was_watered_recently()

        self._state = is_above_max and was_watered_recently

    async def _find_last_watered_sensor(self) -> str | None:
        """
        Find the last watered sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")
            expected_unique_id = (
                f"{DOMAIN}_{self.entry_id}_{location_name_safe}_last_watered"
            )

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id == expected_unique_id
                ):
                    _LOGGER.debug(
                        "Found last watered sensor: %s for location %s",
                        entity.entity_id,
                        self.location_name,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding last watered sensor: %s", exc)

        return None

    @callback
    def _soil_conductivity_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle soil conductivity sensor state changes."""
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._soil_conductivity = None
        else:
            try:
                self._soil_conductivity = float(new_state.state)
            except (ValueError, TypeError):
                _LOGGER.debug(
                    "Could not convert soil conductivity to float: %s",
                    new_state.state,
                )
                self._soil_conductivity = None

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_soil_conductivity_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle max soil conductivity threshold sensor state changes."""
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._max_soil_conductivity = None
        else:
            try:
                self._max_soil_conductivity = float(new_state.state)
            except (ValueError, TypeError):
                _LOGGER.debug(
                    "Could not convert max soil conductivity to float: %s",
                    new_state.state,
                )
                self._max_soil_conductivity = None

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _last_watered_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle last watered sensor state changes."""
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._last_watered_time = None
        else:
            self._last_watered_time = new_state.state

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            "soil_conductivity": self._soil_conductivity,
            "max_soil_conductivity": self._max_soil_conductivity,
            "last_watered": self._last_watered_time,
            "was_watered_recently": self._was_watered_recently(),
            "suppression_period_hours": 24,
        }

    async def _restore_previous_state(self) -> None:
        """Restore previous state from last state."""
        if not (last_state := await self.async_get_last_state()):
            return

        if last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state == "on"

        if last_state.attributes:
            if (
                conductivity := last_state.attributes.get("soil_conductivity")
            ) is not None:
                with contextlib.suppress(ValueError, TypeError):
                    self._soil_conductivity = float(conductivity)

            if (
                max_cond := last_state.attributes.get("max_soil_conductivity")
            ) is not None:
                with contextlib.suppress(ValueError, TypeError):
                    self._max_soil_conductivity = float(max_cond)

            self._last_watered_time = last_state.attributes.get("last_watered")

        _LOGGER.debug(
            "Restored soil conductivity high override sensor %s with state: %s",
            self.entity_id,
            self._state,
        )

    async def _setup_last_watered_listener(self) -> None:
        """Set up listener for last watered sensor."""
        self._last_watered_entity_id = await self._find_last_watered_sensor()
        if not self._last_watered_entity_id:
            return

        if (
            initial_state := self.hass.states.get(self._last_watered_entity_id)
        ) and initial_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._last_watered_time = initial_state.state

        self._unsubscribe_last_watered = async_track_state_change_event(
            self.hass,
            [self._last_watered_entity_id],
            self._last_watered_state_changed,
        )

    async def _setup_max_conductivity_listener(self) -> None:
        """Set up listener for max soil conductivity threshold sensor."""
        location_name_safe = self.location_name.lower().replace(" ", "_")
        max_entity_id = f"number.{location_name_safe}_max_soil_conductivity"

        if not self.hass.states.get(max_entity_id):
            return

        if (
            initial_state := self.hass.states.get(max_entity_id)
        ) and initial_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            with contextlib.suppress(ValueError, TypeError):
                self._max_soil_conductivity = float(initial_state.state)

        self._unsubscribe_max = async_track_state_change_event(
            self.hass,
            [max_entity_id],
            self._max_soil_conductivity_state_changed,
        )

    async def _setup_conductivity_listener(self) -> None:
        """Set up listener for soil conductivity sensor."""
        try:
            if (
                initial_state := self.hass.states.get(self.soil_conductivity_entity_id)
            ) and initial_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                with contextlib.suppress(ValueError, TypeError):
                    self._soil_conductivity = float(initial_state.state)

            self._unsubscribe = async_track_state_change_event(
                self.hass,
                [self.soil_conductivity_entity_id],
                self._soil_conductivity_state_changed,
            )
            _LOGGER.debug(
                "Set up state listener for %s tracking %s",
                self.location_name,
                self.soil_conductivity_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up state listener for %s: %s",
                self.location_name,
                exc,
            )

    async def async_added_to_hass(self) -> None:
        """Set up state listeners when entity is added to hass."""
        await super().async_added_to_hass()

        await self._restore_previous_state()
        await self._setup_last_watered_listener()
        await self._setup_max_conductivity_listener()
        await self._setup_conductivity_listener()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_max") and self._unsubscribe_max:
            self._unsubscribe_max()
        if (
            hasattr(self, "_unsubscribe_last_watered")
            and self._unsubscribe_last_watered
        ):
            self._unsubscribe_last_watered()


class SoilConductivityStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors soil conductivity status against thresholds.

    This sensor combines conductivity monitoring into a single entity with a status
    field. The sensor turns ON (problem detected) when conductivity is outside the
    acceptable range (below minimum or above maximum). The status attribute
    indicates whether the issue is 'low', 'high', or 'normal'.
    """

    def __init__(self, config: SoilConductivityStatusMonitorConfig) -> None:
        """
        Initialize the Soil Conductivity Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.soil_conductivity_entity_id = config.soil_conductivity_entity_id
        self.soil_conductivity_entity_unique_id = (
            config.soil_conductivity_entity_unique_id
        )
        self.has_esphome_device = config.has_esphome_device

        # Set entity attributes
        self._attr_name = f"{self.location_name} Soil Conductivity Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_soil_conductivity_status"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._conductivity_status: str = "normal"  # 'low', 'normal', or 'high'
        self._min_soil_conductivity: float | None = 0.0
        self._max_soil_conductivity: float | None = 0.0
        self._current_soil_conductivity: float | None = 0.0
        self._last_watered_entity_id: str | None = None
        self._unsubscribe: Any = None
        self._unsubscribe_conductivity_min: Any = None
        self._unsubscribe_conductivity_max: Any = None

        # Initialize with current state of soil conductivity entity
        if conductivity_state := self.hass.states.get(self.soil_conductivity_entity_id):
            self._current_soil_conductivity = self._parse_float(
                conductivity_state.state
            )

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _was_watered_recently(self) -> bool:
        """
        Check if plant was watered in the last 24 hours.

        This check is only performed for zones WITHOUT ESPHome devices,
        as ESPHome zones get direct watering data from irrigation events.

        Returns True if watered within last 24 hours, False otherwise.
        """
        # Skip this check if zone has ESPHome device - they have direct watering data
        if self.has_esphome_device:
            return False

        if not self._last_watered_entity_id:
            return False

        last_watered_state = self.hass.states.get(self._last_watered_entity_id)
        if not last_watered_state or last_watered_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            return False

        try:
            last_watered_time = dt_util.parse_datetime(last_watered_state.state)
            if not last_watered_time:
                return False

            now = dt_util.now()
            time_since_watering = (now - last_watered_time).total_seconds()

            # Check if within 24 hours
            if time_since_watering < SECONDS_IN_24_HOURS:
                return True

        except (ValueError, TypeError, AttributeError) as exc:
            _LOGGER.debug("Error checking last watered time: %s", exc)

        return False

    def _update_state(self) -> None:
        """Update binary sensor state based on conductivity and thresholds."""
        # If any required value is unavailable, set state to None (sensor unavailable)
        if (
            self._current_soil_conductivity is None
            or self._min_soil_conductivity is None
            or self._max_soil_conductivity is None
        ):
            self._state = None
            self._conductivity_status = "normal"
            return

        # Determine status and state
        if self._current_soil_conductivity < self._min_soil_conductivity:
            self._state = True
            self._conductivity_status = "low"
        elif self._current_soil_conductivity > self._max_soil_conductivity:
            # For non-ESPHome zones, suppress high conductivity if watered recently
            if not self.has_esphome_device and self._was_watered_recently():
                self._state = False
                self._conductivity_status = "normal"
            else:
                self._state = True
                self._conductivity_status = "high"
        else:
            self._state = False
            self._conductivity_status = "normal"

    async def _find_min_soil_conductivity_sensor(self) -> str | None:
        """
        Find the min soil conductivity aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_min_soil_conductivity"
                    in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found min soil conductivity sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding min soil conductivity sensor: %s", exc)

        return None

    async def _find_max_soil_conductivity_sensor(self) -> str | None:
        """
        Find the max soil conductivity aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_max_soil_conductivity"
                    in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found max soil conductivity sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding max soil conductivity sensor: %s", exc)

        return None

    async def _find_last_watered_sensor(self) -> str | None:
        """
        Find the last watered timestamp sensor for this location.

        Only searches for non-ESPHome zones as ESPHome zones have
        direct watering data from irrigation events.

        Returns the entity_id if found, None otherwise.
        """
        # Skip for ESPHome zones
        if self.has_esphome_device:
            return None

        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_last_watered" in entity.unique_id
                ):
                    _LOGGER.debug("Found last watered sensor: %s", entity.entity_id)
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding last watered sensor: %s", exc)

        return None

    @callback
    def _soil_conductivity_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle soil conductivity sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._current_soil_conductivity = None
        else:
            self._current_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_conductivity_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle minimum soil conductivity threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._min_soil_conductivity = None
        else:
            self._min_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_soil_conductivity_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle maximum soil conductivity threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._max_soil_conductivity = None
        else:
            self._max_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if conductivity is outside acceptable range (problem)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state and status."""
        if self._state is True:
            if self._conductivity_status == "low":
                return "mdi:flash-off"
            if self._conductivity_status == "high":
                return "mdi:flash-alert"
        return "mdi:flash-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return {
            "type": "Critical",
            "message": f"Soil Conductivity {self._conductivity_status.capitalize()}",
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "current_soil_conductivity": self._current_soil_conductivity,
            "minimum_soil_conductivity_threshold": self._min_soil_conductivity,
            "maximum_soil_conductivity_threshold": self._max_soil_conductivity,
            "source_entity": self.soil_conductivity_entity_id,
            "conductivity_status": self._conductivity_status,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Try resolved entity ID first, fallback to stored ID
        resolved_conductivity_entity_id = _resolve_entity_id(
            self.hass,
            self.soil_conductivity_entity_id,
            self.soil_conductivity_entity_unique_id,
        )
        if not resolved_conductivity_entity_id:
            return False
        conductivity_state = self.hass.states.get(resolved_conductivity_entity_id)
        return conductivity_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                self._conductivity_status = last_state.attributes.get(
                    "conductivity_status", "normal"
                )
                _LOGGER.info(
                    "Restored soil conductivity status for %s: %s (%s)",
                    self.location_name,
                    self._state,
                    self._conductivity_status,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_soil_conductivity_subscription(self) -> None:
        """Subscribe to soil conductivity entity state changes."""
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.soil_conductivity_entity_id,
                self._soil_conductivity_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to soil conductivity sensor: %s",
                self.soil_conductivity_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to soil conductivity entity %s: %s",
                self.soil_conductivity_entity_id,
                exc,
            )

    async def _setup_min_soil_conductivity_subscription(self) -> None:
        """Find and subscribe to min soil conductivity sensor."""
        min_conductivity_entity_id = await self._find_min_soil_conductivity_sensor()
        if min_conductivity_entity_id:
            if min_conductivity_state := self.hass.states.get(
                min_conductivity_entity_id
            ):
                self._min_soil_conductivity = self._parse_float(
                    min_conductivity_state.state
                )

            try:
                self._unsubscribe_conductivity_min = async_track_state_change_event(
                    self.hass,
                    min_conductivity_entity_id,
                    self._min_soil_conductivity_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to min soil conductivity sensor: %s",
                    min_conductivity_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to min soil conductivity sensor %s: %s",
                    min_conductivity_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Min soil conductivity sensor not found for location %s",
                self.location_name,
            )

    async def _setup_max_soil_conductivity_subscription(self) -> None:
        """Find and subscribe to max soil conductivity sensor."""
        max_conductivity_entity_id = await self._find_max_soil_conductivity_sensor()
        if max_conductivity_entity_id:
            if max_conductivity_state := self.hass.states.get(
                max_conductivity_entity_id
            ):
                self._max_soil_conductivity = self._parse_float(
                    max_conductivity_state.state
                )

            try:
                self._unsubscribe_conductivity_max = async_track_state_change_event(
                    self.hass,
                    max_conductivity_entity_id,
                    self._max_soil_conductivity_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to max soil conductivity sensor: %s",
                    max_conductivity_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to max soil conductivity sensor %s: %s",
                    max_conductivity_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Max soil conductivity sensor not found for location %s",
                self.location_name,
            )

    async def _setup_last_watered_subscription(self) -> None:
        """Find last watered sensor for non-ESPHome zones."""
        # Only find last watered sensor for non-ESPHome zones
        if not self.has_esphome_device:
            last_watered_entity_id = await self._find_last_watered_sensor()
            if last_watered_entity_id:
                self._last_watered_entity_id = last_watered_entity_id
                _LOGGER.debug(
                    "Found last watered sensor for %s: %s",
                    self.location_name,
                    last_watered_entity_id,
                )
            else:
                _LOGGER.debug(
                    "No last watered sensor found for location %s",
                    self.location_name,
                )

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Set up subscriptions
        await self._setup_soil_conductivity_subscription()
        await self._setup_min_soil_conductivity_subscription()
        await self._setup_max_soil_conductivity_subscription()
        await self._setup_last_watered_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if (
            hasattr(self, "_unsubscribe_conductivity_min")
            and self._unsubscribe_conductivity_min
        ):
            self._unsubscribe_conductivity_min()
        if (
            hasattr(self, "_unsubscribe_conductivity_max")
            and self._unsubscribe_conductivity_max
        ):
            self._unsubscribe_conductivity_max()


class SoilMoistureStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors soil moisture status against thresholds.

    This sensor combines moisture monitoring into a single entity with a status
    field. The sensor turns ON (problem detected) when moisture is outside the
    acceptable range (below minimum, above maximum, or in water soon zone).
    The status attribute indicates whether the issue is 'low', 'high', 'water_soon',
    or 'normal'.
    """

    def __init__(self, config: SoilMoistureStatusMonitorConfig) -> None:
        """
        Initialize the Soil Moisture Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.soil_moisture_entity_id = config.soil_moisture_entity_id
        self.soil_moisture_entity_unique_id = config.soil_moisture_entity_unique_id
        self.has_esphome_device = config.has_esphome_device

        # Set entity attributes
        self._attr_name = f"{self.location_name} Soil Moisture Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_soil_moisture_status"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._moisture_status: str = (
            "normal"  # 'low', 'high', 'water_soon', or 'normal'
        )
        self._min_soil_moisture: float | None = 0.0
        self._max_soil_moisture: float | None = 0.0
        self._current_soil_moisture: float | None = 0.0
        self._ignore_until_datetime: Any = None
        self._last_watered_entity_id: str | None = None
        self._unsubscribe: Any = None
        self._unsubscribe_moisture_min: Any = None
        self._unsubscribe_moisture_max: Any = None
        self._unsubscribe_ignore_until: Any = None

        # Initialize with current state of soil moisture entity
        if soil_moisture_state := self.hass.states.get(self.soil_moisture_entity_id):
            self._current_soil_moisture = self._parse_float(soil_moisture_state.state)

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _was_watered_recently(self) -> bool:
        """
        Check if plant was watered in the last 24 hours.

        This check is only performed for zones WITHOUT ESPHome devices,
        as ESPHome zones get direct watering data from irrigation events.

        Returns True if watered within last 24 hours, False otherwise.
        """
        # Skip this check if zone has ESPHome device - they have direct watering data
        if self.has_esphome_device:
            return False

        if not self._last_watered_entity_id:
            return False

        last_watered_state = self.hass.states.get(self._last_watered_entity_id)
        if not last_watered_state or last_watered_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            return False

        try:
            last_watered_time = dt_util.parse_datetime(last_watered_state.state)
            if not last_watered_time:
                return False

            now = dt_util.now()
            time_since_watering = (now - last_watered_time).total_seconds()

            # Check if within 24 hours
            if time_since_watering < SECONDS_IN_24_HOURS:
                return True

        except (ValueError, TypeError, AttributeError) as exc:
            _LOGGER.debug("Error checking last watered time: %s", exc)

        return False

    def _update_state(self) -> None:
        """Update binary sensor state based on moisture and thresholds."""
        # If any required value is unavailable, set state to None (sensor unavailable)
        if (
            self._current_soil_moisture is None
            or self._min_soil_moisture is None
            or self._max_soil_moisture is None
        ):
            self._state = None
            self._moisture_status = "normal"
            return

        # Check if we're currently in the ignore period
        if self._ignore_until_datetime is not None:
            try:
                now = dt_util.now()
                if now < self._ignore_until_datetime:
                    # Current time is before ignore until datetime, no problem
                    self._state = False
                    self._moisture_status = "normal"
                    return
            except (TypeError, AttributeError) as exc:
                _LOGGER.debug("Error checking ignore until datetime: %s", exc)

        # Determine status and state based on thresholds
        # Water Soon threshold is low threshold + 5 percentage points
        water_soon_threshold = self._min_soil_moisture + 5

        if self._current_soil_moisture < self._min_soil_moisture:
            self._state = True
            self._moisture_status = "low"
        elif self._current_soil_moisture > self._max_soil_moisture:
            # For non-ESPHome zones, suppress high moisture if watered in last 24 hours
            if not self.has_esphome_device and self._was_watered_recently():
                self._state = False
                self._moisture_status = "normal"
            else:
                self._state = True
                self._moisture_status = "high"
        elif (
            self._current_soil_moisture <= water_soon_threshold
            and self._current_soil_moisture >= self._min_soil_moisture
        ):
            # In water soon zone
            self._state = True
            self._moisture_status = "water_soon"
        else:
            self._state = False
            self._moisture_status = "normal"

    async def _find_min_soil_moisture_sensor(self) -> str | None:
        """
        Find the min soil moisture aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_min_soil_moisture" in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found min soil moisture sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding min soil moisture sensor: %s", exc)

        return None

    async def _find_max_soil_moisture_sensor(self) -> str | None:
        """
        Find the max soil moisture aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_max_soil_moisture" in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found max soil moisture sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding max soil moisture sensor: %s", exc)

        return None

    async def _find_soil_moisture_ignore_until_entity(self) -> str | None:
        """
        Find soil moisture low threshold ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "soil_moisture_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found soil moisture ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding soil moisture ignore until entity: %s", exc)

        return None

    async def _find_last_watered_sensor(self) -> str | None:
        """
        Find the last watered timestamp sensor for this location.

        Only searches for non-ESPHome zones as ESPHome zones have
        direct watering data from irrigation events.

        Returns the entity_id if found, None otherwise.
        """
        # Skip for ESPHome zones
        if self.has_esphome_device:
            return None

        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_last_watered" in entity.unique_id
                ):
                    _LOGGER.debug("Found last watered sensor: %s", entity.entity_id)
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding last watered sensor: %s", exc)

        return None

    @callback
    def _soil_moisture_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle soil moisture sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._current_soil_moisture = None
        else:
            self._current_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_moisture_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle minimum soil moisture threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._min_soil_moisture = None
        else:
            self._min_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_soil_moisture_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle maximum soil moisture threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._max_soil_moisture = None
        else:
            self._max_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _soil_moisture_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle soil moisture ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._ignore_until_datetime = parsed_datetime
                else:
                    self._ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing soil moisture ignore until datetime: %s", exc
                )
                self._ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if moisture is outside acceptable range (problem)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state and status."""
        if self._state is True:
            if self._moisture_status == "low":
                return "mdi:water-minus"
            if self._moisture_status == "high":
                return "mdi:water-plus"
            if self._moisture_status == "water_soon":
                return "mdi:watering-can"
        return "mdi:water-check"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        # Determine type based on moisture status
        # water_soon -> Warning, high/low -> Critical, normal -> Critical (default)
        alert_type = "Critical"
        if self._moisture_status == "water_soon":
            alert_type = "Warning"
        elif self._moisture_status in ("high", "low"):
            alert_type = "Critical"

        attrs = {
            "type": alert_type,
            "message": f"Soil Moisture {self._moisture_status.capitalize()}",
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "current_soil_moisture": self._current_soil_moisture,
            "minimum_soil_moisture_threshold": self._min_soil_moisture,
            "maximum_soil_moisture_threshold": self._max_soil_moisture,
            "source_entity": self.soil_moisture_entity_id,
            "moisture_status": self._moisture_status,
        }

        # Add water soon threshold information
        if self._min_soil_moisture is not None:
            water_soon_threshold = self._min_soil_moisture + 5
            attrs["water_soon_threshold"] = water_soon_threshold

        # Add ignore until information if available
        if self._ignore_until_datetime:
            now = dt_util.now()
            attrs["ignore_until"] = self._ignore_until_datetime.isoformat()
            attrs["currently_ignoring"] = now < self._ignore_until_datetime

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Try resolved entity ID first, fallback to stored ID
        resolved_soil_moisture_entity_id = _resolve_entity_id(
            self.hass, self.soil_moisture_entity_id, self.soil_moisture_entity_unique_id
        )
        if not resolved_soil_moisture_entity_id:
            return False
        soil_moisture_state = self.hass.states.get(resolved_soil_moisture_entity_id)
        return soil_moisture_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                self._moisture_status = last_state.attributes.get(
                    "moisture_status", "normal"
                )
                _LOGGER.info(
                    "Restored soil moisture status for %s: %s (%s)",
                    self.location_name,
                    self._state,
                    self._moisture_status,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_soil_moisture_subscription(self) -> None:
        """Subscribe to soil moisture entity state changes."""
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.soil_moisture_entity_id,
                self._soil_moisture_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to soil moisture sensor: %s",
                self.soil_moisture_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to soil moisture entity %s: %s",
                self.soil_moisture_entity_id,
                exc,
            )

    async def _setup_min_soil_moisture_subscription(self) -> None:
        """Find and subscribe to min soil moisture sensor."""
        min_moisture_entity_id = await self._find_min_soil_moisture_sensor()
        if min_moisture_entity_id:
            if min_moisture_state := self.hass.states.get(min_moisture_entity_id):
                self._min_soil_moisture = self._parse_float(min_moisture_state.state)

            try:
                self._unsubscribe_moisture_min = async_track_state_change_event(
                    self.hass,
                    min_moisture_entity_id,
                    self._min_soil_moisture_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to min soil moisture sensor: %s",
                    min_moisture_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to min soil moisture sensor %s: %s",
                    min_moisture_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Min soil moisture sensor not found for location %s",
                self.location_name,
            )

    async def _setup_max_soil_moisture_subscription(self) -> None:
        """Find and subscribe to max soil moisture sensor."""
        max_moisture_entity_id = await self._find_max_soil_moisture_sensor()
        if max_moisture_entity_id:
            if max_moisture_state := self.hass.states.get(max_moisture_entity_id):
                self._max_soil_moisture = self._parse_float(max_moisture_state.state)

            try:
                self._unsubscribe_moisture_max = async_track_state_change_event(
                    self.hass,
                    max_moisture_entity_id,
                    self._max_soil_moisture_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to max soil moisture sensor: %s",
                    max_moisture_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to max soil moisture sensor %s: %s",
                    max_moisture_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Max soil moisture sensor not found for location %s",
                self.location_name,
            )

    async def _setup_ignore_until_subscription(self) -> None:
        """Find and subscribe to soil moisture ignore until datetime entity."""
        ignore_until_entity_id = await self._find_soil_moisture_ignore_until_entity()
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing soil moisture ignore until datetime: %s", exc
                    )

            try:
                self._unsubscribe_ignore_until = async_track_state_change_event(
                    self.hass,
                    ignore_until_entity_id,
                    self._soil_moisture_ignore_until_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to soil moisture ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to soil moisture ignore until entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Soil moisture ignore until datetime not found for location %s",
                self.location_name,
            )

    async def _setup_last_watered_subscription(self) -> None:
        """Find last watered sensor for non-ESPHome zones."""
        # Only look for last watered sensor if zone doesn't have ESPHome device
        if self.has_esphome_device:
            _LOGGER.debug(
                "Skipping last watered sensor lookup for %s - zone has ESPHome device",
                self.location_name,
            )
            return

        last_watered_entity_id = await self._find_last_watered_sensor()
        if last_watered_entity_id:
            self._last_watered_entity_id = last_watered_entity_id
            _LOGGER.debug(
                "Found last watered sensor for %s: %s",
                self.location_name,
                last_watered_entity_id,
            )
        else:
            _LOGGER.debug(
                "Last watered sensor not found for location %s (will be created later)",
                self.location_name,
            )

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Set up subscriptions
        await self._setup_soil_moisture_subscription()
        await self._setup_min_soil_moisture_subscription()
        await self._setup_max_soil_moisture_subscription()
        await self._setup_ignore_until_subscription()
        await self._setup_last_watered_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if (
            hasattr(self, "_unsubscribe_moisture_min")
            and self._unsubscribe_moisture_min
        ):
            self._unsubscribe_moisture_min()
        if (
            hasattr(self, "_unsubscribe_moisture_max")
            and self._unsubscribe_moisture_max
        ):
            self._unsubscribe_moisture_max()
        if (
            hasattr(self, "_unsubscribe_ignore_until")
            and self._unsubscribe_ignore_until
        ):
            self._unsubscribe_ignore_until()


class TemperatureStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors temperature status against thresholds.

    This sensor turns ON (problem detected) when temperature is outside the
    acceptable range (above maximum or below minimum weekly duration thresholds
    for more than 2 hours).
    The status attribute indicates whether the issue is 'above', 'below', or 'normal'.
    """

    def __init__(self, config: TemperatureStatusMonitorConfig) -> None:
        """
        Initialize the Temperature Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.temperature_entity_id = config.temperature_entity_id
        self.temperature_entity_unique_id = config.temperature_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Temperature Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_temperature_status"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._temperature_status: str = "normal"  # 'above', 'below', or 'normal'
        self._above_threshold_hours: float | None = 0.0
        self._below_threshold_hours: float | None = 0.0
        self._threshold_hours: float = 2.0  # 2 hours threshold
        self._high_threshold_ignore_until_datetime: Any = None
        self._low_threshold_ignore_until_datetime: Any = None
        self._unsubscribe: Any = None
        self._unsubscribe_above: Any = None
        self._unsubscribe_below: Any = None
        self._unsubscribe_high_threshold_ignore_until: Any = None
        self._unsubscribe_low_threshold_ignore_until: Any = None

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _update_state(self) -> None:
        """Update binary sensor state based on temperature threshold durations."""
        # If either duration value is unavailable, set state to None
        if self._above_threshold_hours is None or self._below_threshold_hours is None:
            self._state = None
            self._temperature_status = "normal"
            return

        # Determine status and state based on threshold durations
        # Problem if either above or below duration exceeds 2 hours
        if self._above_threshold_hours > self._threshold_hours:
            # Check if we're currently in the high temperature ignore period
            if self._high_threshold_ignore_until_datetime is not None:
                try:
                    now = dt_util.now()
                    if now < self._high_threshold_ignore_until_datetime:
                        # Current time is before ignore until datetime, no problem
                        self._state = False
                        self._temperature_status = "normal"
                        return
                except (TypeError, AttributeError) as exc:
                    _LOGGER.debug(
                        "Error checking high temperature ignore until datetime: %s", exc
                    )
            self._state = True
            self._temperature_status = "above"
        elif self._below_threshold_hours > self._threshold_hours:
            # Check if we're currently in the low temperature ignore period
            if self._low_threshold_ignore_until_datetime is not None:
                try:
                    now = dt_util.now()
                    if now < self._low_threshold_ignore_until_datetime:
                        # Current time is before ignore until datetime, no problem
                        self._state = False
                        self._temperature_status = "normal"
                        return
                except (TypeError, AttributeError) as exc:
                    _LOGGER.debug(
                        "Error checking low temperature ignore until datetime: %s", exc
                    )
            self._state = True
            self._temperature_status = "below"
        else:
            self._state = False
            self._temperature_status = "normal"

    async def _find_above_threshold_sensor(self) -> str | None:
        """
        Find the temperature above threshold weekly duration sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")
            expected_unique_id = (
                f"{DOMAIN}_{self.entry_id}_{location_name_safe}_"
                "temperature_above_threshold_weekly_duration"
            )

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id == expected_unique_id
                ):
                    _LOGGER.debug(
                        "Found temperature above threshold sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding temperature above threshold sensor: %s", exc)

        return None

    async def _find_below_threshold_sensor(self) -> str | None:
        """
        Find the temperature below threshold weekly duration sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")
            expected_unique_id = (
                f"{DOMAIN}_{self.entry_id}_{location_name_safe}_"
                "temperature_below_threshold_weekly_duration"
            )

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id == expected_unique_id
                ):
                    _LOGGER.debug(
                        "Found temperature below threshold sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding temperature below threshold sensor: %s", exc)

        return None

    async def _find_high_threshold_ignore_until_entity(self) -> str | None:
        """
        Find temperature high threshold ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "temperature_high_threshold_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found temperature high threshold ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Error finding temperature high threshold ignore until entity: %s", exc
            )

        return None

    async def _find_low_threshold_ignore_until_entity(self) -> str | None:
        """
        Find temperature low threshold ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "temperature_low_threshold_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found temperature low threshold ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Error finding temperature low threshold ignore until entity: %s", exc
            )

        return None

    @callback
    def _above_threshold_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle temperature above threshold duration sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._above_threshold_hours = None
        else:
            self._above_threshold_hours = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _below_threshold_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle temperature below threshold duration sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._below_threshold_hours = None
        else:
            self._below_threshold_hours = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _high_threshold_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle temperature high threshold ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._high_threshold_ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._high_threshold_ignore_until_datetime = parsed_datetime
                else:
                    self._high_threshold_ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing temperature high threshold ignore until "
                    "datetime: %s",
                    exc,
                )
                self._high_threshold_ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _low_threshold_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle temperature low threshold ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._low_threshold_ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._low_threshold_ignore_until_datetime = parsed_datetime
                else:
                    self._low_threshold_ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing temperature low threshold ignore until datetime: %s",
                    exc,
                )
                self._low_threshold_ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if temperature is outside acceptable range (problem)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state and status."""
        if self._state is True:
            if self._temperature_status == "above":
                return "mdi:thermometer-high"
            if self._temperature_status == "below":
                return "mdi:thermometer-low"
        return "mdi:thermometer"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        # Alert type based on temperature status
        alert_type = "Critical"
        status_message = f"Temperature {self._temperature_status.capitalize()}"

        attrs = {
            "type": alert_type,
            "message": status_message,
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "temperature_status": self._temperature_status,
            "above_threshold_hours": self._above_threshold_hours,
            "below_threshold_hours": self._below_threshold_hours,
            "threshold_hours": self._threshold_hours,
        }

        # Add high threshold ignore until information if available
        if self._high_threshold_ignore_until_datetime:
            now = dt_util.now()
            attrs["high_threshold_ignore_until"] = (
                self._high_threshold_ignore_until_datetime.isoformat()
            )
            attrs["currently_ignoring_high"] = (
                now < self._high_threshold_ignore_until_datetime
            )

        # Add low threshold ignore until information if available
        if self._low_threshold_ignore_until_datetime:
            now = dt_util.now()
            attrs["low_threshold_ignore_until"] = (
                self._low_threshold_ignore_until_datetime.isoformat()
            )
            attrs["currently_ignoring_low"] = (
                now < self._low_threshold_ignore_until_datetime
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Try resolved entity ID first, fallback to stored ID
        resolved_temperature_entity_id = _resolve_entity_id(
            self.hass, self.temperature_entity_id, self.temperature_entity_unique_id
        )
        if not resolved_temperature_entity_id:
            return False
        temperature_state = self.hass.states.get(resolved_temperature_entity_id)
        return temperature_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                self._temperature_status = last_state.attributes.get(
                    "temperature_status", "normal"
                )
                _LOGGER.info(
                    "Restored temperature status for %s: %s (%s)",
                    self.location_name,
                    self._state,
                    self._temperature_status,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_above_threshold_subscription(self) -> None:
        """Find and subscribe to temperature above threshold sensor."""
        above_threshold_entity_id = await self._find_above_threshold_sensor()
        if above_threshold_entity_id:
            if above_state := self.hass.states.get(above_threshold_entity_id):
                self._above_threshold_hours = self._parse_float(above_state.state)

            try:
                self._unsubscribe_above = async_track_state_change_event(
                    self.hass,
                    above_threshold_entity_id,
                    self._above_threshold_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to temperature above threshold sensor: %s",
                    above_threshold_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to temperature above threshold sensor %s: %s",
                    above_threshold_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Temperature above threshold sensor not found for location %s",
                self.location_name,
            )

    async def _setup_below_threshold_subscription(self) -> None:
        """Find and subscribe to temperature below threshold sensor."""
        below_threshold_entity_id = await self._find_below_threshold_sensor()
        if below_threshold_entity_id:
            if below_state := self.hass.states.get(below_threshold_entity_id):
                self._below_threshold_hours = self._parse_float(below_state.state)

            try:
                self._unsubscribe_below = async_track_state_change_event(
                    self.hass,
                    below_threshold_entity_id,
                    self._below_threshold_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to temperature below threshold sensor: %s",
                    below_threshold_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to temperature below threshold sensor %s: %s",
                    below_threshold_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Temperature below threshold sensor not found for location %s",
                self.location_name,
            )

    async def _setup_high_threshold_ignore_until_subscription(self) -> None:
        """Find and subscribe to temperature high threshold ignore until datetime."""
        ignore_until_entity_id = await self._find_high_threshold_ignore_until_entity()
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._high_threshold_ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing temperature high threshold ignore until "
                        "datetime: %s",
                        exc,
                    )

            try:
                self._unsubscribe_high_threshold_ignore_until = (
                    async_track_state_change_event(
                        self.hass,
                        ignore_until_entity_id,
                        self._high_threshold_ignore_until_state_changed,
                    )
                )
                _LOGGER.debug(
                    "Subscribed to temperature high threshold ignore until "
                    "datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to temperature high threshold ignore "
                    "until entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Temperature high threshold ignore until datetime not found "
                "for location %s",
                self.location_name,
            )

    async def _setup_low_threshold_ignore_until_subscription(self) -> None:
        """Find and subscribe to temperature low threshold ignore until datetime."""
        ignore_until_entity_id = await self._find_low_threshold_ignore_until_entity()
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._low_threshold_ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing temperature low threshold ignore until "
                        "datetime: %s",
                        exc,
                    )

            try:
                self._unsubscribe_low_threshold_ignore_until = (
                    async_track_state_change_event(
                        self.hass,
                        ignore_until_entity_id,
                        self._low_threshold_ignore_until_state_changed,
                    )
                )
                _LOGGER.debug(
                    "Subscribed to temperature low threshold ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to temperature low threshold ignore "
                    "until entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Temperature low threshold ignore until datetime not found "
                "for location %s",
                self.location_name,
            )

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Set up subscriptions
        await self._setup_above_threshold_subscription()
        await self._setup_below_threshold_subscription()
        await self._setup_high_threshold_ignore_until_subscription()
        await self._setup_low_threshold_ignore_until_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_above") and self._unsubscribe_above:
            self._unsubscribe_above()
        if hasattr(self, "_unsubscribe_below") and self._unsubscribe_below:
            self._unsubscribe_below()
        if (
            hasattr(self, "_unsubscribe_high_threshold_ignore_until")
            and self._unsubscribe_high_threshold_ignore_until
        ):
            self._unsubscribe_high_threshold_ignore_until()
        if (
            hasattr(self, "_unsubscribe_low_threshold_ignore_until")
            and self._unsubscribe_low_threshold_ignore_until
        ):
            self._unsubscribe_low_threshold_ignore_until()


class HumidityStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors humidity status against thresholds.

    This sensor turns ON (problem detected) when humidity is outside the
    acceptable range (above maximum or below minimum weekly duration thresholds
    for more than 2 hours).
    The status attribute indicates whether the issue is 'above', 'below', or 'normal'.
    """

    def __init__(self, config: HumidityStatusMonitorConfig) -> None:
        """
        Initialize the Humidity Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.humidity_entity_id = config.humidity_entity_id
        self.humidity_entity_unique_id = config.humidity_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Humidity Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_humidity_status"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._humidity_status: str = "normal"  # 'above', 'below', or 'normal'
        self._above_threshold_hours: float | None = 0.0
        self._below_threshold_hours: float | None = 0.0
        self._threshold_hours: float = 2.0  # 2 hours threshold
        self._high_threshold_ignore_until_datetime: Any = None
        self._low_threshold_ignore_until_datetime: Any = None
        self._unsubscribe: Any = None
        self._unsubscribe_above: Any = None
        self._unsubscribe_below: Any = None
        self._unsubscribe_high_threshold_ignore_until: Any = None
        self._unsubscribe_low_threshold_ignore_until: Any = None

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _update_state(self) -> None:
        """Update binary sensor state based on humidity threshold durations."""
        # If either duration value is unavailable, set state to None
        if self._above_threshold_hours is None or self._below_threshold_hours is None:
            self._state = None
            self._humidity_status = "normal"
            return

        # Determine status and state based on threshold durations
        # Problem if either above or below duration exceeds 2 hours
        if self._above_threshold_hours > self._threshold_hours:
            # Check if we're currently in the high humidity ignore period
            if self._high_threshold_ignore_until_datetime is not None:
                try:
                    now = dt_util.now()
                    if now < self._high_threshold_ignore_until_datetime:
                        # Current time is before ignore until datetime, no problem
                        self._state = False
                        self._humidity_status = "normal"
                        return
                except (TypeError, AttributeError) as exc:
                    _LOGGER.debug(
                        "Error checking high humidity ignore until datetime: %s", exc
                    )
            self._state = True
            self._humidity_status = "above"
        elif self._below_threshold_hours > self._threshold_hours:
            # Check if we're currently in the low humidity ignore period
            if self._low_threshold_ignore_until_datetime is not None:
                try:
                    now = dt_util.now()
                    if now < self._low_threshold_ignore_until_datetime:
                        # Current time is before ignore until datetime, no problem
                        self._state = False
                        self._humidity_status = "normal"
                        return
                except (TypeError, AttributeError) as exc:
                    _LOGGER.debug(
                        "Error checking low humidity ignore until datetime: %s", exc
                    )
            self._state = True
            self._humidity_status = "below"
        else:
            self._state = False
            self._humidity_status = "normal"

    async def _find_above_threshold_sensor(self) -> str | None:
        """
        Find the humidity above threshold weekly duration sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")
            expected_unique_id = (
                f"{DOMAIN}_{self.entry_id}_{location_name_safe}_"
                "humidity_above_threshold_weekly_duration"
            )

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id == expected_unique_id
                ):
                    _LOGGER.debug(
                        "Found humidity above threshold sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding humidity above threshold sensor: %s", exc)

        return None

    async def _find_below_threshold_sensor(self) -> str | None:
        """
        Find the humidity below threshold weekly duration sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")
            expected_unique_id = (
                f"{DOMAIN}_{self.entry_id}_{location_name_safe}_"
                "humidity_below_threshold_weekly_duration"
            )

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id == expected_unique_id
                ):
                    _LOGGER.debug(
                        "Found humidity below threshold sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding humidity below threshold sensor: %s", exc)

        return None

    async def _find_high_threshold_ignore_until_entity(self) -> str | None:
        """
        Find humidity high threshold ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "humidity_high_threshold_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found humidity high threshold ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Error finding humidity high threshold ignore until entity: %s", exc
            )

        return None

    async def _find_low_threshold_ignore_until_entity(self) -> str | None:
        """
        Find humidity low threshold ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "humidity_low_threshold_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found humidity low threshold ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Error finding humidity low threshold ignore until entity: %s", exc
            )

        return None

    @callback
    def _above_threshold_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle humidity above threshold duration sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._above_threshold_hours = None
        else:
            self._above_threshold_hours = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _below_threshold_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle humidity below threshold duration sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._below_threshold_hours = None
        else:
            self._below_threshold_hours = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _high_threshold_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle humidity high threshold ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._high_threshold_ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._high_threshold_ignore_until_datetime = parsed_datetime
                else:
                    self._high_threshold_ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing humidity high threshold ignore until datetime: %s",
                    exc,
                )
                self._high_threshold_ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _low_threshold_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle humidity low threshold ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._low_threshold_ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._low_threshold_ignore_until_datetime = parsed_datetime
                else:
                    self._low_threshold_ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing humidity low threshold ignore until datetime: %s",
                    exc,
                )
                self._low_threshold_ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if humidity is outside acceptable range (problem)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state and status."""
        if self._state is True:
            if self._humidity_status == "above":
                return "mdi:water-percent"
            if self._humidity_status == "below":
                return "mdi:water-percent-alert"
        return "mdi:water-percent"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        # Alert type based on humidity status
        alert_type = "Critical"
        status_message = f"Humidity {self._humidity_status.capitalize()}"

        attrs = {
            "type": alert_type,
            "message": status_message,
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "humidity_status": self._humidity_status,
            "above_threshold_hours": self._above_threshold_hours,
            "below_threshold_hours": self._below_threshold_hours,
            "threshold_hours": self._threshold_hours,
        }

        # Add high threshold ignore until information if available
        if self._high_threshold_ignore_until_datetime:
            now = dt_util.now()
            attrs["high_threshold_ignore_until"] = (
                self._high_threshold_ignore_until_datetime.isoformat()
            )
            attrs["currently_ignoring_high"] = (
                now < self._high_threshold_ignore_until_datetime
            )

        # Add low threshold ignore until information if available
        if self._low_threshold_ignore_until_datetime:
            now = dt_util.now()
            attrs["low_threshold_ignore_until"] = (
                self._low_threshold_ignore_until_datetime.isoformat()
            )
            attrs["currently_ignoring_low"] = (
                now < self._low_threshold_ignore_until_datetime
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Try resolved entity ID first, fallback to stored ID
        resolved_humidity_entity_id = _resolve_entity_id(
            self.hass, self.humidity_entity_id, self.humidity_entity_unique_id
        )
        if not resolved_humidity_entity_id:
            return False
        humidity_state = self.hass.states.get(resolved_humidity_entity_id)
        return humidity_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                self._humidity_status = last_state.attributes.get(
                    "humidity_status", "normal"
                )
                _LOGGER.info(
                    "Restored humidity status for %s: %s (%s)",
                    self.location_name,
                    self._state,
                    self._humidity_status,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_above_threshold_subscription(self) -> None:
        """Find and subscribe to humidity above threshold sensor."""
        above_threshold_entity_id = await self._find_above_threshold_sensor()
        if above_threshold_entity_id:
            if above_state := self.hass.states.get(above_threshold_entity_id):
                self._above_threshold_hours = self._parse_float(above_state.state)

            try:
                self._unsubscribe_above = async_track_state_change_event(
                    self.hass,
                    above_threshold_entity_id,
                    self._above_threshold_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to humidity above threshold sensor: %s",
                    above_threshold_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to humidity above threshold sensor %s: %s",
                    above_threshold_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Humidity above threshold sensor not found for location %s",
                self.location_name,
            )

    async def _setup_below_threshold_subscription(self) -> None:
        """Find and subscribe to humidity below threshold sensor."""
        below_threshold_entity_id = await self._find_below_threshold_sensor()
        if below_threshold_entity_id:
            if below_state := self.hass.states.get(below_threshold_entity_id):
                self._below_threshold_hours = self._parse_float(below_state.state)

            try:
                self._unsubscribe_below = async_track_state_change_event(
                    self.hass,
                    below_threshold_entity_id,
                    self._below_threshold_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to humidity below threshold sensor: %s",
                    below_threshold_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to humidity below threshold sensor %s: %s",
                    below_threshold_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Humidity below threshold sensor not found for location %s",
                self.location_name,
            )

    async def _setup_high_threshold_ignore_until_subscription(self) -> None:
        """Find and subscribe to humidity high threshold ignore until datetime."""
        ignore_until_entity_id = await self._find_high_threshold_ignore_until_entity()
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._high_threshold_ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing humidity high threshold ignore until datetime: %s",  # noqa: E501
                        exc,
                    )

            try:
                self._unsubscribe_high_threshold_ignore_until = (
                    async_track_state_change_event(
                        self.hass,
                        ignore_until_entity_id,
                        self._high_threshold_ignore_until_state_changed,
                    )
                )
                _LOGGER.debug(
                    "Subscribed to humidity high threshold ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to humidity high threshold ignore until "
                    "datetime %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Humidity high threshold ignore until datetime not found for "
                "location %s",
                self.location_name,
            )

    async def _setup_low_threshold_ignore_until_subscription(self) -> None:
        """Find and subscribe to humidity low threshold ignore until datetime."""
        ignore_until_entity_id = await self._find_low_threshold_ignore_until_entity()
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._low_threshold_ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing humidity low threshold ignore until datetime: %s",  # noqa: E501
                        exc,
                    )

            try:
                self._unsubscribe_low_threshold_ignore_until = (
                    async_track_state_change_event(
                        self.hass,
                        ignore_until_entity_id,
                        self._low_threshold_ignore_until_state_changed,
                    )
                )
                _LOGGER.debug(
                    "Subscribed to humidity low threshold ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to humidity low threshold ignore until "
                    "datetime %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Humidity low threshold ignore until datetime not found for "
                "location %s",
                self.location_name,
            )

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Set up subscriptions
        await self._setup_above_threshold_subscription()
        await self._setup_below_threshold_subscription()
        await self._setup_high_threshold_ignore_until_subscription()
        await self._setup_low_threshold_ignore_until_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_above") and self._unsubscribe_above:
            self._unsubscribe_above()
        if hasattr(self, "_unsubscribe_below") and self._unsubscribe_below:
            self._unsubscribe_below()
        if (
            hasattr(self, "_unsubscribe_high_threshold_ignore_until")
            and self._unsubscribe_high_threshold_ignore_until
        ):
            self._unsubscribe_high_threshold_ignore_until()
        if (
            hasattr(self, "_unsubscribe_low_threshold_ignore_until")
            and self._unsubscribe_low_threshold_ignore_until
        ):
            self._unsubscribe_low_threshold_ignore_until()


class BatteryLevelStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors battery level as a problem state.

    This sensor turns ON (problem detected) when the battery level falls
    below 10%, indicating low battery warning.
    """

    def __init__(self, config: BatteryLevelStatusMonitorConfig) -> None:
        """
        Initialize the Battery Level Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.battery_entity_id = config.battery_entity_id
        self.battery_entity_unique_id = config.battery_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Monitor Battery Level Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        unique_id_suffix = "monitor_battery_level_status"
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_{unique_id_suffix}"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._current_battery_level: float | None = None
        self._ignore_until_datetime: Any = None
        self._unsubscribe: Any = None
        self._unsubscribe_ignore_until: Any = None

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    async def _find_battery_low_ignore_until_entity(self) -> str | None:
        """
        Find battery low threshold ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "battery_low_threshold_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found battery low threshold ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Error finding battery low threshold ignore until entity: %s", exc
            )

        return None

    @callback
    def _battery_low_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle battery low threshold ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._ignore_until_datetime = parsed_datetime
                else:
                    self._ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing battery low threshold ignore until datetime: %s",
                    exc,
                )
                self._ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    def _update_state(self) -> None:
        """Update binary sensor state based on current battery level."""
        # If battery level is unavailable, set state to None (sensor unavailable)
        if self._current_battery_level is None:
            self._state = None
            return

        # Check if we're currently in the ignore period
        if self._ignore_until_datetime is not None:
            try:
                now = dt_util.now()
                if now < self._ignore_until_datetime:
                    # Current time is before ignore until datetime, no problem
                    self._state = False
                    return
            except (TypeError, AttributeError) as exc:
                _LOGGER.debug("Error checking battery ignore until datetime: %s", exc)

        # Binary sensor is ON (problem) when battery level < threshold
        self._state = self._current_battery_level < BATTERY_LEVEL_THRESHOLD

    @callback
    def _battery_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle battery level sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._current_battery_level = None
        else:
            self._current_battery_level = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if battery level is low (problem detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:battery-alert"
        return "mdi:battery"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        alert_type = "Critical" if self._state is True else "Normal"
        status_message = (
            "Battery level low (< 10%)"
            if self._state is True
            else "Battery level normal"
        )

        attrs = {
            "type": alert_type,
            "message": status_message,
            "task": self._state is True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "current_battery_level": self._current_battery_level,
            "source_entity": self.battery_entity_id,
        }

        # Add ignore until information if available
        if self._ignore_until_datetime:
            now = dt_util.now()
            attrs["ignore_until"] = self._ignore_until_datetime.isoformat()
            attrs["currently_ignoring"] = now < self._ignore_until_datetime

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Try resolved entity ID first, fallback to stored ID
        resolved_battery_entity_id = _resolve_entity_id(
            self.hass, self.battery_entity_id, self.battery_entity_unique_id
        )
        if not resolved_battery_entity_id:
            return False
        battery_state = self.hass.states.get(resolved_battery_entity_id)
        return battery_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored battery level status monitor state for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_battery_subscription(self) -> None:
        """Subscribe to battery entity state changes."""
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.battery_entity_id,
                self._battery_state_changed,
            )
            _LOGGER.debug(
                "Subscribed to battery sensor: %s",
                self.battery_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to battery entity %s: %s",
                self.battery_entity_id,
                exc,
            )

    async def _setup_battery_ignore_until_subscription(self) -> None:
        """Subscribe to battery low threshold ignore until datetime changes."""
        ignore_until_entity_id = await self._find_battery_low_ignore_until_entity()
        if ignore_until_entity_id:
            try:
                self._unsubscribe_ignore_until = async_track_state_change_event(
                    self.hass,
                    ignore_until_entity_id,
                    self._battery_low_ignore_until_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to battery low threshold ignore until entity: %s",
                    ignore_until_entity_id,
                )

                # Initialize with current state of ignore until entity
                if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                    synthetic_event = cast(
                        "Event[EventStateChangedData]",
                        Event(
                            "state_changed",
                            {
                                "entity_id": ignore_until_entity_id,
                                "old_state": None,
                                "new_state": ignore_until_state,
                            },
                        ),
                    )
                    self._battery_low_ignore_until_state_changed(synthetic_event)
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to battery low threshold ignore until "
                    "entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "Battery low threshold ignore until entity not found for %s",
                self.location_name,
            )

    async def async_added_to_hass(self) -> None:
        """Restore and initialize battery level monitoring on addition."""
        # Restore previous state
        await self._restore_previous_state()

        # Initialize with current state of battery entity
        if battery_state := self.hass.states.get(self.battery_entity_id):
            self._current_battery_level = self._parse_float(battery_state.state)

        # Update state based on initial value
        self._update_state()

        # Set up subscriptions
        await self._setup_battery_subscription()
        await self._setup_battery_ignore_until_subscription()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if self._unsubscribe_ignore_until:
            self._unsubscribe_ignore_until()


class LinkMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors monitoring device availability (link status).

    This sensor turns ON when the associated monitoring device
    is available, indicating a normal connection with the device.
    """

    def __init__(self, config: LinkMonitorConfig) -> None:
        """
        Initialize the Link Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.monitoring_device_id = config.monitoring_device_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Monitor Link"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_monitor_link"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

        self._state: bool | None = None
        self._device_available: bool | None = None
        self._unsubscribe: Any = None
        self._unsubscribe_entities: Any = None

    def _update_state(self) -> None:
        """Update binary sensor state based on device availability."""
        # If device availability is unknown, set state to None (sensor unavailable)
        if self._device_available is None:
            self._state = None
            return

        # Binary sensor is ON (connected) when device is available
        self._state = self._device_available

    @callback
    def _device_availability_changed(self, device_id: str, available: bool) -> None:  # noqa: FBT001
        """Handle device availability changes."""
        if device_id == self.monitoring_device_id:
            self._device_available = available
            self._update_state()
            self.async_write_ha_state()

    def _check_device_availability(self) -> bool | None:
        """Check the current availability of the monitoring device."""
        try:
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get(self.monitoring_device_id)

            if device is None:
                _LOGGER.warning(
                    "Monitoring device %s not found in device registry",
                    self.monitoring_device_id,
                )
                return None

            # Device is unavailable if:
            # 1. It's explicitly disabled
            # 2. It's marked as "gone" (not recoverable)
            if device.disabled_by is not None:
                _LOGGER.debug(
                    "Device %s is disabled: %s",
                    self.monitoring_device_id,
                    device.disabled_by,
                )
                return False

            # Check if device has any entities that we can use to determine connectivity
            # A device is considered unavailable if all its entities are unavailable
            return self._check_device_entity_availability()

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error checking device availability: %s", exc)
            return None

    def _check_device_entity_availability(self) -> bool | None:
        """
        Check device availability by examining its entities' states.

        A device is considered available if at least one of its entities
        is in an available state (not UNAVAILABLE or UNKNOWN).

        Returns True if device is available, False if unavailable, None if unknown.
        """
        try:
            ent_reg = er.async_get(self.hass)

            # Find all entities associated with this device
            device_entities = [
                entity
                for entity in ent_reg.entities.values()
                if entity.device_id == self.monitoring_device_id
            ]

            if not device_entities:
                _LOGGER.debug(
                    "No entities found for device %s", self.monitoring_device_id
                )
                return None

            # Check state of each entity
            available_count = 0
            unavailable_count = 0

            for entity in device_entities:
                entity_state = self.hass.states.get(entity.entity_id)

                if entity_state is None:
                    continue

                if entity_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    unavailable_count += 1
                else:
                    available_count += 1

            # If all entities are unavailable, device is unavailable
            if available_count == 0 and unavailable_count > 0:
                _LOGGER.debug(
                    "Device %s is unavailable - all entities are unavailable",
                    self.monitoring_device_id,
                )
                return False

            # If at least one entity is available, device is available
            if available_count > 0:
                _LOGGER.debug(
                    "Device %s is available - %d available entities",
                    self.monitoring_device_id,
                    available_count,
                )
                return True

            # If we have no state information, return None
            _LOGGER.debug(
                "Device %s availability unknown - no state information",
                self.monitoring_device_id,
            )
            return None  # noqa: TRY300

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error checking device entity availability: %s", exc)
            return None

    @property
    def is_on(self) -> bool | None:
        """Return True if device is available (connected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:link"
        return "mdi:link-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        return {
            "monitoring_device_id": self.monitoring_device_id,
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Entity is always available, it reports on device availability
        return True

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored link status for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and set up device availability monitoring."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Check initial device availability
        self._device_available = self._check_device_availability()

        # Subscribe to both device registry updates and entity state changes
        try:

            @callback
            def _device_registry_updated(_event: Any) -> None:
                """Handle device registry updates."""
                self._device_available = self._check_device_availability()
                self._update_state()
                self.async_write_ha_state()

            @callback
            def _entity_state_changed(_event: Event[EventStateChangedData]) -> None:
                """Handle entity state changes for device's entities."""
                # Re-check device availability when any of its entities change state
                self._device_available = self._check_device_availability()
                self._update_state()
                self.async_write_ha_state()

            self._unsubscribe = self.hass.bus.async_listen(
                "device_registry_updated", _device_registry_updated
            )
            _LOGGER.debug(
                "Subscribed to device registry updates for link monitor %s",
                self.location_name,
            )

            # Subscribe to state changes of all entities belonging to this device
            try:
                ent_reg = er.async_get(self.hass)
                device_entity_ids = [
                    entity.entity_id
                    for entity in ent_reg.entities.values()
                    if entity.device_id == self.monitoring_device_id
                ]

                if device_entity_ids:
                    self._unsubscribe_entities = async_track_state_change_event(
                        self.hass,
                        device_entity_ids,
                        _entity_state_changed,
                    )
                    _LOGGER.debug(
                        "Subscribed to %d entities for device %s",
                        len(device_entity_ids),
                        self.monitoring_device_id,
                    )
                else:
                    _LOGGER.debug(
                        "No entities found for device %s to monitor",
                        self.monitoring_device_id,
                    )

            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.debug(
                    "Failed to subscribe to device entity state changes: %s", exc
                )

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to device registry updates for link monitor"
                " %s: %s",
                self.location_name,
                exc,
            )

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_entities") and self._unsubscribe_entities:
            self._unsubscribe_entities()


class LinkStatusBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors monitoring device availability as a problem state.

    This sensor turns ON (problem detected) when the associated monitoring device
    is unavailable, indicating a communication or connectivity issue with the device.
    This is a complementary sensor to LinkMonitorBinarySensor that uses a PROBLEM
    device class for alerting purposes.
    """

    def __init__(self, config: LinkMonitorConfig) -> None:
        """
        Initialize the Link Status binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name
        self.monitoring_device_id = config.monitoring_device_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Monitor Link Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_monitor_link_status"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._device_available: bool | None = None
        self._ignore_until_datetime: Any = None
        self._unsubscribe: Any = None
        self._unsubscribe_entities: Any = None
        self._unsubscribe_ignore_until: Any = None

    def _update_state(self) -> None:
        """Update binary sensor state based on device availability."""
        # If device availability is unknown, set state to None (sensor unavailable)
        if self._device_available is None:
            self._state = None
            return

        # Check if we're currently in the ignore period
        if self._ignore_until_datetime is not None:
            try:
                now = dt_util.now()
                if now < self._ignore_until_datetime:
                    # Current time is before ignore until datetime, suppress problem
                    self._state = False
                    return
            except (TypeError, AttributeError) as exc:
                _LOGGER.debug(
                    "Error checking monitor link ignore until datetime: %s", exc
                )

        # Binary sensor is ON (problem) when device is unavailable
        self._state = not self._device_available

    async def _find_monitor_link_ignore_until_entity(self) -> str | None:
        """
        Find monitor link ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "monitor_link_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found monitor link ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding monitor link ignore until entity: %s", exc)

        return None

    @callback
    def _monitor_link_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle monitor link ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._ignore_until_datetime = parsed_datetime
                else:
                    self._ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing monitor link ignore until datetime: %s", exc
                )
                self._ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _device_availability_changed(self, device_id: str, available: bool) -> None:  # noqa: FBT001
        """Handle device availability changes."""
        if device_id == self.monitoring_device_id:
            self._device_available = available
            self._update_state()
            self.async_write_ha_state()

    def _check_device_availability(self) -> bool | None:
        """Check the current availability of the monitoring device."""
        try:
            device_registry = dr.async_get(self.hass)
            device = device_registry.async_get(self.monitoring_device_id)

            if device is None:
                _LOGGER.warning(
                    "Monitoring device %s not found in device registry",
                    self.monitoring_device_id,
                )
                return None

            # Device is unavailable if:
            # 1. It's explicitly disabled
            # 2. It's marked as "gone" (not recoverable)
            if device.disabled_by is not None:
                _LOGGER.debug(
                    "Device %s is disabled: %s",
                    self.monitoring_device_id,
                    device.disabled_by,
                )
                return False

            # Check if device has any entities that we can use to determine connectivity
            # A device is considered unavailable if all its entities are unavailable
            return self._check_device_entity_availability()

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error checking device availability: %s", exc)
            return None

    def _check_device_entity_availability(self) -> bool | None:
        """
        Check device availability by examining its entities' states.

        A device is considered available if at least one of its entities
        is in an available state (not UNAVAILABLE or UNKNOWN).

        Returns True if device is available, False if unavailable, None if unknown.
        """
        try:
            ent_reg = er.async_get(self.hass)

            # Find all entities associated with this device
            device_entities = [
                entity
                for entity in ent_reg.entities.values()
                if entity.device_id == self.monitoring_device_id
            ]

            if not device_entities:
                _LOGGER.debug(
                    "No entities found for device %s", self.monitoring_device_id
                )
                return None

            # Check state of each entity
            available_count = 0
            unavailable_count = 0

            for entity in device_entities:
                entity_state = self.hass.states.get(entity.entity_id)

                if entity_state is None:
                    continue

                if entity_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    unavailable_count += 1
                else:
                    available_count += 1

            # If all entities are unavailable, device is unavailable
            if available_count == 0 and unavailable_count > 0:
                _LOGGER.debug(
                    "Device %s is unavailable - all entities are unavailable",
                    self.monitoring_device_id,
                )
                return False

            # If at least one entity is available, device is available
            if available_count > 0:
                _LOGGER.debug(
                    "Device %s is available - %d available entities",
                    self.monitoring_device_id,
                    available_count,
                )
                return True

            # If we have no state information, return None
            _LOGGER.debug(
                "Device %s availability unknown - no state information",
                self.monitoring_device_id,
            )
            return None  # noqa: TRY300

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error checking device entity availability: %s", exc)
            return None

    @property
    def is_on(self) -> bool | None:
        """Return True if device is unavailable (problem detected)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state."""
        if self._state is True:
            return "mdi:link-off"
        return "mdi:link"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        alert_type = "Critical" if self._state is True else "Normal"
        status_message = (
            "Monitoring device unavailable"
            if self._state is True
            else "Monitoring device available"
        )

        attrs = {
            "type": alert_type,
            "message": status_message,
            "task": self._state is True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "device_available": self._device_available,
            "monitoring_device_id": self.monitoring_device_id,
        }

        # Add ignore until information if available
        if self._ignore_until_datetime:
            now = dt_util.now()
            attrs["ignore_until"] = self._ignore_until_datetime.isoformat()
            attrs["currently_ignoring"] = now < self._ignore_until_datetime

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Entity is always available, it reports on device availability
        return True

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                _LOGGER.info(
                    "Restored link status for %s: %s",
                    self.location_name,
                    self._state,
                )
            except (AttributeError, ValueError):
                pass

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and set up device availability monitoring."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Check initial device availability
        self._device_available = self._check_device_availability()

        # Subscribe to both device registry updates and entity state changes
        try:

            @callback
            def _device_registry_updated(_event: Any) -> None:
                """Handle device registry updates."""
                self._device_available = self._check_device_availability()
                self._update_state()
                self.async_write_ha_state()

            @callback
            def _entity_state_changed(_event: Event[EventStateChangedData]) -> None:
                """Handle entity state changes for device's entities."""
                # Re-check device availability when any of its entities change state
                self._device_available = self._check_device_availability()
                self._update_state()
                self.async_write_ha_state()

            self._unsubscribe = self.hass.bus.async_listen(
                "device_registry_updated", _device_registry_updated
            )
            _LOGGER.debug(
                "Subscribed to device registry updates for link status monitor %s",
                self.location_name,
            )

            # Subscribe to state changes of all entities belonging to this device
            try:
                ent_reg = er.async_get(self.hass)
                device_entity_ids = [
                    entity.entity_id
                    for entity in ent_reg.entities.values()
                    if entity.device_id == self.monitoring_device_id
                ]

                if device_entity_ids:
                    self._unsubscribe_entities = async_track_state_change_event(
                        self.hass,
                        device_entity_ids,
                        _entity_state_changed,
                    )
                    _LOGGER.debug(
                        "Subscribed to %d entities for device %s",
                        len(device_entity_ids),
                        self.monitoring_device_id,
                    )
                else:
                    _LOGGER.debug(
                        "No entities found for device %s to monitor",
                        self.monitoring_device_id,
                    )

            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.debug(
                    "Failed to subscribe to device entity state changes: %s", exc
                )

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to device registry updates for link status"
                " monitor %s: %s",
                self.location_name,
                exc,
            )

        # Subscribe to monitor link ignore until datetime entity
        try:
            ignore_until_entity_id = await self._find_monitor_link_ignore_until_entity()
            if ignore_until_entity_id:
                self._unsubscribe_ignore_until = async_track_state_change_event(
                    self.hass,
                    ignore_until_entity_id,
                    self._monitor_link_ignore_until_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to monitor link ignore until entity %s",
                    ignore_until_entity_id,
                )
            else:
                _LOGGER.debug(
                    "Monitor link ignore until datetime entity not found for %s",
                    self.location_name,
                )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Failed to subscribe to monitor link ignore until entity: %s", exc
            )

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_entities") and self._unsubscribe_entities:
            self._unsubscribe_entities()
        if (
            hasattr(self, "_unsubscribe_ignore_until")
            and self._unsubscribe_ignore_until
        ):
            self._unsubscribe_ignore_until()


class RecentlyWateredBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that detects when a plant location has been recently watered.

    This sensor monitors a 'recent_change' statistics sensor that tracks the
    percentage change in soil moisture over a 3-hour window. When the change
    is >= 10%, it indicates the plant was likely watered, and this sensor turns ON.

    This sensor is only created for plant locations associated with irrigation zones
    that do NOT have ESPHome devices, as ESPHome zones have direct irrigation data.
    """

    def __init__(self, config: RecentlyWateredBinarySensorConfig) -> None:
        """
        Initialize the Recently Watered binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.recent_change_entity_id = config.recent_change_entity_id

        # Set entity attributes
        self._attr_name = f"{self.location_name} Recently Watered"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_recently_watered"
        )

        # Set binary sensor properties - use moisture device class
        self._attr_device_class = BinarySensorDeviceClass.MOISTURE
        self._attr_icon = "mdi:water-check"

        # Set device info to associate with the location device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.location_device_id)},
        )

        self._state: bool | None = None
        self._recent_change: float | None = None
        self._unsubscribe: Any = None

    def _update_state(self) -> None:
        """Update binary sensor state based on recent moisture change."""
        # If recent change is unknown, set state to False (off)
        # This prevents the sensor from showing as "Unknown"
        if self._recent_change is None:
            self._state = False
            return

        # Binary sensor is ON when recent change exceeds threshold
        # This indicates watering was detected
        self._state = self._recent_change >= WATERING_RECENT_CHANGE_THRESHOLD

    @callback
    def _recent_change_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle recent change sensor state changes."""
        new_state = event.data.get("new_state")

        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._recent_change = None
        else:
            try:
                self._recent_change = float(new_state.state)
            except (ValueError, TypeError):
                _LOGGER.debug(
                    "Could not convert recent change to float: %s",
                    new_state.state,
                )
                self._recent_change = None

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            "recent_change_percent": self._recent_change,
            "detection_threshold": 10.0,
            "source_entity": self.recent_change_entity_id,
        }

    async def async_added_to_hass(self) -> None:
        """Set up state listener when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if last_state := await self.async_get_last_state():
            if last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                self._state = last_state.state == "on"

            # Restore recent_change from attributes if available
            if last_state.attributes:
                recent_change = last_state.attributes.get("recent_change_percent")
                if recent_change is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        self._recent_change = float(recent_change)

            _LOGGER.debug(
                "Restored recently watered sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        # Subscribe to recent change sensor state changes
        try:
            # Get initial state
            if (
                initial_state := self.hass.states.get(self.recent_change_entity_id)
            ) and initial_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self._recent_change = float(initial_state.state)
                    self._update_state()
                except (ValueError, TypeError):
                    pass

            self._unsubscribe = async_track_state_change_event(
                self.hass,
                [self.recent_change_entity_id],
                self._recent_change_state_changed,
            )
            _LOGGER.debug(
                "Set up state listener for %s tracking %s",
                self.location_name,
                self.recent_change_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up state listener for %s: %s",
                self.location_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class DailyLightIntegralStatusMonitorBinarySensor(BinarySensorEntity, RestoreEntity):
    """
    Binary sensor that monitors Daily Light Integral (DLI) status against thresholds.

    This sensor turns ON (problem detected) when the DLI Weekly Average is outside
    the acceptable range (above maximum or below minimum). The status attribute
    indicates whether the issue is 'above', 'below', or 'normal'.

    The sensor respects DLI High/Low Threshold Ignore Until datetime entities,
    temporarily suppressing problem alerts when the ignore period is active.
    """

    def __init__(self, config: DailyLightIntegralStatusMonitorConfig) -> None:
        """
        Initialize the Daily Light Integral Status Monitor binary sensor.

        Args:
            config: Configuration object containing sensor parameters.

        """
        self.hass = config.hass
        self.entry_id = config.entry_id
        self.location_device_id = config.location_device_id
        self.location_name = config.location_name
        self.irrigation_zone_name = config.irrigation_zone_name

        # Set entity attributes
        self._attr_name = f"{self.location_name} Daily Light Integral Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_dli_status"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

        self._state: bool | None = None
        self._dli_status: str = "normal"  # 'above', 'below', or 'normal'
        self._weekly_average_dli: float | None = 0.0
        self._min_dli: float | None = 0.0
        self._max_dli: float | None = 0.0
        self._high_threshold_ignore_until_datetime: Any = None
        self._low_threshold_ignore_until_datetime: Any = None
        self._unsubscribe: Any = None
        self._unsubscribe_weekly_avg: Any = None
        self._unsubscribe_min_dli: Any = None
        self._unsubscribe_max_dli: Any = None
        self._unsubscribe_high_threshold_ignore_until: Any = None
        self._unsubscribe_low_threshold_ignore_until: Any = None

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _update_state(self) -> None:
        """Update binary sensor state based on DLI and thresholds."""
        # If any required value is unavailable, set state to None (sensor unavailable)
        if (
            self._weekly_average_dli is None
            or self._min_dli is None
            or self._max_dli is None
        ):
            self._state = None
            self._dli_status = "normal"
            return

        # Check if we're in an ignore period
        if self._weekly_average_dli > self._max_dli:
            # High DLI condition
            if self._high_threshold_ignore_until_datetime is not None:
                try:
                    now = dt_util.now()
                    if now < self._high_threshold_ignore_until_datetime:
                        # Currently ignoring high DLI threshold
                        self._state = False
                        self._dli_status = "normal"
                        return
                except (TypeError, AttributeError) as exc:
                    _LOGGER.debug(
                        "Error checking DLI high threshold ignore until datetime: %s",
                        exc,
                    )
            self._state = True
            self._dli_status = "above"
        elif self._weekly_average_dli < self._min_dli:
            # Low DLI condition
            if self._low_threshold_ignore_until_datetime is not None:
                try:
                    now = dt_util.now()
                    if now < self._low_threshold_ignore_until_datetime:
                        # Currently ignoring low DLI threshold
                        self._state = False
                        self._dli_status = "normal"
                        return
                except (TypeError, AttributeError) as exc:
                    _LOGGER.debug(
                        "Error checking DLI low threshold ignore until datetime: %s",
                        exc,
                    )
            self._state = True
            self._dli_status = "below"
        else:
            # Within acceptable range
            self._state = False
            self._dli_status = "normal"

    async def _find_weekly_average_dli_sensor(self) -> str | None:
        """
        Find the weekly average DLI sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_daily_light_integral_weekly_average"
                    in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found weekly average DLI sensor: %s", entity.entity_id
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding weekly average DLI sensor: %s", exc)

        return None

    async def _find_min_dli_sensor(self) -> str | None:
        """
        Find the minimum DLI aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_min_dli" in entity.unique_id
                ):
                    _LOGGER.debug("Found minimum DLI sensor: %s", entity.entity_id)
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding minimum DLI sensor: %s", exc)

        return None

    async def _find_max_dli_sensor(self) -> str | None:
        """
        Find the maximum DLI aggregated sensor for this location.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)
            location_name_safe = self.location_name.lower().replace(" ", "_")

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and f"{location_name_safe}_max_dli" in entity.unique_id
                ):
                    _LOGGER.debug("Found maximum DLI sensor: %s", entity.entity_id)
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error finding maximum DLI sensor: %s", exc)

        return None

    async def _find_high_threshold_ignore_until_entity(self) -> str | None:
        """
        Find DLI high threshold ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "dli_high_threshold_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found DLI high threshold ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Error finding DLI high threshold ignore until entity: %s", exc
            )

        return None

    async def _find_low_threshold_ignore_until_entity(self) -> str | None:
        """
        Find DLI low threshold ignore until datetime entity.

        Returns the entity_id if found, None otherwise.
        """
        try:
            ent_reg = er.async_get(self.hass)

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "datetime"
                    and entity.unique_id
                    and "dli_low_threshold_ignore_until" in entity.unique_id
                    and self.entry_id in entity.unique_id
                ):
                    _LOGGER.debug(
                        "Found DLI low threshold ignore until datetime: %s",
                        entity.entity_id,
                    )
                    return entity.entity_id

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug(
                "Error finding DLI low threshold ignore until entity: %s", exc
            )

        return None

    @callback
    def _weekly_average_dli_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle weekly average DLI sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._weekly_average_dli = None
        else:
            self._weekly_average_dli = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_dli_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle minimum DLI threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._min_dli = None
        else:
            self._min_dli = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_dli_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """Handle maximum DLI threshold changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._max_dli = None
        else:
            self._max_dli = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _high_threshold_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle DLI high threshold ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._high_threshold_ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._high_threshold_ignore_until_datetime = parsed_datetime
                else:
                    self._high_threshold_ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing DLI high threshold ignore until datetime: %s", exc
                )
                self._high_threshold_ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _low_threshold_ignore_until_state_changed(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle DLI low threshold ignore until datetime changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._low_threshold_ignore_until_datetime = None
        else:
            try:
                parsed_datetime = dt_util.parse_datetime(new_state.state)
                if parsed_datetime is not None:
                    # Ensure timezone info
                    if parsed_datetime.tzinfo is None:
                        parsed_datetime = parsed_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )
                    self._low_threshold_ignore_until_datetime = parsed_datetime
                else:
                    self._low_threshold_ignore_until_datetime = None
            except (ValueError, TypeError) as exc:
                _LOGGER.debug(
                    "Error parsing DLI low threshold ignore until datetime: %s", exc
                )
                self._low_threshold_ignore_until_datetime = None

        self._update_state()
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool | None:
        """Return True if DLI is outside acceptable range (problem)."""
        return self._state

    @property
    def icon(self) -> str:
        """Return icon based on sensor state and status."""
        if self._state is True:
            if self._dli_status == "above":
                return "mdi:white-balance-sunny"
            if self._dli_status == "below":
                return "mdi:sun-compass"
        return "mdi:counter"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        # Alert type based on DLI status
        alert_type = "Critical"
        status_message = f"Daily Light Integral {self._dli_status.capitalize()}"

        attrs = {
            "type": alert_type,
            "message": status_message,
            "task": True,
            "tags": [
                self.location_name.lower().replace(" ", "_"),
                self.irrigation_zone_name.lower().replace(" ", "_"),
            ],
            "dli_status": self._dli_status,
            "weekly_average_dli": self._weekly_average_dli,
            "minimum_dli_threshold": self._min_dli,
            "maximum_dli_threshold": self._max_dli,
        }

        # Add high threshold ignore until information if available
        if self._high_threshold_ignore_until_datetime:
            now = dt_util.now()
            attrs["high_threshold_ignore_until"] = (
                self._high_threshold_ignore_until_datetime.isoformat()
            )
            attrs["currently_ignoring_high"] = (
                now < self._high_threshold_ignore_until_datetime
            )

        # Add low threshold ignore until information if available
        if self._low_threshold_ignore_until_datetime:
            now = dt_util.now()
            attrs["low_threshold_ignore_until"] = (
                self._low_threshold_ignore_until_datetime.isoformat()
            )
            attrs["currently_ignoring_low"] = (
                now < self._low_threshold_ignore_until_datetime
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Entity is available if we can access the sensor registry
        return True

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def _restore_previous_state(self) -> None:
        """Restore previous state if available."""
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                self._state = last_state.state == "on"
                self._dli_status = last_state.attributes.get("dli_status", "normal")
                _LOGGER.info(
                    "Restored DLI status for %s: %s (%s)",
                    self.location_name,
                    self._state,
                    self._dli_status,
                )
            except (AttributeError, ValueError):
                pass

    async def _setup_weekly_average_dli_subscription(self) -> None:
        """Find and subscribe to weekly average DLI sensor."""
        weekly_avg_dli_entity_id = await self._find_weekly_average_dli_sensor()
        if weekly_avg_dli_entity_id:
            if weekly_avg_state := self.hass.states.get(weekly_avg_dli_entity_id):
                self._weekly_average_dli = self._parse_float(weekly_avg_state.state)

            try:
                self._unsubscribe_weekly_avg = async_track_state_change_event(
                    self.hass,
                    weekly_avg_dli_entity_id,
                    self._weekly_average_dli_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to weekly average DLI sensor: %s",
                    weekly_avg_dli_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to weekly average DLI sensor %s: %s",
                    weekly_avg_dli_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Weekly average DLI sensor not found for location %s",
                self.location_name,
            )

    async def _setup_min_dli_subscription(self) -> None:
        """Find and subscribe to minimum DLI sensor."""
        min_dli_entity_id = await self._find_min_dli_sensor()
        if min_dli_entity_id:
            if min_dli_state := self.hass.states.get(min_dli_entity_id):
                self._min_dli = self._parse_float(min_dli_state.state)

            try:
                self._unsubscribe_min_dli = async_track_state_change_event(
                    self.hass,
                    min_dli_entity_id,
                    self._min_dli_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to minimum DLI sensor: %s",
                    min_dli_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to minimum DLI sensor %s: %s",
                    min_dli_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Minimum DLI sensor not found for location %s",
                self.location_name,
            )

    async def _setup_max_dli_subscription(self) -> None:
        """Find and subscribe to maximum DLI sensor."""
        max_dli_entity_id = await self._find_max_dli_sensor()
        if max_dli_entity_id:
            if max_dli_state := self.hass.states.get(max_dli_entity_id):
                self._max_dli = self._parse_float(max_dli_state.state)

            try:
                self._unsubscribe_max_dli = async_track_state_change_event(
                    self.hass,
                    max_dli_entity_id,
                    self._max_dli_state_changed,
                )
                _LOGGER.debug(
                    "Subscribed to maximum DLI sensor: %s",
                    max_dli_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to maximum DLI sensor %s: %s",
                    max_dli_entity_id,
                    exc,
                )
        else:
            _LOGGER.warning(
                "Maximum DLI sensor not found for location %s",
                self.location_name,
            )

    async def _setup_high_threshold_ignore_until_subscription(self) -> None:
        """Find and subscribe to DLI high threshold ignore until datetime."""
        ignore_until_entity_id = await self._find_high_threshold_ignore_until_entity()
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._high_threshold_ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing DLI high threshold ignore until datetime: %s",
                        exc,
                    )

            try:
                self._unsubscribe_high_threshold_ignore_until = (
                    async_track_state_change_event(
                        self.hass,
                        ignore_until_entity_id,
                        self._high_threshold_ignore_until_state_changed,
                    )
                )
                _LOGGER.debug(
                    "Subscribed to DLI high threshold ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to DLI high threshold ignore until "
                    "entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "DLI high threshold ignore until datetime not found for location %s",
                self.location_name,
            )

    async def _setup_low_threshold_ignore_until_subscription(self) -> None:
        """Find and subscribe to DLI low threshold ignore until datetime."""
        ignore_until_entity_id = await self._find_low_threshold_ignore_until_entity()
        if ignore_until_entity_id:
            if ignore_until_state := self.hass.states.get(ignore_until_entity_id):
                try:
                    parsed_datetime = dt_util.parse_datetime(ignore_until_state.state)
                    if parsed_datetime is not None:
                        if parsed_datetime.tzinfo is None:
                            parsed_datetime = parsed_datetime.replace(
                                tzinfo=dt_util.get_default_time_zone()
                            )
                        self._low_threshold_ignore_until_datetime = parsed_datetime
                except (ValueError, TypeError) as exc:
                    _LOGGER.debug(
                        "Error parsing DLI low threshold ignore until datetime: %s", exc
                    )

            try:
                self._unsubscribe_low_threshold_ignore_until = (
                    async_track_state_change_event(
                        self.hass,
                        ignore_until_entity_id,
                        self._low_threshold_ignore_until_state_changed,
                    )
                )
                _LOGGER.debug(
                    "Subscribed to DLI low threshold ignore until datetime: %s",
                    ignore_until_entity_id,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to subscribe to DLI low threshold ignore until "
                    "entity %s: %s",
                    ignore_until_entity_id,
                    exc,
                )
        else:
            _LOGGER.debug(
                "DLI low threshold ignore until datetime not found for location %s",
                self.location_name,
            )

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Set up subscriptions
        await self._setup_weekly_average_dli_subscription()
        await self._setup_min_dli_subscription()
        await self._setup_max_dli_subscription()
        await self._setup_high_threshold_ignore_until_subscription()
        await self._setup_low_threshold_ignore_until_subscription()

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe_weekly_avg:
            self._unsubscribe_weekly_avg()
        if self._unsubscribe_min_dli:
            self._unsubscribe_min_dli()
        if self._unsubscribe_max_dli:
            self._unsubscribe_max_dli()
        if (
            hasattr(self, "_unsubscribe_high_threshold_ignore_until")
            and self._unsubscribe_high_threshold_ignore_until
        ):
            self._unsubscribe_high_threshold_ignore_until()
        if (
            hasattr(self, "_unsubscribe_low_threshold_ignore_until")
            and self._unsubscribe_low_threshold_ignore_until
        ):
            self._unsubscribe_low_threshold_ignore_until()


def _find_soil_moisture_entity(
    hass: HomeAssistant, location_name: str
) -> tuple[str, str | None] | None:
    """
    Find soil moisture entity from mirrored sensors.

    Returns:
        Tuple of (entity_id, unique_id) if found, None otherwise.

    """
    ent_reg = er.async_get(hass)
    soil_moisture_entity_id = None
    soil_moisture_unique_id = None

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "soil_moisture_mirror" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            soil_moisture_entity_id = entity.entity_id
            soil_moisture_unique_id = entity.unique_id
            _LOGGER.debug("Found soil moisture sensor: %s", soil_moisture_entity_id)
            break

    if soil_moisture_entity_id:
        return (soil_moisture_entity_id, soil_moisture_unique_id)
    return None


def _find_soil_conductivity_entity(
    hass: HomeAssistant, location_name: str
) -> tuple[str, str | None] | None:
    """
    Find soil conductivity entity from mirrored sensors.

    Returns:
        Tuple of (entity_id, unique_id) if found, None otherwise.

    """
    ent_reg = er.async_get(hass)
    soil_conductivity_entity_id = None
    soil_conductivity_unique_id = None

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "soil_conductivity_mirror" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            soil_conductivity_entity_id = entity.entity_id
            soil_conductivity_unique_id = entity.unique_id
            _LOGGER.debug(
                "Found soil conductivity sensor: %s", soil_conductivity_entity_id
            )
            break

    if soil_conductivity_entity_id:
        return (soil_conductivity_entity_id, soil_conductivity_unique_id)
    return None


def _find_temperature_entity(
    hass: HomeAssistant, location_name: str
) -> tuple[str, str | None] | None:
    """
    Find temperature entity from mirrored sensors.

    Returns:
        Tuple of (entity_id, unique_id) if found, None otherwise.

    """
    ent_reg = er.async_get(hass)
    temperature_entity_id = None
    temperature_unique_id = None

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "temperature_mirror" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            temperature_entity_id = entity.entity_id
            temperature_unique_id = entity.unique_id
            _LOGGER.debug("Found temperature sensor: %s", temperature_entity_id)
            break

    if temperature_entity_id:
        return (temperature_entity_id, temperature_unique_id)
    return None


def _find_humidity_entity(
    hass: HomeAssistant, location_name: str
) -> tuple[str, str | None] | None:
    """
    Find humidity entity from linked humidity sensors.

    Returns:
        Tuple of (entity_id, unique_id) if found, None otherwise.

    """
    ent_reg = er.async_get(hass)
    humidity_entity_id = None
    humidity_unique_id = None

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "humidity_linked" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            humidity_entity_id = entity.entity_id
            humidity_unique_id = entity.unique_id
            _LOGGER.debug("Found humidity sensor: %s", humidity_entity_id)
            break

    if humidity_entity_id:
        return (humidity_entity_id, humidity_unique_id)
    return None


def _find_battery_entity(
    hass: HomeAssistant, location_name: str
) -> tuple[str, str | None] | None:
    """
    Find battery entity from monitoring device sensors.

    Searches for the MonitoringSensor that mirrors the battery level from
    the monitoring device. The unique_id pattern is:
    plant_assistant_<entry_id>_<location_name>_monitor_battery_level

    Returns:
        Tuple of (entity_id, unique_id) if found, None otherwise.

    """
    ent_reg = er.async_get(hass)
    battery_entity_id = None
    battery_unique_id = None

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "monitor_battery_level" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            battery_entity_id = entity.entity_id
            battery_unique_id = entity.unique_id
            _LOGGER.debug("Found battery sensor: %s", battery_entity_id)
            break

    if battery_entity_id:
        return (battery_entity_id, battery_unique_id)
    return None


def _get_irrigation_zone_name(entry: ConfigEntry[Any], subentry: Any) -> str:
    """Get irrigation zone name from subentry's zone_id."""
    irrigation_zone_name = "Irrigation Zone"
    try:
        zone_id = subentry.data.get("zone_id", "zone-1")
        if entry.options:
            zones = entry.options.get("irrigation_zones", {})
            zone = zones.get(zone_id, {})
            irrigation_zone_name = zone.get("name", "Irrigation Zone")
    except (AttributeError, KeyError):
        pass

    return irrigation_zone_name


def _zone_has_esphome_device(
    hass: HomeAssistant, entry: ConfigEntry[Any], subentry: Any
) -> bool:
    """
    Check if the irrigation zone for this subentry has an ESPHome device linked.

    Returns True if the zone has a linked_device_id with an esphome identifier,
    False otherwise (virtual zone or non-esphome device).
    """
    try:
        zone_id = subentry.data.get("zone_id")
        if not zone_id:
            return False

        if not entry.options:
            return False

        zones = entry.options.get("irrigation_zones", {})
        zone = zones.get(zone_id, {})
        linked_device_id = zone.get("linked_device_id")

        if not linked_device_id:
            return False

        # Check if the device has an esphome identifier
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(linked_device_id)

        if not device or not device.identifiers:
            return False

        # Check if any identifier tuple has 'esphome' as the domain
        return any(domain == "esphome" for domain, _ in device.identifiers)

    except (AttributeError, KeyError):
        return False


def _find_recent_change_entity(hass: HomeAssistant, location_name: str) -> str | None:
    """
    Find soil moisture recent change entity for a location.

    Returns:
        Entity ID if found, None otherwise.

    """
    ent_reg = er.async_get(hass)

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "soil_moisture_recent_change" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            _LOGGER.debug(
                "Found soil moisture recent change sensor: %s", entity.entity_id
            )
            return entity.entity_id

    return None


async def _create_soil_moisture_sensor(  # noqa: PLR0913
    hass: HomeAssistant,
    subentry_id: str,
    location_name: str,
    irrigation_zone_name: str,
    location_device_id: str | None,
    *,
    has_esphome_device: bool = False,
) -> BinarySensorEntity | None:
    """Create soil moisture status monitor sensor."""
    soil_moisture_result = _find_soil_moisture_entity(hass, location_name)
    if not soil_moisture_result:
        _LOGGER.debug("No soil moisture sensor found for location %s", location_name)
        return None

    soil_moisture_entity_id, soil_moisture_unique_id = soil_moisture_result
    moisture_status_config = SoilMoistureStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        soil_moisture_entity_id=soil_moisture_entity_id,
        soil_moisture_entity_unique_id=soil_moisture_unique_id,
        location_device_id=location_device_id,
        has_esphome_device=has_esphome_device,
    )
    sensor = SoilMoistureStatusMonitorBinarySensor(moisture_status_config)
    _LOGGER.debug(
        "Created soil moisture status monitor binary sensor for %s",
        location_name,
    )
    return sensor


async def _create_soil_conductivity_sensor(  # noqa: PLR0913
    hass: HomeAssistant,
    subentry_id: str,
    location_name: str,
    irrigation_zone_name: str,
    location_device_id: str | None,
    *,
    has_esphome_device: bool = False,
) -> BinarySensorEntity | None:
    """Create soil conductivity status monitor sensor."""
    soil_conductivity_result = _find_soil_conductivity_entity(hass, location_name)
    if not soil_conductivity_result:
        _LOGGER.debug(
            "No soil conductivity sensor found for location %s", location_name
        )
        return None

    soil_conductivity_entity_id, soil_conductivity_unique_id = soil_conductivity_result
    conductivity_status_config = SoilConductivityStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        soil_conductivity_entity_id=soil_conductivity_entity_id,
        soil_conductivity_entity_unique_id=soil_conductivity_unique_id,
        location_device_id=location_device_id,
        has_esphome_device=has_esphome_device,
    )
    sensor = SoilConductivityStatusMonitorBinarySensor(conductivity_status_config)
    _LOGGER.debug(
        "Created soil conductivity status monitor binary sensor for %s",
        location_name,
    )
    return sensor


async def _create_temperature_sensor(
    hass: HomeAssistant,
    subentry_id: str,
    location_name: str,
    irrigation_zone_name: str,
    location_device_id: str | None,
) -> BinarySensorEntity | None:
    """Create temperature status monitor sensor."""
    temperature_result = _find_temperature_entity(hass, location_name)
    if not temperature_result:
        _LOGGER.debug("No temperature sensor found for location %s", location_name)
        return None

    temperature_entity_id, temperature_unique_id = temperature_result
    temperature_status_config = TemperatureStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        temperature_entity_id=temperature_entity_id,
        temperature_entity_unique_id=temperature_unique_id,
        location_device_id=location_device_id,
    )
    sensor = TemperatureStatusMonitorBinarySensor(temperature_status_config)
    _LOGGER.debug(
        "Created temperature status monitor binary sensor for %s",
        location_name,
    )
    return sensor


async def _create_humidity_sensor(
    hass: HomeAssistant,
    subentry_id: str,
    location_name: str,
    irrigation_zone_name: str,
    location_device_id: str | None,
) -> BinarySensorEntity | None:
    """Create humidity status monitor sensor."""
    humidity_result = _find_humidity_entity(hass, location_name)
    if not humidity_result:
        _LOGGER.debug("No humidity sensor found for location %s", location_name)
        return None

    humidity_entity_id, humidity_entity_unique_id = humidity_result
    humidity_status_config = HumidityStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        humidity_entity_id=humidity_entity_id,
        humidity_entity_unique_id=humidity_entity_unique_id,
        location_device_id=location_device_id,
    )
    sensor = HumidityStatusMonitorBinarySensor(humidity_status_config)
    _LOGGER.debug(
        "Created humidity status monitor binary sensor for %s",
        location_name,
    )
    return sensor


async def _create_battery_sensor(
    hass: HomeAssistant,
    subentry_id: str,
    location_name: str,
    irrigation_zone_name: str,
    location_device_id: str | None,
) -> BinarySensorEntity | None:
    """Create battery level status monitor sensor."""
    battery_result = _find_battery_entity(hass, location_name)
    if not battery_result:
        _LOGGER.debug("No battery sensor found for location %s", location_name)
        return None

    battery_entity_id, battery_entity_unique_id = battery_result
    battery_status_config = BatteryLevelStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        battery_entity_id=battery_entity_id,
        battery_entity_unique_id=battery_entity_unique_id,
        location_device_id=location_device_id,
    )
    sensor = BatteryLevelStatusMonitorBinarySensor(battery_status_config)
    _LOGGER.debug(
        "Created battery level status monitor binary sensor for %s",
        location_name,
    )
    return sensor


async def _create_dli_sensor(
    hass: HomeAssistant,
    subentry_id: str,
    location_name: str,
    irrigation_zone_name: str,
    location_device_id: str | None,
) -> BinarySensorEntity | None:
    """Create Daily Light Integral status monitor sensor."""
    dli_config = DailyLightIntegralStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        location_device_id=location_device_id,
    )
    sensor = DailyLightIntegralStatusMonitorBinarySensor(dli_config)
    _LOGGER.debug(
        "Created Daily Light Integral status monitor binary sensor for %s",
        location_name,
    )
    return sensor


async def _create_plant_count_sensor(
    config: PlantCountStatusMonitorConfig,
) -> BinarySensorEntity | None:
    """Create plant count status monitor sensor."""
    sensor = PlantCountStatusMonitorBinarySensor(config)
    _LOGGER.debug(
        "Created plant count status monitor binary sensor for %s",
        config.location_name,
    )
    return sensor


async def _create_ignored_statuses_sensor(
    config: IgnoredStatusesMonitorConfig,
) -> BinarySensorEntity | None:
    """Create ignored statuses monitor sensor."""
    sensor = IgnoredStatusesMonitorBinarySensor(config)
    _LOGGER.debug(
        "Created ignored statuses monitor binary sensor for %s",
        config.location_name,
    )
    return sensor


async def _create_status_sensor(
    config: StatusMonitorConfig,
) -> BinarySensorEntity | None:
    """Create overall status monitor sensor."""
    sensor = StatusMonitorBinarySensor(config)
    _LOGGER.debug(
        "Created overall status monitor binary sensor for %s",
        config.location_name,
    )
    return sensor


async def _create_master_schedule_status_sensor(
    config: MasterScheduleStatusMonitorConfig,
) -> BinarySensorEntity | None:
    """Create master schedule status monitor sensor."""
    sensor = MasterScheduleStatusMonitorBinarySensor(config)
    _LOGGER.debug(
        "Created master schedule status monitor binary sensor for %s",
        config.location_name,
    )
    return sensor


async def _create_schedule_misconfiguration_status_sensor(
    config: ScheduleMisconfigurationStatusMonitorConfig,
) -> BinarySensorEntity | None:
    """Create schedule misconfiguration status monitor sensor."""
    sensor = ScheduleMisconfigurationStatusMonitorBinarySensor(config)
    _LOGGER.debug(
        "Created schedule misconfiguration status monitor binary sensor for %s",
        config.location_name,
    )
    return sensor


async def _create_water_delivery_preference_status_sensor(
    config: WaterDeliveryPreferenceStatusMonitorConfig,
) -> BinarySensorEntity | None:
    """Create water delivery preference status monitor sensor."""
    sensor = WaterDeliveryPreferenceStatusMonitorBinarySensor(config)
    _LOGGER.debug(
        "Created water delivery preference status monitor binary sensor for %s",
        config.location_name,
    )
    return sensor


async def _create_error_status_sensor(
    config: ErrorStatusMonitorConfig,
) -> BinarySensorEntity | None:
    """Create error status monitor sensor."""
    sensor = ErrorStatusMonitorBinarySensor(config)
    _LOGGER.debug(
        "Created error status monitor binary sensor for %s",
        config.location_name,
    )
    return sensor


async def _create_esphome_running_status_sensor(
    config: ESPHomeRunningStatusMonitorConfig,
) -> BinarySensorEntity | None:
    """Create ESPHome running status monitor sensor."""
    sensor = ESPHomeRunningStatusMonitorBinarySensor(config)
    _LOGGER.debug(
        "Created esphome running status monitor binary sensor for %s",
        config.location_name,
    )
    return sensor


async def _create_irrigation_zone_status_sensor(
    config: IrrigationZoneStatusMonitorConfig,
) -> BinarySensorEntity | None:
    """Create irrigation zone overall status monitor sensor."""
    sensor = IrrigationZoneStatusMonitorBinarySensor(config)
    _LOGGER.debug(
        "Created irrigation zone status monitor binary sensor for %s",
        config.location_name,
    )
    return sensor


async def _create_link_monitors(
    config: LinkMonitorConfig,
) -> list[BinarySensorEntity]:
    """Create link (device availability) monitor sensors."""
    sensors: list[BinarySensorEntity] = []

    # Create link monitor sensor
    link_monitor_sensor = LinkMonitorBinarySensor(config)
    sensors.append(link_monitor_sensor)
    _LOGGER.debug(
        "Created link monitor binary sensor for %s",
        config.location_name,
    )

    # Create link status sensor
    link_status_sensor = LinkStatusBinarySensor(config)
    sensors.append(link_status_sensor)
    _LOGGER.debug(
        "Created link status monitor binary sensor for %s",
        config.location_name,
    )

    return sensors


async def _create_subentry_sensors(  # noqa: PLR0912, PLR0915
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    subentry_id: str,
    subentry: Any,
) -> list[BinarySensorEntity]:
    """Create binary sensors for a subentry if conditions are met."""
    subentry_binary_sensors: list[BinarySensorEntity] = []

    if "device_id" not in subentry.data:
        _LOGGER.warning("Subentry %s missing device_id", subentry_id)
        return subentry_binary_sensors

    location_name = subentry.data.get("name", "Plant Location")
    location_device_id = subentry_id
    monitoring_device_id = subentry.data.get("monitoring_device_id")
    plant_slots = subentry.data.get("plant_slots", {})

    # Calculate plant count
    plant_count = sum(
        1
        for slot in plant_slots.values()
        if isinstance(slot, dict) and slot.get("plant_device_id")
    )

    # Create plant count status sensor (always created to monitor plant assignments)
    irrigation_zone_name = _get_irrigation_zone_name(entry, subentry)
    plant_count_sensor_config = PlantCountStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        plant_count=plant_count,
        location_device_id=location_device_id,
    )
    plant_count_sensor = await _create_plant_count_sensor(
        plant_count_sensor_config,
    )
    if plant_count_sensor:
        subentry_binary_sensors.append(plant_count_sensor)

    # Create ignored statuses monitor sensor (always created to monitor ignored alerts)
    ignored_statuses_config = IgnoredStatusesMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        location_device_id=location_device_id,
    )
    ignored_statuses_sensor = await _create_ignored_statuses_sensor(
        ignored_statuses_config,
    )
    if ignored_statuses_sensor:
        subentry_binary_sensors.append(ignored_statuses_sensor)

    # Create overall status monitor sensor
    # (always created to monitor all status sensors)
    status_config = StatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        location_device_id=location_device_id,
    )
    status_sensor = await _create_status_sensor(status_config)
    if status_sensor:
        subentry_binary_sensors.append(status_sensor)

    has_plants = plant_count > 0

    if not (monitoring_device_id and has_plants):
        _LOGGER.debug(
            "Skipping environmental binary sensor creation for %s - "
            "monitoring_device_id=%s, has_plants=%s",
            location_name,
            monitoring_device_id,
            has_plants,
        )
        return subentry_binary_sensors

    soil_moisture_entity_id = _find_soil_moisture_entity(hass, location_name)
    if not soil_moisture_entity_id:
        _LOGGER.debug("No soil moisture sensor found for location %s", location_name)
        return subentry_binary_sensors

    # Determine if zone has ESPHome device
    has_esphome_device = _zone_has_esphome_device(hass, entry, subentry)

    # Create all environmental sensors
    moisture_sensor = await _create_soil_moisture_sensor(
        hass,
        subentry_id,
        location_name,
        irrigation_zone_name,
        location_device_id,
        has_esphome_device=has_esphome_device,
    )
    if moisture_sensor:
        subentry_binary_sensors.append(moisture_sensor)

    conductivity_sensor = await _create_soil_conductivity_sensor(
        hass,
        subentry_id,
        location_name,
        irrigation_zone_name,
        location_device_id,
        has_esphome_device=has_esphome_device,
    )
    if conductivity_sensor:
        subentry_binary_sensors.append(conductivity_sensor)

    temperature_sensor = await _create_temperature_sensor(
        hass, subentry_id, location_name, irrigation_zone_name, location_device_id
    )
    if temperature_sensor:
        subentry_binary_sensors.append(temperature_sensor)

    humidity_sensor = await _create_humidity_sensor(
        hass, subentry_id, location_name, irrigation_zone_name, location_device_id
    )
    if humidity_sensor:
        subentry_binary_sensors.append(humidity_sensor)

    battery_sensor = await _create_battery_sensor(
        hass, subentry_id, location_name, irrigation_zone_name, location_device_id
    )
    if battery_sensor:
        subentry_binary_sensors.append(battery_sensor)

    dli_sensor = await _create_dli_sensor(
        hass, subentry_id, location_name, irrigation_zone_name, location_device_id
    )
    if dli_sensor:
        subentry_binary_sensors.append(dli_sensor)

    # Create link monitors
    link_monitor_config = LinkMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        monitoring_device_id=monitoring_device_id,
        location_device_id=location_device_id,
    )
    link_monitors = await _create_link_monitors(link_monitor_config)
    subentry_binary_sensors.extend(link_monitors)

    # Create Recently Watered binary sensor for non-ESPHome zones
    # This sensor monitors the Recent Change sensor and turns ON when
    # soil moisture increases by 10% or more (indicating watering)
    if not _zone_has_esphome_device(hass, entry, subentry):
        recent_change_entity_id = _find_recent_change_entity(hass, location_name)
        if recent_change_entity_id:
            recently_watered_config = RecentlyWateredBinarySensorConfig(
                hass=hass,
                entry_id=subentry_id,
                location_name=location_name,
                location_device_id=location_device_id,
                recent_change_entity_id=recent_change_entity_id,
            )
            recently_watered_sensor = RecentlyWateredBinarySensor(
                recently_watered_config
            )
            subentry_binary_sensors.append(recently_watered_sensor)
            _LOGGER.debug(
                "Created recently watered binary sensor for %s (non-ESPHome zone)",
                location_name,
            )
        else:
            _LOGGER.debug(
                "No recent change sensor found for %s - "
                "skipping recently watered sensor",
                location_name,
            )
    else:
        _LOGGER.debug(
            "Skipping recently watered sensor for %s - "
            "ESPHome zone has direct watering data",
            location_name,
        )

    return subentry_binary_sensors


async def async_setup_platform(
    _hass: HomeAssistant,
    _config: dict[str, Any] | None,
    async_add_entities: AddEntitiesCallback,
    _discovery_info: Any = None,
) -> None:
    """Set up the binary_sensor platform."""
    # Binary sensors are set up via config entries


async def _create_zone_sensors(  # noqa: PLR0912, PLR0913, PLR0915
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    zone_id: str,
    zone_name: str,
    linked_device_id: str,
    zone_device_identifier: tuple[str, str],
) -> list[BinarySensorEntity]:
    """Create all sensors for a single irrigation zone."""
    zone_sensors: list[BinarySensorEntity] = []

    # Discover switch entities for this device instead of constructing entity IDs
    # This is more resilient to entity renames and doesn't assume naming patterns
    # Get all switch entities for this device to find them by unique_id patterns
    switch_entities = find_device_entities_by_pattern(
        hass,
        linked_device_id,
        "switch",
        None,  # Get all switches, we'll filter by unique_id
    )

    _LOGGER.debug(
        "Found switch entities for zone %s (device %s): %s",
        zone_name,
        linked_device_id,
        switch_entities,
    )

    # Discover sensor entities for error count
    sensor_entities = find_device_entities_by_pattern(
        hass,
        linked_device_id,
        "sensor",
        None,  # Get all sensors, we'll filter by unique_id
    )

    _LOGGER.debug(
        "Found sensor entities for zone %s (device %s): %s",
        zone_name,
        linked_device_id,
        sensor_entities,
    )

    # Filter switches by unique_id patterns
    master_schedule_entity_id = None
    master_schedule_unique_id = None
    sunrise_entity_id = None
    sunrise_unique_id = None
    afternoon_entity_id = None
    afternoon_unique_id = None
    sunset_entity_id = None
    sunset_unique_id = None
    rain_delivery_entity_id = None
    rain_delivery_unique_id = None
    main_delivery_entity_id = None
    main_delivery_unique_id = None

    for entity_id, unique_id in switch_entities.values():
        if unique_id:
            if "master_schedule" in unique_id:
                master_schedule_entity_id = entity_id
                master_schedule_unique_id = unique_id
            elif "sunrise_schedule" in unique_id:
                sunrise_entity_id = entity_id
                sunrise_unique_id = unique_id
            elif "afternoon_schedule" in unique_id:
                afternoon_entity_id = entity_id
                afternoon_unique_id = unique_id
            elif "sunset_schedule" in unique_id:
                sunset_entity_id = entity_id
                sunset_unique_id = unique_id
            elif "allow_rain_water_delivery" in unique_id:
                rain_delivery_entity_id = entity_id
                rain_delivery_unique_id = unique_id
            elif "allow_water_main_delivery" in unique_id:
                main_delivery_entity_id = entity_id
                main_delivery_unique_id = unique_id

    # Filter sensors by unique_id patterns
    error_count_entity_id = None
    error_count_unique_id = None

    for entity_id, unique_id in sensor_entities.values():
        if unique_id and "error_count" in unique_id:
            error_count_entity_id = entity_id
            error_count_unique_id = unique_id
            break

    if not master_schedule_entity_id:
        _LOGGER.warning(
            "Could not find master schedule switch for zone %s (device %s)",
            zone_name,
            linked_device_id,
        )
        # Don't create sensors if we can't find the master schedule switch
        return zone_sensors

    # Create master schedule status sensor
    master_schedule_config = MasterScheduleStatusMonitorConfig(
        hass=hass,
        entry_id=entry.entry_id,
        location_name=zone_name,
        irrigation_zone_name=zone_name,
        master_schedule_switch_entity_id=master_schedule_entity_id,
        master_schedule_switch_unique_id=master_schedule_unique_id,
        zone_device_identifier=zone_device_identifier,
    )
    master_schedule_sensor = await _create_master_schedule_status_sensor(
        master_schedule_config
    )
    if master_schedule_sensor:
        zone_sensors.append(master_schedule_sensor)
        _LOGGER.debug(
            "Created master schedule status sensor for irrigation zone %s "
            "(entity: %s, unique_id: %s)",
            zone_name,
            master_schedule_entity_id,
            master_schedule_unique_id,
        )

    # Create schedule misconfiguration status sensor if we have all required switches
    if all([sunrise_entity_id, afternoon_entity_id, sunset_entity_id]):
        schedule_misconfiguration_config = ScheduleMisconfigurationStatusMonitorConfig(
            hass=hass,
            entry_id=entry.entry_id,
            location_name=zone_name,
            irrigation_zone_name=zone_name,
            master_schedule_switch_entity_id=master_schedule_entity_id,
            master_schedule_switch_unique_id=master_schedule_unique_id,
            sunrise_switch_entity_id=sunrise_entity_id,
            sunrise_switch_unique_id=sunrise_unique_id,
            afternoon_switch_entity_id=afternoon_entity_id,
            afternoon_switch_unique_id=afternoon_unique_id,
            sunset_switch_entity_id=sunset_entity_id,
            sunset_switch_unique_id=sunset_unique_id,
            zone_device_identifier=zone_device_identifier,
        )
        schedule_misconfiguration_sensor = (
            await _create_schedule_misconfiguration_status_sensor(
                schedule_misconfiguration_config
            )
        )
        if schedule_misconfiguration_sensor:
            zone_sensors.append(schedule_misconfiguration_sensor)
            _LOGGER.debug(
                "Created schedule misconfiguration status sensor for irrigation "
                "zone %s",
                zone_name,
            )
    else:
        _LOGGER.debug(
            "Skipping schedule misconfiguration sensor for zone %s - "
            "not all time schedule switches found",
            zone_name,
        )

    # Create water delivery preference status sensor if we have both switches
    if rain_delivery_entity_id and main_delivery_entity_id:
        water_delivery_preference_config = WaterDeliveryPreferenceStatusMonitorConfig(
            hass=hass,
            entry_id=entry.entry_id,
            location_name=zone_name,
            irrigation_zone_name=zone_name,
            master_schedule_switch_entity_id=master_schedule_entity_id,
            master_schedule_switch_unique_id=master_schedule_unique_id,
            allow_rain_water_delivery_switch_entity_id=rain_delivery_entity_id,
            allow_rain_water_delivery_switch_unique_id=rain_delivery_unique_id,
            allow_water_main_delivery_switch_entity_id=main_delivery_entity_id,
            allow_water_main_delivery_switch_unique_id=main_delivery_unique_id,
            zone_device_identifier=zone_device_identifier,
        )
        water_delivery_preference_sensor = (
            await _create_water_delivery_preference_status_sensor(
                water_delivery_preference_config
            )
        )
        if water_delivery_preference_sensor:
            zone_sensors.append(water_delivery_preference_sensor)
            _LOGGER.debug(
                "Created water delivery preference status sensor for irrigation "
                "zone %s",
                zone_name,
            )
    else:
        _LOGGER.debug(
            "Skipping water delivery preference sensor for zone %s - "
            "not all delivery switches found",
            zone_name,
        )

    # Create error status sensor if we have the error count sensor
    if error_count_entity_id:
        error_status_config = ErrorStatusMonitorConfig(
            hass=hass,
            entry_id=entry.entry_id,
            location_name=zone_name,
            irrigation_zone_name=zone_name,
            error_count_entity_id=error_count_entity_id,
            error_count_entity_unique_id=error_count_unique_id,
            zone_device_identifier=zone_device_identifier,
        )
        error_status_sensor = await _create_error_status_sensor(error_status_config)
        if error_status_sensor:
            zone_sensors.append(error_status_sensor)
            _LOGGER.debug(
                "Created error status sensor for irrigation zone %s "
                "(entity: %s, unique_id: %s)",
                zone_name,
                error_count_entity_id,
                error_count_unique_id,
            )
    else:
        _LOGGER.debug(
            "Skipping error status sensor for zone %s - error count sensor not found",
            zone_name,
        )

    # Create ESPHome running status sensor (monitors binary sensor with 'running'
    # device class on linked ESPHome device)
    esphome_running_config = ESPHomeRunningStatusMonitorConfig(
        hass=hass,
        entry_id=entry.entry_id,
        location_name=zone_name,
        irrigation_zone_name=zone_name,
        monitoring_device_id=linked_device_id,
        zone_device_identifier=zone_device_identifier,
    )
    esphome_running_sensor = await _create_esphome_running_status_sensor(
        esphome_running_config
    )
    if esphome_running_sensor:
        zone_sensors.append(esphome_running_sensor)
        _LOGGER.debug(
            "Created esphome running status sensor for irrigation zone %s",
            zone_name,
        )

    # Create overall irrigation zone status sensor (monitors all zone problem sensors
    # and associated plant location status sensors)
    irrigation_zone_status_config = IrrigationZoneStatusMonitorConfig(
        hass=hass,
        entry_id=entry.entry_id,
        location_name=zone_name,
        irrigation_zone_name=zone_name,
        zone_id=zone_id,
        zone_device_identifier=zone_device_identifier,
    )
    irrigation_zone_status_sensor = await _create_irrigation_zone_status_sensor(
        irrigation_zone_status_config
    )
    if irrigation_zone_status_sensor:
        zone_sensors.append(irrigation_zone_status_sensor)
        _LOGGER.debug(
            "Created overall status sensor for irrigation zone %s",
            zone_name,
        )

    return zone_sensors


async def _setup_irrigation_zone_sensors(
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up master schedule status sensors for irrigation zones."""
    irrigation_zones = entry.options.get("irrigation_zones", {})
    if not irrigation_zones:
        return

    _LOGGER.debug(
        "Processing %d irrigation zones for master schedule status sensors",
        len(irrigation_zones),
    )

    irrigation_zone_sensors: list[BinarySensorEntity] = []
    device_registry = dr.async_get(hass)

    for zone_id, zone_data in irrigation_zones.items():
        if not isinstance(zone_data, dict):
            continue

        linked_device_id = zone_data.get("linked_device_id")
        if not linked_device_id:
            continue

        zone_name = zone_data.get("name", f"Zone {zone_id}")

        # Get the zone device from device registry
        zone_device = device_registry.async_get(linked_device_id)
        if not zone_device:
            _LOGGER.warning(
                "Could not find zone device with ID %s for zone %s",
                linked_device_id,
                zone_name,
            )
            continue

        # Get the first identifier from the zone device
        zone_device_identifier = (
            next(iter(zone_device.identifiers))
            if zone_device.identifiers
            else (DOMAIN, linked_device_id)
        )

        # Create all sensors for this zone
        zone_sensors = await _create_zone_sensors(
            hass, entry, zone_id, zone_name, linked_device_id, zone_device_identifier
        )
        irrigation_zone_sensors.extend(zone_sensors)

    if irrigation_zone_sensors:
        async_add_entities(irrigation_zone_sensors)


async def _setup_subentry_sensors(
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for subentries."""
    if not entry.subentries:
        return

    _LOGGER.debug(
        "Processing main entry with %d subentries for binary sensors",
        len(entry.subentries),
    )

    for subentry_id, subentry in entry.subentries.items():
        subentry_binary_sensors = await _create_subentry_sensors(
            hass, entry, subentry_id, subentry
        )

        # Add entities with proper subentry association (like openplantbook_ref)
        if subentry_binary_sensors:
            _LOGGER.debug(
                "Adding %d binary sensors for subentry %s",
                len(subentry_binary_sensors),
                subentry_id,
            )
            _add_entities = cast("Callable[..., Any]", async_add_entities)
            _add_entities(subentry_binary_sensors, config_subentry_id=subentry_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for a config entry."""
    _LOGGER.debug(
        "Setting up binary sensors for entry: %s (%s)",
        entry.title,
        entry.entry_id,
    )

    # Skip individual subentry processing - they are handled by main entry
    if "device_id" in entry.data and not entry.subentries:
        _LOGGER.debug(
            "Skipping individual subentry processing for %s - handled by main entry",
            entry.entry_id,
        )
        return

    # Process master schedule status sensors for irrigation zones with linked devices
    await _setup_irrigation_zone_sensors(hass, entry, async_add_entities)

    # Process main entry subentries (like openplantbook_ref)
    await _setup_subentry_sensors(hass, entry, async_add_entities)
