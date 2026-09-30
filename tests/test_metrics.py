from types import SimpleNamespace

from webapi.server import _avg_block_time_seconds


def blocks_at(*seconds_after_start, base_ms=1_790_000_000_000):
    """Blocks whose ts are epoch milliseconds, like the real chain."""
    return [SimpleNamespace(ts=base_ms + s * 1000) for s in seconds_after_start]


def test_millisecond_timestamps_give_seconds_not_milliseconds():
    # genesis, then blocks 60s apart: this used to display as "60037.9s"
    assert _avg_block_time_seconds(blocks_at(0, 500, 560, 620, 680)) == 60.0


def test_genesis_gap_is_not_counted():
    # the wait before the first stake (500s) is idle time, not a block time
    assert _avg_block_time_seconds(blocks_at(0, 500, 560)) == 60.0


def test_uses_only_the_recent_window():
    old = list(range(0, 1000, 100))          # ten slow blocks, 100s apart
    recent = [1000 + 60 * i for i in range(1, 12)]  # then eleven fast ones, 60s apart
    assert _avg_block_time_seconds(blocks_at(*old, *recent), window=10) == 60.0


def test_too_little_data_gives_none():
    assert _avg_block_time_seconds(blocks_at(0)) is None
    assert _avg_block_time_seconds(blocks_at(0, 500)) is None  # genesis + one block
    assert _avg_block_time_seconds([]) is None


def test_second_based_timestamps_still_work():
    seconds = [SimpleNamespace(ts=1_790_000_000 + s) for s in (0, 500, 560, 620)]
    assert _avg_block_time_seconds(seconds) == 60.0
