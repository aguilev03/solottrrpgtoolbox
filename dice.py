"""Dice rolling utilities and the core Progress dice pool mechanic."""

import random
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class ProgressRollResult:
    """Represents the outcome of a hidden exploration Progress roll."""
    dice_pool: int        # number_of_dice = progress_points + 1 (min 1)
    rolls: List[int]      # individual d6 results
    successes: int        # count of 5s and 6s
    outcome: str          # 'failure' (0 successes), 'weak' (1 success), 'strong' (2+ successes)
    progress_before: int
    progress_after: int
    progress_message: Optional[str] = None


def roll_die(sides: int) -> int:
    """Roll a single die with the given number of sides."""
    if sides < 1:
        raise ValueError(f"Sides must be >= 1, got {sides}")
    return random.randint(1, sides)


def roll_d66() -> int:
    """
    Roll d66: two d6 dice, first is tens digit (1-6), second is ones digit (1-6).
    Possible results: 11-16, 21-26, 31-36, 41-46, 51-56, 61-66.
    """
    tens = roll_die(6)
    ones = roll_die(6)
    return tens * 10 + ones


def roll_notation(notation: str) -> Tuple[int, List[int]]:
    """
    Roll standard dice notation like '1d6', '2d6', 'd12', 'd8', 'd66'.
    Returns (total_sum, list_of_rolls).
    """
    clean = notation.strip().lower()
    if clean == "d66":
        val = roll_d66()
        return val, [val]

    match = re.fullmatch(r"(\d*)d(\d+)", clean)
    if not match:
        raise ValueError(f"Invalid dice notation: '{notation}'")

    count_str, sides_str = match.groups()
    count = int(count_str) if count_str else 1
    sides = int(sides_str)

    rolls = [roll_die(sides) for _ in range(count)]
    return sum(rolls), rolls


def roll_progress(progress_points: int) -> ProgressRollResult:
    """
    The Core Progress Mechanic:
    - Progress starts at 0.
    - Minimum Progress Pool is always 1D6.
    - Formula: number_of_dice = max(1, progress_points + 1)
    - Each D6 is evaluated separately:
        5 or 6 = 1 success
        1, 2, 3, 4 = 0 (blank)
    - ZERO successes = FAILURE:
        Generate normal room. progress_points remains unchanged.
    - ONE success = WEAK SUCCESS:
        Generate normal room. progress_points += 1 (next roll gets +1D6).
    - TWO OR MORE successes = STRONG SUCCESS:
        Generate UNIQUE ROOM for the current level!
    """
    if progress_points < 0:
        progress_points = 0

    dice_pool = progress_points + 1
    rolls = [roll_die(6) for _ in range(dice_pool)]
    successes = sum(1 for r in rolls if r in (5, 6))

    progress_message = None
    if successes >= 2:
        outcome = "strong"
        progress_after = progress_points  # Unique room generated; level completion/reset handled separately
    elif successes == 1:
        outcome = "weak"
        progress_after = progress_points + 1
        disp_before = progress_points + 1
        disp_after = progress_after + 1
        progress_message = f"Progress made! {disp_before} → {disp_after}"
    else:
        outcome = "failure"
        progress_after = progress_points

    return ProgressRollResult(
        dice_pool=dice_pool,
        rolls=rolls,
        successes=successes,
        outcome=outcome,
        progress_before=progress_points,
        progress_after=progress_after,
        progress_message=progress_message,
    )
