from soma.ring_buffer import RingBuffer


def test_empty_buffer():
    rb = RingBuffer(capacity=5)
    assert len(rb) == 0
    assert list(rb) == []
    assert not rb


def test_append_within_capacity():
    rb = RingBuffer(capacity=3)
    rb.append("a")
    rb.append("b")
    assert len(rb) == 2
    assert list(rb) == ["a", "b"]
    assert rb


def test_overflow_drops_oldest():
    rb = RingBuffer(capacity=3)
    for x in ["a", "b", "c", "d", "e"]:
        rb.append(x)
    assert len(rb) == 3
    assert list(rb) == ["c", "d", "e"]


def test_last_n():
    rb = RingBuffer(capacity=5)
    for i in range(5):
        rb.append(i)
    assert rb.last(3) == [2, 3, 4]
    assert rb.last(10) == [0, 1, 2, 3, 4]


def test_clear():
    rb = RingBuffer(capacity=5)
    rb.append(1)
    rb.append(2)
    rb.clear()
    assert len(rb) == 0


def test_getitem():
    rb = RingBuffer(capacity=3)
    rb.append("a")
    rb.append("b")
    rb.append("c")
    rb.append("d")
    assert rb[0] == "b"
    assert rb[-1] == "d"


def test_repr():
    rb = RingBuffer(capacity=2)
    rb.append(1)
    assert "RingBuffer" in repr(rb)
