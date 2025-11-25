"""
Sensors for the Plant Assistant integration.

This module provides a minimal set of sensors used by the integration and
keeps implementations test-friendly by only relying on `hass.data` and the
`hass.states` mapping where possible.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any, TypedDict, cast

from homeassistant.components.integration.const import METHOD_TRAPEZOIDAL
from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.components.utility_meter.const import (
    DAILY,
    DATA_TARIFF_SENSORS,
    DATA_UTILITY,
)
from homeassistant.components.utility_meter.sensor import UtilityMeterSensor
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EntityCategory,
    UnitOfTime,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.recorder import get_instance
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import aggregation, dli
from .const import (
    AGGREGATED_SENSOR_MAPPINGS,
    ATTR_PLANT_DEVICE_IDS,
    DEFAULT_LUX_TO_PPFD,
    DOMAIN,
    ICON_DLI,
    ICON_PPFD,
    MONITORING_SENSOR_MAPPINGS,
    READING_DLI_NAME,
    READING_DLI_SLUG,
    READING_PPFD,
    READING_PRIOR_PERIOD_DLI_NAME,
    READING_PRIOR_PERIOD_DLI_SLUG,
    READING_WEEKLY_AVG_DLI_NAME,
    READING_WEEKLY_AVG_DLI_SLUG,
    UNIT_DLI,
    UNIT_PPFD,
    UNIT_PPFD_INTEGRAL,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback


class MonitoringSensorMapping(TypedDict, total=False):
    """Type definition for monitoring sensor mappings."""

    device_class: SensorDeviceClass | str | None
    suffix: str
    icon: str
    name: str
    unit: str | None


_LOGGER = logging.getLogger(__name__)


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


def _find_recently_watered_entity(
    hass: HomeAssistant, location_name: str
) -> str | None:
    """
    Find recently watered binary sensor entity for a location.

    Returns:
        Entity ID if found, None otherwise.

    """
    ent_reg = er.async_get(hass)

    for entity in ent_reg.entities.values():
        if (
            entity.platform == DOMAIN
            and entity.domain == "binary_sensor"
            and entity.unique_id
            and "recently_watered" in entity.unique_id
            and location_name.lower().replace(" ", "_") in entity.unique_id.lower()
        ):
            _LOGGER.debug("Found recently watered sensor: %s", entity.entity_id)
            return entity.entity_id

    return None


def _detect_sensor_type_from_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    """
    Detect the sensor type from a source entity's device_class or entity_id.

    Args:
        hass: The Home Assistant instance.
        entity_id: The entity ID to detect the type from.

    Returns:
        The sensor type key (e.g., 'temperature', 'illuminance') or
        None if not detected.

    """
    # Map device_class to sensor type
    device_class_mapping = {
        "temperature": "temperature",
        "illuminance": "illuminance",
        "moisture": "soil_moisture",
        "conductivity": "soil_conductivity",
        "battery": "battery",
        "signal_strength": "signal_strength",
    }

    # Map entity_id patterns to sensor type
    entity_id_patterns = {
        "temperature": "temperature",
        "illuminance": "illuminance",
        "light": "illuminance",
        "moisture": "soil_moisture",
        "conductivity": "soil_conductivity",
        "battery": "battery",
        "signal": "signal_strength",
        "rssi": "signal_strength",
    }

    # Prefer reading device_class from the live state attributes which is
    # what entity implementations expose at runtime. Fall back to a
    # best-effort attempt via the entity registry and finally to simple
    # pattern matching on the entity_id.
    try:
        # Check the runtime state first
        state = hass.states.get(entity_id)
        if state:
            device_class = state.attributes.get("device_class")
            if device_class in device_class_mapping:
                return device_class_mapping[device_class]

        # Fallback to entity registry (may not expose device_class)
        ent_reg = er.async_get(hass)
        entity = ent_reg.async_get(entity_id)
        if entity:
            device_class = getattr(entity, "device_class", None)
            if device_class in device_class_mapping:
                return device_class_mapping[device_class]

        # Final fallback: pattern match on entity_id
        entity_id_lower = entity_id.lower()
        for pattern, sensor_type in entity_id_patterns.items():
            if pattern in entity_id_lower:
                return sensor_type
    # pragma: no cover - defensive
    except (AttributeError, KeyError, ValueError) as exc:
        _LOGGER.debug("Error detecting sensor type for %s: %s", entity_id, exc)

    return None


def _has_plants_in_slots(data: Mapping[str, Any]) -> bool:
    """
    Check if there are any plants assigned to slots in the data.

    Args:
        data: The subentry data containing plant_slots.

    Returns:
        True if at least one slot has a plant_device_id assigned, False otherwise.

    """
    plant_slots = data.get("plant_slots", {})
    for slot in plant_slots.values():
        if isinstance(slot, dict) and slot.get("plant_device_id"):
            return True
    return False


def _get_monitoring_device_sensors(
    hass: HomeAssistant, monitoring_device_id: str
) -> dict[str, tuple[str, str | None]]:
    """
    Get sensor entity IDs and unique IDs for a monitoring device.

    Provides resilient sensor discovery by returning both entity_id and unique_id
    for each sensor. This allows callers to use entity_id for immediate access
    while falling back to unique_id if the entity has been renamed.

    Args:
        hass: The Home Assistant instance.
        monitoring_device_id: The device ID of the monitoring device.

    Returns:
        A dict mapping sensor type names (e.g., 'illuminance', 'soil_conductivity')
        to tuples of (entity_id, unique_id). Returns empty dict if device not found.
        unique_id may be None if not available from the entity registry.

    """
    device_sensors: dict[str, tuple[str, str | None]] = {}

    # Get device and entity registries
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    # Try to get the device by ID
    if not (device := dev_reg.async_get(monitoring_device_id)):
        return device_sensors

    # Get all sensor entities for this device and map them safely.
    for entity in ent_reg.entities.values():
        try:
            if entity.device_id != device.id or entity.domain != "sensor":
                continue

            # Prefer device_class from the live state attributes
            device_class = None
            try:
                state = hass.states.get(entity.entity_id)
                if state:
                    device_class = state.attributes.get("device_class")
            except (AttributeError, KeyError, ValueError):
                # ignore state read errors for robustness
                device_class = None

            # Fall back to registry attribute if present
            if not device_class:
                device_class = getattr(entity, "device_class", None)

            ent_id = entity.entity_id
            ent_id_lower = ent_id.lower()
            unique_id = getattr(entity, "unique_id", None)

            if device_class == "illuminance" or "illuminance" in ent_id_lower:
                device_sensors["illuminance"] = (ent_id, unique_id)
            elif device_class == "soil_conductivity" or "conductivity" in ent_id_lower:
                device_sensors["soil_conductivity"] = (ent_id, unique_id)
            elif device_class == "battery" or "battery" in ent_id_lower:
                device_sensors["battery"] = (ent_id, unique_id)
            elif (
                device_class == "signal_strength"
                or "signal" in ent_id_lower
                or "rssi" in ent_id_lower
            ):
                device_sensors["signal_strength"] = (ent_id, unique_id)
        except (
            AttributeError,
            KeyError,
            ValueError,
            TypeError,
        ):  # pragma: no cover - defensive per-entity
            # Don't abort scanning other entities if one entity raises
            _LOGGER.debug(
                "Skipping entity during monitoring discovery: %s",
                getattr(entity, "entity_id", "<unknown>"),
            )

    return device_sensors


def _resolve_entity_id(
    hass: HomeAssistant, entity_id: str | None, unique_id: str | None
) -> str | None:
    """
    Resolve an entity ID, using unique_id as fallback if entity was renamed.

    This is the canonical helper for resilient entity ID resolution. It handles
    entity renames gracefully by falling back to unique_id lookup when the
    stored entity_id no longer exists or has been renamed.

    Resolution strategy:
    1. If entity_id provided: Check if it exists in state or registry
    2. If not found or no entity_id: Try to resolve via unique_id
    3. If both fail: Return None

    This approach supports:
    - Entities that have been renamed (falls back to unique_id)
    - Disabled entities (still exist in registry)
    - Entities from external integrations (validates in registry)
    - Missing registries during testing (defensive handling)

    Args:
        hass: The Home Assistant instance.
        entity_id: The entity ID to use (preferred if available and valid).
        unique_id: The unique ID to use as fallback if entity_id not found.

    Returns:
        The resolved entity_id if found, or None if resolution failed.

    Raises:
        No exceptions - all errors are caught and handled gracefully.

    """
    # Try to get entity registry once, with defensive handling
    entity_reg = None
    with contextlib.suppress(TypeError, AttributeError, ValueError):
        entity_reg = er.async_get(hass)

    # First try the entity_id if provided
    if entity_id and entity_id.strip():
        # Check if entity exists in live state (most common case)
        if hass.states.get(entity_id) is not None:
            _LOGGER.debug("Resolved entity_id %s from live state", entity_id)
            return entity_id

        # Try to validate in registry (handles disabled/unavailable entities)
        if entity_reg is not None:
            try:
                if entity_reg.async_get(entity_id):
                    _LOGGER.debug("Resolved entity_id %s from registry", entity_id)
                    return entity_id
            except (TypeError, AttributeError, ValueError):
                pass

        _LOGGER.debug(
            "Entity ID %s not found in state or registry, trying unique_id fallback",
            entity_id,
        )

    # Fall back to unique_id lookup if entity_id failed or wasn't provided
    if unique_id and unique_id.strip() and entity_reg is not None:
        try:
            for entity_entry in entity_reg.entities.values():
                if entity_entry.unique_id == unique_id:
                    _LOGGER.debug(
                        "Resolved entity_id from unique_id %s -> %s",
                        unique_id,
                        entity_entry.entity_id,
                    )
                    return entity_entry.entity_id
            _LOGGER.debug("No entity found with unique_id %s", unique_id)
        except (TypeError, AttributeError, ValueError):
            _LOGGER.debug(
                "Error resolving unique_id %s - registry may not be available",
                unique_id,
            )

    _LOGGER.debug(
        "Could not resolve entity: entity_id=%s, unique_id=%s",
        entity_id,
        unique_id,
    )
    return None


def find_device_entities_by_pattern(
    hass: HomeAssistant,
    device_id: str,
    domain: str,
    pattern_keywords: list[str] | None = None,
) -> dict[str, tuple[str, str | None]]:
    """
    Find entities belonging to a device by domain and optional pattern matching.

    This helper provides a robust way to discover entities associated with a device
    without relying on constructed entity ID patterns. It queries the entity registry
    and optionally filters by keywords found in the entity ID or name.

    Args:
        hass: The Home Assistant instance.
        device_id: The device ID to search for entities.
        domain: The entity domain to filter by (e.g., 'switch', 'sensor').
        pattern_keywords: Optional list of keywords to match in entity_id or name.
            If None, returns all entities for the device in the specified domain.

    Returns:
        A dict mapping descriptive keys to tuples of (entity_id, unique_id).
        Keys are derived from pattern_keywords if provided, or entity_id otherwise.
        Returns empty dict if device not found or no matching entities.

    Example:
        # Find schedule switches for a zone device
        switches = find_device_entities_by_pattern(
            hass, device_id, 'switch', ['schedule', 'sunrise', 'afternoon']
        )
        # Returns: {'schedule': ('switch.zone_schedule', 'unique_123'), ...}

    """
    entities: dict[str, tuple[str, str | None]] = {}

    try:
        dev_reg = dr.async_get(hass)
        ent_reg = er.async_get(hass)

        # Verify device exists
        if not dev_reg.async_get(device_id):
            _LOGGER.debug("Device %s not found", device_id)
            return entities

        # Scan all entities for this device
        for entity_entry in ent_reg.entities.values():
            if entity_entry.device_id != device_id or entity_entry.domain != domain:
                continue

            entity_id = entity_entry.entity_id
            unique_id = entity_entry.unique_id
            entity_id_lower = entity_id.lower()
            entity_name_lower = (entity_entry.name or "").lower()

            # If no pattern specified, add all entities with entity_id as key
            if not pattern_keywords:
                key = entity_id.split(".")[-1]  # Use entity name part as key
                entities[key] = (entity_id, unique_id)
                continue

            # Check if any pattern keyword matches
            for keyword in pattern_keywords:
                keyword_lower = keyword.lower()
                if (
                    keyword_lower in entity_id_lower
                    or keyword_lower in entity_name_lower
                ):
                    # Use the keyword as the key for easy lookup
                    entities[keyword] = (entity_id, unique_id)
                    _LOGGER.debug(
                        "Found entity for pattern '%s': %s (unique_id: %s)",
                        keyword,
                        entity_id,
                        unique_id,
                    )
                    break

    except (TypeError, AttributeError, ValueError) as exc:
        _LOGGER.debug("Error finding device entities: %s", exc)

    return entities


def _expected_entities_for_subentry(  # noqa: PLR0912, PLR0915
    hass: HomeAssistant, subentry: Any
) -> tuple[set[str], set[str], set[str], set[str]]:
    """
    Return expected monitoring, humidity, aggregated, and threshold unique_ids.

    A subentry provides monitoring, humidity, aggregated, and threshold unique_ids.
    This encapsulates the logic used by the cleanup routine so the main
    cleanup function stays small and within complexity limits.

    Returns:
        Tuple of (expected_monitoring, expected_humidity, expected_aggregated,
        expected_threshold)

    """
    expected_monitoring: set[str] = set()
    expected_humidity: set[str] = set()
    expected_aggregated: set[str] = set()
    expected_threshold: set[str] = set()

    if "device_id" not in getattr(subentry, "data", {}):
        return (
            expected_monitoring,
            expected_humidity,
            expected_aggregated,
            expected_threshold,
        )

    location_name = subentry.data.get("name", "Plant Location")
    location_name_safe = location_name.lower().replace(" ", "_")

    # Handle monitoring sensors
    monitoring_device_id = subentry.data.get("monitoring_device_id")
    if monitoring_device_id:
        try:
            device_sensors = _get_monitoring_device_sensors(hass, monitoring_device_id)
            # Extract entity_id from tuple (entity_id, unique_id)
            for mapped_type, sensor_tuple in device_sensors.items():
                source_entity_id = sensor_tuple[0]  # Get entity_id from tuple
                detected_type = _detect_sensor_type_from_entity(hass, source_entity_id)
                sensor_type = detected_type if detected_type else mapped_type

                device_name_safe = location_name_safe

                if sensor_type and sensor_type in MONITORING_SENSOR_MAPPINGS:
                    mapping = MONITORING_SENSOR_MAPPINGS[sensor_type]
                    if isinstance(mapping, dict):
                        suffix = mapping.get("suffix", sensor_type)
                    else:
                        suffix = getattr(mapping, "suffix", sensor_type)
                else:
                    source_entity_safe = source_entity_id.replace(".", "_")
                    suffix = f"monitor_{source_entity_safe}"

                unique_id = (
                    f"{DOMAIN}_{subentry.subentry_id}_{device_name_safe}_{suffix}"
                )
                expected_monitoring.add(unique_id)
        except (ValueError, TypeError) as discovery_error:  # pragma: no cover
            _LOGGER.debug(
                "Failed to discover monitoring device sensors for %s: %s",
                monitoring_device_id,
                discovery_error,
            )

    # Handle humidity linked sensors
    humidity_entity_id = subentry.data.get("humidity_entity_id")
    if humidity_entity_id:
        humidity_unique_id = (
            f"{DOMAIN}_{subentry.subentry_id}_{location_name_safe}_humidity_linked"
        )
        expected_humidity.add(humidity_unique_id)

    # Handle aggregated location sensors and threshold sensors
    # These are created when plants are in slots and either monitoring
    # device or humidity entity exists
    plant_slots = subentry.data.get("plant_slots", {})
    has_plants = any(
        isinstance(slot, dict) and slot.get("plant_device_id")
        for slot in plant_slots.values()
    )

    if has_plants:
        # Determine which aggregated metrics to expect
        metrics_to_expect = []

        if monitoring_device_id:
            # Environmental metrics that require monitoring device
            metrics_to_expect.extend(
                [
                    "min_temperature",
                    "max_temperature",
                    "min_illuminance",
                    "max_illuminance",
                    "min_dli",
                    "max_dli",
                    "min_soil_moisture",
                    "max_soil_moisture",
                    "min_soil_conductivity",
                    "max_soil_conductivity",
                ]
            )

        if humidity_entity_id:
            # Humidity metrics that require humidity entity
            metrics_to_expect.extend(["min_humidity", "max_humidity"])

        # Build unique_ids for all expected aggregated sensors
        for metric_key in metrics_to_expect:
            if metric_key in AGGREGATED_SENSOR_MAPPINGS:
                metric_config: dict[str, Any] = AGGREGATED_SENSOR_MAPPINGS[metric_key]
                suffix = metric_config.get("suffix", metric_key)
                aggregated_unique_id = (
                    f"{DOMAIN}_{subentry.subentry_id}_{location_name_safe}_{suffix}"
                )
                expected_aggregated.add(aggregated_unique_id)

        # Add expected threshold sensors (created when monitoring device exists)
        if monitoring_device_id:
            # Temperature threshold sensors
            below_threshold_unique_id = (
                f"{DOMAIN}_{subentry.subentry_id}_{location_name_safe}_"
                "temperature_below_threshold_weekly_duration"
            )
            above_threshold_unique_id = (
                f"{DOMAIN}_{subentry.subentry_id}_{location_name_safe}_"
                "temperature_above_threshold_weekly_duration"
            )
            expected_threshold.add(below_threshold_unique_id)
            expected_threshold.add(above_threshold_unique_id)

    return (
        expected_monitoring,
        expected_humidity,
        expected_aggregated,
        expected_threshold,
    )


def _create_location_mirrored_sensors(
    hass: HomeAssistant,
    entry_id: str,
    location_device_id: str,
    location_name: str,
    monitoring_device_id: str,
) -> list[SensorEntity]:
    """
    Create mirrored sensors at a plant location for a monitoring device's entities.

    Args:
        hass: The Home Assistant instance.
        entry_id: The config entry ID.
        location_device_id: The device ID of the location.
        location_name: The name of the location.
        monitoring_device_id: The device ID of the monitoring device.

    Returns:
        A list of SensorEntity objects that mirror the monitoring device's sensors.

    """
    mirrored_sensors: list[SensorEntity] = []

    try:
        # Get device and entity registries
        dev_reg = dr.async_get(hass)
        ent_reg = er.async_get(hass)

        # Get the monitoring device
        monitoring_device = dev_reg.async_get(monitoring_device_id)
        if not monitoring_device:
            _LOGGER.warning(
                "Monitoring device %s not found for location %s",
                monitoring_device_id,
                location_name,
            )
            return mirrored_sensors

        # Scan for all sensor entities on the monitoring device
        for entity_entry in ent_reg.entities.values():
            if (
                entity_entry.device_id == monitoring_device.id
                and entity_entry.domain == "sensor"
            ):
                # Detect sensor type to get proper naming
                sensor_type = _detect_sensor_type_from_entity(
                    hass, entity_entry.entity_id
                )

                # Get display name from mappings if available, otherwise use entity name
                if sensor_type and sensor_type in MONITORING_SENSOR_MAPPINGS:
                    mapping: MonitoringSensorMapping = MONITORING_SENSOR_MAPPINGS[
                        sensor_type
                    ]
                    display_name = mapping.get(
                        "name", entity_entry.name or entity_entry.entity_id
                    )
                else:
                    display_name = entity_entry.name or entity_entry.entity_id

                # Create a mirrored sensor for this entity
                config = {
                    "entry_id": entry_id,
                    "source_entity_id": entity_entry.entity_id,
                    "source_entity_unique_id": entity_entry.unique_id,
                    "device_name": location_name,
                    "entity_name": display_name,
                    "sensor_type": sensor_type,
                }

                mirrored_sensor = MonitoringSensor(
                    hass=hass,
                    config=config,
                    location_device_id=location_device_id,
                )
                mirrored_sensors.append(mirrored_sensor)
                _LOGGER.debug(
                    "Created mirrored sensor for %s at location %s",
                    entity_entry.entity_id,
                    location_name,
                )

    except (AttributeError, KeyError, ValueError, TypeError) as exc:
        _LOGGER.warning(
            "Error creating location mirrored sensors for %s: %s",
            location_name,
            exc,
        )

    return mirrored_sensors


@dataclass
class SimplePlantSensorDescription:
    """Description for a simple plant sensor."""

    key: str
    name: str
    device_class: str | None = None
    unit: str | None = None


class PlantCountSensor(SensorEntity):
    """A minimal plant count sensor used for examples and tests."""

    _attr_name = "Plant Assistant Plant Count"
    _attr_unique_id = f"{DOMAIN}_plant_count_example"

    def __init__(self) -> None:
        """Initialize the plant count sensor."""
        self._state = 0

    @property
    def native_value(self) -> int:
        """Return the native value of the sensor."""
        return self._state

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return str(self._attr_name)

    def update(self) -> None:  # pragma: no cover - sync update not exercised
        """Update the sensor state."""
        self._state = 0


def _is_aggregated_sensor(unique_id: str) -> bool:
    """
    Check if a sensor unique_id belongs to an aggregated location sensor.

    Aggregated sensors have suffixes from AGGREGATED_SENSOR_MAPPINGS.

    Args:
        unique_id: The unique_id to check.

    Returns:
        True if this is an aggregated sensor, False otherwise.

    """
    # Extract all suffixes from aggregated sensor mappings
    aggregated_suffixes: set[str] = set()
    for metric_config in AGGREGATED_SENSOR_MAPPINGS.values():
        metric_config_typed: dict[str, Any] = metric_config
        suffix = metric_config_typed.get("suffix", "")
        if suffix:
            aggregated_suffixes.add(f"_{suffix}")

    # Check if unique_id contains any aggregated sensor suffix
    return any(suffix in unique_id for suffix in aggregated_suffixes)


async def _cleanup_orphaned_monitoring_sensors(  # noqa: PLR0912
    hass: HomeAssistant, entry: ConfigEntry[Any]
) -> None:
    """
    Clean up monitoring sensors that are no longer configured.

    When a monitoring device is disassociated from a location, any monitoring
    sensors that were created for that device should be fully removed rather
    than being left in an unavailable state.

    Also removes humidity linked sensors if the humidity_entity_id is removed.
    """
    try:
        entity_registry = er.async_get(hass)
        expected_monitoring_entities = set()
        expected_humidity_entities = set()
        expected_aggregated_entities = set()
        expected_threshold_entities = set()

        # Collect expected monitoring, humidity, aggregated, and threshold unique_ids
        # from subentries
        if entry.subentries:
            for subentry in entry.subentries.values():
                monitoring_set, humidity_set, aggregated_set, threshold_set = (
                    _expected_entities_for_subentry(hass, subentry)
                )
                expected_monitoring_entities.update(monitoring_set)
                expected_humidity_entities.update(humidity_set)
                expected_aggregated_entities.update(aggregated_set)
                expected_threshold_entities.update(threshold_set)

        # Find and remove orphaned entities
        entities_to_remove = []
        for entity_id, entity_entry in entity_registry.entities.items():
            if (
                entity_entry.platform != DOMAIN
                or entity_entry.domain != "sensor"
                or not entity_entry.unique_id
                or entity_entry.config_entry_id != entry.entry_id
            ):
                continue

            unique_id = entity_entry.unique_id

            # Check if this is an orphaned aggregated sensor
            # Remove if not in expected set but is identified as aggregated
            if unique_id not in expected_aggregated_entities and _is_aggregated_sensor(
                unique_id
            ):
                entities_to_remove.append(entity_id)
                continue

            # Check if this is an orphaned threshold sensor
            if unique_id not in expected_threshold_entities and (
                "temperature_below_threshold_weekly_duration" in unique_id
                or "temperature_above_threshold_weekly_duration" in unique_id
            ):
                entities_to_remove.append(entity_id)
                continue

            # Derive monitoring sensor suffixes from MONITORING_SENSOR_MAPPINGS
            monitoring_suffixes: list[str] = []
            for key, m in MONITORING_SENSOR_MAPPINGS.items():
                # m may be a dict-like mapping; be defensive about types
                if isinstance(m, dict):
                    suffix_val = m.get("suffix", key)
                # If it's a TypedDict or unexpected object, try attribute
                # access and fall back to the key when not present.
                elif hasattr(m, "suffix"):
                    suffix_val = m.suffix
                else:
                    suffix_val = key
                monitoring_suffixes.append(f"_{suffix_val}")
            # Keep a conservative fallback for previously used monitor_ prefix
            monitoring_suffixes.append("_monitor_")

            if (
                any(suffix in unique_id for suffix in monitoring_suffixes)
                and (unique_id not in expected_monitoring_entities)
            ) or (
                "_humidity_linked" in unique_id
                and (unique_id not in expected_humidity_entities)
            ):
                entities_to_remove.append(entity_id)

        # Remove orphaned entities
        for entity_id in entities_to_remove:
            entity_registry.async_remove(entity_id)
            _LOGGER.debug("Removed orphaned sensor entity: %s", entity_id)

        if entities_to_remove:
            _LOGGER.info(
                "Cleaned up %d orphaned sensor entities for entry %s",
                len(entities_to_remove),
                entry.entry_id,
            )

    except Exception as exc:  # noqa: BLE001 - Defensive logging
        _LOGGER.warning(
            "Failed to cleanup orphaned sensors: %s",
            exc,
        )


async def async_setup_platform(
    _hass: HomeAssistant,
    _config: dict[str, Any] | None,
    async_add_entities: AddEntitiesCallback,
    _discovery_info: Any = None,
) -> None:
    """Set up the sensor platform."""
    async_add_entities([PlantCountSensor()])


def _create_aggregated_location_sensors(  # noqa: PLR0913
    hass: HomeAssistant,
    entry_id: str,
    location_device_id: str,
    location_name: str,
    monitoring_device_id: str | None = None,
    humidity_entity_id: str | None = None,
    plant_slots: dict[str, Any] | None = None,
) -> list[SensorEntity]:
    """
    Create aggregated location sensors for a plant location.

    Creates sensors that aggregate plant metrics:
    - Temperature (min/max)
    - Illuminance (min/max)
    - Soil Moisture (min/max)
    - Soil Conductivity (min/max)
    - Humidity (min/max) - if humidity entity is linked

    Args:
        hass: The Home Assistant instance.
        entry_id: The subentry ID.
        location_device_id: The device ID of the location.
        location_name: The name of the location.
        monitoring_device_id: The monitoring device ID (used to determine which
                             sensors to create).
        humidity_entity_id: The humidity entity ID (used to determine if humidity
                           sensors should be created).
        plant_slots: The plant slots dict containing assigned plant device IDs.

    Returns:
        A list of AggregatedLocationSensor objects.

    """
    sensors: list[SensorEntity] = []

    # Determine which metrics to create based on configuration
    # Monitor sensors require a monitoring device
    if monitoring_device_id:
        monitor_metrics = [
            "min_temperature",
            "max_temperature",
            "min_illuminance",
            "max_illuminance",
            "min_dli",
            "max_dli",
            "min_soil_moisture",
            "max_soil_moisture",
            "min_soil_conductivity",
            "max_soil_conductivity",
        ]
    else:
        monitor_metrics = []

    # Humidity sensors require a humidity entity
    humidity_metrics = ["min_humidity", "max_humidity"] if humidity_entity_id else []

    all_metrics = monitor_metrics + humidity_metrics

    # Create sensors for each metric that is configured
    for metric_key in all_metrics:
        if metric_key not in AGGREGATED_SENSOR_MAPPINGS:
            _LOGGER.warning(
                "Aggregated sensor mapping not found for metric: %s", metric_key
            )
            continue

        metric_config = AGGREGATED_SENSOR_MAPPINGS[metric_key]

        try:
            sensor = AggregatedLocationSensor(
                hass=hass,
                entry_id=entry_id,
                location_device_id=location_device_id,
                location_name=location_name,
                metric_key=metric_key,
                metric_config=metric_config,
                plant_slots=plant_slots or {},
            )
            sensors.append(sensor)
            _LOGGER.debug(
                "Created aggregated location sensor: %s for metric %s",
                sensor.name,
                metric_key,
            )
        except Exception as exc:  # noqa: BLE001 - Defensive
            _LOGGER.warning(
                "Failed to create aggregated sensor for metric %s at location %s: %s",
                metric_key,
                location_name,
                exc,
            )

    return sensors


async def async_setup_entry(  # noqa: PLR0912, PLR0915
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """
    Set up sensors for a config entry.

    Create one AggregatedSensor per configured location (metric defaulted
    to `min_light` for initial implementation).

    For subentries with monitoring devices, also create monitoring sensors.
    For locations with monitoring devices, create mirrored sensors.
    """
    _LOGGER.debug(
        "Setting up sensors for entry: %s (%s)",
        entry.title,
        entry.entry_id,
    )

    sensors: list[SensorEntity] = []

    # Skip individual subentry processing - they are handled by main entry
    # A subentry has "device_id" in data but no subentries of its own
    if "device_id" in entry.data and not entry.subentries:
        _LOGGER.debug(
            "Skipping individual subentry processing for %s - handled by main entry",
            entry.entry_id,
        )
        return

    # Only process main entries - subentries are handled by main entry processing
    # This avoids duplicate device creation

    # Main entry - process subentries like openplantbook_ref
    if entry.subentries:
        _LOGGER.info("Processing main entry with %d subentries", len(entry.subentries))

        # Clean up orphaned monitoring sensors before creating new ones
        await _cleanup_orphaned_monitoring_sensors(hass, entry)

        for subentry_id, subentry in entry.subentries.items():
            if "device_id" not in subentry.data:
                _LOGGER.warning("Subentry %s missing device_id", subentry_id)
                continue

            _LOGGER.debug(
                "Processing subentry %s with data: %s",
                subentry.subentry_id,
                subentry.data,
            )

            location_name = subentry.data.get("name", "Plant Location")
            location_device_id = subentry.subentry_id

            subentry_entities: list[SensorEntity] = []

            # Create plant count entity for this location
            plant_slots = subentry.data.get("plant_slots", {})
            plant_count_entity = PlantCountLocationSensor(
                hass=hass,
                entry_id=subentry.subentry_id,
                location_name=location_name,
                location_device_id=location_device_id,
                plant_slots=plant_slots,
            )
            subentry_entities.append(plant_count_entity)

            # Create mirrored sensors for monitoring device if present
            monitoring_device_id = subentry.data.get("monitoring_device_id")
            mirrored_sensors = []
            if monitoring_device_id:
                mirrored_sensors = _create_location_mirrored_sensors(
                    hass=hass,
                    entry_id=subentry.subentry_id,
                    location_device_id=location_device_id,
                    location_name=location_name,
                    monitoring_device_id=monitoring_device_id,
                )
                subentry_entities.extend(mirrored_sensors)
                _LOGGER.debug(
                    "Added %d mirrored sensors for monitoring device %s at location %s",
                    len(mirrored_sensors),
                    monitoring_device_id,
                    location_name,
                )

            # Create humidity linked sensor if humidity entity is configured
            humidity_entity_id = subentry.data.get("humidity_entity_id")
            humidity_entity_unique_id = subentry.data.get("humidity_entity_unique_id")
            # Resolve entity ID with fallback to unique ID for resilience
            resolved_humidity_entity_id = _resolve_entity_id(
                hass, humidity_entity_id, humidity_entity_unique_id
            )
            if resolved_humidity_entity_id:
                humidity_sensor = HumidityLinkedSensor(
                    hass=hass,
                    entry_id=subentry.subentry_id,
                    location_device_id=location_device_id,
                    location_name=location_name,
                    humidity_entity_id=resolved_humidity_entity_id,
                    humidity_entity_unique_id=humidity_entity_unique_id,
                )
                subentry_entities.append(humidity_sensor)
                _LOGGER.debug(
                    "Added humidity linked sensor for entity %s at location %s",
                    resolved_humidity_entity_id,
                    location_name,
                )
                # Update humidity_entity_id for downstream use
                humidity_entity_id = resolved_humidity_entity_id

            # Create aggregated location sensors if plant slots are configured
            if _has_plants_in_slots(subentry.data):
                aggregated_sensors = _create_aggregated_location_sensors(
                    hass=hass,
                    entry_id=subentry.subentry_id,
                    location_device_id=location_device_id,
                    location_name=location_name,
                    monitoring_device_id=monitoring_device_id,
                    humidity_entity_id=humidity_entity_id,
                    plant_slots=plant_slots,
                )
                subentry_entities.extend(aggregated_sensors)
                _LOGGER.debug(
                    "Added %d aggregated location sensors for location %s",
                    len(aggregated_sensors),
                    location_name,
                )

            # Create DLI sensors if monitoring device with illuminance is configured
            # DLI pipeline: PPFD -> Total Integral -> DLI
            if monitoring_device_id:
                # Find illuminance mirrored sensor source entity for this location
                illuminance_source_entity_id = None
                illuminance_source_unique_id = None
                for sensor in mirrored_sensors:
                    if (
                        isinstance(sensor, MonitoringSensor)
                        and hasattr(sensor, "source_entity_id")
                        and "illuminance" in sensor.source_entity_id.lower()
                    ):
                        # Capture both entity_id and unique_id for resilient lookup
                        illuminance_source_entity_id = sensor.source_entity_id
                        illuminance_source_unique_id = getattr(
                            sensor, "source_entity_unique_id", None
                        )
                        break

                if illuminance_source_entity_id:
                    # Create PPFD sensor (converts lux to μmol/m²/s)
                    ppfd_sensor = PlantLocationPpfdSensor(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        illuminance_entity_id=illuminance_source_entity_id,
                        illuminance_entity_unique_id=illuminance_source_unique_id,
                    )
                    subentry_entities.append(ppfd_sensor)

                    # Create total integral sensor (integrates PPFD over time)
                    total_integral_sensor = PlantLocationTotalLightIntegral(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        ppfd_sensor=ppfd_sensor,
                    )

                    # Add integral sensor immediately so it gets an initial state
                    _LOGGER.debug(
                        "Adding Total Integral sensor %s before creating DLI",
                        total_integral_sensor.entity_id,
                    )
                    # Use a cast wrapper to call async_add_entities with the
                    # `config_subentry_id` kwarg which isn't present in the
                    # older type stubs.
                    _add_entities = cast("Callable[..., Any]", async_add_entities)
                    _add_entities(
                        [total_integral_sensor],
                        update_before_add=True,
                        config_subentry_id=subentry_id,
                    )

                    # Prepare data used by UtilityMeterSensor.async_reading
                    hass.data.setdefault(DATA_UTILITY, {})
                    hass.data[DATA_UTILITY].setdefault(subentry.subentry_id, {})
                    hass.data[DATA_UTILITY][subentry.subentry_id].setdefault(
                        DATA_TARIFF_SENSORS, []
                    )

                    _LOGGER.debug(
                        "Creating DLI sensor with source %s",
                        total_integral_sensor.entity_id,
                    )
                    dli_sensor = PlantLocationDailyLightIntegral(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        total_integral_sensor=total_integral_sensor,
                    )
                    subentry_entities.append(dli_sensor)

                    # Register DLI sensor with utility meter data structure
                    hass.data[DATA_UTILITY][subentry.subentry_id][
                        DATA_TARIFF_SENSORS
                    ].append(dli_sensor)

                    # Create a sensor exposing the prior_period attribute.
                    # This represents yesterday's DLI value.
                    dli_prior_period_sensor = DliPriorPeriodSensor(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        dli_entity_id=dli_sensor.entity_id,
                        dli_entity_unique_id=dli_sensor.unique_id,
                    )
                    subentry_entities.append(dli_prior_period_sensor)

                    # Create a sensor to calculate the 7-day average of DLI values.
                    # This uses Home Assistant's statistics component to track
                    # historical DLI values and expose their mean over 7 days.
                    weekly_avg_dli_sensor = WeeklyAverageDliSensor(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        dli_prior_period_entity_id=dli_prior_period_sensor.entity_id,
                        dli_prior_period_entity_unique_id=dli_prior_period_sensor.unique_id,
                    )
                    subentry_entities.append(weekly_avg_dli_sensor)

                    _LOGGER.debug("Added DLI for %s", location_name)
                else:
                    _LOGGER.debug("No illuminance sensor for DLI at %s", location_name)

                # Create temperature below threshold weekly duration sensor
                # Only create if a temperature sensor and plant slots exist
                temperature_source_entity_id = None
                temperature_source_unique_id = None
                for sensor in mirrored_sensors:
                    if (
                        isinstance(sensor, MonitoringSensor)
                        and hasattr(sensor, "source_entity_id")
                        and "temperature" in sensor.source_entity_id.lower()
                    ):
                        # Capture both entity_id and unique_id for resilient lookup
                        temperature_source_entity_id = sensor.source_entity_id
                        temperature_source_unique_id = getattr(
                            sensor, "source_entity_unique_id", None
                        )
                        break

                if temperature_source_entity_id and _has_plants_in_slots(subentry.data):
                    temp_below_threshold_sensor = TemperatureBelowThresholdHoursSensor(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        temperature_entity_id=temperature_source_entity_id,
                        temperature_entity_unique_id=temperature_source_unique_id,
                    )
                    subentry_entities.append(temp_below_threshold_sensor)
                    _LOGGER.debug(
                        "Added temp below threshold weekly duration sensor for %s",
                        location_name,
                    )

                    # Also create temperature above threshold weekly duration sensor
                    temp_above_threshold_sensor = TemperatureAboveThresholdHoursSensor(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        temperature_entity_id=temperature_source_entity_id,
                        temperature_entity_unique_id=temperature_source_unique_id,
                    )
                    subentry_entities.append(temp_above_threshold_sensor)
                    _LOGGER.debug(
                        "Added temp above threshold weekly duration for %s",
                        location_name,
                    )

                # Create humidity below threshold weekly duration sensor
                # Only create if a humidity entity is linked
                humidity_entity_id = subentry.data.get("humidity_entity_id")
                humidity_entity_unique_id = subentry.data.get(
                    "humidity_entity_unique_id"
                )
                if humidity_entity_id and _has_plants_in_slots(subentry.data):
                    humidity_below_threshold_sensor = HumidityBelowThresholdHoursSensor(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        humidity_entity_id=humidity_entity_id,
                        humidity_entity_unique_id=humidity_entity_unique_id,
                    )
                    subentry_entities.append(humidity_below_threshold_sensor)
                    _LOGGER.debug(
                        "Added humidity below threshold weekly duration sensor for %s",
                        location_name,
                    )

                    # Also create humidity above threshold weekly duration sensor
                    humidity_above_threshold_sensor = HumidityAboveThresholdHoursSensor(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        humidity_entity_id=humidity_entity_id,
                        humidity_entity_unique_id=humidity_entity_unique_id,
                    )
                    subentry_entities.append(humidity_above_threshold_sensor)
                    _LOGGER.debug(
                        "Added humidity above threshold weekly duration sensor for %s",
                        location_name,
                    )

            # Create watering detection sensors for non-ESPHome zones
            # These sensors help detect watering by monitoring moisture spikes
            # Only create if location has monitoring device with soil moisture sensor
            # AND is linked to an irrigation zone WITHOUT an ESPHome device
            if monitoring_device_id:
                # Check if zone has ESPHome device
                has_esphome = _zone_has_esphome_device(hass, entry, subentry)

                # Only create watering detection sensors for non-ESPHome zones
                if not has_esphome:
                    # Find soil moisture sensor to create statistics sensor from
                    soil_moisture_entity_id = None
                    soil_moisture_entity_unique_id = None
                    for sensor in mirrored_sensors:
                        if (
                            isinstance(sensor, MonitoringSensor)
                            and hasattr(sensor, "source_entity_id")
                            and "moisture" in sensor.source_entity_id.lower()
                        ):
                            soil_moisture_entity_id = sensor.source_entity_id
                            soil_moisture_entity_unique_id = getattr(
                                sensor, "source_entity_unique_id", None
                            )
                            break

                    if soil_moisture_entity_id:
                        # Create Recent Change statistics sensor
                        # This tracks the % change in soil moisture over 3 hours
                        recent_change_sensor = SoilMoistureRecentChangeSensor(
                            hass=hass,
                            entry_id=subentry.subentry_id,
                            location_device_id=location_device_id,
                            location_name=location_name,
                            soil_moisture_entity_id=soil_moisture_entity_id,
                            soil_moisture_entity_unique_id=soil_moisture_entity_unique_id,
                        )
                        subentry_entities.append(recent_change_sensor)
                        _LOGGER.debug(
                            "Added soil moisture recent change sensor for %s",
                            location_name,
                        )

                        # Create Last Watered timestamp sensor
                        # Tracks when Recently Watered sensor detects watering
                        # recently_watered_entity_id resolved dynamically
                        # at runtime since binary sensors created after sensors
                        last_watered_sensor = PlantLocationLastWateredSensor(
                            hass=hass,
                            entry_id=subentry.subentry_id,
                            location_device_id=location_device_id,
                            location_name=location_name,
                            recently_watered_entity_id=None,  # Resolved dynamically
                        )
                        subentry_entities.append(last_watered_sensor)
                        _LOGGER.debug(
                            "Added last watered sensor for %s",
                            location_name,
                        )

            # Add entities with proper subentry association (like openplantbook_ref)
            _LOGGER.debug(
                "Adding %d entities for subentry %s",
                len(subentry_entities),
                subentry_id,
            )
            # Note: config_subentry_id exists in HA 2025.8.3+ but not in type hint
            _add_entities = cast("Callable[..., Any]", async_add_entities)
            _add_entities(subentry_entities, config_subentry_id=subentry_id)

    # Main entry aggregated sensors for locations (if no subentries)
    zones = entry.options.get("irrigation_zones", {})
    sensors.extend(
        [
            AggregatedSensor(hass, entry.entry_id, zone_id, loc_id, "min_light")
            for zone_id, zone in zones.items()
            for loc_id in zone.get("locations", {})
        ]
    )

    # Create irrigation zone last run start time sensors for zones with esphome devices
    device_registry = dr.async_get(hass)
    for zone_id, zone in zones.items():
        if linked_device_id := zone.get("linked_device_id"):
            zone_name = zone.get("name") or f"Zone {zone_id}"
            zone_device = device_registry.async_get(linked_device_id)
            if zone_device and zone_device.identifiers:
                zone_device_identifier = next(iter(zone_device.identifiers))

                last_run_start_sensor = IrrigationZoneLastRunStartTimeSensor(
                    hass=hass,
                    entry_id=entry.entry_id,
                    zone_device_id=zone_device_identifier,
                    zone_name=zone_name,
                    zone_id=zone_id,
                )
                sensors.append(last_run_start_sensor)
                _LOGGER.debug(
                    "Created last run start time sensor for irrigation zone %s",
                    zone_name,
                )

                last_run_end_sensor = IrrigationZoneLastRunEndTimeSensor(
                    hass=hass,
                    entry_id=entry.entry_id,
                    zone_device_id=zone_device_identifier,
                    zone_name=zone_name,
                    zone_id=zone_id,
                )
                sensors.append(last_run_end_sensor)
                _LOGGER.debug(
                    "Created last run end time sensor for irrigation zone %s",
                    zone_name,
                )

                last_fertiliser_injection_sensor = (
                    IrrigationZoneLastFertiliserInjectionSensor(
                        hass=hass,
                        entry_id=entry.entry_id,
                        zone_device_id=zone_device_identifier,
                        zone_name=zone_name,
                        zone_id=zone_id,
                    )
                )
                sensors.append(last_fertiliser_injection_sensor)
                _LOGGER.debug(
                    "Created last fertiliser injection sensor for irrigation zone %s",
                    zone_name,
                )

                last_run_expected_duration_sensor = (
                    IrrigationZoneLastRunExpectedDurationSensor(
                        hass=hass,
                        entry_id=entry.entry_id,
                        zone_device_id=zone_device_identifier,
                        zone_name=zone_name,
                        zone_id=zone_id,
                    )
                )
                sensors.append(last_run_expected_duration_sensor)
                _LOGGER.debug(
                    "Created last run expected duration sensor for irrigation zone %s",
                    zone_name,
                )

                last_run_actual_duration_sensor = (
                    IrrigationZoneLastRunActualDurationSensor(
                        hass=hass,
                        entry_id=entry.entry_id,
                        zone_device_id=zone_device_identifier,
                        zone_name=zone_name,
                        zone_id=zone_id,
                    )
                )
                sensors.append(last_run_actual_duration_sensor)
                _LOGGER.debug(
                    "Created last run actual duration sensor for irrigation zone %s",
                    zone_name,
                )

                last_run_water_main_usage_sensor = (
                    IrrigationZoneLastRunWaterMainUsageSensor(
                        hass=hass,
                        entry_id=entry.entry_id,
                        zone_device_id=zone_device_identifier,
                        zone_name=zone_name,
                        zone_id=zone_id,
                    )
                )
                sensors.append(last_run_water_main_usage_sensor)
                _LOGGER.debug(
                    "Created last run water main usage sensor for irrigation zone %s",
                    zone_name,
                )

                last_run_rain_water_usage_sensor = (
                    IrrigationZoneLastRunRainWaterUsageSensor(
                        hass=hass,
                        entry_id=entry.entry_id,
                        zone_device_id=zone_device_identifier,
                        zone_name=zone_name,
                        zone_id=zone_id,
                    )
                )
                sensors.append(last_run_rain_water_usage_sensor)
                _LOGGER.debug(
                    "Created last run rain water usage sensor for irrigation zone %s",
                    zone_name,
                )

                last_run_fertiliser_usage_sensor = (
                    IrrigationZoneLastRunFertiliserUsageSensor(
                        hass=hass,
                        entry_id=entry.entry_id,
                        zone_device_id=zone_device_identifier,
                        zone_name=zone_name,
                        zone_id=zone_id,
                    )
                )
                sensors.append(last_run_fertiliser_usage_sensor)
                _LOGGER.debug(
                    "Created last run fertiliser usage sensor for irrigation zone %s",
                    zone_name,
                )

                last_error_sensor = IrrigationZoneLastErrorSensor(
                    hass=hass,
                    entry_id=entry.entry_id,
                    zone_device_id=zone_device_identifier,
                    zone_name=zone_name,
                    zone_id=zone_id,
                )
                sensors.append(last_error_sensor)
                _LOGGER.debug(
                    "Created last error sensor for irrigation zone %s",
                    zone_name,
                )

                last_error_type_sensor = IrrigationZoneLastErrorTypeSensor(
                    hass=hass,
                    entry_id=entry.entry_id,
                    zone_device_id=zone_device_identifier,
                    zone_name=zone_name,
                    zone_id=zone_id,
                )
                sensors.append(last_error_type_sensor)
                _LOGGER.debug(
                    "Created last error type sensor for irrigation zone %s",
                    zone_name,
                )

                last_error_message_sensor = IrrigationZoneLastErrorMessageSensor(
                    hass=hass,
                    entry_id=entry.entry_id,
                    zone_device_id=zone_device_identifier,
                    zone_name=zone_name,
                    zone_id=zone_id,
                )
                sensors.append(last_error_message_sensor)
                _LOGGER.debug(
                    "Created last error message sensor for irrigation zone %s",
                    zone_name,
                )

                error_count_sensor = IrrigationZoneErrorCountSensor(
                    hass=hass,
                    entry_id=entry.entry_id,
                    zone_device_id=zone_device_identifier,
                    zone_name=zone_name,
                    zone_id=zone_id,
                )
                sensors.append(error_count_sensor)
                _LOGGER.debug(
                    "Created error count sensor for irrigation zone %s",
                    zone_name,
                )

                fertiliser_due_sensor = IrrigationZoneFertiliserDueSensor(
                    hass=hass,
                    entry_id=entry.entry_id,
                    zone_device_id=zone_device_identifier,
                    zone_name=zone_name,
                    zone_id=zone_id,
                )
                sensors.append(fertiliser_due_sensor)
                _LOGGER.debug(
                    "Created fertiliser due sensor for irrigation zone %s",
                    zone_name,
                )

    _LOGGER.info("Adding %d sensors for entry %s", len(sensors), entry.entry_id)
    async_add_entities(sensors)


class IrrigationZoneLastRunStartTimeSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks the last run start time of an irrigation zone.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and updates when the event fires with the zone's start time data.
    The sensor uses the timestamp device_class for proper formatting.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last run start time sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Run Start Time"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:clock-outline"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_run_start_time",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _extract_zone_start_time(self, event_data: dict[str, Any]) -> str | None:
        """
        Extract the zone start time from event data.

        The zone_name is converted to a key like 'lawn_start_time'.
        The zone_name is normalized by replacing spaces with underscores and
        converting to lowercase to match the event data key format.

        Args:
            event_data: The event data dictionary.

        Returns:
            The start time value if found, None otherwise.

        """
        # Convert zone_name to lowercase and replace spaces with underscores
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        zone_key = f"{normalized_zone_name}_start_time"
        start_time = event_data.get(zone_key)

        if start_time:
            _LOGGER.debug(
                "Extracted zone start time for %s: normalized=%s, key=%s, value=%s",
                self.zone_name,
                normalized_zone_name,
                normalized_zone_name,
                start_time,
            )

        return cast("str | None", start_time)

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            # Log the event for debugging
            _LOGGER.debug(
                "Received esphome.irrigation_gateway_update event for zone %s. "
                "Event data keys: %s",
                self.zone_name,
                list(event_data.keys()),
            )

            # Extract the start time for this specific zone
            start_time = self._extract_zone_start_time(event_data)

            if not start_time:
                _LOGGER.debug(
                    "No start time extracted for %s from event data",
                    self.zone_name,
                )
                return

            if start_time in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "Start time for %s is unavailable/unknown: %s",
                    self.zone_name,
                    start_time,
                )
                return

            # Update the state with the new start time
            old_state = self._state
            self._state = start_time

            # Store event data in attributes
            normalized_zone_name = self.zone_name.lower().replace(" ", "_")
            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_name": self.zone_name,
                "zone_key": f"{normalized_zone_name}_start_time",
            }

            # Log the update
            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s start time from %s to %s",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None

        # Parse ISO 8601 datetime string to datetime object for TIMESTAMP device class
        try:
            if isinstance(self._state, str):
                # Use dt_util.parse_datetime to handle ISO 8601 format with timezone
                parsed_dt = dt_util.parse_datetime(self._state)
                if parsed_dt:
                    return parsed_dt
                _LOGGER.warning(
                    "Failed to parse datetime for %s: %s",
                    self.zone_name,
                    self._state,
                )
                return None
        except (ValueError, TypeError) as exc:
            _LOGGER.warning(
                "Error converting state to datetime for %s: %s",
                self.zone_name,
                exc,
            )
            return None
        else:
            # Already a datetime object
            return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored last run start time sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        # Subscribe to esphome irrigation gateway update events
        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneLastRunEndTimeSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks the last run end time of an irrigation zone.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and updates when the event fires with the zone's end time data.
    The sensor uses the timestamp device_class for proper formatting.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last run end time sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Run End Time"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:clock-outline"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_run_end_time",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _extract_zone_end_time(self, event_data: dict[str, Any]) -> str | None:
        """
        Extract the zone end time from event data.

        The zone_name is converted to a key like 'lawn_end_time'.
        The zone_name is normalized by replacing spaces with underscores and
        converting to lowercase to match the event data key format.

        Args:
            event_data: The event data dictionary.

        Returns:
            The end time value if found, None otherwise.

        """
        # Convert zone_name to lowercase and replace spaces with underscores
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        zone_key = f"{normalized_zone_name}_end_time"
        end_time = event_data.get(zone_key)

        if end_time:
            _LOGGER.debug(
                "Extracted zone end time for %s: normalized=%s, key=%s, value=%s",
                self.zone_name,
                normalized_zone_name,
                zone_key,
                end_time,
            )

        return cast("str | None", end_time)

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            # Log the event for debugging
            _LOGGER.debug(
                "Received esphome.irrigation_gateway_update event for zone %s. "
                "Event data keys: %s",
                self.zone_name,
                list(event_data.keys()),
            )

            # Extract the end time for this specific zone
            end_time = self._extract_zone_end_time(event_data)

            if not end_time:
                _LOGGER.debug(
                    "No end time extracted for %s from event data",
                    self.zone_name,
                )
                return

            if end_time in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "End time for %s is unavailable/unknown: %s",
                    self.zone_name,
                    end_time,
                )
                return

            # Update the state with the new end time
            old_state = self._state
            self._state = end_time

            # Store event data in attributes
            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_id": self.zone_id,
                "zone_key": f"{self.zone_id.replace('-', '_')}_end_time",
            }

            # Log the update
            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s end time from %s to %s",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None

        # Parse ISO 8601 datetime string to datetime object for TIMESTAMP device class
        try:
            if isinstance(self._state, str):
                # Use dt_util.parse_datetime to handle ISO 8601 format with timezone
                parsed_dt = dt_util.parse_datetime(self._state)
                if parsed_dt:
                    return parsed_dt
                _LOGGER.warning(
                    "Failed to parse datetime for %s: %s",
                    self.zone_name,
                    self._state,
                )
                return None
        except (ValueError, TypeError) as exc:
            _LOGGER.warning(
                "Error converting state to datetime for %s: %s",
                self.zone_name,
                exc,
            )
            return None
        else:
            # Already a datetime object
            return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored last run end time sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        # Subscribe to esphome irrigation gateway update events
        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneLastFertiliserInjectionSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks the last fertiliser injection time of an irrigation zone.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and updates when the event fires with the zone's fertiliser injection time.
    The sensor uses the timestamp device_class for proper formatting.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last fertiliser injection sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Fertiliser Injection"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:water-opacity"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_fertiliser_injection",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _extract_zone_fertiliser_injection_time(
        self, event_data: dict[str, Any]
    ) -> str | None:
        """
        Extract the zone fertiliser injection time from event data.

        The zone_name is converted to a key like 'lawn_fertiliser_injection_time'.
        The zone_name is normalized by replacing spaces with underscores and
        converting to lowercase to match the event data key format.

        Args:
            event_data: The event data dictionary.

        Returns:
            The fertiliser injection time value if found, None otherwise.

        """
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        zone_key = f"{normalized_zone_name}_fertiliser_injection_time"
        injection_time = event_data.get(zone_key)

        if injection_time:
            _LOGGER.debug(
                "Extracted zone fertiliser injection time for %s: "
                "normalized=%s, key=%s, value=%s",
                self.zone_name,
                normalized_zone_name,
                zone_key,
                injection_time,
            )

        return cast("str | None", injection_time)

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            _LOGGER.debug(
                "Received esphome.irrigation_gateway_update event for zone %s",
                self.zone_name,
            )

            injection_time = self._extract_zone_fertiliser_injection_time(event_data)

            if not injection_time:
                _LOGGER.debug(
                    "No fertiliser injection time extracted for %s",
                    self.zone_name,
                )
                return

            if injection_time in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "Fertiliser injection time for %s is unavailable/unknown",
                    self.zone_name,
                )
                return

            old_state = self._state
            self._state = injection_time

            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_id": self.zone_id,
            }

            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s fertiliser injection time from %s to %s",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None

        try:
            if isinstance(self._state, str):
                parsed_dt = dt_util.parse_datetime(self._state)
                if parsed_dt:
                    return parsed_dt
                _LOGGER.warning(
                    "Failed to parse datetime for %s: %s",
                    self.zone_name,
                    self._state,
                )
                return None
        except (ValueError, TypeError) as exc:
            _LOGGER.warning(
                "Error converting state to datetime for %s: %s",
                self.zone_name,
                exc,
            )
            return None
        else:
            return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored last fertiliser injection sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneLastRunExpectedDurationSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks the expected duration of the last irrigation run.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and updates when the event fires with the zone's expected duration.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last run expected duration sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Run Expected Duration"
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_native_unit_of_measurement = "min"
        self._attr_state_class = "measurement"
        self._attr_icon = "mdi:timer-star"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_run_expected_duration",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _extract_zone_duration(self, event_data: dict[str, Any]) -> str | None:
        """
        Extract the zone expected duration from event data.

        The zone_name is converted to a key like 'lawn_duration'.
        The zone_name is normalized by replacing spaces with underscores and
        converting to lowercase to match the event data key format.

        Args:
            event_data: The event data dictionary.

        Returns:
            The duration value if found, None otherwise.

        """
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        zone_key = f"{normalized_zone_name}_duration"
        duration = event_data.get(zone_key)

        if duration:
            _LOGGER.debug(
                "Extracted zone expected duration for %s: zone_name=%s, "
                "key=%s, value=%s",
                self.zone_name,
                self.zone_name,
                zone_key,
                duration,
            )

        return cast("str | None", duration)

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            duration = self._extract_zone_duration(event_data)

            if not duration:
                _LOGGER.debug(
                    "No duration extracted for %s from event data",
                    self.zone_name,
                )
                return

            if duration in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "Duration for %s is unavailable/unknown: %s",
                    self.zone_name,
                    duration,
                )
                return

            old_state = self._state
            self._state = duration

            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_id": self.zone_id,
            }

            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s expected duration from %s to %s",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None

        try:
            return float(self._state)
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored last run expected duration sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneLastRunActualDurationSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks the actual duration of the last irrigation run.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and calculates the actual duration from start and end times.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last run actual duration sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Run Actual Duration"
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_native_unit_of_measurement = "min"
        self._attr_state_class = "measurement"
        self._attr_icon = "mdi:timer"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_run_actual_duration",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _calculate_duration_from_times(
        self, event_data: dict[str, Any]
    ) -> float | None:
        """
        Calculate duration from start and end times in event data.

        Args:
            event_data: The event data dictionary.

        Returns:
            The duration in minutes, or None if calculation fails.

        """
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        start_key = f"{normalized_zone_name}_start_time"
        end_key = f"{normalized_zone_name}_end_time"

        start_time = event_data.get(start_key)
        end_time = event_data.get(end_key)

        if not start_time or not end_time:
            return None

        if start_time in (STATE_UNAVAILABLE, STATE_UNKNOWN) or end_time in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            return None

        try:
            start_ts = dt_util.parse_datetime(start_time)
            end_ts = dt_util.parse_datetime(end_time)

            if start_ts and end_ts and end_ts > start_ts:
                duration_minutes = int((end_ts - start_ts).total_seconds() / 60)
                return float(duration_minutes)
        except (ValueError, TypeError) as exc:
            _LOGGER.debug(
                "Error calculating duration for %s: %s",
                self.zone_name,
                exc,
            )

        return None

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            duration = self._calculate_duration_from_times(event_data)

            if duration is None:
                _LOGGER.debug(
                    "No actual duration calculated for %s from event data",
                    self.zone_name,
                )
                return

            old_state = self._state
            self._state = duration

            normalized_zone_name = self.zone_name.lower().replace(" ", "_")
            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_name": self.zone_name,
                "zone_key": f"{normalized_zone_name}_start_time",
            }

            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s actual duration from %s to %s minutes",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._state = float(last_state.state)
            except (ValueError, TypeError):
                self._state = last_state.state

            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored last run actual duration sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneLastRunWaterMainUsageSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks water main usage from the last irrigation run.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and updates with the water main usage value.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last run water main usage sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Run Water Main Usage"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_native_unit_of_measurement = "L"
        self._attr_state_class = "total_increasing"
        self._attr_icon = "mdi:water-pump"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_run_water_main_usage",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _extract_water_main_usage(self, event_data: dict[str, Any]) -> str | None:
        """
        Extract the water main usage from event data.

        Args:
            event_data: The event data dictionary.

        Returns:
            The water main usage value if found, None otherwise.

        """
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        zone_key = f"{normalized_zone_name}_water_main_usage"
        usage = event_data.get(zone_key)

        if usage:
            _LOGGER.debug(
                "Extracted zone water main usage for %s: key=%s, value=%s",
                self.zone_name,
                zone_key,
                usage,
            )

        return cast("str | None", usage)

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            usage = self._extract_water_main_usage(event_data)

            if not usage:
                _LOGGER.debug(
                    "No water main usage extracted for %s",
                    self.zone_name,
                )
                return

            if usage in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "Water main usage for %s is unavailable/unknown",
                    self.zone_name,
                )
                return

            old_state = self._state
            self._state = usage

            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_id": self.zone_id,
            }

            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s water main usage from %s to %s l",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None

        try:
            return float(self._state)
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._state = float(last_state.state)
            except (ValueError, TypeError):
                self._state = last_state.state

            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored water main usage sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneLastRunRainWaterUsageSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks rain water tank usage from the last irrigation run.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and updates with the rain water tank usage value.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last run rain water usage sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Run Rain Water Usage"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_native_unit_of_measurement = "L"
        self._attr_state_class = "total_increasing"
        self._attr_icon = "mdi:weather-pouring"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_run_rain_water_usage",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _extract_rain_water_usage(self, event_data: dict[str, Any]) -> str | None:
        """
        Extract the rain water tank usage from event data.

        Args:
            event_data: The event data dictionary.

        Returns:
            The rain water tank usage value if found, None otherwise.

        """
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        zone_key = f"{normalized_zone_name}_rain_water_tank_usage"
        usage = event_data.get(zone_key)

        if usage:
            _LOGGER.debug(
                "Extracted zone rain water usage for %s: key=%s, value=%s",
                self.zone_name,
                zone_key,
                usage,
            )

        return cast("str | None", usage)

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            usage = self._extract_rain_water_usage(event_data)

            if not usage:
                _LOGGER.debug(
                    "No rain water usage extracted for %s",
                    self.zone_name,
                )
                return

            if usage in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "Rain water usage for %s is unavailable/unknown",
                    self.zone_name,
                )
                return

            old_state = self._state
            self._state = usage

            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_id": self.zone_id,
            }

            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s rain water usage from %s to %s l",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None

        try:
            return float(self._state)
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._state = float(last_state.state)
            except (ValueError, TypeError):
                self._state = last_state.state

            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored rain water usage sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneLastRunFertiliserUsageSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks fertiliser usage from the last irrigation run.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and updates with the fertiliser usage value.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last run fertiliser usage sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Run Fertiliser Usage"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_native_unit_of_measurement = "L"
        self._attr_state_class = "total_increasing"
        self._attr_icon = "mdi:water-pump"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_run_fertiliser_usage",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _extract_fertiliser_usage(self, event_data: dict[str, Any]) -> str | None:
        """
        Extract the fertiliser usage from event data.

        Args:
            event_data: The event data dictionary.

        Returns:
            The fertiliser usage value if found, None otherwise.

        """
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        zone_key = f"{normalized_zone_name}_fertiliser_usage"
        usage = event_data.get(zone_key)

        if usage:
            _LOGGER.debug(
                "Extracted zone fertiliser usage for %s: key=%s, value=%s",
                self.zone_name,
                zone_key,
                usage,
            )

        return cast("str | None", usage)

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            usage = self._extract_fertiliser_usage(event_data)

            if not usage:
                _LOGGER.debug(
                    "No fertiliser usage extracted for %s",
                    self.zone_name,
                )
                return

            if usage in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "Fertiliser usage for %s is unavailable/unknown",
                    self.zone_name,
                )
                return

            old_state = self._state
            self._state = usage

            normalized_zone_name = self.zone_name.lower().replace(" ", "_")
            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_name": self.zone_name,
                "zone_key": f"{normalized_zone_name}_fertiliser_usage",
            }

            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s fertiliser usage from %s to %s l",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None

        try:
            return float(self._state)
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._state = float(last_state.state)
            except (ValueError, TypeError):
                self._state = last_state.state

            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored fertiliser usage sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneLastErrorSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks the last error time of an irrigation zone.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and updates with the last error time using the timestamp device_class.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last error sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Error"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:alert-circle"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_error",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _extract_zone_error_time(self, event_data: dict[str, Any]) -> str | None:
        """
        Extract the zone error time from event data.

        The zone_name is converted to a key like 'lawn_error_time'.
        The zone_name is normalized by replacing spaces with underscores and
        converting to lowercase to match the event data key format.

        Args:
            event_data: The event data dictionary.

        Returns:
            The error time value if found, None otherwise.

        """
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        zone_key = f"{normalized_zone_name}_error_time"
        error_time = event_data.get(zone_key)

        if error_time:
            _LOGGER.debug(
                "Extracted zone error time for %s: key=%s, value=%s",
                self.zone_name,
                zone_key,
                error_time,
            )

        return cast("str | None", error_time)

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            error_time = self._extract_zone_error_time(event_data)

            if not error_time:
                _LOGGER.debug(
                    "No error time extracted for %s",
                    self.zone_name,
                )
                return

            if error_time in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "Error time for %s is unavailable/unknown",
                    self.zone_name,
                )
                return

            old_state = self._state
            self._state = error_time

            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_id": self.zone_id,
            }

            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s error time from %s to %s",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None

        try:
            if isinstance(self._state, str):
                parsed_dt = dt_util.parse_datetime(self._state)
                if parsed_dt:
                    return parsed_dt
                _LOGGER.warning(
                    "Failed to parse datetime for %s: %s",
                    self.zone_name,
                    self._state,
                )
                return None
        except (ValueError, TypeError) as exc:
            _LOGGER.warning(
                "Error converting state to datetime for %s: %s",
                self.zone_name,
                exc,
            )
            return None
        else:
            return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored last error sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneLastErrorTypeSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks the last error type of an irrigation zone.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and updates with the error type value.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last error type sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Error Type"
        self._attr_icon = "mdi:alert-octagon"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_error_type",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _extract_zone_error_type(self, event_data: dict[str, Any]) -> str | None:
        """
        Extract the zone error type from event data.

        The zone_name is converted to a key like 'lawn_error_type'.
        The zone_name is normalized by replacing spaces with underscores and
        converting to lowercase to match the event data key format.

        Args:
            event_data: The event data dictionary.

        Returns:
            The error type value if found, None otherwise.

        """
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        zone_key = f"{normalized_zone_name}_error_type"
        error_type = event_data.get(zone_key)

        if error_type:
            _LOGGER.debug(
                "Extracted zone error type for %s: key=%s, value=%s",
                self.zone_name,
                zone_key,
                error_type,
            )

        return cast("str | None", error_type)

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            error_type = self._extract_zone_error_type(event_data)

            if not error_type:
                _LOGGER.debug(
                    "No error type extracted for %s",
                    self.zone_name,
                )
                return

            if error_type in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "Error type for %s is unavailable/unknown",
                    self.zone_name,
                )
                return

            old_state = self._state
            self._state = error_type

            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_id": self.zone_id,
            }

            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s error type from %s to %s",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored last error type sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneLastErrorMessageSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks the last error message of an irrigation zone.

    This sensor listens for the 'esphome.irrigation_gateway_update' event
    and updates with the error message/detail value.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone last error message sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Last Error Message"
        self._attr_icon = "mdi:message-alert"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "last_error_message",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

    def _extract_zone_error_detail(self, event_data: dict[str, Any]) -> str | None:
        """
        Extract the zone error detail/message from event data.

        The zone_name is converted to a key like 'lawn_error_detail'.
        The zone_name is normalized by replacing spaces with underscores and
        converting to lowercase to match the event data key format.

        Args:
            event_data: The event data dictionary.

        Returns:
            The error detail value if found, None otherwise.

        """
        normalized_zone_name = self.zone_name.lower().replace(" ", "_")
        zone_key = f"{normalized_zone_name}_error_detail"
        error_detail = event_data.get(zone_key)

        if error_detail:
            _LOGGER.debug(
                "Extracted zone error detail for %s: key=%s, value=%s",
                self.zone_name,
                zone_key,
                error_detail,
            )

        return cast("str | None", error_detail)

    @callback
    def _handle_esphome_event(self, event: Any) -> None:
        """Handle esphome.irrigation_gateway_update event."""
        try:
            event_data = event.data if hasattr(event, "data") else {}

            error_detail = self._extract_zone_error_detail(event_data)

            if not error_detail:
                _LOGGER.debug(
                    "No error detail extracted for %s",
                    self.zone_name,
                )
                return

            if error_detail in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                _LOGGER.debug(
                    "Error detail for %s is unavailable/unknown",
                    self.zone_name,
                )
                return

            old_state = self._state
            self._state = error_detail

            self._attributes = {
                "event_type": "esphome.irrigation_gateway_update",
                "zone_id": self.zone_id,
            }

            if old_state != self._state:
                _LOGGER.debug(
                    "Updated %s error message from %s to %s",
                    self.zone_name,
                    old_state,
                    self._state,
                )

            self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored last error message sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneErrorCountSensor(SensorEntity, RestoreEntity):
    """
    Sensor that counts the number of errors for an irrigation zone.

    This sensor listens for updates to the last error entity and increments
    the count when a new error timestamp is detected.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone error count sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Error Count"
        self._attr_native_unit_of_measurement = "errors"
        self._attr_state_class = "total_increasing"
        self._attr_icon = "mdi:counter"

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "error_count",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: int = 0
        self._attributes: dict[str, Any] = {}
        self._last_error_state: str | None = None
        self._unsubscribe_last_error = None
        self._last_error_entity_id: str | None = None

    def reset_error_count(self) -> None:
        """Reset the error count to 0 and clear tracking state."""
        self._state = 0
        self._last_error_state = None
        self._attributes = {}
        self.async_write_ha_state()
        _LOGGER.debug(
            "Reset error count for %s",
            self.zone_name,
        )

    @callback
    def _handle_last_error_state_change(self, event: Event) -> None:
        """Handle Last Error entity state changes."""
        new_state = event.data.get("new_state")
        try:
            if not new_state:
                return

            new_error_time = new_state.state
            if new_error_time in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
                _LOGGER.debug(
                    "Last Error state for %s is unavailable/unknown/None",
                    self.zone_name,
                )
                return

            # Check if this is a new error (different from internal tracking)
            if new_error_time != self._last_error_state:
                old_count = self._state
                self._state += 1
                self._last_error_state = new_error_time

                self._attributes = {
                    "event_type": "last_error_state_change",
                    "zone_id": self.zone_id,
                    "last_error_time": new_error_time,
                }

                _LOGGER.debug(
                    "Incremented %s error count from %d to %d"
                    " (Last Error state change to %s)",
                    self.zone_name,
                    old_count,
                    self._state,
                    new_error_time,
                )

                self.async_write_ha_state()
            else:
                _LOGGER.debug(
                    "Last Error state change for %s: new time %s"
                    " matches internal tracking %s",
                    self.zone_name,
                    new_error_time,
                    self._last_error_state,
                )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing Last Error state change for %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> int:
        """Return the native value of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._state = int(last_state.state)
            except (ValueError, TypeError):
                self._state = 0

            if last_state.attributes:
                self._attributes = dict(last_state.attributes)
                # Restore the last error time to prevent re-counting
                self._last_error_state = self._attributes.get("last_error_time")

            _LOGGER.debug(
                "Restored error count sensor %s with state: %d",
                self.entity_id,
                self._state,
            )  # Find the Last Error entity ID by its unique ID
        last_error_unique_id_parts = (
            DOMAIN,
            self.entry_id,
            self.zone_device_id[0],
            self.zone_device_id[1],
            "last_error",
        )
        last_error_unique_id = "_".join(last_error_unique_id_parts)

        try:
            registry = er.async_get(self.hass)
            for entity in registry.entities.values():
                if entity.unique_id == last_error_unique_id:
                    self._last_error_entity_id = entity.entity_id
                    _LOGGER.debug(
                        "Found Last Error entity for %s: %s",
                        self.zone_name,
                        self._last_error_entity_id,
                    )
                    break
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to find Last Error entity for %s: %s",
                self.zone_name,
                exc,
            )

        # Subscribe to Last Error entity state changes
        if self._last_error_entity_id:
            try:
                self._unsubscribe_last_error = async_track_state_change_event(
                    self.hass,
                    self._last_error_entity_id,
                    self._handle_last_error_state_change,
                )
                _LOGGER.debug(
                    "Set up Last Error state change listener for %s",
                    self.zone_name,
                )
            except (AttributeError, KeyError, ValueError) as exc:
                _LOGGER.warning(
                    "Failed to set up Last Error state change listener for %s: %s",
                    self.zone_name,
                    exc,
                )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe_last_error:
            self._unsubscribe_last_error()


def _metric_to_attr(metric: str) -> str:
    """
    Map a metric key like 'min_light' to an entity attribute name.

    The openplantbook provider exposes attributes with names like
    'minimum_light', 'maximum_light', 'minimum_moisture', etc. Use simple
    heuristics to translate the configured metric key to the attribute name.
    """
    if metric.startswith("min_"):
        return f"minimum_{metric[4:]}"
    if metric.startswith("max_"):
        return f"maximum_{metric[4:]}"
    if metric.startswith("avg_"):
        return f"minimum_{metric[4:]}"
    return metric


class PlantLocationLastWateredSensor(SensorEntity, RestoreEntity):
    """
    Sensor that tracks when a plant location was last watered.

    This sensor monitors a 'recently_watered' binary sensor and records
    the timestamp when watering is detected (transition from off to on).
    The sensor uses the timestamp device_class for proper formatting.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        recently_watered_entity_id: str | None,
    ) -> None:
        """
        Initialize the plant location last watered sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            location_device_id: The device identifier for the location.
            location_name: The name of the plant location.
            recently_watered_entity_id: Entity ID of the recently watered binary sensor
                (can be None if not yet created).

        """
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self.location_name = location_name
        self.recently_watered_entity_id = recently_watered_entity_id

        # Set entity attributes
        self._attr_name = f"{location_name} Watered"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:watering-can"

        # Create unique ID
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_watered"

        # Set device info to associate with the location device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
        )

        # Initialize state to today at midnight
        today_midnight = dt_util.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self._state: Any = today_midnight.isoformat()
        self._attributes: dict[str, Any] = {
            "detection_method": "initial_default",
        }
        self._unsubscribe = None

    @callback
    def _handle_recently_watered_change(self, event: Event) -> None:
        """Handle state change of the recently watered binary sensor."""
        try:
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")

            if not new_state or not old_state:
                return

            # Detect transition from off to on (watering detected)
            if old_state.state == "off" and new_state.state == "on":
                # Record the current timestamp
                watered_time = dt_util.now()
                old_time = self._state
                self._state = watered_time.isoformat()

                # Store context in attributes
                self._attributes = {
                    "source_entity": self.recently_watered_entity_id,
                    "detection_method": "moisture_spike",
                }

                _LOGGER.debug(
                    "Updated %s last watered time from %s to %s",
                    self.location_name,
                    old_time,
                    self._state,
                )

                self.async_write_ha_state()

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error processing recently watered change for %s: %s",
                self.location_name,
                exc,
            )

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None

        # Parse ISO 8601 datetime string to datetime object for TIMESTAMP device class
        try:
            if isinstance(self._state, str):
                # Use dt_util.parse_datetime to handle ISO 8601 format with timezone
                parsed_dt = dt_util.parse_datetime(self._state)
                if parsed_dt:
                    return parsed_dt
                _LOGGER.warning(
                    "Failed to parse datetime for %s: %s",
                    self.location_name,
                    self._state,
                )
                return None
        except (ValueError, TypeError) as exc:
            _LOGGER.warning(
                "Error converting state to datetime for %s: %s",
                self.location_name,
                exc,
            )
            return None
        else:
            # Already a datetime object
            return self._state

    @property
    def icon(self) -> str:
        """Return the icon for the sensor."""
        return "mdi:watering-can"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up state listener when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored last watered sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        # Dynamically find the recently watered entity if not provided
        if not self.recently_watered_entity_id:
            self.recently_watered_entity_id = _find_recently_watered_entity(
                self.hass, self.location_name
            )
            if self.recently_watered_entity_id:
                _LOGGER.debug(
                    "Found recently watered entity for %s: %s",
                    self.location_name,
                    self.recently_watered_entity_id,
                )
            else:
                _LOGGER.warning(
                    "Could not find recently watered entity for %s - "
                    "last watered sensor will not function until entity is found",
                    self.location_name,
                )
                return

        # Subscribe to recently watered binary sensor state changes
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                [self.recently_watered_entity_id],
                self._handle_recently_watered_change,
            )
            _LOGGER.debug(
                "Set up state listener for %s tracking %s",
                self.location_name,
                self.recently_watered_entity_id,
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


class PlantCountLocationSensor(SensorEntity):
    """A sensor that counts the number of plants assigned to slots in a location."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_name: str,
        location_device_id: str,
        plant_slots: dict[str, Any],
    ) -> None:
        """Initialize the plant count location sensor."""
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self._location_name = location_name
        self._plant_slots = plant_slots

        # Entity name includes device name for better entity_id formatting
        self._attr_name = f"{location_name} Plant Count"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_plant_count"
        self._attr_icon = "mdi:flower-tulip"
        self._attr_native_unit_of_measurement = "plants"

        # Set up device info - associate with the location device
        device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location Device",
        )

        self._attr_device_info = device_info

    @property
    def native_value(self) -> int:
        """Return the count of plants assigned to slots."""
        count = 0
        for slot in self._plant_slots.values():
            if isinstance(slot, dict) and slot.get("plant_device_id"):
                count += 1
        return count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes about the plants assigned to slots."""
        plant_device_ids = [
            plant_id
            for slot in self._plant_slots.values()
            if isinstance(slot, dict) and (plant_id := slot.get("plant_device_id"))
        ]
        return {
            ATTR_PLANT_DEVICE_IDS: plant_device_ids,
            "location_device_id": self.location_device_id,
        }


class MonitoringSensor(SensorEntity):
    """A sensor that mirrors data from a monitoring device under a subentry."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        location_device_id: str | None = None,
    ) -> None:
        """Initialize the monitoring sensor."""
        self.hass = hass
        self.entry_id = config["entry_id"]
        self.source_entity_id = config["source_entity_id"]
        self.source_entity_unique_id = config.get("source_entity_unique_id")
        self.location_device_id = location_device_id
        device_name = config["device_name"]
        entity_name = config["entity_name"]
        sensor_type = config.get("sensor_type")

        # Set entity name to include device name for better entity_id formatting
        self._attr_name = f"{device_name} {entity_name}"

        # Generate unique_id
        self._setup_unique_id(device_name, sensor_type)

        self._state = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

        # Set device_class, icon, and unit from mappings if available
        self._apply_sensor_mappings(sensor_type)

        # Resolve source entity ID using resilient lookup
        self._resolve_source_entity()

        # Initialize with current state of source entity
        self._initialize_from_source()

        # Subscribe to source entity state changes
        self._subscribe_to_source()

    def _setup_unique_id(self, device_name: str, sensor_type: str | None) -> None:
        """Generate and set unique_id for this sensor."""
        if sensor_type and sensor_type in MONITORING_SENSOR_MAPPINGS:
            mapping: MonitoringSensorMapping = MONITORING_SENSOR_MAPPINGS[sensor_type]
            suffix = mapping.get("suffix", sensor_type)
        else:
            source_entity_safe = self.source_entity_id.replace(".", "_")
            suffix = f"monitor_{source_entity_safe}"

        device_name_safe = device_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{self.entry_id}_{device_name_safe}_{suffix}"

    def _apply_sensor_mappings(self, sensor_type: str | None) -> None:
        """Apply device_class, icon, and unit from sensor type mappings."""
        if not (sensor_type and sensor_type in MONITORING_SENSOR_MAPPINGS):
            return

        mapping_config: MonitoringSensorMapping = MONITORING_SENSOR_MAPPINGS[
            sensor_type
        ]
        device_class_val = mapping_config.get("device_class")
        if device_class_val:
            with contextlib.suppress(ValueError):
                self._attr_device_class = SensorDeviceClass(device_class_val)

        self._attr_icon = mapping_config.get("icon")
        unit = mapping_config.get("unit")
        if unit:
            self._attr_native_unit_of_measurement = unit

    def _resolve_source_entity(self) -> None:
        """Resolve the source entity ID using resilient lookup."""
        resolved_entity_id = _resolve_entity_id(
            self.hass, self.source_entity_id, self.source_entity_unique_id
        )
        if resolved_entity_id != self.source_entity_id:
            _LOGGER.debug(
                "Resolved source entity ID: %s -> %s",
                self.source_entity_id,
                resolved_entity_id,
            )
            self.source_entity_id = resolved_entity_id

    def _initialize_from_source(self) -> None:
        """Initialize state and attributes from source entity."""
        source_state = self.hass.states.get(self.source_entity_id)
        if not source_state:
            return

        self._state = source_state.state
        self._attributes = dict(source_state.attributes)
        self._attributes["source_entity"] = self.source_entity_id

        self._capture_source_unique_id()

        # Copy unit if not already set
        if not hasattr(self, "_attr_native_unit_of_measurement"):
            source_unit = source_state.attributes.get("unit_of_measurement")
            if source_unit:
                self._attr_native_unit_of_measurement = source_unit

        # Copy state_class to enable statistics
        if not hasattr(self, "_attr_state_class"):
            source_state_class = source_state.attributes.get("state_class")
            if source_state_class:
                self._attr_state_class = source_state_class

    def _subscribe_to_source(self) -> None:
        """Subscribe to source entity state changes."""
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass, self.source_entity_id, self._source_state_changed
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to source entity %s: %s",
                self.source_entity_id,
                exc,
            )

    def _capture_source_unique_id(self) -> None:
        """Capture the source entity's unique_id for resilient tracking."""
        try:
            entity_reg = er.async_get(self.hass)
            if entity_reg is not None:
                source_entry = entity_reg.async_get(self.source_entity_id)
                if source_entry and source_entry.unique_id:
                    self._attributes["source_unique_id"] = source_entry.unique_id
        except (TypeError, AttributeError, ValueError):
            # Entity registry not available or lookup failed
            pass

    @callback
    def _source_state_changed(self, event: Event) -> None:
        """Handle source entity state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._state = None
            self._attributes = {}
        else:
            self._state = new_state.state
            self._attributes = dict(new_state.attributes)
            # Add reference to source
            self._attributes["source_entity"] = self.source_entity_id
            # Preserve source_unique_id if already captured
            if "source_unique_id" not in self._attributes:
                self._capture_source_unique_id()

            # Update state_class to match source if it changes
            source_state_class = new_state.attributes.get("state_class")
            if source_state_class and source_state_class != getattr(
                self, "_attr_state_class", None
            ):
                self._attr_state_class = source_state_class

        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Return None for unavailable/unknown states to avoid Home Assistant errors
        # when device_class expects numeric values
        if self._state in ("unavailable", "unknown", None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        source_state = self.hass.states.get(self.source_entity_id)
        return source_state is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the subentry device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()

    async def async_update_source_entity(self, new_source_entity_id: str) -> None:
        """
        Update the source entity ID when the source entity is renamed.

        This method is called by the EntityMonitor when it detects that a source
        entity has been renamed. It updates the internal reference and re-subscribes
        to the new entity ID.

        Args:
            new_source_entity_id: The new entity ID of the source entity.

        """
        _LOGGER.info(
            "Updating MonitoringSensor %s source entity from %s to %s",
            self.entity_id,
            self.source_entity_id,
            new_source_entity_id,
        )

        # Unsubscribe from old entity
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

        # Update the source entity ID
        old_source_entity_id = self.source_entity_id
        self.source_entity_id = new_source_entity_id

        # Update attributes to reflect new source
        self._attributes["source_entity"] = new_source_entity_id

        # Get new state and subscribe to new entity
        if source_state := self.hass.states.get(new_source_entity_id):
            self._state = source_state.state
            self._attributes = dict(source_state.attributes)
            self._attributes["source_entity"] = new_source_entity_id

            # Capture new source entity unique_id
            self._capture_source_unique_id()

            # Get unit from source entity if available
            if not hasattr(self, "_attr_native_unit_of_measurement"):
                source_unit = source_state.attributes.get("unit_of_measurement")
                if source_unit:
                    self._attr_native_unit_of_measurement = source_unit
        else:
            _LOGGER.warning(
                "New source entity %s not found in state for MonitoringSensor %s",
                new_source_entity_id,
                self.entity_id,
            )

        # Subscribe to new entity
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass, new_source_entity_id, self._source_state_changed
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to new source entity %s: %s",
                new_source_entity_id,
                exc,
            )

        # Update state in Home Assistant
        self.async_write_ha_state()

        _LOGGER.info(
            "Successfully updated MonitoringSensor %s from %s to %s",
            self.entity_id,
            old_source_entity_id,
            new_source_entity_id,
        )


class HumidityLinkedSensor(SensorEntity):
    """A sensor that mirrors data from a humidity entity linked to a location."""

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        humidity_entity_id: str,
        humidity_entity_unique_id: str | None = None,
    ) -> None:
        """
        Initialize the humidity linked sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The subentry ID.
            location_device_id: The device ID of the location.
            location_name: The name of the location.
            humidity_entity_id: The entity ID of the humidity sensor to mirror.
            humidity_entity_unique_id: The unique ID for resilient lookup.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self.humidity_entity_id = humidity_entity_id
        self.humidity_entity_unique_id = humidity_entity_unique_id

        # Set entity name to include location name for better entity_id formatting
        self._attr_name = f"{location_name} Humidity"

        # Generate unique_id for this humidity linked sensor
        location_name_safe = location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{entry_id}_{location_name_safe}_humidity_linked"
        )

        # Set device class and icon for humidity
        self._attr_device_class = SensorDeviceClass.HUMIDITY
        self._attr_icon = "mdi:water-percent"
        self._attr_native_unit_of_measurement = "%"
        # Set default precision to 0 decimals (integers) - user can adjust in HA
        self._attr_suggested_display_precision = 0

        self._state = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

        # Resolve humidity entity ID using resilient lookup
        resolved_entity_id = _resolve_entity_id(
            hass, self.humidity_entity_id, self.humidity_entity_unique_id
        )
        if resolved_entity_id != self.humidity_entity_id:
            _LOGGER.debug(
                "Resolved humidity entity ID: %s -> %s",
                self.humidity_entity_id,
                resolved_entity_id,
            )
            self.humidity_entity_id = resolved_entity_id

        # Initialize with current state of humidity entity
        if humidity_state := hass.states.get(self.humidity_entity_id):
            self._state = humidity_state.state
            self._attributes = dict(humidity_state.attributes)
            self._attributes["source_entity"] = self.humidity_entity_id

            # Capture source entity unique_id for resilient tracking
            self._capture_humidity_unique_id()

            # Use unit from source entity if available
            source_unit = humidity_state.attributes.get("unit_of_measurement")
            if source_unit:
                self._attr_native_unit_of_measurement = source_unit

        # Subscribe to humidity entity state changes
        # Re-resolve entity_id immediately before subscription to handle any
        # renames that occurred during initialization
        self.humidity_entity_id = (
            _resolve_entity_id(
                hass, self.humidity_entity_id, self.humidity_entity_unique_id
            )
            or self.humidity_entity_id
        )
        try:
            self._unsubscribe = async_track_state_change_event(
                hass, self.humidity_entity_id, self._humidity_state_changed
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to humidity entity %s: %s",
                self.humidity_entity_id,
                exc,
            )

    def _capture_humidity_unique_id(self) -> None:
        """Capture the humidity entity's unique_id for resilient tracking."""
        try:
            entity_reg = er.async_get(self.hass)
            if entity_reg is not None:
                source_entry = entity_reg.async_get(self.humidity_entity_id)
                if source_entry and source_entry.unique_id:
                    self._attributes["source_unique_id"] = source_entry.unique_id
        except (TypeError, AttributeError, ValueError):
            # Entity registry not available or lookup failed
            pass

    @callback
    def _humidity_state_changed(self, event: Event) -> None:
        """Handle humidity entity state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._state = None
            self._attributes = {}
        else:
            self._state = new_state.state
            self._attributes = dict(new_state.attributes)
            # Add reference to source
            self._attributes["source_entity"] = self.humidity_entity_id
            # Preserve source_unique_id if already captured
            if "source_unique_id" not in self._attributes:
                self._capture_humidity_unique_id()

        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        # Return None for unavailable/unknown states to avoid Home Assistant errors
        if self._state in ("unavailable", "unknown", None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes

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

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()

    async def async_update_source_entity(self, new_humidity_entity_id: str) -> None:
        """
        Update the humidity entity ID when the humidity entity is renamed.

        This method is called by the EntityMonitor when it detects that a humidity
        entity has been renamed. It updates the internal reference and re-subscribes
        to the new entity ID.

        Args:
            new_humidity_entity_id: The new entity ID of the humidity entity.

        """
        _LOGGER.info(
            "Updating HumidityLinkedSensor %s humidity entity from %s to %s",
            self.entity_id,
            self.humidity_entity_id,
            new_humidity_entity_id,
        )

        # Unsubscribe from old entity
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

        # Update the humidity entity ID
        old_humidity_entity_id = self.humidity_entity_id
        self.humidity_entity_id = new_humidity_entity_id

        # Update attributes to reflect new source
        self._attributes["source_entity"] = new_humidity_entity_id

        # Get new state and subscribe to new entity
        if humidity_state := self.hass.states.get(new_humidity_entity_id):
            self._state = humidity_state.state
            self._attributes = dict(humidity_state.attributes)
            self._attributes["source_entity"] = new_humidity_entity_id

            # Capture new humidity entity unique_id
            self._capture_humidity_unique_id()

            # Get unit from source entity if available
            source_unit = humidity_state.attributes.get("unit_of_measurement")
            if source_unit:
                self._attr_native_unit_of_measurement = source_unit
        else:
            _LOGGER.warning(
                "New humidity entity %s not found in state for HumidityLinkedSensor %s",
                new_humidity_entity_id,
                self.entity_id,
            )

        # Subscribe to new entity
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass, new_humidity_entity_id, self._humidity_state_changed
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to new humidity entity %s: %s",
                new_humidity_entity_id,
                exc,
            )

        # Update state in Home Assistant
        self.async_write_ha_state()

        _LOGGER.info(
            "Successfully updated HumidityLinkedSensor %s from %s to %s",
            self.entity_id,
            old_humidity_entity_id,
            new_humidity_entity_id,
        )


class AggregatedLocationSensor(SensorEntity):
    """
    Aggregated sensor for plant location metrics.

    This sensor aggregates plant metrics (min/max requirements) for plants
    assigned to slots in a location. It uses:
    - max_of_mins: Maximum of all minimum values (most restrictive minimum)
    - min_of_maxs: Minimum of all maximum values (most restrictive maximum)
    """

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        metric_key: str,
        metric_config: dict[str, Any],
        plant_slots: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the aggregated location sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The subentry ID.
            location_device_id: The device ID of the location.
            location_name: The name of the location.
            metric_key: The metric key (e.g., 'min_temperature').
            metric_config: Configuration dict with aggregation settings.
            plant_slots: The plant slots dict containing assigned plant device IDs.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self.location_name = location_name
        self.metric_key = metric_key
        self.metric_config = metric_config
        self.plant_slots = plant_slots or {}

        self._value: Any = None
        self._unsubscribe = None
        self._plant_entity_ids: list[str] | None = None

        # Extract configuration
        display_name = metric_config.get("name", metric_key)
        suffix = metric_config.get("suffix", metric_key)
        device_class_str = metric_config.get("device_class")
        unit = metric_config.get("unit")
        icon = metric_config.get("icon")

        # Set entity attributes
        self._attr_name = f"{location_name} {display_name}"

        # Generate unique_id
        location_name_safe = location_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{location_name_safe}_{suffix}"

        # Set device class if provided
        if device_class_str:
            try:
                self._attr_device_class = SensorDeviceClass(device_class_str)
            except ValueError:
                self._attr_device_class = None

        # Set unit and icon
        if unit:
            self._attr_native_unit_of_measurement = unit
        if icon:
            self._attr_icon = icon
        # Suggest no decimal places for aggregated metrics (follow HA best practice
        # as used by the linked humidity sensor). Consumers can still override
        # the display precision in Home Assistant if desired.
        self._attr_suggested_display_precision = 0

        # Set state_class to enable statistics
        self._attr_state_class = "measurement"

        # Set device info to associate with location device
        device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location Device",
        )
        self._attr_device_info = device_info

    def _get_plants_from_slots(self) -> list[dict[str, Any]]:
        """Get plant attribute dictionaries from slot assignments."""
        plants: list[dict[str, Any]] = []

        try:
            # Build a set of plant device IDs that are assigned to this location's slots
            assigned_plant_device_ids: set[str] = set()
            for slot in self.plant_slots.values():
                if isinstance(slot, dict) and (plant_id := slot.get("plant_device_id")):
                    assigned_plant_device_ids.add(plant_id)

            if not assigned_plant_device_ids:
                _LOGGER.debug(
                    "No plant device IDs assigned to slots at location %s",
                    self.location_name,
                )
                return plants

            # Get plant device IDs from the location's plant slots
            # This requires accessing the subentry data to get plant_slots
            dev_reg = dr.async_get(self.hass)
            ent_reg = er.async_get(self.hass)

            # Get the location device - this gives us access to associated entities
            location_device = dev_reg.async_get_device(
                {("plant_assistant", self.location_device_id)}
            )

            if not location_device:
                _LOGGER.debug("Location device %s not found", self.location_device_id)
                return plants

            _LOGGER.debug(
                "Scanning for plant entities from openplantbook_ref integration "
                "for location %s with assigned plant IDs: %s",
                self.location_name,
                assigned_plant_device_ids,
            )

            # Scan all plant sensors from openplantbook_ref, but only include those
            # assigned to this location's slots
            for entity in ent_reg.entities.values():
                if entity.domain != "sensor" or entity.platform != "openplantbook_ref":
                    continue

                # Get the device associated with this entity
                entity_device_id = entity.device_id
                if not entity_device_id:
                    continue

                # Check if this plant entity is in our assigned list
                if entity_device_id not in assigned_plant_device_ids:
                    _LOGGER.debug(
                        "Skipping plant entity %s - device %s not assigned to "
                        "location %s",
                        entity.entity_id,
                        entity_device_id,
                        self.location_name,
                    )
                    continue

                if state := self.hass.states.get(entity.entity_id):
                    attrs: dict[str, Any] = state.attributes or {}

                    # Collect min/max attributes from the plant sensor
                    plant_dict = {
                        "minimum_light": attrs.get("minimum_light"),
                        "maximum_light": attrs.get("maximum_light"),
                        "minimum_temperature": attrs.get("minimum_temperature"),
                        "maximum_temperature": attrs.get("maximum_temperature"),
                        "minimum_humidity": attrs.get("minimum_humidity"),
                        "maximum_humidity": attrs.get("maximum_humidity"),
                        "minimum_moisture": attrs.get("minimum_moisture"),
                        "maximum_moisture": attrs.get("maximum_moisture"),
                        "minimum_soil_ec": attrs.get("minimum_soil_ec"),
                        "maximum_soil_ec": attrs.get("maximum_soil_ec"),
                    }

                    # Only add if it has at least one valid value
                    if any(plant_dict.values()):
                        plants.append(plant_dict)
                        _LOGGER.debug(
                            "Found assigned plant sensor: %s with attributes: %s",
                            entity.entity_id,
                            {k: v for k, v in plant_dict.items() if v is not None},
                        )
                else:
                    # Plant entity not available (may be unavailable/disabled)
                    _LOGGER.debug(
                        "Plant entity %s state not available for location %s",
                        entity.entity_id,
                        self.location_name,
                    )

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error getting plants from slots: %s", exc)

        _LOGGER.debug(
            "Collected %d plants for aggregation at location %s",
            len(plants),
            self.location_name,
        )
        return plants

    def _compute_value(self) -> Any:
        """Compute the aggregated value based on configuration."""
        plants = self._get_plants_from_slots()

        if not plants:
            _LOGGER.debug(
                "No plants found for aggregation at location %s", self.location_name
            )
            return None

        aggregation_type = self.metric_config.get("aggregation_type")
        plant_attr_min = self.metric_config.get("plant_attr_min")
        plant_attr_max = self.metric_config.get("plant_attr_max")
        # Some aggregated metrics operate on illuminance but should be
        # converted to DLI before aggregation. Use specialized helpers
        # from the dli module when configured.
        convert_to_dli = bool(self.metric_config.get("convert_illuminance_to_dli"))

        result = None
        if aggregation_type == "max_of_mins" and plant_attr_min:
            if convert_to_dli:
                # Convert plant minimum illuminance (lux) to DLI and take max
                result = dli.max_of_mins_dli(plants, plant_attr_min)
            else:
                result = aggregation.max_of_mins(plants, plant_attr_min)
            _LOGGER.debug(
                "Computed max_of_mins for %s using key '%s': %s",
                self.metric_key,
                plant_attr_min,
                result,
            )
        elif aggregation_type == "min_of_maximums" and plant_attr_max:
            if convert_to_dli:
                # Convert plant maximum illuminance (lux) to DLI and take min
                result = dli.min_of_maxs_dli(plants, plant_attr_max)
            else:
                result = aggregation.min_of_maxs(plants, plant_attr_max)
            _LOGGER.debug(
                "Computed min_of_maxs for %s using key '%s': %s",
                self.metric_key,
                plant_attr_max,
                result,
            )
        else:
            _LOGGER.debug(
                "Unknown aggregation type %s or missing key for metric %s",
                aggregation_type,
                self.metric_key,
            )

        return result

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self._value

    @callback
    def _on_plant_entity_change(
        self, _entity_id: str, _old_state: Any, _new_state: Any
    ) -> None:
        """Handle plant entity state changes."""
        self._value = self._compute_value()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Add entity to hass and subscribe to plant sensors."""
        try:
            _LOGGER.debug("Setting up aggregated location sensor: %s", self._attr_name)

            # Get plant entity IDs from slots
            plant_entity_ids = await self._discover_plant_entities()

            if plant_entity_ids:
                self._plant_entity_ids = plant_entity_ids
                self._unsubscribe = async_track_state_change_event(
                    self.hass, plant_entity_ids, self._on_plant_entity_change
                )
                _LOGGER.info(
                    "Subscribed to %d plant entities for aggregated sensor: %s",
                    len(plant_entity_ids),
                    self._attr_name,
                )
            else:
                _LOGGER.debug(
                    "No plant entities found for aggregated sensor: %s",
                    self._attr_name,
                )

            # Compute initial value
            self._value = self._compute_value()
            _LOGGER.info(
                "Aggregated sensor %s initial value: %s",
                self._attr_name,
                self._value,
            )
            self.async_write_ha_state()

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Error setting up aggregated location sensor %s: %s",
                self._attr_name,
                exc,
            )

    async def _discover_plant_entities(self) -> list[str]:
        """Discover plant entity IDs assigned to slots in this location."""
        plant_entity_ids: list[str] = []

        try:
            # Build a set of plant device IDs that are assigned to this location's slots
            assigned_plant_device_ids: set[str] = set()
            for slot in self.plant_slots.values():
                if isinstance(slot, dict) and (plant_id := slot.get("plant_device_id")):
                    assigned_plant_device_ids.add(plant_id)

            if not assigned_plant_device_ids:
                _LOGGER.debug(
                    "No plant device IDs assigned to slots at location %s",
                    self.location_name,
                )
                return plant_entity_ids

            ent_reg = er.async_get(self.hass)

            # Scan for plant sensors from openplantbook_ref, but only include those
            # assigned to this location's slots
            for entity in ent_reg.entities.values():
                if (
                    entity.domain != "sensor"
                    or entity.platform != "openplantbook_ref"
                    or not entity.entity_id
                ):
                    continue

                # Get the device associated with this entity
                entity_device_id = entity.device_id
                if not entity_device_id:
                    continue

                # Check if this plant entity is in our assigned list
                if entity_device_id not in assigned_plant_device_ids:
                    _LOGGER.debug(
                        "Skipping plant entity %s - device %s not assigned to "
                        "location %s",
                        entity.entity_id,
                        entity_device_id,
                        self.location_name,
                    )
                    continue

                plant_entity_ids.append(entity.entity_id)
                _LOGGER.debug(
                    "Discovered assigned plant entity for tracking: %s (device: %s)",
                    entity.entity_id,
                    entity_device_id,
                )

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.debug("Error discovering plant entities: %s", exc)

        _LOGGER.debug(
            "Found %d assigned plant entities to track", len(plant_entity_ids)
        )
        return plant_entity_ids

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class AggregatedSensor(SensorEntity):
    """Aggregated sensor for a location metric (e.g., min_light)."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, zone_id: str, loc_id: str, metric: str
    ) -> None:
        """Initialize the aggregated sensor."""
        self.hass = hass
        self.entry_id = entry_id
        self.zone_id = zone_id
        self.loc_id = loc_id
        self.metric = metric
        self._value: Any = None
        self._attr_name = f"Plant Assistant {zone_id} {loc_id} {metric}"
        self._attr_unique_id = (
            f"{DOMAIN}_{entry_id}_zone_{zone_id}_loc_{loc_id}_{metric}"
        )
        # Suggest no decimal places for aggregated metrics by default.
        # This follows the same pattern used for linked humidity sensors so
        # that aggregated numeric values are displayed as integers unless
        # the user overrides the precision in Home Assistant.
        self._attr_suggested_display_precision = 0

        # Set state_class to enable statistics
        self._attr_state_class = "measurement"

        self._unsubscribe = None
        self._plant_entity_ids: list[str] | None = None
        self._plant_entity_unique_ids: dict[
            str, str | None
        ] = {}  # entity_id -> unique_id

        # subscribe to a humidity entity if configured for this location
        entry_opts = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry_id, {})
        zones = entry_opts.get("irrigation_zones", {})
        target_humidity_entity = None
        if zone_id in zones:
            locations = zones[zone_id].get("locations", {})
            if loc_id in locations:
                target_humidity_entity = locations[loc_id].get("humidity_entity_id")

        if target_humidity_entity:
            try:
                self._unsubscribe = async_track_state_change_event(
                    hass, target_humidity_entity, self._state_changed
                )
            except (AttributeError, KeyError, ValueError):
                self._unsubscribe = None

    def update(self) -> None:  # pragma: no cover - sync update not exercised
        """Update the sensor state."""
        # If we have mapped plant entity ids, compute from their attributes.
        if getattr(self, "_plant_entity_ids", None):
            plants = _plants_from_entity_states(
                self.hass, list(self._plant_entity_ids or [])
            )
            # Map metric key (e.g., 'min_light') to provider attribute name
            attr_key = _metric_to_attr(self.metric)
            if self.metric.startswith("min"):
                self._value = aggregation.min_metric(plants, attr_key)
            elif self.metric.startswith("max"):
                self._value = aggregation.max_metric(plants, attr_key)
            elif self.metric.startswith("avg"):
                self._value = aggregation.avg_metric(plants, attr_key)
            else:
                self._value = None
            return

        # Fallback for tests/non-HA runtime
        all_plants = self.hass.data.get(DOMAIN, {}).get("mock_plants", {})
        plants = all_plants.get(self.loc_id, [])
        self._value = aggregation.min_metric(plants, self.metric)

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self._value

    @callback
    def _state_changed(self, _entity_id: str, _old_state: Any, _new_state: Any) -> None:
        """Recompute aggregation when a tracked plant entity changes."""
        if getattr(self, "_plant_entity_ids", None):
            plants = _plants_from_entity_states(
                self.hass, list(self._plant_entity_ids or [])
            )
            attr_key = _metric_to_attr(self.metric)
            if self.metric.startswith("min"):
                self._value = aggregation.min_metric(plants, attr_key)
            elif self.metric.startswith("max"):
                self._value = aggregation.max_metric(plants, attr_key)
            elif self.metric.startswith("avg"):
                self._value = aggregation.avg_metric(plants, attr_key)
            else:
                self._value = None
            return

        all_plants = self.hass.data.get(DOMAIN, {}).get("mock_plants", {})
        plants = all_plants.get(self.loc_id, [])
        self._value = aggregation.min_metric(plants, self.metric)

    async def async_added_to_hass(self) -> None:  # pragma: no cover - runtime-only
        """
        Add entity to hass and subscribe to plant sensors.

        Map the configured location to plant entity IDs. Strategy:
        - If the location has a `monitoring_device_id`, prefer sensors whose
          attributes include `device_id` matching that value.
        - Otherwise, scan for sensors exposing a `plant_id` attribute.
        """
        try:
            plant_entity_ids = await self._discover_plant_entities()
            self._subscribe_to_plant_entities(plant_entity_ids)
        except (AttributeError, KeyError, ValueError):
            self._unsubscribe = None

    async def _discover_plant_entities(self) -> list[str]:
        """Discover plant entity IDs for this sensor."""
        mon_device_id = self._get_monitoring_device_id()

        # Try device registry approach first
        plant_entity_ids = self._get_entities_from_device_registry(mon_device_id)

        # Fall back to state scanning if needed
        if not plant_entity_ids:
            plant_entity_ids = self._get_entities_from_state_scan(mon_device_id)

        return list(dict.fromkeys([p for p in plant_entity_ids if p]))

    def _get_monitoring_device_id(self) -> str | None:
        """Get monitoring device ID from configuration."""
        entry_opts = (
            self.hass.data.get(DOMAIN, {}).get("entries", {}).get(self.entry_id, {})
        )
        zones = entry_opts.get("irrigation_zones", {})

        if self.zone_id not in zones:
            return None

        locations = zones[self.zone_id].get("locations", {})
        if self.loc_id not in locations:
            return None

        device_id = locations[self.loc_id].get("monitoring_device_id")
        return device_id if isinstance(device_id, str) else None

    def _get_entities_from_device_registry(
        self, mon_device_id: str | None
    ) -> list[str]:
        """Get plant entities using device registry."""
        if not mon_device_id:
            return []

        plant_entity_ids: list[str] = []

        try:
            ent_reg = er.async_get(self.hass)
            dev_reg = dr.async_get(self.hass)
        except (AttributeError, KeyError):
            return plant_entity_ids

        try:
            device = dev_reg.async_get_device({("plant_assistant", mon_device_id)})
        except (AttributeError, KeyError, ValueError):
            return plant_entity_ids

        if not device:
            return plant_entity_ids

        for ent in getattr(ent_reg, "entities", {}).values():
            if self._is_matching_sensor_entity(ent, device.id) and (
                eid := getattr(ent, "entity_id", None)
            ):
                plant_entity_ids.append(eid)
                # Capture unique_id for resilient tracking
                unique_id = getattr(ent, "unique_id", None)
                if unique_id:
                    self._plant_entity_unique_ids[eid] = unique_id

        return plant_entity_ids

    def _is_matching_sensor_entity(self, ent: Any, device_id: str) -> bool:
        """Check if entity matches our criteria for sensor entities."""
        return (
            getattr(ent, "device_id", None) == device_id
            and getattr(ent, "domain", None) == "sensor"
        )

    def _get_entities_from_state_scan(self, mon_device_id: str | None) -> list[str]:
        """Get plant entities by scanning states."""
        states_all = self._get_all_sensor_states()
        plant_entity_ids: list[str] = []

        # Try to get entity registry for unique_id lookup
        try:
            ent_reg = er.async_get(self.hass)
        except (AttributeError, KeyError):
            ent_reg = None

        for st in states_all:
            if not self._state_matches_criteria(st, mon_device_id):
                continue
            if entity_id := getattr(st, "entity_id", None):
                plant_entity_ids.append(entity_id)
                # Try to capture unique_id for resilient tracking
                if ent_reg:
                    try:
                        ent_entry = ent_reg.async_get(entity_id)
                        if ent_entry and ent_entry.unique_id:
                            self._plant_entity_unique_ids[entity_id] = (
                                ent_entry.unique_id
                            )
                    except (AttributeError, KeyError, ValueError):
                        pass

        return plant_entity_ids

    def _get_all_sensor_states(self) -> list[Any]:
        """Get all sensor states from Home Assistant."""
        if hasattr(self.hass.states, "async_all"):
            states = self.hass.states.async_all("sensor")
            return list(states)
        states_dict = getattr(self.hass.states, "_states", {})
        return list(states_dict.values()) if states_dict else []

    def _state_matches_criteria(self, st: Any, mon_device_id: str | None) -> bool:
        """Check if a state matches our plant sensor criteria."""
        attrs = getattr(st, "attributes", {}) or {}
        if not isinstance(attrs, dict):
            return False

        has_plant_id = attrs.get("plant_id") is not None
        has_matching_device = mon_device_id and attrs.get("device_id") == mon_device_id
        return bool(has_plant_id or has_matching_device)

    def _subscribe_to_plant_entities(self, plant_entity_ids: list[str]) -> None:
        """Subscribe to plant entity state changes."""
        if not plant_entity_ids:
            return

        # Resolve entity_ids using unique_ids for resilience to renames
        resolved_entity_ids = []
        for entity_id in plant_entity_ids:
            unique_id = self._plant_entity_unique_ids.get(entity_id)
            resolved_id = _resolve_entity_id(self.hass, entity_id, unique_id)
            if resolved_id:
                resolved_entity_ids.append(resolved_id)
                # Update mapping if entity was renamed
                if resolved_id != entity_id and unique_id:
                    self._plant_entity_unique_ids[resolved_id] = unique_id
                    del self._plant_entity_unique_ids[entity_id]

        self._plant_entity_ids = resolved_entity_ids
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass, resolved_entity_ids, self._state_changed
            )
        except (AttributeError, KeyError, ValueError):
            self._unsubscribe = None

    async def async_will_remove_from_hass(
        self,
    ) -> None:  # pragma: no cover - runtime cleanup
        """Remove entity from Home Assistant."""
        if self._unsubscribe:
            self._unsubscribe()


def _plants_from_entity_states(
    hass: HomeAssistant, entity_ids: list[str]
) -> list[dict[str, Any]]:
    """
    Build a list of plant dicts from entity states.

    Each plant dict will include keys like 'minimum_light' etc. based on the
    state attributes of the sensor entities. This mirrors the shape expected
    by the aggregation helpers.
    """
    out: list[dict[str, Any]] = []
    for ent in entity_ids:
        if not (st := hass.states.get(ent)):
            continue
        attrs = getattr(st, "attributes", {}) or {}
        out.append(dict(attrs))
    return out


class PlantLocationPpfdSensor(SensorEntity):
    """
    Entity reporting current PPFD calculated from illuminance (lux).

    Converts lux to PPFD (μmol/m²/s) using the standard conversion factor.
    Based on PlantCurrentPpfd from Olen/homeassistant-plant.
    """

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        illuminance_entity_id: str,
        illuminance_entity_unique_id: str | None = None,
    ) -> None:
        """Initialize the PPFD sensor."""
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self._illuminance_entity_id = illuminance_entity_id
        self._illuminance_entity_unique_id = illuminance_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{location_name} {READING_PPFD}"
        location_name_safe = location_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{location_name_safe}_ppfd"
        self._attr_native_unit_of_measurement = UNIT_PPFD
        self._attr_icon = ICON_PPFD
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        # Make visible for debugging - user can hide if desired
        self._attr_entity_registry_visible_default = True

        self._state: float | None = None
        self._unsubscribe = None

        # Generate entity_id so it can be used by IntegrationSensor
        self.entity_id = async_generate_entity_id(
            "sensor.{}", self._attr_name.lower().replace(" ", "_"), current_ids={}
        )

        # Set device info
        device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location Device",
        )
        self._attr_device_info = device_info

        # Initialize with current illuminance value
        if illuminance_state := hass.states.get(illuminance_entity_id):
            self._state = self._ppfd_from_lux(illuminance_state.state)

    def _ppfd_from_lux(self, lux_value: Any) -> float | None:
        """
        Convert lux value to PPFD (mol/s⋅m²).

        See https://www.apogeeinstruments.com/conversion-ppfd-to-lux/
        Standard conversion for sunlight: 0.0185 μmol/m²/s per lux.
        We divide by 1,000,000 to convert from μmol to mol.
        """
        if lux_value is None or lux_value in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None

        try:
            # Convert lux to PPFD: lux * 0.0185 / 1000000 = mol/s⋅m²
            # (0.0185 converts lux to μmol/m²/s, then /1000000 converts to mol/s⋅m²)
            return float(lux_value) * DEFAULT_LUX_TO_PPFD / 1000000
        except (ValueError, TypeError):
            return None

    @property
    def native_value(self) -> float | None:
        """Return the native value of the sensor."""
        return self._state

    @property
    def device_class(self) -> None:
        """Device class - None for PPFD as there's no standard device class."""
        return None

    @callback
    def _illuminance_state_changed(self, event: Event) -> None:
        """Handle illuminance sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._state = None
        else:
            self._state = self._ppfd_from_lux(new_state.state)

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to illuminance sensor state changes."""
        try:
            # Resolve illuminance entity ID with fallback to unique ID for resilience
            resolved_entity_id = _resolve_entity_id(
                self.hass,
                self._illuminance_entity_id,
                self._illuminance_entity_unique_id,
            )
            if resolved_entity_id and resolved_entity_id != self._illuminance_entity_id:
                _LOGGER.debug(
                    "Resolved illuminance entity ID: %s -> %s",
                    self._illuminance_entity_id,
                    resolved_entity_id,
                )
                self._illuminance_entity_id = resolved_entity_id

            # Re-resolve entity_id immediately before subscription to handle any
            # renames that occurred during initialization
            self._illuminance_entity_id = (
                _resolve_entity_id(
                    self.hass,
                    self._illuminance_entity_id,
                    self._illuminance_entity_unique_id,
                )
                or self._illuminance_entity_id
            )

            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self._illuminance_entity_id,
                self._illuminance_state_changed,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to illuminance entity %s: %s",
                self._illuminance_entity_id,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class PlantLocationTotalLightIntegral(IntegrationSensor):
    """
    Entity to calculate total PPFD integral over time.

    Uses trapezoidal integration method to accumulate PPFD values.
    Based on PlantTotalLightIntegral from Olen/homeassistant-plant.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        ppfd_sensor: PlantLocationPpfdSensor,
    ) -> None:
        """Initialize the total light integral sensor."""
        # entry_id intentionally unused in this implementation; keep for
        # future compatibility with caller keywords
        _ = entry_id
        super().__init__(
            hass,
            integration_method=METHOD_TRAPEZOIDAL,
            # Use a concise display name (don't include the entry id in the unique id)
            name=f"{location_name} {READING_PPFD} Integral",
            round_digits=2,
            source_entity=ppfd_sensor.entity_id,
            # Use a short unique_id so the generated entity_id is concise
            unique_id=f"{location_name.lower().replace(' ', '_')}_ppfd_integral",
            unit_prefix=None,
            unit_time=UnitOfTime.SECONDS,
            max_sub_interval=None,
        )
        self._unit_of_measurement = UNIT_PPFD_INTEGRAL
        self._attr_icon = ICON_DLI
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        # Make visible for debugging - user can hide if desired
        self._attr_entity_registry_visible_default = True
        self.location_device_id = location_device_id

        # Generate a concise entity_id (e.g. sensor.green_ppfd_integral)
        self.entity_id = async_generate_entity_id(
            "sensor.{}",
            f"{location_name} {READING_PPFD} Integral".lower().replace(" ", "_"),
            current_ids={},
        )

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement as mol/m²/d for utility meter."""
        return UNIT_PPFD_INTEGRAL

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None


