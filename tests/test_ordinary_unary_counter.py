from ordinary_unary_counter import Sign, SignedUnaryCounter, UnaryCounter


def test_unsigned_counter_literal_push_pop_and_copy():
    first = UnaryCounter.zero()
    second = UnaryCounter.zero()
    for _ in range(7):
        first.increment()
    second.copy_from(first)
    assert first.value() == second.value() == 7
    for _ in range(3):
        second.decrement()
    assert first.value() == 7
    assert second.value() == 4


def test_signed_counter_crosses_zero():
    counter = SignedUnaryCounter.zero()
    for _ in range(4):
        counter.decrement()
    assert counter.value() == -4
    for _ in range(6):
        counter.increment()
    assert counter.value() == 2
    assert counter.sign is Sign.POSITIVE
    counter.clear()
    assert counter.value() == 0
