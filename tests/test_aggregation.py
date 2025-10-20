"""Unit tests for aggregation functions."""

from custom_components.plant_assistant import aggregation


def test_aggregation_full_data():
    plants = [
        {"id": "p1", "light": 100, "humidity": 40},
        {"id": "p2", "light": 200, "humidity": 50},
        {"id": "p3", "light": 150, "humidity": 45},
    ]

    assert aggregation.min_metric(plants, "light") == 100
    assert aggregation.max_metric(plants, "light") == 200
    assert aggregation.avg_metric(plants, "light") == 150


def test_aggregation_missing_metrics():
    plants = [
        {"id": "p1", "light": None},
        {"id": "p2"},
        {"id": "p3", "light": 50},
    ]

    assert aggregation.min_metric(plants, "light") == 50
    assert aggregation.max_metric(plants, "light") == 50
    assert aggregation.avg_metric(plants, "light") == 50


def test_aggregation_empty_list():
    plants = []
    assert aggregation.min_metric(plants, "light") is None
    assert aggregation.max_metric(plants, "light") is None
    assert aggregation.avg_metric(plants, "light") is None


def test_aggregation_non_numeric_values():
    plants = [
        {"id": "p1", "light": "100"},
        {"id": "p2", "light": "not-a-number"},
        {"id": "p3", "light": None},
    ]

    assert aggregation.min_metric(plants, "light") == 100.0
    assert aggregation.max_metric(plants, "light") == 100.0
    assert aggregation.avg_metric(plants, "light") == 100.0


def test_aggregation_large_input():
    plants = [{"id": f"p{i}", "light": i} for i in range(1000)]
    assert aggregation.min_metric(plants, "light") == 0
    assert aggregation.max_metric(plants, "light") == 999
    assert aggregation.avg_metric(plants, "light") == sum(range(1000)) / 1000


def test_aggregation_nan_and_infinite_values():
    plants = [
        {"id": "p1", "light": float("nan")},
        {"id": "p2", "light": float("inf")},
        {"id": "p3", "light": 10},
    ]

    assert aggregation.min_metric(plants, "light") == 10
    assert aggregation.max_metric(plants, "light") == 10
    assert aggregation.avg_metric(plants, "light") == 10


def test_aggregation_all_non_numeric():
    plants = [{"id": "p1", "light": "a"}, {"id": "p2", "light": None}]
    assert aggregation.min_metric(plants, "light") is None
    assert aggregation.max_metric(plants, "light") is None
    assert aggregation.avg_metric(plants, "light") is None


def test_max_of_mins():
    """Test max_of_mins aggregation."""
    plants = [
        {"id": "p1", "minimum_light": 100},
        {"id": "p2", "minimum_light": 200},
        {"id": "p3", "minimum_light": 150},
    ]

    # Should return the maximum of the minimums (most restrictive minimum)
    assert aggregation.max_of_mins(plants, "minimum_light") == 200


def test_max_of_mins_with_missing_values():
    """Test max_of_mins with some missing values."""
    plants = [
        {"id": "p1", "minimum_light": 100},
        {"id": "p2"},
        {"id": "p3", "minimum_light": 150},
    ]

    assert aggregation.max_of_mins(plants, "minimum_light") == 150


def test_max_of_mins_empty():
    """Test max_of_mins with empty list."""
    assert aggregation.max_of_mins([], "minimum_light") is None


def test_min_of_maxs():
    """Test min_of_maxs aggregation."""
    plants = [
        {"id": "p1", "maximum_light": 1000},
        {"id": "p2", "maximum_light": 800},
        {"id": "p3", "maximum_light": 900},
    ]

    # Should return the minimum of the maximums (most restrictive maximum)
    assert aggregation.min_of_maxs(plants, "maximum_light") == 800


def test_min_of_maxs_with_missing_values():
    """Test min_of_maxs with some missing values."""
    plants = [
        {"id": "p1", "maximum_light": 1000},
        {"id": "p2"},
        {"id": "p3", "maximum_light": 900},
    ]

    assert aggregation.min_of_maxs(plants, "maximum_light") == 900


def test_min_of_maxs_empty():
    """Test min_of_maxs with empty list."""
    assert aggregation.min_of_maxs([], "maximum_light") is None


def test_location_sensor_aggregation():
    """Test location sensor aggregation with realistic plant data."""
    plants = [
        {
            "minimum_temperature": 15,
            "maximum_temperature": 25,
            "minimum_light": 500,
            "maximum_light": 2000,
        },
        {
            "minimum_temperature": 18,
            "maximum_temperature": 28,
            "minimum_light": 300,
            "maximum_light": 1500,
        },
        {
            "minimum_temperature": 16,
            "maximum_temperature": 26,
            "minimum_light": 400,
            "maximum_light": 1800,
        },
    ]

    # Min temperature: should be highest minimum (18°C - most restrictive)
    assert aggregation.max_of_mins(plants, "minimum_temperature") == 18

    # Max temperature: should be lowest maximum (25°C - most restrictive)
    assert aggregation.min_of_maxs(plants, "maximum_temperature") == 25

    # Min light: should be highest minimum (500 lx)
    assert aggregation.max_of_mins(plants, "minimum_light") == 500

    # Max light: should be lowest maximum (1500 lx)
    assert aggregation.min_of_maxs(plants, "maximum_light") == 1500
