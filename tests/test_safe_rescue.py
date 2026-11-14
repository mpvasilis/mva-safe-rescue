import itertools

import pytest

from rare_mva.track2.decision import BENEFITS, SAFETY, QUALIFICATION, evaluate


def inputs():
    return dict.fromkeys(BENEFITS, "pass"), dict.fromkeys(SAFETY, "pass"), dict.fromkeys(QUALIFICATION, "pass")


def test_synthetic_positive_control_and_ineligible_control():
    b, s, q = inputs()
    assert evaluate(b, s, q, advancement_candidate=True).advance
    assert not evaluate(b, s, q, advancement_candidate=False).advance


@pytest.mark.parametrize("gate", SAFETY)
def test_every_safety_failure_vetoes_every_benefit_pattern(gate):
    for pattern in itertools.product(("pass", "fail"), repeat=len(BENEFITS)):
        b, s, q = inputs(); b.update(zip(BENEFITS, pattern)); s[gate] = "fail"
        result = evaluate(b, s, q, advancement_candidate=True)
        assert not result.advance
        assert result.reason == "CONFIRMED_SAFETY_VETO"


@pytest.mark.parametrize("gate", (*BENEFITS, *SAFETY, *QUALIFICATION))
def test_uncertainty_never_becomes_positive_or_confirmed_harm(gate):
    b, s, q = inputs()
    for values in (b, s, q):
        if gate in values:
            values[gate] = "indeterminate"
    decision = evaluate(b, s, q, advancement_candidate=True)
    assert not decision.advance
    assert decision.reason == "INDETERMINATE_NO_ADVANCE"
    assert decision.blocking_checks == (gate,)


def test_missing_or_extra_fields_cannot_silently_shrink_the_contract():
    b, s, q = inputs(); b.pop(BENEFITS[0])
    with pytest.raises(ValueError):
        evaluate(b, s, q, advancement_candidate=True)
    b[BENEFITS[0]] = "pass"; s["invented"] = "pass"
    with pytest.raises(ValueError):
        evaluate(b, s, q, advancement_candidate=True)


@pytest.mark.parametrize("bad", [True, 1, None, [], {}, "PASS", "unknown"])
def test_invalid_status_is_rejected(bad):
    b, s, q = inputs(); s[SAFETY[0]] = bad
    with pytest.raises(ValueError):
        evaluate(b, s, q, advancement_candidate=True)


@pytest.mark.parametrize("gate", (*BENEFITS, *QUALIFICATION))
def test_one_failed_requirement_blocks_advance(gate):
    b, s, q = inputs()
    (b if gate in b else q)[gate] = "fail"
    result = evaluate(b, s, q, advancement_candidate=True)
    assert not result.advance
    assert result.blocking_checks == (gate,)


def test_candidate_eligibility_is_not_coerced():
    with pytest.raises(ValueError):
        evaluate(*inputs(), advancement_candidate="false")
