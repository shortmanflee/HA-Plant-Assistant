"""
Plant Assistant integration.

Minimal implementation to provide a safe foundation for further development.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import device as device_helper
from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant import config_entries
    from homeassistant.core import HomeAssistant

# Entity monitor is now handled per-sensor (like HA-Battery-Notes approach)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, _config: dict[str, Any]) -> bool:
    """Set up the Plant Assistant integration (legacy YAML)."""
    hass.data.setdefault(DOMAIN, {})
    return True


PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.DATETIME,
    Platform.SWITCH,
    Platform.NUMBER,
]


async def async_setup_location_subentry(
    hass: HomeAssistant, entry: config_entries.ConfigEntry[Any]
) -> bool:
    """Set up a location device subentry."""
    _LOGGER.debug("Setting up subentry: %s (ID: %s)", entry.title, entry.entry_id)

    try:
        hass.data.setdefault(DOMAIN, {})

        # Device creation is handled by sensor platform when processing subentries
        # This avoids duplication since subentries are processed by main entry

        _LOGGER.debug("Subentry setup for: %s (ID: %s)", entry.title, entry.entry_id)

        # Store entry data for reference
        hass.data.setdefault(DOMAIN, {}).setdefault("entries", {})[entry.entry_id] = (
            entry.data
        )

        # Set up sensor platforms (device is now already created)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        _LOGGER.exception(
            "Failed to set up location subentry '%s'",
            entry.title,
        )
        return False
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: config_entries.ConfigEntry[Any]
) -> bool:  # pragma: no cover - requires HA runtime
    """Set up a config entry for Plant Assistant."""
    _LOGGER.info(
        "Setting up Plant Assistant entry: %s (ID: %s), Data: %s",
        entry.title,
        entry.entry_id,
        entry.data,
    )

    hass.data.setdefault(DOMAIN, {})

    # Check if this is a location device subentry
    entry_data = getattr(entry, "data", {})
    has_parent_entry_id = "parent_entry_id" in entry_data

    _LOGGER.debug(
        "Setting up entry - ID: %s, Title: %s, Is subentry: %s",
        entry.entry_id,
        entry.title,
        has_parent_entry_id,
    )

    if has_parent_entry_id:
        _LOGGER.debug(
            "Detected subentry - delegating to subentry setup for entry %s",
            entry.entry_id,
        )
        # Perform migration: capture unique_ids for existing configs
        await _migrate_subentry_unique_ids(hass, entry)
        return await async_setup_location_subentry(hass, entry)

    # This is a main Plant Assistant entry
    # Ensure water events storage
    hass.data[DOMAIN].setdefault("water_events", [])

    # Entity monitoring is now handled per-sensor (like HA-Battery-Notes approach)

    # Handle device association if a device was selected during setup
    if linked_device_id := getattr(entry, "data", {}).get("linked_device_id"):
        await device_helper.async_add_to_existing_device(hass, entry, linked_device_id)

    # If options include irrigation_zones, handle devices
    zones_dict = entry.options.get("irrigation_zones", {})
    zone_devices = {}  # Keep track of created zone devices for subentries to reference

    for zone_id, zone in zones_dict.items():
        zone_device = device_helper.async_get_or_create_zone_device(hass, entry, zone)
        zone_devices[zone_id] = zone_device  # Store for later use

        locations_dict = zone.get("locations", {})
        for loc in locations_dict.values():
            # Skip locations that have sub-entries (they're handled separately)
            if "sub_entry_id" not in loc:
                device_helper.async_get_or_create_location_device(
                    hass,
                    entry,
                    zone_device,
                    {"zone_id": zone.get("id"), "location": loc},
                )

                # Handle monitoring device association for existing locations
                if monitoring_device_id := loc.get("monitoring_device_id"):
                    await device_helper.async_add_to_existing_device(
                        hass, entry, monitoring_device_id
                    )

    # Devices for subentries are created by platforms using config_subentry_id
    # This ensures proper device registry association and avoids duplication

    # Keep options snapshot for sensors to reference
    hass.data.setdefault(DOMAIN, {}).setdefault("entries", {})[entry.entry_id] = (
        entry.options
    )

    # Set up options update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # Forward setup to all platforms (use plural API) - devices are now created
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_update_options(
    hass: HomeAssistant, entry: config_entries.ConfigEntry[Any]
) -> None:
    """Handle options update."""
    # Update the stored options for sensors to reference
    hass.data.setdefault(DOMAIN, {}).setdefault("entries", {})[entry.entry_id] = (
        entry.options
    )

    # Reload the integration when options change
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: config_entries.ConfigEntry[Any]
) -> bool:  # pragma: no cover - requires HA runtime
    """Unload a config entry."""
    # Remove this entry's data
    domain_data = hass.data.get(DOMAIN, {})
    entries_data = domain_data.get("entries", {})
    entries_data.pop(entry.entry_id, None)

    # Only clear domain data if no other entries exist
    if not entries_data:
        # Entity monitoring cleanup is handled per-sensor
        hass.data.pop(DOMAIN, None)

    result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return bool(result)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: config_entries.ConfigEntry[Any]
) -> dict[str, Any]:  # pragma: no cover - runtime-only
    """
    Return diagnostics for the config entry.

    Provide the raw entry options and a best-effort mapping of locations to
    plant entity ids by consulting the entity registry / device registry if
    available, otherwise scanning states for `plant_id` attributes.
    """
    diagnostics: dict[str, Any] = {"options": entry.options}

    try:
        mappings = _build_diagnostics_mappings(hass, entry)
        diagnostics["mappings"] = mappings
    except (
        AttributeError,
        KeyError,
        ValueError,
    ) as exc:  # pragma: no cover - best-effort
        diagnostics["mappings_error"] = str(exc)

    return diagnostics


def _build_diagnostics_mappings(
    hass: HomeAssistant, entry: config_entries.ConfigEntry[Any]
) -> dict[str, list[str]]:
    """Build diagnostics mappings for the config entry."""
    mappings = {}
    ent_reg = None
    dev_reg = None
    try:
        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)
    except (AttributeError, KeyError):
        ent_reg = None
        dev_reg = None

    entry_opts = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id, {})
    zones_dict = entry_opts.get("irrigation_zones", {}) or {}
    for z in zones_dict.values():
        locations_dict = z.get("locations", {}) or {}
        for loc in locations_dict.values():
            mon = loc.get("monitoring_device_id")
            found: list[str] = []
            if mon and ent_reg and dev_reg:
                # try to resolve device
                try:
                    device = dev_reg.async_get_device({("plant_assistant", mon)})
                except (AttributeError, KeyError, ValueError):
                    device = None
                if device:
                    found.extend(
                        ent.entity_id
                        for ent in ent_reg.entities.values()
                        if ent.device_id == device.id and ent.domain == "sensor"
                    )

            if not found:
                # scan states
                states_all = []
                if hasattr(hass.states, "async_all"):
                    states_all = hass.states.async_all("sensor")
                else:
                    states_all = list(getattr(hass.states, "_states", {}).values())

                for st in states_all:
                    attrs = getattr(st, "attributes", {}) or {}
                    if (
                        attrs.get("plant_id") is not None
                        or (mon and attrs.get("device_id") == mon)
                    ) and (entity_id := getattr(st, "entity_id", None)):
                        found.append(entity_id)

            mappings[f"{z.get('id')}/{loc.get('id')}"] = list(dict.fromkeys(found))

    return mappings


async def _migrate_subentry_unique_ids(
    hass: HomeAssistant, entry: config_entries.ConfigEntry[Any]
) -> None:
    """
    Migrate subentry config to include unique_ids for entity references.

    This provides backward compatibility by capturing unique_ids for existing
    entity_id references, allowing the system to handle entity renames.
    """
    try:
        entity_registry = er.async_get(hass)
        if entity_registry is None:
            return

        data = dict(entry.data)
        updated = False

        # Migrate humidity_entity_id to include unique_id
        if (humidity_entity_id := data.get("humidity_entity_id")) and (
            "humidity_entity_unique_id" not in data
        ):  # Only if not already migrated
            try:
                entity_entry = entity_registry.async_get(humidity_entity_id)
                if entity_entry and entity_entry.unique_id:
                    data["humidity_entity_unique_id"] = entity_entry.unique_id
                    updated = True
                    _LOGGER.debug(
                        "Migrated humidity_entity_unique_id for entry %s: %s",
                        entry.entry_id,
                        entity_entry.unique_id,
                    )
            except (AttributeError, KeyError, ValueError):
                pass

        if updated:
            hass.config_entries.async_update_entry(entry, data=data)

    except Exception:
        _LOGGER.exception(
            "Error migrating subentry unique_ids for entry %s", entry.entry_id
        )
