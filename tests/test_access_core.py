import pytest

from src.access import (CODE_ALPHABET, CODE_LENGTH, SESSION_COOKIE, AccessControl, TooManyTries,
                        access, format_code, new_code, normalize_code, wait_after)

IP = "192.168.1.20"
OTHER_IP = "192.168.1.21"


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def ac(clock):
    control = AccessControl(clock=clock)
    control.start(require_code=True)
    return control


def wrong_code(control):
    """A valid-shaped code that isn't the current one."""
    return next(c * CODE_LENGTH for c in CODE_ALPHABET if c * CODE_LENGTH != control.code)


def fail(control, times, ip=IP):
    for _ in range(times):
        assert control.try_code(ip, wrong_code(control)) is None


# --- The code ---

def test_alphabet_leaves_out_look_alikes():
    assert CODE_ALPHABET == "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    assert len(CODE_ALPHABET) == 31
    assert not set("01OIL") & set(CODE_ALPHABET)
    assert CODE_LENGTH == 6
    assert SESSION_COOKIE == "rs_session"


def test_new_code_has_the_right_shape():
    codes = {new_code() for _ in range(200)}
    assert all(len(c) == CODE_LENGTH and set(c) <= set(CODE_ALPHABET) for c in codes)
    assert len(codes) > 190


@pytest.mark.parametrize("text", ["K7M2X9", "k7m2x9", "K7M 2X9", "k7m-2x9", " K7M-2X9 ", "K-7 M2X9"])
def test_normalize_ignores_case_spaces_and_dashes(text):
    assert normalize_code(text) == "K7M2X9"


@pytest.mark.parametrize("text", [
    "", "K7M2X", "K7M2X9A", "K7M 2X", "K7M0X9", "K7MOX9", "K7M1X9", "K7MIX9", "K7MLX9",
    "K7M_X9", "K7M.X9", "K7M\tX9", "K7M2Xſ", None, 123456,
])
def test_normalize_rejects_wrong_lengths_and_characters(text):
    assert normalize_code(text) is None


def test_format_code_shows_two_groups_of_three():
    assert format_code("K7M2X9") == "K7M 2X9"


# --- Wrong guesses ---

@pytest.mark.parametrize("failures, wait", [
    (0, 0), (1, 0), (4, 0), (5, 2), (6, 4), (7, 8), (8, 16), (11, 128), (12, 256), (13, 300), (50, 300),
])
def test_wait_after_doubles_from_two_seconds_up_to_five_minutes(failures, wait):
    assert wait_after(failures) == wait


def test_five_free_tries_then_too_many_tries(ac):
    fail(ac, 5)
    with pytest.raises(TooManyTries) as exc:
        ac.try_code(IP, ac.code)
    assert exc.value.retry_after == 2


def test_the_wait_ends_and_doubles_on_the_next_failure(ac, clock):
    fail(ac, 5)
    clock.now += 2
    fail(ac, 1)
    with pytest.raises(TooManyTries) as exc:
        ac.try_code(IP, wrong_code(ac))
    assert exc.value.retry_after == 4


def test_retry_after_counts_down_and_rounds_up(ac, clock):
    fail(ac, 5)
    clock.now += 1.5
    with pytest.raises(TooManyTries) as exc:
        ac.try_code(IP, wrong_code(ac))
    assert exc.value.retry_after == 1


def test_attempts_during_a_wait_are_not_counted(ac, clock):
    fail(ac, 5)
    for _ in range(10):
        with pytest.raises(TooManyTries):
            ac.try_code(IP, wrong_code(ac))
    clock.now += 2
    fail(ac, 1)
    with pytest.raises(TooManyTries) as exc:
        ac.try_code(IP, wrong_code(ac))
    assert exc.value.retry_after == 4


def test_other_ips_are_unaffected(ac):
    fail(ac, 5)
    with pytest.raises(TooManyTries):
        ac.try_code(IP, ac.code)
    assert ac.try_code(OTHER_IP, wrong_code(ac)) is None
    assert ac.try_code(OTHER_IP, ac.code)


def test_a_success_resets_that_ip(ac, clock):
    fail(ac, 4)
    assert ac.try_code(IP, ac.code)
    fail(ac, 4)
    assert ac.try_code(IP, ac.code)
    fail(ac, 5)
    clock.now += 2
    assert ac.try_code(IP, ac.code)
    fail(ac, 4)
    assert ac.try_code(IP, ac.code)


def test_start_clears_wrong_guesses(ac):
    fail(ac, 5)
    ac.start(require_code=True)
    assert ac.try_code(IP, ac.code)


# --- Sessions ---

def test_a_correct_code_starts_a_session(ac):
    token = ac.try_code(IP, format_code(ac.code).lower())
    assert isinstance(token, str) and len(token) >= 43
    assert ac.is_valid(token)


def test_each_success_gets_its_own_session(ac):
    first, second = ac.try_code(IP, ac.code), ac.try_code(OTHER_IP, ac.code)
    assert first != second
    assert ac.is_valid(first) and ac.is_valid(second)


@pytest.mark.parametrize("text", ["", "nonsense", None, 123])
def test_wrong_input_starts_no_session(ac, text):
    assert ac.try_code(IP, text) is None


@pytest.mark.parametrize("token", [None, "", "made-up"])
def test_unknown_tokens_are_not_valid(ac, token):
    assert not ac.is_valid(token)


def test_end_session_ends_only_that_session(ac):
    first, second = ac.try_code(IP, ac.code), ac.try_code(IP, ac.code)
    ac.end_session(first)
    assert not ac.is_valid(first)
    assert ac.is_valid(second)
    ac.end_session(first)
    ac.end_session(None)


def test_stop_ends_sessions_and_throws_away_the_code(ac):
    code = ac.code
    token = ac.try_code(IP, code)
    ac.stop()
    assert ac.code is None
    assert not ac.is_valid(token)
    assert ac.try_code(IP, code) is None


def test_stop_clears_wrong_guesses(ac):
    fail(ac, 5)
    ac.stop()
    ac.start(require_code=True)
    assert ac.try_code(IP, ac.code)


# --- Start ---

def test_start_with_the_code_required_returns_the_code(clock):
    control = AccessControl(clock=clock)
    code = control.start(require_code=True)
    assert control.require_code is True
    assert control.code == code
    assert normalize_code(code) == code


def test_each_start_makes_a_new_code(ac):
    codes = {ac.start(require_code=True) for _ in range(20)}
    assert len(codes) > 1


def test_start_without_the_code_has_no_code(ac):
    token = ac.try_code(IP, ac.code)
    assert ac.start(require_code=False) is None
    assert ac.require_code is False
    assert ac.code is None
    assert not ac.is_valid(token)


def test_module_singleton():
    assert isinstance(access, AccessControl)
