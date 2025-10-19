"""Device registry helpers for Plant Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import device_registry as dr

from .const import DOMAIN


def async_get_or_create_zone_device(hass: Any, entry: Any, zone: dict[str, Any]) -> Any:
    """Get or create a device for an irrigation zone."""
    device_registry = dr.async_get(hass)

    # If the zone has a linked device ID, use that existing device
    if (linked_device_id := zone.get("linked_device_id")) and (
        existing_device := device_registry.async_get(linked_device_id)
    ):
        # Associate this config entry with the existing device
        device_registry.async_update_device(
            linked_device_id, add_config_entry_id=entry.entry_id
        )
        return existing_device

    # Otherwise, create a new device
    identifiers = {(DOMAIN, f"{entry.entry_id}_zone_{zone['id']}")}
    return device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=identifiers,
        manufacturer="Plant Assistant",
        name=zone.get("name") or f"Zone {zone['id']}",
        model="Irrigation Zone",
    )


def async_get_or_create_location_device(
    hass: Any,
    entry: Any,
    zone_device: Any,
    location_config: dict[str, Any],
    via_device: tuple[str, str] | None = None,
) -> Any:
    """Get or create a device for a plant location."""
    device_registry = dr.async_get(hass)
    zone_id = location_config["zone_id"]
    loc = location_config["location"]
    identifiers = {(DOMAIN, f"{entry.entry_id}_zone_{zone_id}_loc_{loc['id']}")}

    # Use provided via_device (identifier tuple) or extract from zone_device
    if via_device is None and zone_device and zone_device.identifiers:
        via_device = next(iter(zone_device.identifiers))

    return device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=identifiers,
        via_device=via_device,
        manufacturer="Plant Assistant",
        name=loc.get("name") or f"Location {loc['id']}",
        model="Plant Location",
    )


def async_get_or_create_monitoring_device(
    hass: Any,
    entry: Any,
    loc: dict[str, Any],
    zone_id: str,
    location_device: Any = None,
) -> Any:
    """Get or create a monitoring device for a location."""
    device_registry = dr.async_get(hass)

    # If the location has a monitoring device ID, use that existing device
    if (monitoring_device_id := loc.get("monitoring_device_id")) and (
        existing_device := device_registry.async_get(monitoring_device_id)
    ):
        # Associate this config entry with the existing device
        device_registry.async_update_device(
            monitoring_device_id, add_config_entry_id=entry.entry_id
        )
        return existing_device

    # Determine via_device for hierarchy (link to location device)
    via_device = None
    if location_device and location_device.identifiers:
        via_device = next(iter(location_device.identifiers))

    # Otherwise, create a new monitoring device for this location
    identifiers = {(DOMAIN, f"{entry.entry_id}_zone_{zone_id}_loc_{loc['id']}_monitor")}
    return device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=identifiers,
        via_device=via_device,
        manufacturer="Plant Assistant",
        name=f"{loc.get('name', f'Location {loc["id"]}')} Monitor",
        model="Plant Location Monitor",
    )


async def async_add_to_existing_device(hass: Any, entry: Any, device_id: str) -> None:
    """Associate this config entry with an existing device."""
    device_registry = dr.async_get(hass)

    if device_registry.async_get(device_id):
        device_registry.async_update_device(
            device_id, add_config_entry_id=entry.entry_id
        )
