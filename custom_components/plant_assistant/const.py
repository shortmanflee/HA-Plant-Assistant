"""Constants for the Plant Assistant integration."""

from __future__ import annotations

DOMAIN = "plant_assistant"

# Storage
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.storage"

# Services
SERVICE_REPLACE_MONITORING_DEVICE = "replace_monitoring_device"
SERVICE_REORDER_PLANTS = "reorder_plants"
SERVICE_EXPORT_CONFIG = "export_config"
SERVICE_IMPORT_CONFIG = "import_config"

# Sensor types
SENSOR_LOCATION_COUNT = "location_count"
SENSOR_PLANT_COUNT = "plant_count"
SENSOR_MIN_LIGHT = "min_light"
SENSOR_MAX_LIGHT = "max_light"
SENSOR_MIN_TEMPERATURE = "min_temperature"
SENSOR_MAX_TEMPERATURE = "max_temperature"
SENSOR_MIN_ILLUMINANCE = "min_illuminance"
SENSOR_MAX_ILLUMINANCE = "max_illuminance"
SENSOR_MIN_MOISTURE = "min_moisture"
SENSOR_MAX_MOISTURE = "max_moisture"
SENSOR_MIN_SOIL_MOISTURE = "min_soil_moisture"
SENSOR_MAX_SOIL_MOISTURE = "max_soil_moisture"
SENSOR_MIN_CONDUCTIVITY = "min_conductivity"
SENSOR_MAX_CONDUCTIVITY = "max_conductivity"
SENSOR_MIN_SOIL_CONDUCTIVITY = "min_soil_conductivity"
SENSOR_MAX_SOIL_CONDUCTIVITY = "max_soil_conductivity"
SENSOR_MIN_HUMIDITY = "min_humidity"
SENSOR_MAX_HUMIDITY = "max_humidity"
SENSOR_PPFD = "ppfd"
SENSOR_DLI_INTEGRAL = "dli_integral"
SENSOR_DLI = "dli"
SENSOR_MIN_DLI = "min_dli"
SENSOR_MAX_DLI = "max_dli"

# Config flow steps
STEP_USER = "user"
STEP_DEVICE_SELECTION = "device_selection"
STEP_MANUAL_NAME = "manual_name"
STEP_INITIAL_ZONE = "initial_zone"
STEP_INITIAL_DEVICE = "initial_device"
STEP_INIT = "init"
STEP_ADD_ZONE = "add_zone"
STEP_EDIT_ZONE = "edit_zone"
STEP_SELECT_ZONE = "select_zone"

STEP_MANAGE_LOCATIONS = "manage_locations"
STEP_ADD_LOCATION = "add_location"
STEP_EDIT_LOCATION = "edit_location"
STEP_SELECT_LOCATION = "select_location"
STEP_SELECT_LOCATION_FOR_DELETE = "select_location_for_delete"

STEP_LINK_HUMIDITY_ENTITY = "link_humidity_entity"
STEP_MANAGE_SLOTS = "manage_slots"
STEP_ADD_SLOT = "add_slot"
STEP_EDIT_SLOT = "edit_slot"
STEP_SELECT_SLOT = "select_slot"
STEP_REORDER_SLOTS = "reorder_slots"
STEP_DELETE_ZONE = "delete_zone"
STEP_DELETE_LOCATION = "delete_location"
STEP_DELETE_SLOT = "delete_slot"


# Config flow actions
ACTION_ADD_ZONE = "add_zone"
ACTION_EDIT_ZONE = "edit_zone"
ACTION_DELETE_ZONE = "delete_zone"

ACTION_MANAGE_LOCATIONS = "manage_locations"
ACTION_ADD_LOCATION = "add_location"
ACTION_EDIT_LOCATION = "edit_location"
ACTION_DELETE_LOCATION = "delete_location"
ACTION_REORDER_LOCATIONS = "reorder_locations"
ACTION_MANAGE_SLOTS = "manage_slots"
ACTION_ADD_SLOT = "add_slot"
ACTION_EDIT_SLOT = "edit_slot"
ACTION_DELETE_SLOT = "delete_slot"
ACTION_REORDER_SLOTS = "reorder_slots"

