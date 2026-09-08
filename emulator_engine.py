"""Character Emulator Engine - Triple-O procedural referee for solo RPGs."""

import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple
from dice import roll_die, roll_d66


def roll_d6() -> int:
    """Roll a single 6-sided die."""
    return roll_die(6)


def roll_triple_o() -> Tuple[int, str]:
    """
    Roll 1d6 for a Triple-O check:
    1      = THE ODD (16.67%)
    2-3    = THE OPTION (33.33%)
    4-6    = THE OBVIOUS (50.00%)
    """
    roll = roll_d6()
    if roll == 1:
        classification = "THE ODD"
    elif roll in (2, 3):
        classification = "THE OPTION"
    else:
        classification = "THE OBVIOUS"
    return roll, classification


class EmulatorEngine:
    """Handles data tables, weighted trait resolution, specific actions, and sparks."""

    ACTION_TABLE_NAMES = [
        "combat",
        "social",
        "exploration",
        "delving",
        "interpretation",
        "downtime",
        "planning",
    ]

    SPARK_TABLE_NAMES = [
        "action",
        "focus",
        "method",
        "disposition",
        "motivation",
        "dynamics",
    ]

    SPARK_COMBINATIONS = {
        "action_focus": ("action", "focus"),
        "action_method": ("action", "method"),
        "action_motivation": ("action", "motivation"),
    }

    def __init__(self, data_dir: str = "data"):
        self.data_dir = os.path.abspath(data_dir)
        self.action_tables: Dict[str, Dict[str, str]] = {}
        self.spark_tables: Dict[str, Dict[str, str]] = {}
        self.load_tables()

    def load_tables(self) -> None:
        """Load Action and Spark tables from JSON."""
        actions_file = os.path.join(self.data_dir, "character_actions.json")
        sparks_file = os.path.join(self.data_dir, "character_sparks.json")

        if os.path.exists(actions_file):
            with open(actions_file, "r", encoding="utf-8") as f:
                self.action_tables = json.load(f)
        else:
            raise FileNotFoundError(f"Missing character actions table file: {actions_file}")

        if os.path.exists(sparks_file):
            with open(sparks_file, "r", encoding="utf-8") as f:
                self.spark_tables = json.load(f)
        else:
            raise FileNotFoundError(f"Missing character sparks table file: {sparks_file}")

    def select_weighted_trait(self, traits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Select a trait using weighted random selection:
        - Default: weight 1
        - Prevalent: weight 2 (twice as likely)
        - Temporary: weight 1
        
        If the NPC has no stored traits, returns a display-only DEFAULT placeholder.
        No fake trait is saved to the database.
        """
        if not traits:
            return {
                "id": None,
                "status": "Default",
                "trait": "DEFAULT",
                "category": "",
                "is_placeholder": True,
            }

        weights: List[float] = []
        for t in traits:
            status = (t.get("status") or "").strip().lower()
            if status == "prevalent":
                weights.append(2.0)
            else:
                weights.append(1.0)

        chosen = random.choices(traits, weights=weights, k=1)[0]
        status_raw = chosen.get("status", "default")
        status_disp = status_raw.capitalize() if status_raw else "Default"
        return {
            "id": chosen.get("id"),
            "status": status_disp,
            "trait": chosen.get("trait", ""),
            "category": chosen.get("category", ""),
            "is_placeholder": False,
        }

    def roll_specific_action(
        self, action_type: str, traits: List[Dict[str, Any]], count: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Roll 'count' (default 3) independent Action Prompts:
        Each prompt contains:
        1. Selected Trait (weighted, or DEFAULT placeholder)
        2. Trait Status
        3. Trait Category
        4. d66 roll
        5. Specific Action result
        6. 1d6 Triple-O Check
        7. Triple-O classification
        """
        table_key = action_type.strip().lower()
        if table_key not in self.action_tables:
            raise ValueError(
                f"Unknown action table: '{action_type}'. Valid tables: {', '.join(self.ACTION_TABLE_NAMES)}"
            )

        table = self.action_tables[table_key]
        results = []

        for i in range(count):
            trait = self.select_weighted_trait(traits)
            d66 = roll_d66()
            action_text = table.get(str(d66), "Unknown action")
            triple_o_roll, triple_o_class = roll_triple_o()

            results.append({
                "index": i + 1,
                "trait": trait,
                "d66": d66,
                "action": action_text,
                "action_type": action_type.capitalize(),
                "triple_o_roll": triple_o_roll,
                "triple_o_classification": triple_o_class,
            })

        return results

    def roll_spark(self, spark_type: str) -> Dict[str, Any]:
        """
        Roll on a single Spark table or a predefined Spark combination:
        Tables: action, focus, method, disposition, motivation, dynamics
        Combinations: action_focus, action_method, action_motivation
        """
        clean_key = spark_type.strip().lower().replace(" ", "_").replace("+", "_")
        # Collapse multiple underscores
        while "__" in clean_key:
            clean_key = clean_key.replace("__", "_")

        # Check combination
        if clean_key in self.SPARK_COMBINATIONS:
            t1_name, t2_name = self.SPARK_COMBINATIONS[clean_key]
            t1 = self.spark_tables.get(t1_name, {})
            t2 = self.spark_tables.get(t2_name, {})
            d66_1 = roll_d66()
            d66_2 = roll_d66()
            return {
                "type": "combination",
                "spark_type": clean_key,
                "display_name": f"{t1_name.capitalize()} + {t2_name.capitalize()}",
                "rolls": [
                    {
                        "table": t1_name.capitalize(),
                        "d66": d66_1,
                        "result": t1.get(str(d66_1), "Unknown"),
                    },
                    {
                        "table": t2_name.capitalize(),
                        "d66": d66_2,
                        "result": t2.get(str(d66_2), "Unknown"),
                    },
                ],
            }

        if clean_key in self.spark_tables:
            table = self.spark_tables[clean_key]
            d66 = roll_d66()
            return {
                "type": "single",
                "spark_type": clean_key,
                "display_name": clean_key.capitalize(),
                "rolls": [
                    {
                        "table": clean_key.capitalize(),
                        "d66": d66,
                        "result": table.get(str(d66), "Unknown"),
                    }
                ],
            }

        raise ValueError(
            f"Unknown spark type: '{spark_type}'. Valid tables: {', '.join(self.SPARK_TABLE_NAMES)} or combinations ({', '.join(self.SPARK_COMBINATIONS.keys())})"
        )


_DEFAULT_EMULATOR: Optional[EmulatorEngine] = None

def get_emulator_engine(data_dir: str = "data") -> EmulatorEngine:
    global _DEFAULT_EMULATOR
    if _DEFAULT_EMULATOR is None:
        _DEFAULT_EMULATOR = EmulatorEngine(data_dir)
    return _DEFAULT_EMULATOR
