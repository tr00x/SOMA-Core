from soma.types import Level, AutonomyMode, Action, VitalsSnapshot, DriftMode


def test_level_ordering():
    assert Level.HEALTHY < Level.RESTART
    assert Level.SAFE_MODE.value == 5


def test_level_comparison():
    assert Level.CAUTION <= Level.DEGRADE
    assert not Level.QUARANTINE < Level.CAUTION
    assert Level.RESTART > Level.CAUTION
    assert Level.DEGRADE >= Level.DEGRADE


def test_action_immutable():
    a = Action(tool_name="bash", output_text="hello")
    assert a.error is False
    assert a.token_count == 0
    try:
        a.error = True  # type: ignore
        assert False, "Should not allow mutation"
    except AttributeError:
        pass


def test_vitals_snapshot_defaults():
    v = VitalsSnapshot()
    assert v.uncertainty == 0.0
    assert v.drift_mode == DriftMode.INFORMATIONAL