# Data schema keys
CONF_NAME = "name"
CONF_LINKED_DEVICE_ID = "linked_device_id"
CONF_MONITORING_DEVICE_ID = "monitoring_device_id"
CONF_HUMIDITY_ENTITY_ID = "humidity_entity_id"
CONF_HUMIDITY_ENTITY_UNIQUE_ID = "humidity_entity_unique_id"
CONF_PLANT_DEVICE_ID = "plant_device_id"
CONF_SLOT_NAME = "slot_name"
CONF_ZONE_ID = "zone_id"
CONF_LOCATION_ID = "location_id"
CONF_SLOT_ID = "slot_id"
CONF_ACTION = "action"
CONF_ORDER = "order"

# Unique ID fields for entity references (entity rename resilience)
CONF_MASTER_SCHEDULE_SWITCH_UNIQUE_ID = "master_schedule_switch_unique_id"
CONF_SUNRISE_SWITCH_UNIQUE_ID = "sunrise_switch_unique_id"
CONF_AFTERNOON_SWITCH_UNIQUE_ID = "afternoon_switch_unique_id"
CONF_SUNSET_SWITCH_UNIQUE_ID = "sunset_switch_unique_id"
CONF_ALLOW_RAIN_WATER_DELIVERY_SWITCH_UNIQUE_ID = (
    "allow_rain_water_delivery_switch_unique_id"
)
CONF_ALLOW_WATER_MAIN_DELIVERY_SWITCH_UNIQUE_ID = (
    "allow_water_main_delivery_switch_unique_id"
)
CONF_SOIL_MOISTURE_ENTITY_UNIQUE_ID = "soil_moisture_entity_unique_id"

# Limits
MAX_PLANT_SLOTS = 20

# Device info
MANUFACTURER = "Plant Assistant"
MODEL_IRRIGATION_ZONE = "Irrigation Zone"
MODEL_PLANT_LOCATION = "Plant Location"

# Dependencies
OPENPLANTBOOK_DOMAIN = "openplantbook_ref"

# Daily Light Integral (DLI) Constants
# Conversion factors
# Standard conversion from lux to μmol/m²/s. To obtain mol/s⋅m² divide
# the μmol/m²/s value by 1_000_000.
DEFAULT_LUX_TO_PPFD = 0.0185
PPFD_DLI_FACTOR = 0.000001  # Convert PPFD integral (μmol/m²) to DLI (mol/m²/d)

# DLI Units and Icons
UNIT_PPFD = "mol/m²/s"  # Photosynthetic Photon Flux Density
UNIT_PPFD_INTEGRAL = "mol/m²/d"  # PPFD Integral (same as DLI for utility meter)
UNIT_DLI = "mol/m²/d"  # Daily Light Integral
ICON_PPFD = "mdi:white-balance-sunny"
ICON_DLI = "mdi:counter"

# DLI sensor types
# Human-friendly reading name for PPFD (capitalized for display).
# Keep short tokens/unique ids lowercase elsewhere.
READING_PPFD = "PPFD"
READING_DLI = "dli"

# Friendly display name for Daily Light Integral and a slug for entity ids
READING_DLI_NAME = "Daily Light Integral"
READING_DLI_SLUG = "daily_light_integral"

# Weekly Average DLI sensor
READING_WEEKLY_AVG_DLI_NAME = "Daily Light Integral Weekly Average"
READING_WEEKLY_AVG_DLI_SLUG = "daily_light_integral_weekly_average"

# Prior Period DLI sensor (yesterday's DLI)
READING_PRIOR_PERIOD_DLI_NAME = "Daily Light Integral Prior Period"
READING_PRIOR_PERIOD_DLI_SLUG = "daily_light_integral_prior_period"

