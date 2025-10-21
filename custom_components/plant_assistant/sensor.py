"""
Sensors for the Plant Assistant integration.

This module provides a minimal set of sensors used by the integration and
keeps implementations test-friendly by only relying on `hass.data` and the
`hass.states` mapping where possible.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any, TypedDict, cast

from homeassistant.components.integration.const import METHOD_TRAPEZOIDAL
from homeassistant.components.integration.sensor import IntegrationSensor
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.event import async_track_state_change

from . import aggregation
from .const import (
    AGGREGATED_SENSOR_MAPPINGS,
    ATTR_PLANT_DEVICE_IDS,
    DEFAULT_LUX_TO_PPFD,
    DOMAIN,
    ICON_DLI,
    ICON_PPFD,
    MONITORING_SENSOR_MAPPINGS,
    READING_DLI,
    READING_PPFD,
    UNIT_DLI,
    UNIT_PPFD,
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
) -> dict[str, str]:
    """
    Get sensor entity IDs for a monitoring device.

    Args:
        hass: The Home Assistant instance.
        monitoring_device_id: The device ID of the monitoring device.

    Returns:
        A dict mapping sensor type names (e.g., 'illuminance', 'soil_conductivity')
        to their entity IDs. Returns empty dict if device not found.

    """
    device_sensors: dict[str, str] = {}

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

            if device_class == "illuminance" or "illuminance" in ent_id_lower:
                device_sensors["illuminance"] = ent_id
            elif device_class == "soil_conductivity" or "conductivity" in ent_id_lower:
                device_sensors["soil_conductivity"] = ent_id
            elif device_class == "battery" or "battery" in ent_id_lower:
                device_sensors["battery"] = ent_id
            elif (
                device_class == "signal_strength"
                or "signal" in ent_id_lower
                or "rssi" in ent_id_lower
            ):
                device_sensors["signal_strength"] = ent_id
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


def _expected_entities_for_subentry(  # noqa: PLR0912
    hass: HomeAssistant, subentry: Any
) -> tuple[set[str], set[str], set[str]]:
    """
    Return expected monitoring, humidity, and aggregated unique_ids for a subentry.

    This encapsulates the logic used by the cleanup routine so the main
    cleanup function stays small and within complexity limits.

    Returns:
        Tuple of (expected_monitoring, expected_humidity, expected_aggregated)

    """
    expected_monitoring: set[str] = set()
    expected_humidity: set[str] = set()
    expected_aggregated: set[str] = set()

    if "device_id" not in getattr(subentry, "data", {}):
        return expected_monitoring, expected_humidity, expected_aggregated

    location_name = subentry.data.get("name", "Plant Location")
    location_name_safe = location_name.lower().replace(" ", "_")

    # Handle monitoring sensors
    monitoring_device_id = subentry.data.get("monitoring_device_id")
    if monitoring_device_id:
        try:
            device_sensors = _get_monitoring_device_sensors(hass, monitoring_device_id)
            for mapped_type, source_entity_id in device_sensors.items():
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

    # Handle aggregated location sensors
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

    return expected_monitoring, expected_humidity, expected_aggregated


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

        # Collect expected monitoring, humidity, and aggregated unique_ids
        # from subentries
        if entry.subentries:
            for subentry in entry.subentries.values():
                monitoring_set, humidity_set, aggregated_set = (
                    _expected_entities_for_subentry(hass, subentry)
                )
                expected_monitoring_entities.update(monitoring_set)
                expected_humidity_entities.update(humidity_set)
                expected_aggregated_entities.update(aggregated_set)

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
    """Set up the sensor platform (legacy)."""
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


async def async_setup_entry(  # noqa: PLR0915
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
            if humidity_entity_id:
                humidity_sensor = HumidityLinkedSensor(
                    hass=hass,
                    entry_id=subentry.subentry_id,
                    location_device_id=location_device_id,
                    location_name=location_name,
                    humidity_entity_id=humidity_entity_id,
                )
                subentry_entities.append(humidity_sensor)
                _LOGGER.debug(
                    "Added humidity linked sensor for entity %s at location %s",
                    humidity_entity_id,
                    location_name,
                )

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
                for sensor in mirrored_sensors:
                    if (
                        isinstance(sensor, MonitoringSensor)
                        and hasattr(sensor, "source_entity_id")
                        and "illuminance" in sensor.source_entity_id.lower()
                    ):
                        # Use source entity ID (mirrored entity_id not yet created)
                        illuminance_source_entity_id = sensor.source_entity_id
                        break

                if illuminance_source_entity_id:
                    # Create PPFD sensor (converts lux to μmol/m²/s)
                    ppfd_sensor = PlantLocationPpfdSensor(
                        hass=hass,
                        entry_id=subentry.subentry_id,
                        location_device_id=location_device_id,
                        location_name=location_name,
                        illuminance_entity_id=illuminance_source_entity_id,
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

                    _LOGGER.debug("Added DLI for %s", location_name)
                else:
                    _LOGGER.debug("No illuminance sensor for DLI at %s", location_name)

            # Add entities with proper subentry association (like openplantbook_ref)
            _LOGGER.debug(
                "Adding %d entities for subentry %s",
                len(subentry_entities),
                subentry_id,
            )
            # Note: config_subentry_id exists in HA 2025.8.3+ but not in type hint
            _add_entities = cast("Callable[..., Any]", async_add_entities)
            _add_entities(subentry_entities, config_subentry_id=subentry_id)
        _LOGGER.warning("Subentry %s missing device_id", subentry_id)
        return

    # Main entry aggregated sensors for locations (if no subentries)
    zones = entry.options.get("irrigation_zones", {})
    sensors.extend(
        [
            AggregatedSensor(hass, entry.entry_id, zone_id, loc_id, "min_light")
            for zone_id, zone in zones.items()
            for loc_id in zone.get("locations", {})
        ]
    )

    _LOGGER.info("Adding %d sensors for entry %s", len(sensors), entry.entry_id)
    async_add_entities(sensors)


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
        self.location_device_id = location_device_id
        device_name = config["device_name"]
        entity_name = config["entity_name"]
        sensor_type = config.get("sensor_type")

        # Set entity name to include device name for better entity_id formatting
        self._attr_name = f"{device_name} {entity_name}"

        # Generate unique_id using device name and sensor type suffix
        # Format: plant_assistant_<entry_id>_<device_name>_<sensor_type_suffix>
        if sensor_type and sensor_type in MONITORING_SENSOR_MAPPINGS:
            mapping: MonitoringSensorMapping = MONITORING_SENSOR_MAPPINGS[sensor_type]
            suffix = mapping.get("suffix", sensor_type)
        else:
            # Fallback to sanitized source entity id
            source_entity_safe = self.source_entity_id.replace(".", "_")
            suffix = f"monitor_{source_entity_safe}"

        # Create a safe device name for the unique_id
        device_name_safe = device_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{self.entry_id}_{device_name_safe}_{suffix}"

        self._state = None
        self._attributes = {}
        self._unsubscribe = None

        # Set device_class, icon, and unit from mappings if available
        if sensor_type and sensor_type in MONITORING_SENSOR_MAPPINGS:
            mapping_config: MonitoringSensorMapping = MONITORING_SENSOR_MAPPINGS[
                sensor_type
            ]
            device_class_val = mapping_config.get("device_class")
            if device_class_val:
                try:
                    self._attr_device_class = SensorDeviceClass(device_class_val)
                except ValueError:
                    self._attr_device_class = None
            self._attr_icon = mapping_config.get("icon")
            # Use unit from mapping if available, otherwise get from source
            unit = mapping_config.get("unit")
            if unit:
                self._attr_native_unit_of_measurement = unit

        # Initialize with current state of source entity
        if source_state := hass.states.get(self.source_entity_id):
            self._state = source_state.state
            self._attributes = dict(source_state.attributes)
            self._attributes["source_entity"] = self.source_entity_id

            # If no unit was set from mapping, try to get it from source entity
            if not hasattr(self, "_attr_native_unit_of_measurement"):
                source_unit = source_state.attributes.get("unit_of_measurement")
                if source_unit:
                    self._attr_native_unit_of_measurement = source_unit

        # Subscribe to source entity state changes
        try:
            self._unsubscribe = async_track_state_change(
                hass, self.source_entity_id, self._source_state_changed
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to source entity %s: %s",
                self.source_entity_id,
                exc,
            )

    @callback
    def _source_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle source entity state changes."""
        if new_state is None:
            self._state = None
            self._attributes = {}
        else:
            self._state = new_state.state
            self._attributes = dict(new_state.attributes)
            # Add reference to source
            self._attributes["source_entity"] = self.source_entity_id

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


