"""Inclusive d100 thresholds from the Ask The Game Master chart.

Source: One-Page Mythic, Mythic Magazine #25, Tana Pigeon / Word Mill Games.
https://www.wordmillgames.com/onepagemythicgme.html
Each tuple gives the upper bounds for Exceptional Yes, Yes, and No;
the remaining values through 100 are Exceptional No.
"""

ODDS = {
    'Certain': (18, 90, 98),
    'Nearly Certain': (17, 85, 97),
    'Very Likely': (15, 75, 95),
    'Likely': (13, 65, 93),
    '50/50 or Unknown': (10, 50, 90),
    'Unlikely': (7, 35, 87),
    'Very Unlikely': (5, 25, 85),
    'Nearly Impossible': (3, 15, 83),
    'Impossible': (2, 10, 82),
}
DEFAULT_ODDS = '50/50 or Unknown'
OUTCOMES = ('Exceptional Yes', 'Yes', 'No', 'Exceptional No')


def resolve(odds, roll):
    if not isinstance(odds, str) or odds not in ODDS:
        raise ValueError('Choose one of the nine Fate Oracle odds settings.')
    if type(roll) is not int or not 1 <= roll <= 100:
        raise ValueError('A Fate Oracle roll must be a whole number from 1 to 100.')
    return OUTCOMES[sum(roll > threshold for threshold in ODDS[odds])]
