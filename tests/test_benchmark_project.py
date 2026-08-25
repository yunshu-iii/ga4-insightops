import statistics


def test_median_baseline_is_resistant_to_one_slow_sample() -> None:
    samples = [1.2, 1.3, 1.4, 1.5, 100.0]

    assert statistics.median(samples) == 1.4
