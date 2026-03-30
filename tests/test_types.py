from soma.types import Level, ResponseMode, AutonomyMode, Action, VitalsSnapshot, DriftMode


# --- ResponseMode tests ---

def test_response_mode_ordering():
    assert ResponseMode.OBSERVE < ResponseMode.BLOCK
    assert ResponseMode.BLOCK.value == 3


def test_response_mode_comparison():
    assert ResponseMode.GUIDE <= ResponseMode.WARN
    assert not ResponseMode.BLOCK < ResponseMode.GUIDE
    assert ResponseMode.WARN > ResponseMode.GUIDE
    assert ResponseMode.WARN >= ResponseMode.WARN


def test_response_mode_values():
    assert ResponseMode.OBSERVE.value == 0
    assert ResponseMode.GUIDE.value == 1
    assert ResponseMode.WARN.value == 2
    assert ResponseMode.BLOCK.value == 3


def test_level_is_response_mode_alias():
    assert Level is ResponseMode


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