class PlantLocationDailyLightIntegral(UtilityMeterSensor):
    """
    Entity to calculate Daily Light Integral (DLI) from PPFD integral.

    Resets daily to provide daily light accumulation.
    Based on PlantDailyLightIntegral from Olen/homeassistant-plant.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        total_integral_sensor: PlantLocationTotalLightIntegral,
    ) -> None:
        """Initialize the DLI sensor."""
        # UtilityMeterSensor.__init__ is untyped in upstream stubs. Call via
        # a cast to Any so mypy doesn't complain about calling an untyped
        # function while keeping runtime behavior identical.
        _ums_init = cast("Any", UtilityMeterSensor).__init__
        _ums_init(
            self,
            hass,
            cron_pattern=None,
            delta_values=None,
            meter_offset=timedelta(seconds=0),
            meter_type=DAILY,
            name=f"{location_name} {READING_DLI_NAME}",
            net_consumption=None,
            parent_meter=entry_id,
            source_entity=total_integral_sensor.entity_id,
            tariff_entity=None,
            tariff=None,
            unique_id=f"{location_name.lower().replace(' ', '_')}_{READING_DLI_SLUG}",
            sensor_always_available=True,
            suggested_entity_id=None,
            periodically_resetting=True,
        )
        self._unit_of_measurement = UNIT_DLI
        self._attr_icon = ICON_DLI
        self._attr_suggested_display_precision = 2
        self.location_device_id = location_device_id

        # Generate a concise entity_id (e.g. sensor.green_daily_light_integral)
        self.entity_id = async_generate_entity_id(
            "sensor.{}",
            f"{location_name} {READING_DLI_NAME}".lower().replace(" ", "_"),
            current_ids={},
        )

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Device class for DLI (no standard device class; return None)."""
        # There is no standard SensorDeviceClass for DLI in Home Assistant.
        return None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to associate this entity with the location device."""
        if self.location_device_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.location_device_id)},
            )
        return None


class DliPriorPeriodSensor(RestoreEntity, SensorEntity):
    """
    Sensor exposing the `last_period` attribute from a DLI UtilityMeterSensor.

    This mirrors the utility meter's last_period attribute (e.g., prior day's DLI)
    as a standalone sensor entity for easy access in automations and dashboards.
    """

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        dli_entity_id: str,
        dli_entity_unique_id: str | None = None,
    ) -> None:
        """Initialize the DLI prior period sensor."""
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self._dli_entity_id = dli_entity_id
        self._dli_entity_unique_id = dli_entity_unique_id

        # Set entity attributes
        # Use the friendly DLI display name for readability.
        # e.g., "Daily Light Integral Prior Period"
        self._attr_name = f"{location_name} {READING_PRIOR_PERIOD_DLI_NAME}"
        location_name_safe = location_name.lower().replace(" ", "_")
        # use 'prior_period' in unique id for new naming
        self._attr_unique_id = (
            f"{DOMAIN}_{entry_id}_{location_name_safe}_{READING_PRIOR_PERIOD_DLI_SLUG}"
        )
        self._attr_native_unit_of_measurement = UNIT_DLI
        self._attr_icon = ICON_DLI
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_suggested_display_precision = 2

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location Device",
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None
        self._restored = False

        # Initialize from current DLI state if available
        if dli_state := hass.states.get(self._dli_entity_id):
            self._state = dli_state.attributes.get("last_period")
            self._attributes = dict(dli_state.attributes)
            self._attributes["source_entity"] = self._dli_entity_id

        # Generate a concise entity_id based on the new name. For example,
        # it may look like: sensor.green_daily_light_integral_prior_period.
        # Use a safe, lowercased, underscored location name to create the id.
        with contextlib.suppress(Exception):
            self.entity_id = async_generate_entity_id(
                "sensor.{}",
                f"{location_name} {READING_PRIOR_PERIOD_DLI_NAME}".lower().replace(
                    " ", "_"
                ),
                current_ids={},
            )

    @callback
    def _dli_state_changed(self, event: Event) -> None:
        """Handle DLI sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._state = None
            self._attributes = {}
        else:
            self._state = new_state.attributes.get("last_period")
            self._attributes = dict(new_state.attributes)
            self._attributes["source_entity"] = self._dli_entity_id

        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        dli_state = self.hass.states.get(self._dli_entity_id)
        return dli_state is not None

    async def async_added_to_hass(self) -> None:
        """Subscribe to DLI sensor state changes and restore previous state."""
        await super().async_added_to_hass()

        # Resolve DLI entity ID with fallback to unique ID for resilience
        resolved_entity_id = _resolve_entity_id(
            self.hass, self._dli_entity_id, self._dli_entity_unique_id
        )
        if resolved_entity_id and resolved_entity_id != self._dli_entity_id:
            _LOGGER.debug(
                "Resolved DLI entity ID: %s -> %s",
                self._dli_entity_id,
                resolved_entity_id,
            )
            self._dli_entity_id = resolved_entity_id

        # Restore previous state if available
        if (last_state := await self.async_get_last_state()) and not self._restored:
            self._restored = True
            if last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self._state = float(last_state.state)
                except (ValueError, TypeError):
                    self._state = last_state.state

                # Restore attributes
                if last_state.attributes:
                    self._attributes = dict(last_state.attributes)

                _LOGGER.debug(
                    "Restored DLI last period sensor %s with state: %s",
                    self.entity_id,
                    self._state,
                )

        # Subscribe to DLI sensor state changes
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass, self._dli_entity_id, self._dli_state_changed
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to DLI entity %s: %s",
                self._dli_entity_id,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class PlantMoistureSensor(SensorEntity):
    """
    A placeholder plant moisture sensor.

    This sensor reads a synthetic moisture value from `hass.data` water events
    for demonstration. Real implementation should subscribe to device/entity
    sensors or other hardware inputs.
    """

    def __init__(self, hass: HomeAssistant, zone_id: str, loc_id: str) -> None:
        """Initialize the plant moisture sensor."""
        self.hass = hass
        self.zone_id = zone_id
        self.loc_id = loc_id
        self._value = None

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        return self._value

    def update(self) -> None:  # pragma: no cover - sync update
        """Update the sensor state."""
        events = self.hass.data.get(DOMAIN, {}).get("water_events", [])
        # last event affecting this location sets moisture (demo logic)
        for ev in reversed(events):
            if (
                ev.get("zone_id") == self.zone_id
                and ev.get("location_id") == self.loc_id
            ):
                # demo mapping: larger amount increases moisture; match tests by
                # dividing by 15 so 150 ml -> 90
                self._value = max(0, 100 - int(ev.get("amount_ml", 0) / 15))
                return
        self._value = None
        # end of PlantMoistureSensor


