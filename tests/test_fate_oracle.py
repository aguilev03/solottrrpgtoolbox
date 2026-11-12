"""Independent transcription of the chart: check every d100 value and boundary."""
import pytest

from fate_oracle import ODDS, resolve


CHART = [
    ('Certain', ((1, 18), (19, 90), (91, 98), (99, 100))),
    ('Nearly Certain', ((1, 17), (18, 85), (86, 97), (98, 100))),
    ('Very Likely', ((1, 15), (16, 75), (76, 95), (96, 100))),
    ('Likely', ((1, 13), (14, 65), (66, 93), (94, 100))),
    ('50/50 or Unknown', ((1, 10), (11, 50), (51, 90), (91, 100))),
    ('Unlikely', ((1, 7), (8, 35), (36, 87), (88, 100))),
    ('Very Unlikely', ((1, 5), (6, 25), (26, 85), (86, 100))),
    ('Nearly Impossible', ((1, 3), (4, 15), (16, 83), (84, 100))),
    ('Impossible', ((1, 2), (3, 10), (11, 82), (83, 100))),
]
OUTCOMES = ('Exceptional Yes', 'Yes', 'No', 'Exceptional No')


@pytest.mark.parametrize('odds,ranges', CHART)
def test_every_d100_outcome(odds, ranges):
    covered = []
    for outcome, (low, high) in zip(OUTCOMES, ranges):
        for roll in range(low, high + 1):
            assert resolve(odds, roll) == outcome
            covered.append(roll)
    assert covered == list(range(1, 101))


def test_exact_nine_odds_settings():
    assert list(ODDS) == [odds for odds, _ in CHART]


@pytest.mark.parametrize('roll', [0, 101, -1, 1.5, True, None, '50'])
def test_invalid_d100(roll):
    with pytest.raises(ValueError):
        resolve('50/50 or Unknown', roll)


@pytest.mark.parametrize('odds', ['', 'unknown', None, [], {}])
def test_invalid_odds(odds):
    with pytest.raises(ValueError):
        resolve(odds, 50)
