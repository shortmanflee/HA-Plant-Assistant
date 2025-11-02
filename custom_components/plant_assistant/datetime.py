"""
Datetime entities for the Plant Assistant integration.

This module provides datetime entities for managing plant care scheduling,
such as "temperature low threshold ignore until" functionality.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .sensor import _get_monitoring_device_sensors, _has_plants_in_slots

if TYPE_CHECKING:
    import datetime as py_datetime
    from collections.abc import Mapping

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


def _collect_expected_datetime_entities(
    subentry: Any,
) -> set[str]:
    """Collect expected datetime entity unique IDs for a subentry."""
    expected: set[str] = set()
    if "device_id" not in subentry.data:
        return expected

    monitoring_device_id = subentry.data.get("monitoring_device_id")
    humidity_entity_id = subentry.data.get("humidity_entity_id")

    has_monitoring_device = bool(monitoring_device_id)
    has_humidity_sensor = bool(humidity_entity_id)
    has_plant_slots = _has_plants_in_slots(subentry.data)

    # Temperature entities
    if has_monitoring_device and has_plant_slots:
        expected.add(
            f"{DOMAIN}_{subentry.subentry_id}_temperature_low_threshold_ignore_until"
        )
        expected.add(
            f"{DOMAIN}_{subentry.subentry_id}_temperature_high_threshold_ignore_until"
        )

    # Humidity entities
    if has_humidity_sensor and has_plant_slots:
        expected.add(f"{DOMAIN}_{subentry.subentry_id}_humidity_ignore_until")
        expected.add(
            f"{DOMAIN}_{subentry.subentry_id}_humidity_high_threshold_ignore_until"
        )

    # Soil moisture entities
    if has_monitoring_device and has_plant_slots:
        expected.add(f"{DOMAIN}_{subentry.subentry_id}_soil_moisture_ignore_until")
        expected.add(
            f"{DOMAIN}_{subentry.subentry_id}_soil_moisture_high_threshold_ignore_until"
        )

    # Plant count ignore until entity
    if has_plant_slots:
        expected.add(f"{DOMAIN}_{subentry.subentry_id}_plant_count_ignore_until")

    return expected


async def _cleanup_orphaned_datetime_entities(  # noqa: PLR0912
    hass: HomeAssistant, entry: ConfigEntry[Any]
) -> None:
    """Clean up datetime entities that are no longer configured."""
    try:
        entity_registry = er.async_get(hass)
        expected_datetime_entities = set()

        # Collect expected entities from all subentries
        if entry.subentries:
            for subentry in entry.subentries.values():
                expected_datetime_entities.update(
                    _collect_expected_datetime_entities(subentry)
                )

                # Additional entities for soil conductivity and DLI
                if "device_id" in subentry.data:
                    monitoring_device_id = subentry.data.get("monitoring_device_id")
                    has_monitoring_device = bool(monitoring_device_id)
                    has_plant_slots = _has_plants_in_slots(subentry.data)

                    if has_monitoring_device and has_plant_slots:
                        try:
                            device_sensors = _get_monitoring_device_sensors(
                                hass, monitoring_device_id
                            )
                            soil_conductivity_entity_id = device_sensors.get(
                                "soil_conductivity"
                            )
                            illuminance_entity_id = device_sensors.get("illuminance")

                            if soil_conductivity_entity_id:
                                expected_datetime_entities.add(
                                    f"{DOMAIN}_{subentry.subentry_id}_"
                                    "soil_conductivity_ignore_until"
                                )
                                expected_datetime_entities.add(
                                    f"{DOMAIN}_{subentry.subentry_id}_"
                                    "soil_conductivity_high_threshold_ignore_until"
                                )

                            if illuminance_entity_id:
                                expected_datetime_entities.add(
                                    f"{DOMAIN}_{subentry.subentry_id}_"
                                    "daily_light_integral_high_threshold_ignore_until"
                                )
                                expected_datetime_entities.add(
                                    f"{DOMAIN}_{subentry.subentry_id}_"
                                    "daily_light_integral_low_threshold_ignore_until"
                                )
                        except (
                            ValueError,
                            TypeError,
                        ) as discovery_error:  # pragma: no cover
                            _LOGGER.debug(
                                "Failed to discover monitoring device sensors "
                                "for %s during datetime cleanup: %s",
                                monitoring_device_id,
                                discovery_error,
                            )

        # Find and remove orphaned entities
        entities_to_remove = []
        for entity_id, entity_entry in entity_registry.entities.items():
            if (
                entity_entry.platform != DOMAIN
                or entity_entry.domain != "datetime"
                or not entity_entry.unique_id
                or entity_entry.config_entry_id != entry.entry_id
            ):
                continue

            # Check if this is a datetime entity for our domain
            unique_id = entity_entry.unique_id
            datetime_keywords = [
                "_temperature_low_threshold_ignore_until",
                "_temperature_high_threshold_ignore_until",
                "_temperature_ignore_until",
                "_humidity_ignore_until",
                "_humidity_high_threshold_ignore_until",
                "_soil_moisture_ignore_until",
                "_soil_moisture_high_threshold_ignore_until",
                "_soil_conductivity_ignore_until",
                "_soil_conductivity_high_threshold_ignore_until",
                "_daily_light_integral_high_threshold_ignore_until",
                "_daily_light_integral_low_threshold_ignore_until",
            ]

            if any(kw in unique_id for kw in datetime_keywords) and (
                unique_id not in expected_datetime_entities
            ):
                entities_to_remove.append(entity_id)

        # Remove orphaned entities
        for entity_id in entities_to_remove:
            entity_registry.async_remove(entity_id)
            _LOGGER.debug("Removed orphaned datetime entity: %s", entity_id)

        if entities_to_remove:
            _LOGGER.info(
                "Cleaned up %d orphaned datetime entities for entry %s",
                len(entities_to_remove),
                entry.entry_id,
            )

    except Exception as exc:  # noqa: BLE001 - Defensive logging
        _LOGGER.warning(
            "Failed to cleanup orphaned datetime entities: %s",
            exc,
        )


async def async_setup_entry(  # noqa: PLR0912,PLR0915
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up datetime entities for a config entry."""
    _LOGGER.debug(
        "Setting up datetime entities for entry: %s (%s)",
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

    # Main entry - process subentries
    if entry.subentries:
        _LOGGER.info(
            "Processing main entry with %d subentries for datetime entities",
            len(entry.subentries),
        )

        # Clean up orphaned datetime entities before creating new ones
        await _cleanup_orphaned_datetime_entities(hass, entry)

        for subentry_id, subentry in entry.subentries.items():
            _LOGGER.debug(
                "Processing subentry %s with data: %s",
                subentry.subentry_id,
                subentry.data,
            )

            # Create entities for this specific subentry
            subentry_datetime_entities = []

            # Only create datetime entities for subentries with configured plant slots
            if "device_id" in subentry.data:
                monitoring_device_id = subentry.data.get("monitoring_device_id")
                humidity_entity_id = subentry.data.get("humidity_entity_id")
                location_name = subentry.data.get("name", "Plant Location")

                # Check conditions
                has_monitoring_device = bool(monitoring_device_id)
                has_humidity_sensor = bool(humidity_entity_id)
                has_plant_slots = _has_plants_in_slots(subentry.data)

                _LOGGER.debug(
                    "Datetime entity conditions for subentry %s: "
                    "monitoring_device=%s, humidity_sensor=%s, plant_slots=%s",
                    subentry_id,
                    has_monitoring_device,
                    has_humidity_sensor,
                    has_plant_slots,
                )

                device_sensors: dict[str, str] = {}
                illuminance_entity_id: str | None = None
                soil_conductivity_entity_id: str | None = None
                if has_monitoring_device:
                    try:
                        device_sensors = _get_monitoring_device_sensors(
                            hass, monitoring_device_id
                        )
                        illuminance_entity_id = device_sensors.get("illuminance")
                        soil_conductivity_entity_id = device_sensors.get(
                            "soil_conductivity"
                        )

                        if illuminance_entity_id:
                            _LOGGER.debug(
                                "Discovered illuminance sensor %s for subentry %s",
                                illuminance_entity_id,
                                subentry_id,
                            )

                        if soil_conductivity_entity_id:
                            _LOGGER.debug(
                                "Discovered soil conductivity sensor %s "
                                "for subentry %s",
                                soil_conductivity_entity_id,
                                subentry_id,
                            )
                    except Exception as discovery_error:  # noqa: BLE001
                        illuminance_entity_id = None
                        soil_conductivity_entity_id = None
                        _LOGGER.debug(
                            "Failed to discover monitoring device sensors "
                            "for %s during datetime setup: %s",
                            monitoring_device_id,
                            discovery_error,
                        )

                # Create temperature threshold entities if device and slots exist
                if has_monitoring_device and has_plant_slots:
                    _LOGGER.debug(
                        "Creating temperature threshold ignore until datetime "
                        "entities for subentry %s with monitoring device %s "
                        "and configured plant slots",
                        subentry_id,
                        monitoring_device_id,
                    )

                    temperature_low_threshold_ignore_entity = (
                        TemperatureLowThresholdIgnoreUntilEntity(
                            hass=hass,
                            entry_id=entry.entry_id,
                            subentry_id=subentry.subentry_id,
                            location_name=location_name,
                            subentry_data=subentry.data,
                        )
                    )
                    subentry_datetime_entities.append(
                        temperature_low_threshold_ignore_entity
                    )

                    temperature_high_threshold_ignore_entity = (
                        TemperatureHighThresholdIgnoreUntilEntity(
                            hass=hass,
                            entry_id=entry.entry_id,
                            subentry_id=subentry.subentry_id,
                            location_name=location_name,
                            subentry_data=subentry.data,
                        )
                    )
                    subentry_datetime_entities.append(
                        temperature_high_threshold_ignore_entity
                    )
                else:
                    _LOGGER.debug(
                        "Skipping temperature threshold ignore until entities "
                        "for subentry %s: monitoring_device=%s, plant_slots=%s",
                        subentry_id,
                        has_monitoring_device,
                        has_plant_slots,
                    )

                # Create humidity threshold entities if sensor and slots exist
                if has_humidity_sensor and has_plant_slots:
                    _LOGGER.debug(
                        "Creating humidity low/high threshold ignore until "
                        "datetime entities for subentry %s with humidity sensor %s "
                        "and configured plant slots",
                        subentry_id,
                        humidity_entity_id,
                    )

                    humidity_ignore_entity = HumidityLowThresholdIgnoreUntilEntity(
                        hass=hass,
                        entry_id=entry.entry_id,
                        subentry_id=subentry.subentry_id,
                        location_name=location_name,
                        subentry_data=subentry.data,
                    )
                    subentry_datetime_entities.append(humidity_ignore_entity)

                    humidity_high_ignore_entity = (
                        HumidityHighThresholdIgnoreUntilEntity(
                            hass=hass,
                            entry_id=entry.entry_id,
                            subentry_id=subentry.subentry_id,
                            location_name=location_name,
                            subentry_data=subentry.data,
                        )
                    )
                    subentry_datetime_entities.append(humidity_high_ignore_entity)
                else:
                    _LOGGER.debug(
                        "Skipping humidity threshold ignore until entities "
                        "for subentry %s: humidity_sensor=%s, plant_slots=%s",
                        subentry_id,
                        has_humidity_sensor,
                        has_plant_slots,
                    )

                # Create soil moisture threshold entities if device and slots exist
                if has_monitoring_device and has_plant_slots:
                    _LOGGER.debug(
                        "Creating soil moisture low/high threshold ignore until "
                        "entities for subentry %s with monitoring device %s "
                        "and configured plant slots",
                        subentry_id,
                        monitoring_device_id,
                    )

                    soil_moisture_ignore_entity = (
                        SoilMoistureLowThresholdIgnoreUntilEntity(
                            hass=hass,
                            entry_id=entry.entry_id,
                            subentry_id=subentry.subentry_id,
                            location_name=location_name,
                            subentry_data=subentry.data,
                        )
                    )
                    subentry_datetime_entities.append(soil_moisture_ignore_entity)

                    soil_moisture_high_ignore_entity = (
                        SoilMoistureHighThresholdIgnoreUntilEntity(
                            hass=hass,
                            entry_id=entry.entry_id,
                            subentry_id=subentry.subentry_id,
                            location_name=location_name,
                            subentry_data=subentry.data,
                        )
                    )
                    subentry_datetime_entities.append(soil_moisture_high_ignore_entity)
                else:
                    _LOGGER.debug(
                        "Skipping soil moisture threshold ignore until entities "
                        "for subentry %s: monitoring_device=%s, plant_slots=%s",
                        subentry_id,
                        has_monitoring_device,
                        has_plant_slots,
                    )

                # Create soil conductivity threshold entities if sensor exists
                if (
                    soil_conductivity_entity_id
                    and has_monitoring_device
                    and has_plant_slots
                ):
                    _LOGGER.debug(
                        "Creating soil conductivity low/high threshold ignore "
                        "until entities for subentry %s with monitoring device %s "
                        "and conductivity sensor %s",
                        subentry_id,
                        monitoring_device_id,
                        soil_conductivity_entity_id,
                    )

                    soil_conductivity_low_ignore_entity = (
                        SoilConductivityLowThresholdIgnoreUntilEntity(
                            hass=hass,
                            entry_id=entry.entry_id,
                            subentry_id=subentry.subentry_id,
                            location_name=location_name,
                            subentry_data=subentry.data,
                            soil_conductivity_entity_id=soil_conductivity_entity_id,
                        )
                    )
                    subentry_datetime_entities.append(
                        soil_conductivity_low_ignore_entity
                    )

                    soil_conductivity_high_ignore_entity = (
                        SoilConductivityHighThresholdIgnoreUntilEntity(
                            hass=hass,
                            entry_id=entry.entry_id,
                            subentry_id=subentry.subentry_id,
                            location_name=location_name,
                            subentry_data=subentry.data,
                            soil_conductivity_entity_id=soil_conductivity_entity_id,
                        )
                    )
                    subentry_datetime_entities.append(
                        soil_conductivity_high_ignore_entity
                    )
                else:
                    _LOGGER.debug(
                        "Skipping soil conductivity threshold ignore until entities "
                        "for subentry %s: monitoring_device=%s, "
                        "conductivity_sensor=%s, plant_slots=%s",
                        subentry_id,
                        has_monitoring_device,
                        bool(soil_conductivity_entity_id),
                        has_plant_slots,
                    )

                # Create DLI threshold entities if illuminance sensor exists
                if illuminance_entity_id and has_plant_slots:
                    _LOGGER.debug(
                        "Creating Daily Light Integral high/low threshold ignore "
                        "entities for subentry %s with illuminance sensor %s",
                        subentry_id,
                        illuminance_entity_id,
                    )

                    dli_high_ignore_entity = (
                        DailyLightIntegralHighThresholdIgnoreUntilEntity(
                            hass=hass,
                            entry_id=entry.entry_id,
                            subentry_id=subentry.subentry_id,
                            location_name=location_name,
                            subentry_data=subentry.data,
                            illuminance_entity_id=illuminance_entity_id,
                        )
                    )
                    subentry_datetime_entities.append(dli_high_ignore_entity)

                    dli_low_ignore_entity = (
                        DailyLightIntegralLowThresholdIgnoreUntilEntity(
                            hass=hass,
                            entry_id=entry.entry_id,
                            subentry_id=subentry.subentry_id,
                            location_name=location_name,
                            subentry_data=subentry.data,
                            illuminance_entity_id=illuminance_entity_id,
                        )
                    )
                    subentry_datetime_entities.append(dli_low_ignore_entity)
                else:
                    _LOGGER.debug(
                        "Skipping Daily Light Integral threshold ignore entities "
                        "for subentry %s: illuminance_sensor=%s, plant_slots=%s",
                        subentry_id,
                        bool(illuminance_entity_id),
                        has_plant_slots,
                    )

                # Create plant count ignore until entity if slots exist
                if has_plant_slots:
                    _LOGGER.debug(
                        "Creating plant count ignore until datetime entity "
                        "for subentry %s with configured plant slots",
                        subentry_id,
                    )

                    plant_count_ignore_entity = PlantCountIgnoreUntilEntity(
                        hass=hass,
                        entry_id=entry.entry_id,
                        subentry_id=subentry.subentry_id,
                        location_name=location_name,
                        subentry_data=subentry.data,
                    )
                    subentry_datetime_entities.append(plant_count_ignore_entity)
                else:
                    _LOGGER.debug(
                        "Skipping plant count ignore until entity "
                        "for subentry %s: no plant slots configured",
                        subentry_id,
                    )

            # Add entities for this subentry with proper subentry association
            if subentry_datetime_entities:
                _LOGGER.info(
                    "Adding %d datetime entities for subentry %s",
                    len(subentry_datetime_entities),
                    subentry_id,
                )
                async_add_entities(
                    subentry_datetime_entities,
                    config_subentry_id=subentry_id,  # type: ignore[call-arg]
                )

    else:
        # Process legacy entries or direct configuration if needed
        _LOGGER.debug("Processing legacy entry or direct configuration")
        # Add logic here if you need to support non-subentry configurations


class TemperatureLowThresholdIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for low temperature threshold ignore until."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
    ) -> None:
        """Initialize the temperature low threshold ignore until datetime entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = f"{location_name} Temperature Low Threshold Ignore Until"
        self._attr_unique_id = (
            f"{DOMAIN}_{subentry_id}_temperature_low_threshold_ignore_until"
        )
        self._attr_has_entity_name = False
        self._attr_icon = "mdi:thermometer-alert"
        # Device created by device registry with config_subentry_id
        # Following OpenAI integration pattern
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                # Parse the datetime string from the last state
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    # Ensure timezone info
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 Temp low threshold ignore until entity %s: "
                        "restored state %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ Temp low threshold ignore until entity %s: "
                        "could not parse datetime from %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ Temp low threshold ignore until entity %s: "
                    "could not restore state from %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 Temp low threshold ignore until entity %s: "
                "initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        # Ensure the datetime has timezone info
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set temperature low threshold ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
            "monitoring_device_id": self._subentry_data.get("monitoring_device_id"),
        }

        # Add information about whether we're currently in ignore period
        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if monitoring device and plant slots configured
        has_monitoring_device = (
            self._subentry_data.get("monitoring_device_id") is not None
        )
        has_plant_slots = _has_plants_in_slots(self._subentry_data)
        return has_monitoring_device and has_plant_slots


class TemperatureHighThresholdIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for high temperature threshold ignore until."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
    ) -> None:
        """Initialize the temperature high threshold ignore until datetime entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = f"{location_name} Temperature High Threshold Ignore Until"
        self._attr_unique_id = (
            f"{DOMAIN}_{subentry_id}_temperature_high_threshold_ignore_until"
        )
        self._attr_icon = "mdi:thermometer-chevron-up"
        self._attr_has_entity_name = False

        # Device created by device registry with config_subentry_id
        # Following OpenAI integration pattern
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                # Parse the datetime string from the last state
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    # Ensure timezone info
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 Temp high threshold ignore %s: restored %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ Temp high threshold ignore %s: could not parse datetime %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ Temp high threshold ignore %s: could not restore %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 Temp high threshold ignore %s: "
                "initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        # Ensure the datetime has timezone info
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set temperature high threshold ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
            "monitoring_device_id": self._subentry_data.get("monitoring_device_id"),
        }

        # Add information about whether we're currently in ignore period
        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if monitoring device and plant slots configured
        has_monitoring_device = (
            self._subentry_data.get("monitoring_device_id") is not None
        )
        has_plant_slots = _has_plants_in_slots(self._subentry_data)
        return has_monitoring_device and has_plant_slots


class HumidityLowThresholdIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for low humidity threshold ignore until."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
    ) -> None:
        """Initialize the humidity low threshold ignore until datetime entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = f"{location_name} Humidity Low Threshold Ignore Until"
        # Keep unique ID stable so existing entities are migrated without recreation
        self._attr_unique_id = f"{DOMAIN}_{subentry_id}_humidity_ignore_until"
        self._attr_icon = "mdi:water-percent-alert"
        self._attr_has_entity_name = False

        # Device created by device registry with config_subentry_id
        # Following OpenAI integration pattern
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                # Parse the datetime string from the last state
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    # Ensure timezone info
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 Humidity low %s: restored state %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ Humidity low %s: could not parse datetime from %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ Humidity low %s: could not restore state from %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 Humidity low %s: initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        # Ensure the datetime has timezone info
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set humidity low threshold ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
            "humidity_entity_id": self._subentry_data.get("humidity_entity_id"),
        }

        # Add information about whether we're currently in ignore period
        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if humidity sensor and plant slots configured
        has_humidity_sensor = self._subentry_data.get("humidity_entity_id") is not None
        has_plant_slots = _has_plants_in_slots(self._subentry_data)
        return has_humidity_sensor and has_plant_slots


class HumidityHighThresholdIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for high humidity threshold ignore until."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
    ) -> None:
        """Initialize the humidity high threshold ignore until datetime entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = f"{location_name} Humidity High Threshold Ignore Until"
        self._attr_unique_id = (
            f"{DOMAIN}_{subentry_id}_humidity_high_threshold_ignore_until"
        )
        self._attr_icon = "mdi:water-alert"
        self._attr_has_entity_name = False

        # Device created by device registry with config_subentry_id
        # Following OpenAI integration pattern
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                # Parse the datetime string from the last state
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    # Ensure timezone info
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 Humidity high %s: restored state %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ Humidity high %s: could not parse datetime from %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ Humidity high %s: could not restore state from %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 Humidity high %s: initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        # Ensure the datetime has timezone info
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set humidity high threshold ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
            "humidity_entity_id": self._subentry_data.get("humidity_entity_id"),
        }

        # Add information about whether we're currently in ignore period
        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if humidity sensor and plant slots configured
        has_humidity_sensor = self._subentry_data.get("humidity_entity_id") is not None
        has_plant_slots = _has_plants_in_slots(self._subentry_data)
        return has_humidity_sensor and has_plant_slots


class SoilMoistureLowThresholdIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for low soil moisture threshold ignore until."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
    ) -> None:
        """Initialize the soil moisture low threshold ignore until datetime entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = f"{location_name} Soil Moisture Low Threshold Ignore Until"
        # Keep unique ID stable so existing entities are migrated without recreation
        self._attr_unique_id = f"{DOMAIN}_{subentry_id}_soil_moisture_ignore_until"
        self._attr_icon = "mdi:water-percent-alert"
        self._attr_has_entity_name = False

        # Device created by device registry with config_subentry_id
        # Following OpenAI integration pattern
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                # Parse the datetime string from the last state
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    # Ensure timezone info
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 Soil moist low %s: restored state %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ Soil moist low %s: could not parse datetime from %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ Soil moist low %s: could not restore state from %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 Soil moist low %s: initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        # Ensure the datetime has timezone info
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set soil moisture low threshold ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
            "monitoring_device_id": self._subentry_data.get("monitoring_device_id"),
        }

        # Add information about whether we're currently in ignore period
        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if monitoring device and plant slots configured
        has_monitoring_device = (
            self._subentry_data.get("monitoring_device_id") is not None
        )
        has_plant_slots = _has_plants_in_slots(self._subentry_data)
        return has_monitoring_device and has_plant_slots


class SoilMoistureHighThresholdIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for high soil moisture threshold ignore until."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
    ) -> None:
        """Initialize the soil moisture high threshold ignore until datetime entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = f"{location_name} Soil Moisture High Threshold Ignore Until"
        self._attr_unique_id = (
            f"{DOMAIN}_{subentry_id}_soil_moisture_high_threshold_ignore_until"
        )
        self._attr_icon = "mdi:water-alert"
        self._attr_has_entity_name = False

        # Device created by device registry with config_subentry_id
        # Following OpenAI integration pattern
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                # Parse the datetime string from the last state
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    # Ensure timezone info
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 Soil moist high %s: restored state %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ Soil moist high %s: could not parse datetime from %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ Soil moist high %s: could not restore state from %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 Soil moist high %s: initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        # Ensure the datetime has timezone info
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set soil moisture high threshold ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
            "monitoring_device_id": self._subentry_data.get("monitoring_device_id"),
        }

        # Add information about whether we're currently in ignore period
        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if monitoring device and plant slots configured
        has_monitoring_device = (
            self._subentry_data.get("monitoring_device_id") is not None
        )
        has_plant_slots = _has_plants_in_slots(self._subentry_data)
        return has_monitoring_device and has_plant_slots


class SoilConductivityLowThresholdIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for low soil conductivity threshold ignore until."""

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
        soil_conductivity_entity_id: str | None = None,
    ) -> None:
        """Initialize soil conductivity low threshold entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._soil_conductivity_entity_id = soil_conductivity_entity_id
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = (
            f"{location_name} Soil Conductivity Low Threshold Ignore Until"
        )
        self._attr_unique_id = f"{DOMAIN}_{subentry_id}_soil_conductivity_ignore_until"
        self._attr_icon = "mdi:flash-outline"
        self._attr_has_entity_name = False

        # Device created by device registry with config_subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 Soil EC low %s: restored state %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ Soil EC low %s: could not parse datetime from %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ Soil EC low %s: could not restore state from %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 Soil EC low %s: initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set soil conductivity low threshold ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
            "monitoring_device_id": self._subentry_data.get("monitoring_device_id"),
            "soil_conductivity_entity_id": self._soil_conductivity_entity_id,
        }

        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        has_monitoring_device = (
            self._subentry_data.get("monitoring_device_id") is not None
        )
        has_plant_slots = _has_plants_in_slots(self._subentry_data)
        has_conductivity_sensor = bool(self._soil_conductivity_entity_id)
        return has_monitoring_device and has_plant_slots and has_conductivity_sensor


class SoilConductivityHighThresholdIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for high soil conductivity threshold ignore until."""

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
        soil_conductivity_entity_id: str | None = None,
    ) -> None:
        """Initialize soil conductivity high threshold entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._soil_conductivity_entity_id = soil_conductivity_entity_id
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = (
            f"{location_name} Soil Conductivity High Threshold Ignore Until"
        )
        self._attr_unique_id = (
            f"{DOMAIN}_{subentry_id}_soil_conductivity_high_threshold_ignore_until"
        )
        self._attr_icon = "mdi:flash-alert"
        self._attr_has_entity_name = False

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 Soil EC high %s: restored state %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ Soil EC high %s: could not parse datetime from %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ Soil EC high %s: could not restore state from %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 Soil EC high %s: initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set soil conductivity high threshold ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
            "monitoring_device_id": self._subentry_data.get("monitoring_device_id"),
            "soil_conductivity_entity_id": self._soil_conductivity_entity_id,
        }

        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        has_monitoring_device = (
            self._subentry_data.get("monitoring_device_id") is not None
        )
        has_plant_slots = _has_plants_in_slots(self._subentry_data)
        has_conductivity_sensor = bool(self._soil_conductivity_entity_id)
        return has_monitoring_device and has_plant_slots and has_conductivity_sensor


class DailyLightIntegralHighThresholdIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for Daily Light Integral high threshold ignore until."""

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
        illuminance_entity_id: str | None = None,
    ) -> None:
        """Initialize the Daily Light Integral high threshold ignore until entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._illuminance_entity_id = illuminance_entity_id
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = (
            f"{location_name} Daily Light Integral High Threshold Ignore Until"
        )
        self._attr_unique_id = (
            f"{DOMAIN}_{subentry_id}_daily_light_integral_high_threshold_ignore_until"
        )
        self._attr_icon = "mdi:brightness-7"
        self._attr_has_entity_name = False

        # Device created by device registry with config_subentry_id
        # Following OpenAI integration pattern
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                # Parse the datetime string from the last state
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    # Ensure timezone info
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 DLI high threshold ignore %s: restored state %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ DLI high %s: could not parse datetime from %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ DLI high %s: could not restore state from %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 DLI high %s: initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        # Ensure the datetime has timezone info
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set DLI high threshold ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
            "illuminance_entity_id": self._illuminance_entity_id,
        }

        # Add information about whether we're currently in ignore period
        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if illuminance sensor and plant slots configured
        has_illuminance_sensor = bool(self._illuminance_entity_id)
        has_plant_slots = _has_plants_in_slots(self._subentry_data)
        return has_illuminance_sensor and has_plant_slots


class DailyLightIntegralLowThresholdIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for Daily Light Integral low threshold ignore until."""

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
        illuminance_entity_id: str | None = None,
    ) -> None:
        """Initialize the Daily Light Integral low threshold ignore until entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._illuminance_entity_id = illuminance_entity_id
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = (
            f"{location_name} Daily Light Integral Low Threshold Ignore Until"
        )
        self._attr_unique_id = (
            f"{DOMAIN}_{subentry_id}_daily_light_integral_low_threshold_ignore_until"
        )
        self._attr_icon = "mdi:brightness-4"
        self._attr_has_entity_name = False

        # Device created by device registry with config_subentry_id
        # Following OpenAI integration pattern
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                # Parse the datetime string from the last state
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    # Ensure timezone info
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 DLI low %s: restored state %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ DLI low %s: could not parse datetime from %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ DLI low %s: could not restore state from %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 DLI low %s: initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        # Ensure the datetime has timezone info
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set DLI low threshold ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs: dict[str, Any] = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
            "illuminance_entity_id": self._illuminance_entity_id,
        }

        # Add information about whether we're currently in ignore period
        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if illuminance sensor and plant slots configured
        has_illuminance_sensor = bool(self._illuminance_entity_id)
        has_plant_slots = _has_plants_in_slots(self._subentry_data)
        return has_illuminance_sensor and has_plant_slots


