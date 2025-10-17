import pytest
import random
from sumrope import SumRope


def ref_prefix_sum(data, i):
    return sum(data[:i])


def ref_range_sum(data, a, b):
    return sum(data[a:b])


@pytest.fixture
def base_rope():
    return SumRope([1, 2, 3, 4, 5])


# --- Basic construction and sums ---


def test_basic_prefix_and_total(base_rope):
    r = base_rope
    assert r.total_sum() == 15
    assert r.prefix_sum(0) == 0
    assert r.prefix_sum(3) == 6
    assert r.prefix_sum(5) == 15
    assert r.range_sum(1, 4) == 2 + 3 + 4


def test_to_list_roundtrip(base_rope):
    assert base_rope.to_list() == [1, 2, 3, 4, 5]


# --- Replacement behavior ---


def test_simple_replace_middle():
    r = SumRope([1, 2, 3, 4, 5])
    r.replace(2, 2, [10, 11, 12])
    assert r.to_list() == [1, 2, 10, 11, 12, 5]
    assert r.total_sum() == sum([1, 2, 10, 11, 12, 5])
    assert r.prefix_sum(5) == sum([1, 2, 10, 11, 12])


def test_replace_at_start_and_end():
    r = SumRope([10, 20, 30])
    r.replace(0, 1, [5, 6])  # replace first
    r.replace(len(r) - 1, 1, [7, 8])  # replace last
    assert r.to_list() == [5, 6, 20, 7, 8]


def test_replace_with_empty_and_insert():
    r = SumRope([1, 2, 3, 4])
    r.replace(1, 2, [])  # delete middle two
    assert r.to_list() == [1, 4]
    r.replace(1, 0, [9, 10])  # insert
    assert r.to_list() == [1, 9, 10, 4]


# --- Randomized consistency checks ---


@pytest.mark.parametrize("seed", range(3))
def test_randomized_equivalence(seed):
    random.seed(seed)
    arr = [random.randint(0, 100) for _ in range(200)]
    r = SumRope(arr)

    for _ in range(100):
        op = random.choice(["replace", "prefix", "range"])
        if op == "replace":
            if len(arr) == 0:
                continue
            start = random.randint(0, len(arr))
            old_len = random.randint(0, min(5, len(arr) - start))
            new_vals = [random.randint(0, 50) for _ in range(random.randint(0, 5))]
            r.replace(start, old_len, new_vals)
            arr[start : start + old_len] = new_vals

        elif op == "prefix":
            i = random.randint(0, len(arr))
            assert pytest.approx(r.prefix_sum(i)) == ref_prefix_sum(arr, i)

        elif op == "range":
            a = random.randint(0, len(arr))
            b = random.randint(a, len(arr))
            assert pytest.approx(r.range_sum(a, b)) == ref_range_sum(arr, a, b)

    # final consistency check
    assert r.to_list() == arr
    assert pytest.approx(r.total_sum()) == sum(arr)


# --- Structural sanity checks ---


def test_balanced_after_many_replacements():
    data = list(range(100))
    r = SumRope(data)
    for i in range(10):
        r.replace(20, 10, list(range(5)))  # shrink
        r.replace(30, 0, list(range(15)))  # expand
    assert r.to_list() == r.to_list()  # structure must remain stable
    # Prefix sums must still match reference
    arr = r.to_list()
    for i in range(0, len(arr), 10):
        assert pytest.approx(r.prefix_sum(i)) == sum(arr[:i])
