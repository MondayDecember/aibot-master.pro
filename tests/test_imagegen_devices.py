from imagegen.devices import parse_devices


def test_default_is_single_card():
    assert parse_devices("", 2) == [0]
    assert parse_devices(None, 4) == [0]


def test_all_expands_to_every_device():
    assert parse_devices("all", 2) == [0, 1]
    assert parse_devices("ALL", 3) == [0, 1, 2]
    # even with one card
    assert parse_devices("all", 1) == [0]


def test_explicit_indices():
    assert parse_devices("0,1", 2) == [0, 1]
    assert parse_devices("1", 2) == [1]
    # order preserved, duplicates dropped
    assert parse_devices("1,0,1", 2) == [1, 0]


def test_out_of_range_and_garbage_ignored():
    # only 2 cards -> index 5 dropped
    assert parse_devices("0,5", 2) == [0]
    # all garbage -> falls back to [0], never empty
    assert parse_devices("x,y", 2) == [0]
    assert parse_devices("9", 2) == [0]
