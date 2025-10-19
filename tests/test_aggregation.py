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
