"""Tests to ensure AGGREGATED_SENSOR_MAPPINGS is well-formed.

These tests prevent accidental duplication of aggregated sensor configuration
(e.g. two keys that produce the same entity suffix), which can lead to
confusion and maintenance issues.
"""

from custom_components.plant_assistant.const import AGGREGATED_SENSOR_MAPPINGS


def test_aggregated_sensor_suffixes_unique():
    """Each aggregated metric should expose a unique `suffix`.

    Duplicated suffixes are a common source of confusion (they mean two
    different metric keys would create the same entity suffix). Catch this
    early.
    """
    suffixes = [
        cfg.get("suffix")
        for cfg in AGGREGATED_SENSOR_MAPPINGS.values()
        if cfg.get("suffix")
    ]
    duplicates = {s for s in suffixes if suffixes.count(s) > 1}
    assert not duplicates, (
        f"Duplicate suffixes found in AGGREGATED_SENSOR_MAPPINGS: {duplicates}"
    )


def test_min_temperature_suffix_unique():
    """Ensure the min_temperature suffix only appears once in the mapping.

    This directly addresses the reviewer comment about duplication of the
    min_temperature configuration.
    """
    keys_with_min_temp_suffix = [
        k
        for k, cfg in AGGREGATED_SENSOR_MAPPINGS.items()
        if cfg.get("suffix") == "min_temperature"
    ]
    assert len(keys_with_min_temp_suffix) == 1, (
        "Found multiple aggregated mappings that use the 'min_temperature' "
        f"suffix: {keys_with_min_temp_suffix}"
    )