class PlantCountIgnoreUntilEntity(RestoreEntity, DateTimeEntity):
    """Datetime entity for plant count ignore until."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        subentry_id: str,
        location_name: str,
        subentry_data: Mapping[str, Any],
    ) -> None:
        """Initialize the plant count ignore until datetime entity."""
        self._hass = hass
        self._entry_id = entry_id
        self._subentry_id = subentry_id
        self._location_name = location_name
        self._subentry_data = subentry_data
        self._attr_native_value: py_datetime.datetime | None = None

        # Set up entity attributes
        self._attr_name = f"{location_name} Plant Count Ignore Until"
        self._attr_unique_id = f"{DOMAIN}_{subentry_id}_plant_count_ignore_until"
        self._attr_has_entity_name = False
        self._attr_icon = "mdi:flower-tulip"
        # Device created by device registry with config_subentry_id
        # Following OpenAI integration pattern
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location",
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        # Restore previous state if available
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()

        if last_state is not None and last_state.state not in (
            "unknown",
            "unavailable",
            None,
        ):
            try:
                # Parse the datetime string from the last state
                restored_datetime = dt_util.parse_datetime(last_state.state)
                if restored_datetime is not None:
                    # Ensure timezone info
                    if restored_datetime.tzinfo is None:
                        restored_datetime = restored_datetime.replace(
                            tzinfo=dt_util.get_default_time_zone()
                        )

                    self._attr_native_value = restored_datetime
                    _LOGGER.info(
                        "🔄 Plant count ignore until entity %s: restored state %s",
                        self._location_name,
                        restored_datetime.isoformat(),
                    )
                else:
                    _LOGGER.warning(
                        "⚠️ Plant count ignore until entity %s: "
                        "could not parse datetime from %s",
                        self._location_name,
                        last_state.state,
                    )
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "⚠️ Plant count ignore until entity %s: "
                    "could not restore state from %s: %s",
                    self._location_name,
                    last_state.state,
                    e,
                )
        else:
            # Initialize to current date at midnight
            now = dt_util.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            self._attr_native_value = midnight
            _LOGGER.info(
                "🆕 Plant count ignore until entity %s: "
                "initialized to current date at midnight (%s)",
                self._location_name,
                midnight.isoformat(),
            )

    @property
    def native_value(self) -> py_datetime.datetime | None:
        """Return the current datetime value."""
        return self._attr_native_value

    async def async_set_value(self, value: py_datetime.datetime) -> None:
        """Set the datetime value."""
        # Ensure the datetime has timezone info
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt_util.get_default_time_zone())

        self._attr_native_value = value
        self.async_write_ha_state()

        _LOGGER.debug(
            "Set plant count ignore until datetime for %s to %s",
            self._location_name,
            value.isoformat(),
        )

    def set_value(self, value: py_datetime.datetime) -> None:
        """Set value - abstract method stub (implementation uses async_set_value)."""
        # pylint: disable=abstract-method

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs: dict[str, Any] = {
            "location_name": self._location_name,
            "subentry_id": self._subentry_id,
        }

        # Add information about whether we're currently in ignore period
        if self._attr_native_value:
            now = dt_util.now()
            is_ignoring = now < self._attr_native_value
            attrs["currently_ignoring"] = is_ignoring
            attrs["ignore_expires_in_seconds"] = (
                int((self._attr_native_value - now).total_seconds())
                if is_ignoring
                else 0
            )

        return attrs

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if plant slots are configured
        return _has_plants_in_slots(self._subentry_data)