# Attribute keys
MONITORING_SENSOR_MAPPINGS = {
    "temperature": {
        "device_class": "temperature",
        "suffix": "temperature_mirror",
        "icon": "mdi:thermometer",
        "name": "Temperature",
        "unit": "°C",
    },
    "illuminance": {
        "device_class": "illuminance",
        "suffix": "illuminance_mirror",
        "icon": "mdi:brightness-6",
        "name": "Illuminance",
        "unit": "lx",
    },
    "soil_moisture": {
        "device_class": "moisture",
        "suffix": "soil_moisture_mirror",
        "icon": "mdi:water-percent",
        "name": "Soil Moisture",
        "unit": "%",
    },
    "soil_conductivity": {
        "device_class": "conductivity",
        "suffix": "soil_conductivity_mirror",
        "icon": "mdi:flash",
        "name": "Soil Conductivity",
        "unit": "µS/cm",
        "unit_pattern": [
            "µS/cm",
            "μS/cm",
            "uS/cm",
            "S/m",
        ],  # Match common conductivity units as backup
    },
    "battery": {
        "device_class": "battery",
        "suffix": "monitor_battery_level",
        "icon": "mdi:battery",
        "name": "Monitor Battery Level",
        "unit": "%",
    },
    "signal_strength": {
        "device_class": "signal_strength",
        "suffix": "monitor_signal_strength",
        "icon": "mdi:wifi",
        "name": "Monitor Signal Strength",
        "unit": "dBm",
    },
}

