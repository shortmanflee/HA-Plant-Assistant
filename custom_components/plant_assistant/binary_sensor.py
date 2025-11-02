"""
Binary sensors for the Plant Assistant integration.

This module provides binary sensors that monitor plant health conditions,
such as soil moisture levels falling below configured thresholds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

# Battery level threshold (percentage) for low battery alert
BATTERY_LEVEL_THRESHOLD = 10


@dataclass
class SoilMoistureLowMonitorConfig:
    """Configuration for SoilMoistureLowMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_moisture_entity_id: str
    location_device_id: str | None = None


@dataclass
class SoilMoistureHighMonitorConfig:
    """Configuration for SoilMoistureHighMonitorBinarySensor."""

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


@dataclass
class SoilConductivityStatusMonitorConfig:
    """Configuration for SoilConductivityStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_conductivity_entity_id: str
    location_device_id: str | None = None


@dataclass
class SoilMoistureStatusMonitorConfig:
    """Configuration for SoilMoistureStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    soil_moisture_entity_id: str
    location_device_id: str | None = None


@dataclass
class TemperatureStatusMonitorConfig:
    """Configuration for TemperatureStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    temperature_entity_id: str
    location_device_id: str | None = None


@dataclass
class HumidityStatusMonitorConfig:
    """Configuration for HumidityStatusMonitorBinarySensor."""

    hass: HomeAssistant
    entry_id: str
    location_name: str
    irrigation_zone_name: str
    humidity_entity_id: str
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
    def _soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil moisture sensor state changes."""
        if new_state is None:
            self._current_soil_moisture = None
        else:
            self._current_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle minimum soil moisture threshold changes."""
        if new_state is None:
            self._min_soil_moisture = None
        else:
            self._min_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _soil_moisture_ignore_until_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil moisture ignore until datetime changes."""
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
                self._unsubscribe_min = async_track_state_change(
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
                self._unsubscribe_ignore_until = async_track_state_change(
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
        try:
            self._unsubscribe = async_track_state_change(
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

    @callback
    def _soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil moisture sensor state changes."""
        if new_state is None:
            self._current_soil_moisture = None
        else:
            self._current_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle maximum soil moisture threshold changes."""
        if new_state is None:
            self._max_soil_moisture = None
        else:
            self._max_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _soil_moisture_ignore_until_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil moisture ignore until datetime changes."""
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
                self._unsubscribe_max = async_track_state_change(
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
                self._unsubscribe_ignore_until = async_track_state_change(
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

    async def _setup_soil_moisture_subscription(self) -> None:
        """Subscribe to soil moisture entity state changes."""
        try:
            self._unsubscribe = async_track_state_change(
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
        await self._setup_max_soil_moisture_subscription()
        await self._setup_ignore_until_subscription()
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
    def _soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil moisture sensor state changes."""
        if new_state is None:
            self._current_soil_moisture = None
        else:
            self._current_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle minimum soil moisture threshold changes."""
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
                self._unsubscribe_min = async_track_state_change(
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
            self._unsubscribe = async_track_state_change(
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
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil conductivity sensor state changes."""
        if new_state is None:
            self._current_soil_conductivity = None
        else:
            self._current_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_conductivity_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle minimum soil conductivity threshold changes."""
        if new_state is None:
            self._min_soil_conductivity = None
        else:
            self._min_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil moisture sensor state changes."""
        if new_state is None:
            self._current_soil_moisture = None
        else:
            self._current_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle minimum soil moisture threshold changes."""
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
            self._unsubscribe = async_track_state_change(
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
            self._unsubscribe_moisture = async_track_state_change(
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
                self._unsubscribe_conductivity_min = async_track_state_change(
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
                self._unsubscribe_moisture_min = async_track_state_change(
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

    def _update_state(self) -> None:
        """Update binary sensor state based on conductivity and maximum threshold."""
        # If either value is unavailable, set state to None (sensor unavailable)
        if (
            self._current_soil_conductivity is None
            or self._max_soil_conductivity is None
        ):
            self._state = None
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

    @callback
    def _soil_conductivity_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil conductivity sensor state changes."""
        if new_state is None:
            self._current_soil_conductivity = None
        else:
            self._current_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_soil_conductivity_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle maximum soil conductivity threshold changes."""
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
            self._unsubscribe = async_track_state_change(
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
                self._unsubscribe_conductivity_max = async_track_state_change(
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

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Set up subscriptions
        await self._setup_soil_conductivity_subscription()
        await self._setup_max_soil_conductivity_subscription()

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
        self._min_soil_conductivity: float | None = None
        self._max_soil_conductivity: float | None = None
        self._current_soil_conductivity: float | None = None
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

    @callback
    def _soil_conductivity_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil conductivity sensor state changes."""
        if new_state is None:
            self._current_soil_conductivity = None
        else:
            self._current_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_conductivity_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle minimum soil conductivity threshold changes."""
        if new_state is None:
            self._min_soil_conductivity = None
        else:
            self._min_soil_conductivity = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_soil_conductivity_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle maximum soil conductivity threshold changes."""
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
            self._unsubscribe = async_track_state_change(
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
                self._unsubscribe_conductivity_min = async_track_state_change(
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
                self._unsubscribe_conductivity_max = async_track_state_change(
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

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to state changes."""
        # Restore previous state if available
        await super().async_added_to_hass()
        await self._restore_previous_state()

        # Set up subscriptions
        await self._setup_soil_conductivity_subscription()
        await self._setup_min_soil_conductivity_subscription()
        await self._setup_max_soil_conductivity_subscription()

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
        self._min_soil_moisture: float | None = None
        self._max_soil_moisture: float | None = None
        self._current_soil_moisture: float | None = None
        self._ignore_until_datetime: Any = None
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

    @callback
    def _soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil moisture sensor state changes."""
        if new_state is None:
            self._current_soil_moisture = None
        else:
            self._current_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle minimum soil moisture threshold changes."""
        if new_state is None:
            self._min_soil_moisture = None
        else:
            self._min_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_soil_moisture_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle maximum soil moisture threshold changes."""
        if new_state is None:
            self._max_soil_moisture = None
        else:
            self._max_soil_moisture = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _soil_moisture_ignore_until_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle soil moisture ignore until datetime changes."""
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
            self._unsubscribe = async_track_state_change(
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
                self._unsubscribe_moisture_min = async_track_state_change(
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
                self._unsubscribe_moisture_max = async_track_state_change(
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
                self._unsubscribe_ignore_until = async_track_state_change(
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
        self._above_threshold_hours: float | None = None
        self._below_threshold_hours: float | None = None
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

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and (
                        f"{location_name_safe}_temperature_above_threshold_weekly_duration"
                        in entity.unique_id
                    )
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

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and (
                        f"{location_name_safe}_temperature_below_threshold_weekly_duration"
                        in entity.unique_id
                    )
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
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle temperature above threshold duration sensor state changes."""
        if new_state is None:
            self._above_threshold_hours = None
        else:
            self._above_threshold_hours = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _below_threshold_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle temperature below threshold duration sensor state changes."""
        if new_state is None:
            self._below_threshold_hours = None
        else:
            self._below_threshold_hours = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _high_threshold_ignore_until_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle temperature high threshold ignore until datetime changes."""
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
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle temperature low threshold ignore until datetime changes."""
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
        temperature_state = self.hass.states.get(self.temperature_entity_id)
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
                self._unsubscribe_above = async_track_state_change(
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
                self._unsubscribe_below = async_track_state_change(
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
                    async_track_state_change(
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
                self._unsubscribe_low_threshold_ignore_until = async_track_state_change(
                    self.hass,
                    ignore_until_entity_id,
                    self._low_threshold_ignore_until_state_changed,
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
        self._above_threshold_hours: float | None = None
        self._below_threshold_hours: float | None = None
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

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and (
                        f"{location_name_safe}_humidity_above_threshold_weekly_duration"
                        in entity.unique_id
                    )
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

            for entity in ent_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.domain == "sensor"
                    and entity.unique_id
                    and (
                        f"{location_name_safe}_humidity_below_threshold_weekly_duration"
                        in entity.unique_id
                    )
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
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle humidity above threshold duration sensor state changes."""
        if new_state is None:
            self._above_threshold_hours = None
        else:
            self._above_threshold_hours = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _below_threshold_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle humidity below threshold duration sensor state changes."""
        if new_state is None:
            self._below_threshold_hours = None
        else:
            self._below_threshold_hours = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _high_threshold_ignore_until_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle humidity high threshold ignore until datetime changes."""
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
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle humidity low threshold ignore until datetime changes."""
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
        humidity_state = self.hass.states.get(self.humidity_entity_id)
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
                self._unsubscribe_above = async_track_state_change(
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
                self._unsubscribe_below = async_track_state_change(
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
                    async_track_state_change(
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
                self._unsubscribe_low_threshold_ignore_until = async_track_state_change(
                    self.hass,
                    ignore_until_entity_id,
                    self._low_threshold_ignore_until_state_changed,
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
        self._unsubscribe: Any = None

    def _parse_float(self, value: Any) -> float | None:
        """Parse a value to float, handling unavailable/unknown states."""
        if value is None or value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _update_state(self) -> None:
        """Update binary sensor state based on current battery level."""
        # If battery level is unavailable, set state to None (sensor unavailable)
        if self._current_battery_level is None:
            self._state = None
            return

        # Binary sensor is ON (problem) when battery level < threshold
        self._state = self._current_battery_level < BATTERY_LEVEL_THRESHOLD

    @callback
    def _battery_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle battery level sensor state changes."""
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

        return {
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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        battery_state = self.hass.states.get(self.battery_entity_id)
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
            self._unsubscribe = async_track_state_change(
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

    async def async_added_to_hass(self) -> None:
        """Restore and initialize battery level monitoring on addition."""
        # Restore previous state
        await self._restore_previous_state()

        # Initialize with current state of battery entity
        if battery_state := self.hass.states.get(self.battery_entity_id):
            self._current_battery_level = self._parse_float(battery_state.state)

        # Update state based on initial value
        self._update_state()

        # Set up subscription
        await self._setup_battery_subscription()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


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
        self._attr_name = f"{self.location_name} Link"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_link_monitor"
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
            def _entity_state_changed(
                _entity_id: str, _old_state: Any, _new_state: Any
            ) -> None:
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
                    self._unsubscribe_entities = async_track_state_change(
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
        self._attr_name = f"{self.location_name} Link Status"

        # Generate unique_id
        location_name_safe = self.location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{self.entry_id}_{location_name_safe}_link_status_monitor"
        )

        # Set binary sensor properties
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM

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

        # Binary sensor is ON (problem) when device is unavailable
        self._state = not self._device_available

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

        return {
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
            def _entity_state_changed(
                _entity_id: str, _old_state: Any, _new_state: Any
            ) -> None:
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
                    self._unsubscribe_entities = async_track_state_change(
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

        # Update initial state
        self._update_state()
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
        if hasattr(self, "_unsubscribe_entities") and self._unsubscribe_entities:
            self._unsubscribe_entities()


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
        self._weekly_average_dli: float | None = None
        self._min_dli: float | None = None
        self._max_dli: float | None = None
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
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle weekly average DLI sensor state changes."""
        if new_state is None:
            self._weekly_average_dli = None
        else:
            self._weekly_average_dli = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _min_dli_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle minimum DLI threshold changes."""
        if new_state is None:
            self._min_dli = None
        else:
            self._min_dli = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _max_dli_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle maximum DLI threshold changes."""
        if new_state is None:
            self._max_dli = None
        else:
            self._max_dli = self._parse_float(new_state.state)

        self._update_state()
        self.async_write_ha_state()

    @callback
    def _high_threshold_ignore_until_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle DLI high threshold ignore until datetime changes."""
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
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle DLI low threshold ignore until datetime changes."""
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
                self._unsubscribe_weekly_avg = async_track_state_change(
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
                self._unsubscribe_min_dli = async_track_state_change(
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
                self._unsubscribe_max_dli = async_track_state_change(
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
                    async_track_state_change(
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
                self._unsubscribe_low_threshold_ignore_until = async_track_state_change(
                    self.hass,
                    ignore_until_entity_id,
                    self._low_threshold_ignore_until_state_changed,
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


def _find_soil_moisture_entity(hass: HomeAssistant, location_name: str) -> str | None:
    """Find soil moisture entity from mirrored sensors."""
    ent_reg = er.async_get(hass)
    soil_moisture_entity_id = None

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "soil_moisture_mirror" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            soil_moisture_entity_id = entity.entity_id
            _LOGGER.debug("Found soil moisture sensor: %s", soil_moisture_entity_id)
            break

    return soil_moisture_entity_id


def _find_soil_conductivity_entity(
    hass: HomeAssistant, location_name: str
) -> str | None:
    """Find soil conductivity entity from mirrored sensors."""
    ent_reg = er.async_get(hass)
    soil_conductivity_entity_id = None

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "soil_conductivity_mirror" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            soil_conductivity_entity_id = entity.entity_id
            _LOGGER.debug(
                "Found soil conductivity sensor: %s", soil_conductivity_entity_id
            )
            break

    return soil_conductivity_entity_id


def _find_temperature_entity(hass: HomeAssistant, location_name: str) -> str | None:
    """Find temperature entity from mirrored sensors."""
    ent_reg = er.async_get(hass)
    temperature_entity_id = None

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "temperature_mirror" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            temperature_entity_id = entity.entity_id
            _LOGGER.debug("Found temperature sensor: %s", temperature_entity_id)
            break

    return temperature_entity_id


def _find_humidity_entity(hass: HomeAssistant, location_name: str) -> str | None:
    """Find humidity entity from linked humidity sensors."""
    ent_reg = er.async_get(hass)
    humidity_entity_id = None

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "humidity_linked" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            humidity_entity_id = entity.entity_id
            _LOGGER.debug("Found humidity sensor: %s", humidity_entity_id)
            break

    return humidity_entity_id


def _find_battery_entity(hass: HomeAssistant, location_name: str) -> str | None:
    """
    Find battery entity from monitoring device sensors.

    Searches for the MonitoringSensor that mirrors the battery level from
    the monitoring device. The unique_id pattern is:
    plant_assistant_<entry_id>_<location_name>_monitor_battery_level
    """
    ent_reg = er.async_get(hass)
    battery_entity_id = None

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id
            and "monitor_battery_level" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            battery_entity_id = entity.entity_id
            _LOGGER.debug("Found battery sensor: %s", battery_entity_id)
            break

    return battery_entity_id


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


async def _create_soil_moisture_sensor(
    hass: HomeAssistant,
    subentry_id: str,
    location_name: str,
    irrigation_zone_name: str,
    location_device_id: str | None,
) -> BinarySensorEntity | None:
    """Create soil moisture status monitor sensor."""
    soil_moisture_entity_id = _find_soil_moisture_entity(hass, location_name)
    if not soil_moisture_entity_id:
        _LOGGER.debug("No soil moisture sensor found for location %s", location_name)
        return None

    moisture_status_config = SoilMoistureStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        soil_moisture_entity_id=soil_moisture_entity_id,
        location_device_id=location_device_id,
    )
    sensor = SoilMoistureStatusMonitorBinarySensor(moisture_status_config)
    _LOGGER.debug(
        "Created soil moisture status monitor binary sensor for %s",
        location_name,
    )
    return sensor


async def _create_soil_conductivity_sensor(
    hass: HomeAssistant,
    subentry_id: str,
    location_name: str,
    irrigation_zone_name: str,
    location_device_id: str | None,
) -> BinarySensorEntity | None:
    """Create soil conductivity status monitor sensor."""
    soil_conductivity_entity_id = _find_soil_conductivity_entity(hass, location_name)
    if not soil_conductivity_entity_id:
        _LOGGER.debug(
            "No soil conductivity sensor found for location %s", location_name
        )
        return None

    conductivity_status_config = SoilConductivityStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        soil_conductivity_entity_id=soil_conductivity_entity_id,
        location_device_id=location_device_id,
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
    temperature_entity_id = _find_temperature_entity(hass, location_name)
    if not temperature_entity_id:
        _LOGGER.debug("No temperature sensor found for location %s", location_name)
        return None

    temperature_status_config = TemperatureStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        temperature_entity_id=temperature_entity_id,
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
    humidity_entity_id = _find_humidity_entity(hass, location_name)
    if not humidity_entity_id:
        _LOGGER.debug("No humidity sensor found for location %s", location_name)
        return None

    humidity_status_config = HumidityStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        humidity_entity_id=humidity_entity_id,
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
    battery_entity_id = _find_battery_entity(hass, location_name)
    if not battery_entity_id:
        _LOGGER.debug("No battery sensor found for location %s", location_name)
        return None

    battery_status_config = BatteryLevelStatusMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        battery_entity_id=battery_entity_id,
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


async def _create_subentry_sensors(
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

    # Create all environmental sensors
    moisture_sensor = await _create_soil_moisture_sensor(
        hass, subentry_id, location_name, irrigation_zone_name, location_device_id
    )
    if moisture_sensor:
        subentry_binary_sensors.append(moisture_sensor)

    conductivity_sensor = await _create_soil_conductivity_sensor(
        hass, subentry_id, location_name, irrigation_zone_name, location_device_id
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

    return subentry_binary_sensors


async def async_setup_platform(
    _hass: HomeAssistant,
    _config: dict[str, Any] | None,
    async_add_entities: AddEntitiesCallback,
    _discovery_info: Any = None,
) -> None:
    """Set up the binary_sensor platform (legacy)."""
    # Binary sensors are set up via config entries, not legacy platform


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

    # Process main entry subentries (like openplantbook_ref)
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
