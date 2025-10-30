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

    has_plants = any(
        isinstance(slot, dict) and slot.get("plant_device_id")
        for slot in plant_slots.values()
    )

    if not (monitoring_device_id and has_plants):
        _LOGGER.debug(
            "Skipping binary sensor creation for %s - "
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

    irrigation_zone_name = _get_irrigation_zone_name(entry, subentry)

    # Create soil moisture low monitor
    low_config = SoilMoistureLowMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        soil_moisture_entity_id=soil_moisture_entity_id,
        location_device_id=location_device_id,
    )
    soil_moisture_low_sensor = SoilMoistureLowMonitorBinarySensor(low_config)
    subentry_binary_sensors.append(soil_moisture_low_sensor)
    _LOGGER.debug(
        "Created soil moisture low monitor binary sensor for %s",
        location_name,
    )

    # Create soil moisture high monitor
    high_config = SoilMoistureHighMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        soil_moisture_entity_id=soil_moisture_entity_id,
        location_device_id=location_device_id,
    )
    soil_moisture_high_sensor = SoilMoistureHighMonitorBinarySensor(high_config)
    subentry_binary_sensors.append(soil_moisture_high_sensor)
    _LOGGER.debug(
        "Created soil moisture high monitor binary sensor for %s",
        location_name,
    )

    # Create soil moisture water soon monitor
    water_soon_config = SoilMoistureWaterSoonMonitorConfig(
        hass=hass,
        entry_id=subentry_id,
        location_name=location_name,
        irrigation_zone_name=irrigation_zone_name,
        soil_moisture_entity_id=soil_moisture_entity_id,
        location_device_id=location_device_id,
    )
    soil_moisture_water_soon_sensor = SoilMoistureWaterSoonMonitorBinarySensor(
        water_soon_config
    )
    subentry_binary_sensors.append(soil_moisture_water_soon_sensor)
    _LOGGER.debug(
        "Created soil moisture water soon monitor binary sensor for %s",
        location_name,
    )

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