# Aggregated sensor mappings for plant location aggregation
#
# Note: each mapping must expose a unique `suffix` value. Duplicated suffixes
# lead to ambiguities when constructing entity unique_ids and make the
# configuration harder to maintain.
AGGREGATED_SENSOR_MAPPINGS = {
    # Environmental sensors (require monitoring device + plant slots)
    "min_light": {
        "plant_attr_min": "minimum_light",
        "plant_attr_max": "maximum_light",
        "aggregation_type": "max_of_mins",  # Max of all minimum light values
        "suffix": "min_light_intensity",
        "icon": "mdi:brightness-7",
        "name": "Minimum Light Intensity",
        "device_class": "illuminance",
        "unit": "lx",
        "requires_monitoring": True,
        "requires_humidity": False,
    },
    "max_light": {
        "plant_attr_min": "minimum_light",
        "plant_attr_max": "maximum_light",
        "aggregation_type": "min_of_maximums",  # Min of all maximum light values
        "suffix": "max_light_intensity",
        "icon": "mdi:brightness-5",
        "name": "Maximum Light Intensity",
        "device_class": "illuminance",
        "unit": "lx",
        "requires_monitoring": True,
        "requires_humidity": False,
    },
    "min_temperature": {
        "plant_attr_min": "minimum_temperature",
        "plant_attr_max": "maximum_temperature",
        "aggregation_type": "max_of_mins",
        "suffix": "min_temperature",
        "icon": "mdi:thermometer-low",
        "name": "Minimum Temperature",
        "device_class": "temperature",
        "unit": "°C",
        "requires_monitoring": True,
        "requires_humidity": False,
    },
    "max_temperature": {
        "plant_attr_min": "minimum_temperature",
        "plant_attr_max": "maximum_temperature",
        "aggregation_type": "min_of_maximums",
        "suffix": "max_temperature",
        "icon": "mdi:thermometer-high",
        "name": "Maximum Temperature",
        "device_class": "temperature",
        "unit": "°C",
        "requires_monitoring": True,
        "requires_humidity": False,
    },
    "min_illuminance": {
        "plant_attr_min": "minimum_light",
        "plant_attr_max": "maximum_light",
        "aggregation_type": "max_of_mins",
        "suffix": "min_illuminance",
        "icon": "mdi:brightness-7",
        "name": "Minimum Illuminance",
        "device_class": "illuminance",
        "unit": "lx",
        "requires_monitoring": True,
        "requires_humidity": False,
    },
    "max_illuminance": {
        "plant_attr_min": "minimum_light",
        "plant_attr_max": "maximum_light",
        "aggregation_type": "min_of_maximums",
        "suffix": "max_illuminance",
        "icon": "mdi:brightness-5",
        "name": "Maximum Illuminance",
        "device_class": "illuminance",
        "unit": "lx",
        "requires_monitoring": True,
        "requires_humidity": False,
    },
    "min_soil_moisture": {
        "plant_attr_min": "minimum_moisture",
        "plant_attr_max": "maximum_moisture",
        "aggregation_type": "max_of_mins",
        "suffix": "min_soil_moisture",
        "icon": "mdi:water-percent",
        "name": "Minimum Soil Moisture",
        "device_class": "moisture",
        "unit": "%",
        "requires_monitoring": True,
        "requires_humidity": False,
    },
    "max_soil_moisture": {
        "plant_attr_min": "minimum_moisture",
        "plant_attr_max": "maximum_moisture",
        "aggregation_type": "min_of_maximums",
        "suffix": "max_soil_moisture",
        "icon": "mdi:water-percent",
        "name": "Maximum Soil Moisture",
        "device_class": "moisture",
        "unit": "%",
        "requires_monitoring": True,
        "requires_humidity": False,
    },
    "min_soil_conductivity": {
        "plant_attr_min": "minimum_soil_ec",
        "plant_attr_max": "maximum_soil_ec",
        "aggregation_type": "max_of_mins",
        "suffix": "min_soil_conductivity",
        "icon": "mdi:flash-triangle",
        "name": "Minimum Soil Conductivity",
        "device_class": "conductivity",
        "unit": "µS/cm",
        "requires_monitoring": True,
        "requires_humidity": False,
    },
    "max_soil_conductivity": {
        "plant_attr_min": "minimum_soil_ec",
        "plant_attr_max": "maximum_soil_ec",
        "aggregation_type": "min_of_maximums",
        "suffix": "max_soil_conductivity",
        "icon": "mdi:flash-triangle-outline",
        "name": "Maximum Soil Conductivity",
        "device_class": "conductivity",
        "unit": "µS/cm",
        "requires_monitoring": True,
        "requires_humidity": False,
    },
    "min_humidity": {
        "plant_attr_min": "minimum_humidity",
        "plant_attr_max": "maximum_humidity",
        "aggregation_type": "max_of_mins",
        "suffix": "min_humidity",
        "icon": "mdi:water-minus",
        "name": "Minimum Humidity",
        "device_class": "humidity",
        "unit": "%",
        "requires_monitoring": False,
        "requires_humidity": True,
    },
    "max_humidity": {
        "plant_attr_min": "minimum_humidity",
        "plant_attr_max": "maximum_humidity",
        "aggregation_type": "min_of_maximums",
        "suffix": "max_humidity",
        "icon": "mdi:water-plus",
        "name": "Maximum Humidity",
        "device_class": "humidity",
        "unit": "%",
        "requires_monitoring": False,
        "requires_humidity": True,
    },
    # DLI aggregation sensors (derived from illuminance values)
    "min_dli": {
        "plant_attr_min": "minimum_light",
        "plant_attr_max": "maximum_light",
        "aggregation_type": "max_of_mins",  # Max of all minimum DLI values
        "suffix": "min_dli",
        "icon": ICON_DLI,
        "name": "Minimum Daily Light Integral",
        "device_class": None,  # No standard device class for DLI
        "unit": UNIT_DLI,
        "requires_monitoring": True,
        "requires_humidity": False,
        "convert_illuminance_to_dli": True,  # Convert lux to DLI
    },
    "max_dli": {
        "plant_attr_min": "minimum_light",
        "plant_attr_max": "maximum_light",
        "aggregation_type": "min_of_maximums",  # Min of all maximum DLI values
        "suffix": "max_dli",
        "icon": ICON_DLI,
        "name": "Maximum Daily Light Integral",
        "device_class": None,  # No standard device class for DLI
        "unit": UNIT_DLI,
        "requires_monitoring": True,
        "requires_humidity": False,
        "convert_illuminance_to_dli": True,  # Convert lux to DLI
    },
}

# Attribute keys
ATTR_SOURCE_PLANT_DEVICE_IDS = "source_plant_device_ids"
ATTR_LAST_UPDATE = "last_update"
ATTR_LOCATION_DEVICE_IDS = "location_device_ids"
ATTR_PLANT_DEVICE_IDS = "plant_device_ids"

# Entity monitoring
ENTITY_MONITOR_KEY = "entity_monitor"