class HumidityLinkedSensor(SensorEntity):
    """A sensor that mirrors data from a humidity entity linked to a location."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        humidity_entity_id: str,
    ) -> None:
        """
        Initialize the humidity linked sensor.

        Args:
            hass: The Home Assistant instance.
            entry_id: The subentry ID.
            location_device_id: The device ID of the location.
            location_name: The name of the location.
            humidity_entity_id: The entity ID of the humidity sensor to mirror.

        """
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self.humidity_entity_id = humidity_entity_id

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

        # Initialize with current state of humidity entity
        if humidity_state := hass.states.get(self.humidity_entity_id):
            self._state = humidity_state.state
            self._attributes = dict(humidity_state.attributes)
            self._attributes["source_entity"] = self.humidity_entity_id

            # Use unit from source entity if available
            source_unit = humidity_state.attributes.get("unit_of_measurement")
            if source_unit:
                self._attr_native_unit_of_measurement = source_unit

        # Subscribe to humidity entity state changes
        try:
            self._unsubscribe = async_track_state_change(
                hass, self.humidity_entity_id, self._humidity_state_changed
            )
        except (AttributeError, KeyError, ValueError) as exc:
            _LOGGER.warning(
                "Failed to subscribe to humidity entity %s: %s",
                self.humidity_entity_id,
                exc,
            )

    @callback
    def _humidity_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle humidity entity state changes."""
        if new_state is None:
            self._state = None
            self._attributes = {}
        else:
            self._state = new_state.state
            self._attributes = dict(new_state.attributes)
            # Add reference to source
            self._attributes["source_entity"] = self.humidity_entity_id

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

        result = None
        if aggregation_type == "max_of_mins" and plant_attr_min:
            result = aggregation.max_of_mins(plants, plant_attr_min)
            _LOGGER.debug(
                "Computed max_of_mins for %s using key '%s': %s",
                self.metric_key,
                plant_attr_min,
                result,
            )
        elif aggregation_type == "min_of_maximums" and plant_attr_max:
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
                self._unsubscribe = async_track_state_change(
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
        self._unsubscribe = None
        self._plant_entity_ids: list[str] | None = None

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
                self._unsubscribe = async_track_state_change(
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

        plant_entity_ids.extend(
            eid
            for ent in getattr(ent_reg, "entities", {}).values()
            if self._is_matching_sensor_entity(ent, device.id)
            and (eid := getattr(ent, "entity_id", None))
        )

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

        return [
            entity_id
            for st in states_all
            if self._state_matches_criteria(st, mon_device_id)
            and (entity_id := getattr(st, "entity_id", None))
        ]

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

        self._plant_entity_ids = plant_entity_ids
        try:
            self._unsubscribe = async_track_state_change(
                self.hass, plant_entity_ids, self._state_changed
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

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        location_device_id: str,
        location_name: str,
        illuminance_entity_id: str,
    ) -> None:
        """Initialize the PPFD sensor."""
        self.hass = hass
        self.entry_id = entry_id
        self.location_device_id = location_device_id
        self._illuminance_entity_id = illuminance_entity_id

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
    def _illuminance_state_changed(
        self, _entity_id: str, _old_state: Any, new_state: Any
    ) -> None:
        """Handle illuminance sensor state changes."""
        if new_state is None:
            self._state = None
        else:
            self._state = self._ppfd_from_lux(new_state.state)

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to illuminance sensor state changes."""
        try:
            self._unsubscribe = async_track_state_change(
                self.hass, self._illuminance_entity_id, self._illuminance_state_changed
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
        self._unit_of_measurement = UNIT_DLI
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

    def _unit(self, source_unit: str) -> str:
        """Override unit to return DLI unit."""
        # source_unit parameter not used; keep to match IntegrationSensor API
        _ = source_unit
        return self._unit_of_measurement or UNIT_DLI

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
            name=f"{location_name} {READING_DLI}",
            net_consumption=None,
            parent_meter=entry_id,
            source_entity=total_integral_sensor.entity_id,
            tariff_entity=None,
            tariff=None,
            unique_id=f"{location_name.lower().replace(' ', '_')}_dli",
            sensor_always_available=True,
            suggested_entity_id=None,
            periodically_resetting=True,
        )
        self._unit_of_measurement = UNIT_DLI
        self._attr_icon = ICON_DLI
        self._attr_suggested_display_precision = 2
        self.location_device_id = location_device_id

        # Generate a concise entity_id (e.g. sensor.green_dli)
        self.entity_id = async_generate_entity_id(
            "sensor.{}",
            f"{location_name} {READING_DLI}".lower().replace(" ", "_"),
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