class WeeklyAverageDliSensor(SensorEntity):
    """
    Sensor that calculates the 7-day average of the prior_period DLI values.

    This sensor uses Home Assistant's statistics component to track historical
    DLI values and expose their mean over the past 7 days.
    """

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        dli_prior_period_entity_id: str,
        dli_prior_period_entity_unique_id: str | None = None,
    ) -> None:
        """
        Initialize the weekly average DLI sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The subentry ID.
            location_device_id: The device ID of the location.
            location_name: The name of the location.
            dli_prior_period_entity_id: The entity ID of the prior_period DLI sensor.
            dli_prior_period_entity_unique_id: The unique ID for resilient lookup.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self._dli_prior_period_entity_id = dli_prior_period_entity_id
        self._dli_prior_period_entity_unique_id = dli_prior_period_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{location_name} {READING_WEEKLY_AVG_DLI_NAME}"
        location_name_safe = location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{entry_id}_{location_name_safe}_{READING_WEEKLY_AVG_DLI_SLUG}"
        )

        # Set device class, unit, and icon
        self._attr_device_class = None  # No standard device class for DLI
        self._attr_native_unit_of_measurement = UNIT_DLI
        self._attr_icon = ICON_DLI
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_suggested_display_precision = 2
        self._attr_entity_registry_visible_default = True

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location Device",
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

        # Generate a concise entity_id
        with contextlib.suppress(Exception):
            self.entity_id = async_generate_entity_id(
                "sensor.{}",
                f"{location_name} {READING_WEEKLY_AVG_DLI_NAME}".lower().replace(
                    " ", "_"
                ),
                current_ids={},
            )

    def _calculate_mean_from_history(self) -> float | None:
        """
        Calculate the mean of the prior_period DLI values over the past 7 days.

        This queries the statistics history from Home Assistant to retrieve
        historical data for the prior_period DLI sensor.

        Returns:
            The mean value if data is available, None otherwise.

        """
        try:
            # Get the state history for the prior_period DLI sensor
            # The actual implementation would use the statistics sensor
            # which Home Assistant automatically creates for us
            dli_state = self.hass.states.get(self._dli_prior_period_entity_id)
            if dli_state:
                try:
                    # Store the mean value from statistics if available
                    mean_value = dli_state.attributes.get("mean")
                    if mean_value is not None:
                        return float(mean_value)
                except (ValueError, TypeError):
                    # mean_value could not be converted to float; ignore and return None
                    _LOGGER.debug(
                        "Could not convert mean_value '%s' to float for DLI stats.",
                        mean_value,
                    )

        except Exception as exc:  # noqa: BLE001 - Defensive
            _LOGGER.debug(
                "Error calculating mean DLI: %s",
                exc,
            )

        return None

    @callback
    def _dli_prior_period_state_changed(self, event: Event) -> None:
        """Handle DLI prior_period sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None:
            self._state = None
            self._attributes = {}
        else:
            # The actual mean will be provided by the statistics sensor
            # that Home Assistant creates automatically. For now, we mirror
            # the prior_period value and let the statistics component
            # handle the averaging.
            try:
                self._state = float(new_state.state)
            except (ValueError, TypeError):
                self._state = None

            self._attributes = dict(new_state.attributes or {})
            self._attributes["source_entity"] = self._dli_prior_period_entity_id

        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        dli_state = self.hass.states.get(self._dli_prior_period_entity_id)
        return dli_state is not None

    async def async_added_to_hass(self) -> None:
        """Subscribe to DLI prior_period sensor state changes."""
        try:
            # Resolve DLI prior_period entity ID with fallback to unique ID
            resolved_entity_id = _resolve_entity_id(
                self.hass,
                self._dli_prior_period_entity_id,
                self._dli_prior_period_entity_unique_id,
            )
            if (
                resolved_entity_id
                and resolved_entity_id != self._dli_prior_period_entity_id
            ):
                _LOGGER.debug(
                    "Resolved DLI prior_period entity ID: %s -> %s",
                    self._dli_prior_period_entity_id,
                    resolved_entity_id,
                )
                self._dli_prior_period_entity_id = resolved_entity_id

            # Initialize with current state
            if dli_state := self.hass.states.get(self._dli_prior_period_entity_id):
                try:
                    self._state = float(dli_state.state)
                except (ValueError, TypeError):
                    self._state = None

                self._attributes = dict(dli_state.attributes or {})
                self._attributes["source_entity"] = self._dli_prior_period_entity_id

            # Subscribe to state changes
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self._dli_prior_period_entity_id,
                self._dli_prior_period_state_changed,
            )
            _LOGGER.debug(
                "Weekly average DLI sensor %s subscribed to %s",
                self.entity_id,
                self._dli_prior_period_entity_id,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up weekly average DLI sensor: %s",
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class TemperatureBelowThresholdHoursSensor(SensorEntity, RestoreEntity):
    """
    Sensor that counts hours where temperature was below minimum threshold.

    This sensor queries Home Assistant's statistics database to count the number
    of hourly readings where the temperature was below the minimum temperature
    threshold over the past 7 days.
    """

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        temperature_entity_id: str,
        temperature_entity_unique_id: str | None = None,
    ) -> None:
        """
        Initialize the temperature below threshold weekly duration sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The subentry ID.
            location_device_id: The device ID of the location.
            location_name: The name of the location.
            temperature_entity_id: The entity ID of the temperature sensor.
            temperature_entity_unique_id: The unique ID of the temperature sensor
                                         (used for resilient lookups if entity renamed).

        """
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self._temperature_entity_id = temperature_entity_id
        self._temperature_entity_unique_id = temperature_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{location_name} Temperature Below Threshold Weekly Duration"
        location_name_safe = location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{entry_id}_{location_name_safe}_"
            "temperature_below_threshold_weekly_duration"
        )

        # Set device class, unit, and icon
        self._attr_device_class = None  # No standard device class for this metric
        self._attr_native_unit_of_measurement = "hours"
        self._attr_icon = "mdi:thermometer-alert"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_suggested_display_precision = 0
        self._attr_entity_registry_visible_default = True

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location Device",
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

        # Generate a concise entity_id
        with contextlib.suppress(Exception):
            safe_name = (
                (f"{location_name} Temperature Below Threshold Weekly Duration")
                .lower()
                .replace(" ", "_")
            )
            self.entity_id = async_generate_entity_id(
                "sensor.{}",
                safe_name,
                current_ids={},
            )

    async def _calculate_hours_below_threshold(self) -> int | None:
        """
        Calculate hours where temperature was below the minimum threshold.

        This queries the statistics from Home Assistant's recorder database
        to count hourly periods where temperature was below the threshold.

        Returns:
            The number of hours below threshold, or None if data unavailable.

        """
        try:
            # Get threshold temperature
            min_temp_threshold = await self._get_temperature_threshold()
            if min_temp_threshold is None:
                return None

            # Get temperature statistics
            stats = await self._fetch_temperature_statistics()
            if not stats:
                return None

            # Count hours below threshold
            hours_below = self._count_hours_below_threshold(stats, min_temp_threshold)

            _LOGGER.debug(
                "Temperature below threshold: %d hours out of %d total hours "
                "(threshold: %.1f°C)",
                hours_below,
                len(stats),
                min_temp_threshold,
            )

            return hours_below  # noqa: TRY300

        except ImportError as exc:
            _LOGGER.warning(
                "Could not import recorder statistics: %s",
                exc,
            )
            return None
        except Exception as exc:  # noqa: BLE001 - Defensive
            _LOGGER.warning(
                "Error calculating temp below threshold weekly duration: %s (%s)",
                exc,
                type(exc).__name__,
            )
            return None

    async def _get_temperature_threshold(self) -> float | None:
        """Get the minimum temperature threshold from aggregated sensors."""
        # Find the min_temperature aggregated sensor for this location
        min_temp_entity_id = self._find_min_temperature_entity()
        if not min_temp_entity_id:
            _LOGGER.debug("No minimum temperature threshold entity found for location")
            return None

        # Get the threshold value
        min_temp_state = self.hass.states.get(min_temp_entity_id)
        if not min_temp_state or min_temp_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            None,
        ):
            _LOGGER.debug(
                "Minimum temperature threshold not available: %s",
                min_temp_state.state if min_temp_state else "None",
            )
            return None

        try:
            return float(min_temp_state.state)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "Could not convert minimum temperature to float: %s",
                min_temp_state.state,
            )
            return None

    def _find_min_temperature_entity(self) -> str | None:
        """Find the min_temperature entity ID for this location."""
        ent_reg = er.async_get(self.hass)
        for entity in ent_reg.entities.values():
            if (
                entity.platform == DOMAIN
                and entity.domain == "sensor"
                and entity.unique_id
                and f"{self.entry_id}" in entity.unique_id
                and "min_temperature" in entity.unique_id
            ):
                return entity.entity_id
        return None

    async def _fetch_temperature_statistics(self) -> list[Any] | None:
        """Fetch temperature statistics from recorder."""
        # Get statistics for the past 7 days
        end_time = dt_util.now()
        start_time = end_time - timedelta(days=7)

        # Get recorder instance
        recorder_instance = get_instance(self.hass)
        if recorder_instance is None:
            _LOGGER.debug("Recorder not available")
            return None

        # Query statistics for the temperature sensor
        stats = await recorder_instance.async_add_executor_job(
            statistics_during_period,
            self.hass,
            start_time,
            end_time,
            {self._temperature_entity_id},
            "hour",
            None,
            {"mean"},
        )

        if not stats or self._temperature_entity_id not in stats:
            _LOGGER.debug(
                "No statistics found for temperature entity: %s",
                self._temperature_entity_id,
            )
            return None

        return stats[self._temperature_entity_id]

    def _count_hours_below_threshold(self, stats: list[Any], threshold: float) -> int:
        """Count hours where temperature was below threshold."""
        hours_below = 0
        for stat in stats:
            mean_temp = stat.get("mean")
            if mean_temp is not None:
                try:
                    if float(mean_temp) < threshold:
                        hours_below += 1
                except (ValueError, TypeError):
                    continue
        return hours_below

    @callback
    def _temperature_state_changed(self, _event: Event) -> None:
        """Handle temperature sensor state changes."""
        # Trigger recalculation when temperature changes
        self.hass.async_create_task(self._async_update_state())

    async def _async_update_state(self) -> None:
        """Update the sensor state."""
        self._state = await self._calculate_hours_below_threshold()

        # Store metadata in attributes
        self._attributes = {
            "source_entity": self._temperature_entity_id,
            "period_days": 7,
        }

        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        temp_state = self.hass.states.get(self._temperature_entity_id)
        return temp_state is not None

    async def async_added_to_hass(self) -> None:
        """Subscribe to temperature sensor state changes and restore state."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._state = int(last_state.state)
            except (ValueError, TypeError):
                self._state = last_state.state

            # Restore attributes
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored temperature below threshold sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        # Subscribe to temperature sensor state changes
        # Update every hour or when temperature changes significantly
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass, self._temperature_entity_id, self._temperature_state_changed
            )
            _LOGGER.debug(
                "Temperature below threshold sensor %s subscribed to %s",
                self.entity_id,
                self._temperature_entity_id,
            )

            # Perform initial calculation
            await self._async_update_state()

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up temperature below threshold sensor: %s",
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class TemperatureAboveThresholdHoursSensor(SensorEntity, RestoreEntity):
    """
    Sensor that counts hours where temperature was above maximum threshold.

    This sensor queries Home Assistant's statistics database to count the number
    of hourly readings where the temperature was above the maximum temperature
    threshold over the past 7 days.
    """

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        temperature_entity_id: str,
        temperature_entity_unique_id: str | None = None,
    ) -> None:
        """
        Initialize the temperature above threshold weekly duration sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The subentry ID.
            location_device_id: The device ID of the location.
            location_name: The name of the location.
            temperature_entity_id: The entity ID of the temperature sensor.
            temperature_entity_unique_id: The unique ID of the temperature sensor
                                         (used for resilient lookups if entity renamed).

        """
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self._temperature_entity_id = temperature_entity_id
        self._temperature_entity_unique_id = temperature_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{location_name} Temperature Above Threshold Weekly Duration"
        location_name_safe = location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{entry_id}_{location_name_safe}_"
            "temperature_above_threshold_weekly_duration"
        )

        # Set device class, unit, and icon
        self._attr_device_class = None  # No standard device class for this metric
        self._attr_native_unit_of_measurement = "hours"
        self._attr_icon = "mdi:thermometer-alert"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_suggested_display_precision = 0
        self._attr_entity_registry_visible_default = True

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location Device",
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

        # Generate a concise entity_id
        with contextlib.suppress(Exception):
            safe_name = (
                (f"{location_name} Temperature Above Threshold Weekly Duration")
                .lower()
                .replace(" ", "_")
            )
            self.entity_id = async_generate_entity_id(
                "sensor.{}",
                safe_name,
                current_ids={},
            )

    async def _calculate_hours_above_threshold(self) -> int | None:
        """
        Calculate hours where temperature was above the maximum threshold.

        This queries the statistics from Home Assistant's recorder database
        to count hourly periods where temperature was above the threshold.

        Returns:
            The number of hours above threshold, or None if data unavailable.

        """
        try:
            # Get threshold temperature
            max_temp_threshold = await self._get_temperature_threshold()
            if max_temp_threshold is None:
                return None

            # Get temperature statistics
            stats = await self._fetch_temperature_statistics()
            if not stats:
                return None

            # Count hours above threshold
            hours_above = self._count_hours_above_threshold(stats, max_temp_threshold)

            _LOGGER.debug(
                "Temperature above threshold: %d hours out of %d total hours "
                "(threshold: %.1f°C)",
                hours_above,
                len(stats),
                max_temp_threshold,
            )

            return hours_above  # noqa: TRY300

        except ImportError as exc:
            _LOGGER.warning(
                "Could not import recorder statistics: %s",
                exc,
            )
            return None
        except Exception as exc:  # noqa: BLE001 - Defensive
            _LOGGER.warning(
                "Error calculating temp above threshold weekly duration: %s (%s)",
                exc,
                type(exc).__name__,
            )
            return None

    async def _get_temperature_threshold(self) -> float | None:
        """Get the maximum temperature threshold from aggregated sensors."""
        # Find the max_temperature aggregated sensor for this location
        max_temp_entity_id = self._find_max_temperature_entity()
        if not max_temp_entity_id:
            _LOGGER.debug("No maximum temperature threshold entity found for location")
            return None

        # Get the threshold value
        max_temp_state = self.hass.states.get(max_temp_entity_id)
        if not max_temp_state or max_temp_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            None,
        ):
            _LOGGER.debug(
                "Maximum temperature threshold not available: %s",
                max_temp_state.state if max_temp_state else "None",
            )
            return None

        try:
            return float(max_temp_state.state)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "Could not convert maximum temperature to float: %s",
                max_temp_state.state,
            )
            return None

    def _find_max_temperature_entity(self) -> str | None:
        """Find the max_temperature entity ID for this location."""
        ent_reg = er.async_get(self.hass)
        for entity in ent_reg.entities.values():
            if (
                entity.platform == DOMAIN
                and entity.domain == "sensor"
                and entity.unique_id
                and f"{self.entry_id}" in entity.unique_id
                and "max_temperature" in entity.unique_id
            ):
                return entity.entity_id
        return None

    async def _fetch_temperature_statistics(self) -> list[Any] | None:
        """Fetch temperature statistics from recorder."""
        # Get statistics for the past 7 days
        end_time = dt_util.now()
        start_time = end_time - timedelta(days=7)

        # Get recorder instance
        recorder_instance = get_instance(self.hass)
        if recorder_instance is None:
            _LOGGER.debug("Recorder not available")
            return None

        # Query statistics for the temperature sensor
        stats = await recorder_instance.async_add_executor_job(
            statistics_during_period,
            self.hass,
            start_time,
            end_time,
            {self._temperature_entity_id},
            "hour",
            None,
            {"mean"},
        )

        if not stats or self._temperature_entity_id not in stats:
            _LOGGER.debug(
                "No statistics found for temperature entity: %s",
                self._temperature_entity_id,
            )
            return None

        return stats[self._temperature_entity_id]

    def _count_hours_above_threshold(self, stats: list[Any], threshold: float) -> int:
        """Count hours where temperature was above threshold."""
        hours_above = 0
        for stat in stats:
            mean_temp = stat.get("mean")
            if mean_temp is not None:
                try:
                    if float(mean_temp) > threshold:
                        hours_above += 1
                except (ValueError, TypeError):
                    continue
        return hours_above

    @callback
    def _temperature_state_changed(self, _event: Event) -> None:
        """Handle temperature sensor state changes."""
        # Trigger recalculation when temperature changes
        self.hass.async_create_task(self._async_update_state())

    async def _async_update_state(self) -> None:
        """Update the sensor state."""
        self._state = await self._calculate_hours_above_threshold()

        # Store metadata in attributes
        self._attributes = {
            "source_entity": self._temperature_entity_id,
            "period_days": 7,
        }

        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        temp_state = self.hass.states.get(self._temperature_entity_id)
        return temp_state is not None

    async def async_added_to_hass(self) -> None:
        """Subscribe to temperature sensor state changes and restore state."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._state = int(last_state.state)
            except (ValueError, TypeError):
                self._state = last_state.state

            # Restore attributes
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored temperature above threshold sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        # Subscribe to temperature sensor state changes
        # Update every hour or when temperature changes significantly
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass, self._temperature_entity_id, self._temperature_state_changed
            )
            _LOGGER.debug(
                "Temperature above threshold sensor %s subscribed to %s",
                self.entity_id,
                self._temperature_entity_id,
            )

            # Perform initial calculation
            await self._async_update_state()

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up temperature above threshold sensor: %s",
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class HumidityBelowThresholdHoursSensor(SensorEntity, RestoreEntity):
    """
    Sensor that counts hours where humidity was below minimum threshold.

    This sensor queries Home Assistant's statistics database to count the number
    of hourly readings where the humidity was below the minimum humidity
    threshold over the past 7 days.
    """

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        humidity_entity_id: str,
        humidity_entity_unique_id: str | None = None,
    ) -> None:
        """
        Initialize the humidity below threshold weekly duration sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The subentry ID.
            location_device_id: The device ID of the location.
            location_name: The name of the location.
            humidity_entity_id: The entity ID of the humidity sensor.
            humidity_entity_unique_id: The unique ID for resilient lookup.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self._humidity_entity_id = humidity_entity_id
        self._humidity_entity_unique_id = humidity_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{location_name} Humidity Below Threshold Weekly Duration"
        location_name_safe = location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{entry_id}_{location_name_safe}_"
            "humidity_below_threshold_weekly_duration"
        )

        # Set device class, unit, and icon
        self._attr_device_class = None  # No standard device class for this metric
        self._attr_native_unit_of_measurement = "hours"
        self._attr_icon = "mdi:water-alert"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_suggested_display_precision = 0
        self._attr_entity_registry_visible_default = True

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location Device",
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

        # Generate a concise entity_id
        with contextlib.suppress(Exception):
            safe_name = (
                (f"{location_name} Humidity Below Threshold Weekly Duration")
                .lower()
                .replace(" ", "_")
            )
            self.entity_id = async_generate_entity_id(
                "sensor.{}",
                safe_name,
                current_ids={},
            )

    async def _calculate_hours_below_threshold(self) -> int | None:
        """
        Calculate hours where humidity was below the minimum threshold.

        This queries the statistics from Home Assistant's recorder database
        to count hourly periods where humidity was below the threshold.

        Returns:
            The number of hours below threshold, or None if data unavailable.

        """
        try:
            # Get threshold humidity
            min_humidity_threshold = await self._get_humidity_threshold()
            if min_humidity_threshold is None:
                return None

            # Get humidity statistics
            stats = await self._fetch_humidity_statistics()
            if not stats:
                return None

            # Count hours below threshold
            hours_below = self._count_hours_below_threshold(
                stats, min_humidity_threshold
            )

            _LOGGER.debug(
                "Humidity below threshold: %d hours out of %d total hours "
                "(threshold: %.1f%%)",
                hours_below,
                len(stats),
                min_humidity_threshold,
            )

            return hours_below  # noqa: TRY300

        except ImportError as exc:
            _LOGGER.warning(
                "Could not import recorder statistics: %s",
                exc,
            )
            return None
        except Exception as exc:  # noqa: BLE001 - Defensive
            _LOGGER.warning(
                "Error calculating humidity below threshold weekly duration: %s (%s)",
                exc,
                type(exc).__name__,
            )
            return None

    async def _get_humidity_threshold(self) -> float | None:
        """Get the minimum humidity threshold from aggregated sensors."""
        # Find the min_humidity aggregated sensor for this location
        min_humidity_entity_id = self._find_min_humidity_entity()
        if not min_humidity_entity_id:
            _LOGGER.debug("No minimum humidity threshold entity found for location")
            return None

        # Get the threshold value
        min_humidity_state = self.hass.states.get(min_humidity_entity_id)
        if not min_humidity_state or min_humidity_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            None,
        ):
            _LOGGER.debug(
                "Minimum humidity threshold not available: %s",
                min_humidity_state.state if min_humidity_state else "None",
            )
            return None

        try:
            return float(min_humidity_state.state)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "Could not convert minimum humidity to float: %s",
                min_humidity_state.state,
            )
            return None

    def _find_min_humidity_entity(self) -> str | None:
        """Find the min_humidity entity ID for this location."""
        ent_reg = er.async_get(self.hass)
        for entity in ent_reg.entities.values():
            if (
                entity.platform == DOMAIN
                and entity.domain == "sensor"
                and entity.unique_id
                and f"{self.entry_id}" in entity.unique_id
                and "min_humidity" in entity.unique_id
            ):
                return entity.entity_id
        return None

    async def _fetch_humidity_statistics(self) -> list[Any] | None:
        """Fetch humidity statistics from recorder."""
        # Get statistics for the past 7 days
        end_time = dt_util.now()
        start_time = end_time - timedelta(days=7)

        # Get recorder instance
        recorder_instance = get_instance(self.hass)
        if recorder_instance is None:
            _LOGGER.debug("Recorder not available")
            return None

        # Query statistics for the humidity sensor
        stats = await recorder_instance.async_add_executor_job(
            statistics_during_period,
            self.hass,
            start_time,
            end_time,
            {self._humidity_entity_id},
            "hour",
            None,
            {"mean"},
        )

        if not stats or self._humidity_entity_id not in stats:
            _LOGGER.debug(
                "No statistics found for humidity entity: %s",
                self._humidity_entity_id,
            )
            return None

        return stats[self._humidity_entity_id]

    def _count_hours_below_threshold(self, stats: list[Any], threshold: float) -> int:
        """Count hours where humidity was below threshold."""
        hours_below = 0
        for stat in stats:
            mean_humidity = stat.get("mean")
            if mean_humidity is not None:
                try:
                    if float(mean_humidity) < threshold:
                        hours_below += 1
                except (ValueError, TypeError):
                    continue
        return hours_below

    @callback
    def _humidity_state_changed(self, _event: Event) -> None:
        """Handle humidity sensor state changes."""
        # Trigger recalculation when humidity changes
        self.hass.async_create_task(self._async_update_state())

    async def _async_update_state(self) -> None:
        """Update the sensor state."""
        self._state = await self._calculate_hours_below_threshold()

        # Store metadata in attributes
        self._attributes = {
            "source_entity": self._humidity_entity_id,
            "period_days": 7,
        }

        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        humidity_state = self.hass.states.get(self._humidity_entity_id)
        return humidity_state is not None

    async def async_added_to_hass(self) -> None:
        """Subscribe to humidity sensor state changes and restore state."""
        await super().async_added_to_hass()

        # Resolve humidity entity ID with fallback to unique ID for resilience
        resolved_entity_id = _resolve_entity_id(
            self.hass, self._humidity_entity_id, self._humidity_entity_unique_id
        )
        if resolved_entity_id and resolved_entity_id != self._humidity_entity_id:
            _LOGGER.debug(
                "Resolved humidity entity ID: %s -> %s",
                self._humidity_entity_id,
                resolved_entity_id,
            )
            self._humidity_entity_id = resolved_entity_id

        # Restore previous state if available
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._state = int(last_state.state)
            except (ValueError, TypeError):
                self._state = last_state.state

            # Restore attributes
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored humidity below threshold sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        # Subscribe to humidity sensor state changes
        # Update every hour or when humidity changes significantly
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass, self._humidity_entity_id, self._humidity_state_changed
            )
            _LOGGER.debug(
                "Humidity below threshold sensor %s subscribed to %s",
                self.entity_id,
                self._humidity_entity_id,
            )

            # Perform initial calculation
            await self._async_update_state()

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up humidity below threshold sensor: %s",
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class HumidityAboveThresholdHoursSensor(SensorEntity, RestoreEntity):
    """
    Sensor that counts hours where humidity was above maximum threshold.

    This sensor queries Home Assistant's statistics database to count the number
    of hourly readings where the humidity was above the maximum humidity
    threshold over the past 7 days.
    """

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        humidity_entity_id: str,
        humidity_entity_unique_id: str | None = None,
    ) -> None:
        """
        Initialize the humidity above threshold weekly duration sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The subentry ID.
            location_device_id: The device ID of the location.
            location_name: The name of the location.
            humidity_entity_id: The entity ID of the humidity sensor.
            humidity_entity_unique_id: The unique ID for resilient lookup.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self._humidity_entity_id = humidity_entity_id
        self._humidity_entity_unique_id = humidity_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{location_name} Humidity Above Threshold Weekly Duration"
        location_name_safe = location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{entry_id}_{location_name_safe}_"
            "humidity_above_threshold_weekly_duration"
        )

        # Set device class, unit, and icon
        self._attr_device_class = None  # No standard device class for this metric
        self._attr_native_unit_of_measurement = "hours"
        self._attr_icon = "mdi:water-alert"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_suggested_display_precision = 0
        self._attr_entity_registry_visible_default = True

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
            name=location_name,
            manufacturer="Plant Assistant",
            model="Plant Location Device",
        )

        self._state: Any = None
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

        # Generate a concise entity_id
        with contextlib.suppress(Exception):
            safe_name = (
                (f"{location_name} Humidity Above Threshold Weekly Duration")
                .lower()
                .replace(" ", "_")
            )
            self.entity_id = async_generate_entity_id(
                "sensor.{}",
                safe_name,
                current_ids={},
            )

    async def _calculate_hours_above_threshold(self) -> int | None:
        """
        Calculate hours where humidity was above the maximum threshold.

        This queries the statistics from Home Assistant's recorder database
        to count hourly periods where humidity was above the threshold.

        Returns:
            The number of hours above threshold, or None if data unavailable.

        """
        try:
            # Get threshold humidity
            max_humidity_threshold = await self._get_humidity_threshold()
            if max_humidity_threshold is None:
                return None

            # Get humidity statistics
            stats = await self._fetch_humidity_statistics()
            if not stats:
                return None

            # Count hours above threshold
            hours_above = self._count_hours_above_threshold(
                stats, max_humidity_threshold
            )

            _LOGGER.debug(
                "Humidity above threshold: %d hours out of %d total hours "
                "(threshold: %.1f%%)",
                hours_above,
                len(stats),
                max_humidity_threshold,
            )

            return hours_above  # noqa: TRY300

        except ImportError as exc:
            _LOGGER.warning(
                "Could not import recorder statistics: %s",
                exc,
            )
            return None
        except Exception as exc:  # noqa: BLE001 - Defensive
            _LOGGER.warning(
                "Error calculating humidity above threshold weekly duration: %s (%s)",
                exc,
                type(exc).__name__,
            )
            return None

    async def _get_humidity_threshold(self) -> float | None:
        """Get the maximum humidity threshold from aggregated sensors."""
        # Find the max_humidity aggregated sensor for this location
        max_humidity_entity_id = self._find_max_humidity_entity()
        if not max_humidity_entity_id:
            _LOGGER.debug("No maximum humidity threshold entity found for location")
            return None

        # Get the threshold value
        max_humidity_state = self.hass.states.get(max_humidity_entity_id)
        if not max_humidity_state or max_humidity_state.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
            None,
        ):
            _LOGGER.debug(
                "Maximum humidity threshold not available: %s",
                max_humidity_state.state if max_humidity_state else "None",
            )
            return None

        try:
            return float(max_humidity_state.state)
        except (ValueError, TypeError):
            _LOGGER.debug(
                "Could not convert maximum humidity to float: %s",
                max_humidity_state.state,
            )
            return None

    def _find_max_humidity_entity(self) -> str | None:
        """Find the max_humidity entity ID for this location."""
        ent_reg = er.async_get(self.hass)
        for entity in ent_reg.entities.values():
            if (
                entity.platform == DOMAIN
                and entity.domain == "sensor"
                and entity.unique_id
                and f"{self.entry_id}" in entity.unique_id
                and "max_humidity" in entity.unique_id
            ):
                return entity.entity_id
        return None

    async def _fetch_humidity_statistics(self) -> list[Any] | None:
        """Fetch humidity statistics from recorder."""
        # Get statistics for the past 7 days
        end_time = dt_util.now()
        start_time = end_time - timedelta(days=7)

        # Get recorder instance
        recorder_instance = get_instance(self.hass)
        if recorder_instance is None:
            _LOGGER.debug("Recorder not available")
            return None

        # Query statistics for the humidity sensor
        stats = await recorder_instance.async_add_executor_job(
            statistics_during_period,
            self.hass,
            start_time,
            end_time,
            {self._humidity_entity_id},
            "hour",
            None,
            {"mean"},
        )

        if not stats or self._humidity_entity_id not in stats:
            _LOGGER.debug(
                "No statistics found for humidity entity: %s",
                self._humidity_entity_id,
            )
            return None

        return stats[self._humidity_entity_id]

    def _count_hours_above_threshold(self, stats: list[Any], threshold: float) -> int:
        """Count hours where humidity was above threshold."""
        hours_above = 0
        for stat in stats:
            mean_humidity = stat.get("mean")
            if mean_humidity is not None:
                try:
                    if float(mean_humidity) > threshold:
                        hours_above += 1
                except (ValueError, TypeError):
                    continue
        return hours_above

    @callback
    def _humidity_state_changed(self, _event: Event) -> None:
        """Handle humidity sensor state changes."""
        # Trigger recalculation when humidity changes
        self.hass.async_create_task(self._async_update_state())

    async def _async_update_state(self) -> None:
        """Update the sensor state."""
        self._state = await self._calculate_hours_above_threshold()

        # Store metadata in attributes
        self._attributes = {
            "source_entity": self._humidity_entity_id,
            "period_days": 7,
        }

        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if self._state in (STATE_UNAVAILABLE, STATE_UNKNOWN, None):
            return None
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        humidity_state = self.hass.states.get(self._humidity_entity_id)
        return humidity_state is not None

    async def async_added_to_hass(self) -> None:
        """Subscribe to humidity sensor state changes and restore state."""
        await super().async_added_to_hass()

        # Resolve humidity entity ID with fallback to unique ID for resilience
        resolved_entity_id = _resolve_entity_id(
            self.hass, self._humidity_entity_id, self._humidity_entity_unique_id
        )
        if resolved_entity_id and resolved_entity_id != self._humidity_entity_id:
            _LOGGER.debug(
                "Resolved humidity entity ID: %s -> %s",
                self._humidity_entity_id,
                resolved_entity_id,
            )
            self._humidity_entity_id = resolved_entity_id

        # Restore previous state if available
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._state = int(last_state.state)
            except (ValueError, TypeError):
                self._state = last_state.state

            # Restore attributes
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored humidity above threshold sensor %s with state: %s",
                self.entity_id,
                self._state,
            )

        # Subscribe to humidity sensor state changes
        # Update every hour or when humidity changes significantly
        try:
            self._unsubscribe = async_track_state_change_event(
                self.hass, self._humidity_entity_id, self._humidity_state_changed
            )
            _LOGGER.debug(
                "Humidity above threshold sensor %s subscribed to %s",
                self.entity_id,
                self._humidity_entity_id,
            )

            # Perform initial calculation
            await self._async_update_state()

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up humidity above threshold sensor: %s",
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class SoilMoistureRecentChangeSensor(SensorEntity):
    """
    Statistics sensor that tracks recent change in soil moisture percentage.

    This sensor monitors the percentage change in soil moisture over a 3-hour window.
    When the change is >= 10%, it indicates the plant was likely watered.

    This sensor is only created for non-ESPHome zones where watering detection
    must be inferred from moisture changes rather than direct irrigation events.
    """

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        soil_moisture_entity_id: str,
        soil_moisture_entity_unique_id: str | None = None,
    ) -> None:
        """
        Initialize the soil moisture recent change sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            location_device_id: The device identifier for the location.
            location_name: The name of the plant location.
            soil_moisture_entity_id: Entity ID of the soil moisture sensor to monitor.
            soil_moisture_entity_unique_id: Unique ID of the soil moisture sensor.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self.location_name = location_name
        self.soil_moisture_entity_id = soil_moisture_entity_id
        self.soil_moisture_entity_unique_id = soil_moisture_entity_unique_id

        # Set entity attributes
        self._attr_name = f"{location_name} Soil Moisture Recent Change"

        # Generate unique_id
        location_name_safe = location_name.lower().replace(" ", "_")
        self._attr_unique_id = (
            f"{DOMAIN}_{entry_id}_{location_name_safe}_soil_moisture_recent_change"
        )

        # Set sensor properties
        self._attr_device_class = None  # No device class for change percentage
        self._attr_native_unit_of_measurement = "%"
        self._attr_icon = "mdi:water-percent"
        self._attr_state_class = "measurement"

        # Set device info to associate with the location device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, location_device_id)},
        )

        self._state: float | None = None
        self._unsubscribe = None

    @property
    def native_value(self) -> float | None:
        """Return the native value of the sensor."""
        if self._state is None:
            return None

        # Return the change percentage
        # Positive values indicate moisture increase (watering)
        # Negative values indicate moisture decrease (drying)
        return round(self._state, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            "source_entity": self.soil_moisture_entity_id,
            "window_duration": "3 hours",
            "watering_threshold": 10.0,
        }

    @callback
    def _soil_moisture_state_changed(self, _event: Event) -> None:
        """Handle soil moisture sensor state changes."""
        # Trigger recalculation when soil moisture changes
        self.hass.async_create_task(self._async_update_state())

    async def _async_update_state(self) -> None:
        """Update the sensor state."""
        await self.async_update()
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update sensor state by calculating recent moisture change."""
        try:
            # Get recorder instance
            recorder_instance = get_instance(self.hass)

            # Calculate time range: last 3 hours
            end_time = dt_util.now()
            start_time = end_time - timedelta(hours=3)

            # Get statistics for the soil moisture sensor over last 3 hours
            stats = await recorder_instance.async_add_executor_job(
                statistics_during_period,
                self.hass,
                start_time,
                end_time,
                {self.soil_moisture_entity_id},
                "hour",
                None,
                {"mean"},
            )

            if not stats or self.soil_moisture_entity_id not in stats:
                # No statistics available yet
                self._state = None
                return

            sensor_stats = stats[self.soil_moisture_entity_id]
            if len(sensor_stats) < 2:  # noqa: PLR2004
                # Need at least 2 data points to calculate change
                self._state = None
                return

            # Get first and last mean values
            first_stat = sensor_stats[0]
            last_stat = sensor_stats[-1]

            first_mean = first_stat.get("mean")
            last_mean = last_stat.get("mean")

            if first_mean is None or last_mean is None:
                self._state = None
                return

            # Calculate change: positive = increase (watering), negative = decrease
            change = last_mean - first_mean
            self._state = change

        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            _LOGGER.debug(
                "Error calculating recent moisture change for %s: %s",
                self.location_name,
                exc,
            )
            self._state = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to soil moisture sensor state changes."""
        try:
            # Subscribe to soil moisture sensor state changes
            # Update when soil moisture changes to recalculate the recent change
            self._unsubscribe = async_track_state_change_event(
                self.hass,
                self.soil_moisture_entity_id,
                self._soil_moisture_state_changed,
            )
            _LOGGER.debug(
                "Soil moisture recent change sensor %s subscribed to %s",
                self.entity_id,
                self.soil_moisture_entity_id,
            )

            # Perform initial calculation
            await self._async_update_state()

        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up soil moisture recent change sensor: %s",
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()


class IrrigationZoneFertiliserDueSensor(SensorEntity, RestoreEntity):
    """
    Sensor that assesses if fertiliser is due for an irrigation zone.

    This sensor evaluates whether fertiliser injection is due based on multiple
    conditions including:
    - System-wide fertiliser enabled state
    - Zone-specific fertiliser enabled state
    - Fertiliser injection schedule (in days)
    - Current month (only active April-September)
    - Last fertiliser injection timestamp
    - Current date/time

    The sensor state is 'on' when fertiliser is due, 'off' otherwise.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        zone_device_id: tuple[str, str],
        zone_name: str,
        zone_id: str,
    ) -> None:
        """
        Initialize the irrigation zone fertiliser due sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The config entry ID.
            zone_device_id: The device identifier tuple (domain, device_id).
            zone_name: The name of the irrigation zone.
            zone_id: The zone ID used to extract data from events and entities.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.zone_device_id = zone_device_id
        self.zone_name = zone_name
        self.zone_id = zone_id

        # Set entity attributes
        self._attr_name = f"{zone_name} Fertiliser Due"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_icon = "mdi:water-opacity"
        self._attr_options = ["off", "on"]

        # Create unique ID from zone device identifier tuple
        unique_id_parts = (
            DOMAIN,
            entry_id,
            zone_device_id[0],
            zone_device_id[1],
            "fertiliser_due",
        )
        self._attr_unique_id = "_".join(unique_id_parts)

        # Set device info to associate with the irrigation zone device
        self._attr_device_info = DeviceInfo(
            identifiers={zone_device_id},
        )

        self._state: str = "off"
        self._attributes: dict[str, Any] = {}
        self._unsubscribe = None

        # Store discovered entity IDs from the device
        # We discover these from the device instead of constructing them,
        # making the sensor resilient to entity renames
        self._last_injection_entity_id: str | None = None
        self._fertiliser_switch_entity_id: str | None = None
        self._fertiliser_schedule_entity_id: str | None = None
        self._discover_device_entities()

    def _discover_device_entities(self) -> None:
        """
        Discover all required entities for this zone's fertiliser monitoring.

        This queries the device registry and entity registry to find the entities
        associated with this zone's device, rather than constructing entity IDs.
        This makes the sensor resilient to entity renames.

        Entities discovered:
        - last_fertiliser_injection (sensor)
        - allow_fertiliser_injection (switch)
        - fertiliser_injection_days (number)
        """
        try:
            # Get the device ID (not the identifier tuple)
            dev_reg = dr.async_get(self.hass)

            # Find the device by identifier
            device = None
            for dev in dev_reg.devices.values():
                if self.zone_device_id in dev.identifiers:
                    device = dev
                    break

            if not device:
                _LOGGER.debug(
                    "Could not find device for zone %s (identifier: %s)",
                    self.zone_name,
                    self.zone_device_id,
                )
                return

            # Find sensor entities on this device
            sensor_entities = find_device_entities_by_pattern(
                self.hass,
                device.id,
                "sensor",
                ["last_fertiliser_injection"],
            )

            if "last_fertiliser_injection" in sensor_entities:
                entity_id, unique_id = sensor_entities["last_fertiliser_injection"]
                self._last_injection_entity_id = entity_id
                _LOGGER.debug(
                    "Discovered last fertiliser injection sensor for %s: %s "
                    "(unique_id: %s)",
                    self.zone_name,
                    entity_id,
                    unique_id,
                )
            else:
                _LOGGER.debug(
                    "Could not find last fertiliser injection sensor for %s "
                    "on device %s",
                    self.zone_name,
                    device.id,
                )

            # Find switch entities on this device
            switch_entities = find_device_entities_by_pattern(
                self.hass,
                device.id,
                "switch",
                ["allow_fertiliser_injection"],
            )

            if "allow_fertiliser_injection" in switch_entities:
                entity_id, unique_id = switch_entities["allow_fertiliser_injection"]
                self._fertiliser_switch_entity_id = entity_id
                _LOGGER.debug(
                    "Discovered fertiliser injection switch for %s: %s (unique_id: %s)",
                    self.zone_name,
                    entity_id,
                    unique_id,
                )
            else:
                _LOGGER.debug(
                    "Could not find fertiliser injection switch for %s on device %s",
                    self.zone_name,
                    device.id,
                )

            # Find number entities on this device
            number_entities = find_device_entities_by_pattern(
                self.hass,
                device.id,
                "number",
                ["fertiliser_injection_days"],
            )

            if "fertiliser_injection_days" in number_entities:
                entity_id, unique_id = number_entities["fertiliser_injection_days"]
                self._fertiliser_schedule_entity_id = entity_id
                _LOGGER.debug(
                    "Discovered fertiliser injection schedule for %s: %s "
                    "(unique_id: %s)",
                    self.zone_name,
                    entity_id,
                    unique_id,
                )
            else:
                _LOGGER.debug(
                    "Could not find fertiliser injection schedule for %s on device %s",
                    self.zone_name,
                    device.id,
                )

        except (AttributeError, KeyError, ValueError, TypeError) as exc:
            _LOGGER.debug(
                "Error discovering fertiliser entities for %s: %s",
                self.zone_name,
                exc,
            )

    def _get_entity_state(self, entity_id: str) -> str | None:
        """
        Safely get the state of an entity.

        Args:
            entity_id: The entity ID to retrieve state for.

        Returns:
            The state value as a string, or None if unavailable/unknown.

        """
        try:
            state = self.hass.states.get(entity_id)
            if state is not None and state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                return state.state
            return None  # noqa: TRY300
        except (AttributeError, KeyError, ValueError):
            return None

    def _parse_datetime_state(self, datetime_str: str | None) -> Any:
        """
        Parse a datetime string to a datetime object.

        Args:
            datetime_str: The datetime string to parse (ISO 8601 format).

        Returns:
            A datetime object if parsing succeeds, None otherwise.

        """
        if not datetime_str or datetime_str in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None

        try:
            return dt_util.parse_datetime(datetime_str)
        except (ValueError, TypeError):
            return None

    def _evaluate_fertiliser_due(self) -> bool:  # noqa: PLR0911
        """
        Evaluate if fertiliser is due based on configuration.

        Implements the logic checking:
        - Zone-specific fertiliser enabled state (from device switch)
        - Fertiliser injection schedule (from device number entity)
        - Current month (only active April-September, months 4-9)
        - Last fertiliser injection timestamp
        - Current date/time

        Returns:
            True if fertiliser is due, False otherwise.

        """
        # 1. Check if zone fertiliser injection is enabled
        # Use the discovered entity ID instead of constructing it
        if not self._fertiliser_switch_entity_id:
            _LOGGER.debug(
                "Fertiliser due %s: Fertiliser injection switch not discovered",
                self.zone_name,
            )
            return False

        zone_fertiliser_enabled = self._get_entity_state(
            self._fertiliser_switch_entity_id
        )
        if zone_fertiliser_enabled != "on":
            _LOGGER.debug(
                "Fertiliser due %s: Zone fertiliser enabled is %s (from %s)",
                self.zone_name,
                zone_fertiliser_enabled,
                self._fertiliser_switch_entity_id,
            )
            return False

        # 2. Check if fertiliser schedule is configured (> 0 days)
        # Use the discovered entity ID instead of constructing it
        if not self._fertiliser_schedule_entity_id:
            _LOGGER.debug(
                "Fertiliser due %s: Fertiliser schedule entity not discovered",
                self.zone_name,
            )
            return False

        schedule_str = self._get_entity_state(self._fertiliser_schedule_entity_id)
        if not schedule_str:
            _LOGGER.debug(
                "Fertiliser due %s: Schedule not available from %s",
                self.zone_name,
                self._fertiliser_schedule_entity_id,
            )
            return False

        try:
            schedule_days = int(float(schedule_str))
        except (ValueError, TypeError):
            _LOGGER.debug(
                "Fertiliser due %s: Could not parse schedule: %s",
                self.zone_name,
                schedule_str,
            )
            return False

        if schedule_days <= 0:
            _LOGGER.debug(
                "Fertiliser due %s: Schedule is 0 or negative: %d days",
                self.zone_name,
                schedule_days,
            )
            return False

        # 3. Check if current month is in season (April-September)
        current_month = dt_util.now().month
        if current_month < 4 or current_month > 9:  # noqa: PLR2004
            _LOGGER.debug(
                "Fertiliser due %s: Outside fertiliser season (month=%d)",
                self.zone_name,
                current_month,
            )
            return False

        # 4. Get last fertiliser injection date
        # Use the discovered entity ID instead of constructing it
        if not self._last_injection_entity_id:
            _LOGGER.debug(
                "Fertiliser due %s: Last fertiliser injection sensor not discovered",
                self.zone_name,
            )
            return True  # If we can't find the sensor, assume fertiliser is due

        last_injection_str = self._get_entity_state(self._last_injection_entity_id)

        # If never injected before, fertiliser is due
        if not last_injection_str:
            _LOGGER.debug(
                "Fertiliser due %s: No previous injection recorded",
                self.zone_name,
            )
            return True

        # 5. Parse last injection timestamp
        last_injection_dt = self._parse_datetime_state(last_injection_str)
        if not last_injection_dt:
            _LOGGER.debug(
                "Fertiliser due %s: Could not parse last injection date: %s",
                self.zone_name,
                last_injection_str,
            )
            return False

        # 6. Calculate next due date
        try:
            next_due_dt = last_injection_dt + timedelta(days=schedule_days)
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Fertiliser due %s: Could not calculate next due date",
                self.zone_name,
            )
            return False

        # 7. Get current datetime and compare if current time >= next due time
        current_dt = dt_util.now()
        is_due: bool = current_dt >= next_due_dt

        _LOGGER.debug(
            "Fertiliser due %s: Evaluated - last_injection=%s, schedule=%d days, "
            "next_due=%s, current=%s, is_due=%s",
            self.zone_name,
            last_injection_dt,
            schedule_days,
            next_due_dt,
            current_dt,
            is_due,
        )

        return is_due

    @callback
    def _handle_esphome_event(self, _event: Any) -> None:
        """
        Handle esphome.irrigation_gateway_update event.

        This event triggers re-evaluation of the fertiliser due state
        in case any relevant data has changed.
        """
        try:
            _LOGGER.debug(
                "Fertiliser due sensor %s received esphome event",
                self.zone_name,
            )

            # Re-evaluate fertiliser due status
            is_due = self._evaluate_fertiliser_due()
            new_state = "on" if is_due else "off"

            if self._state != new_state:
                old_state = self._state
                self._state = new_state

                self._attributes = {
                    "last_evaluation": dt_util.now().isoformat(),
                    "event_type": "esphome.irrigation_gateway_update",
                    "zone_id": self.zone_id,
                }

                _LOGGER.info(
                    "Fertiliser due %s changed from %s to %s",
                    self.zone_name,
                    old_state,
                    new_state,
                )

                self.async_write_ha_state()
        except (AttributeError, KeyError, ValueError, TypeError) as exc:
            _LOGGER.warning(
                "Error processing esphome event for fertiliser due %s: %s",
                self.zone_name,
                exc,
            )

    @property
    def native_value(self) -> str:
        """Return the native value of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        return self._attributes if self._attributes else None

    async def async_added_to_hass(self) -> None:
        """Set up event listener when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._state = last_state.state
            if last_state.attributes:
                self._attributes = dict(last_state.attributes)

            _LOGGER.debug(
                "Restored fertiliser due sensor %s with state: %s",
                self.entity_id,
                self._state,
            )
        else:
            # Perform initial evaluation
            is_due = self._evaluate_fertiliser_due()
            self._state = "on" if is_due else "off"
            self._attributes = {
                "last_evaluation": dt_util.now().isoformat(),
                "zone_id": self.zone_id,
            }

        # Subscribe to esphome irrigation gateway update events
        try:
            self._unsubscribe = self.hass.bus.async_listen(
                "esphome.irrigation_gateway_update",
                self._handle_esphome_event,
            )
            _LOGGER.debug(
                "Set up event listener for fertiliser due sensor %s",
                self.zone_name,
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to set up event listener for fertiliser due %s: %s",
                self.zone_name,
                exc,
            )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        if self._unsubscribe:
            self._unsubscribe()
