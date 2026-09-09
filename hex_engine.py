"""Wilderness & Hex Generator Engine for Solo TTRPG Tools.

Based on procedural worldbuilding algorithms from:
- Atelier Clandestin's 'Sandbox Generator' (temperate biomes, landmarks, settlements, lairs, 19-hex flower cluster)
- Jason Lutes' 'The Perilous Tables' (discoveries, hazards, names, environmental dressing)
"""

import json
import math
import os
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from table_loader import TableManager, get_table_manager


BIOME_LIST = ["Grassland", "Forest", "Hills", "Marsh", "Mountains"]

HEX_COORDINATES_19 = [
    # Center (1)
    {"index": 1, "q": 0, "r": 0, "label": "Center"},
    # Ring 1 (6 hexes: 2-7)
    {"index": 2, "q": 0, "r": -1, "label": "North"},
    {"index": 3, "q": 1, "r": -1, "label": "Northeast"},
    {"index": 4, "q": 1, "r": 0, "label": "Southeast"},
    {"index": 5, "q": 0, "r": 1, "label": "South"},
    {"index": 6, "q": -1, "r": 1, "label": "Southwest"},
    {"index": 7, "q": -1, "r": 0, "label": "Northwest"},
    # Ring 2 (12 hexes: 8-19)
    {"index": 8, "q": 0, "r": -2, "label": "Far North"},
    {"index": 9, "q": 1, "r": -2, "label": "Far North-Northeast"},
    {"index": 10, "q": 2, "r": -2, "label": "Far Northeast"},
    {"index": 11, "q": 2, "r": -1, "label": "Far East-Northeast"},
    {"index": 12, "q": 2, "r": 0, "label": "Far Southeast"},
    {"index": 13, "q": 1, "r": 1, "label": "Far South-Southeast"},
    {"index": 14, "q": 0, "r": 2, "label": "Far South"},
    {"index": 15, "q": -1, "r": 2, "label": "Far South-Southwest"},
    {"index": 16, "q": -2, "r": 2, "label": "Far Southwest"},
    {"index": 17, "q": -2, "r": 1, "label": "Far West-Southwest"},
    {"index": 18, "q": -2, "r": 0, "label": "Far Northwest"},
    {"index": 19, "q": -1, "r": -1, "label": "Far North-Northwest"},
]


@dataclass
class HexCell:
    id: Optional[int] = None
    region_id: Optional[int] = None
    hex_index: int = 1
    q: int = 0
    r: int = 0
    biome: str = "Grassland"
    feature_type: str = "Wilds"  # Wilds, Landmark, Settlement, Lair, Dungeon
    title: str = ""
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    discovered: bool = True
    created_at: Optional[str] = None

    @property
    def biome_color(self) -> str:
        colors = {
            "Grassland": "#7da05a",
            "Forest": "#3f6e43",
            "Hills": "#8c7853",
            "Marsh": "#4d645b",
            "Mountains": "#636d7e",
        }
        return colors.get(self.biome, "#687585")

    @property
    def biome_icon(self) -> str:
        icons = {
            "Grassland": "🌾",
            "Forest": "🌲",
            "Hills": "⛰️",
            "Marsh": "🌿",
            "Mountains": "🏔️",
        }
        return icons.get(self.biome, "🗺️")

    @property
    def feature_icon(self) -> str:
        icons = {
            "Wilds": "🍃",
            "Landmark": "🏛️",
            "Settlement": "🏘️",
            "Lair": "🐺",
            "Dungeon": "🗝️",
        }
        return icons.get(self.feature_type, "📍")

    def svg_center(self, x0: float = 270.0, y0: float = 240.0, r_radius: float = 52.0) -> Tuple[float, float]:
        cx = x0 + r_radius * (math.sqrt(3) * self.q + (math.sqrt(3) / 2.0) * self.r)
        cy = y0 + r_radius * (1.5 * self.r)
        return cx, cy

    def svg_points(self, x0: float = 270.0, y0: float = 240.0, r_radius: float = 52.0) -> str:
        cx, cy = self.svg_center(x0, y0, r_radius)
        pts = []
        for k in range(6):
            angle = math.pi / 6.0 + k * (math.pi / 3.0)
            px = cx + r_radius * math.cos(angle)
            py = cy + r_radius * math.sin(angle)
            pts.append(f"{px:.1f},{py:.1f}")
        return " ".join(pts)


@dataclass
class HexRegion:
    id: Optional[int] = None
    name: str = ""
    layout_type: str = "cluster_19"  # "single", "cluster_7", "cluster_19"
    center_biome: str = "Grassland"
    weather: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    cells: List[HexCell] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class HexEngine:
    """Procedural generator for wilderness hexes, regions, encounters, and landmarks."""

    def __init__(self, table_mgr: Optional[TableManager] = None):
        self.tables = table_mgr or get_table_manager()

    def roll_starting_biome(self) -> str:
        """Rolls the starting biome using Sandbox Generator p. 8 weights."""
        d10 = random.randint(1, 10)
        if d10 <= 4:
            return "Grassland"
        elif d10 <= 6:
            return "Forest"
        elif d10 <= 8:
            return "Hills"
        elif d10 == 9:
            return "Marsh"
        else:
            return "Mountains"

    def roll_neighbor_biome(self, previous_biome: str) -> str:
        """Rolls the next biome relative to the neighboring hex (50% chance to match)."""
        d10 = random.randint(1, 10)
        if d10 <= 5:
            return previous_biome
        elif d10 == 6:
            return "Grassland"
        elif d10 == 7:
            return "Forest"
        elif d10 == 8:
            return "Hills"
        elif d10 == 9:
            return "Marsh"
        else:
            return "Mountains"

    def roll_weather(self) -> Dict[str, Any]:
        """Rolls temperature, conditions, and wind from hex_weather.json."""
        weather_data = self.tables.tables.get("hex_weather", {})
        temp_entries = weather_data.get("temperatures", [])
        cond_entries = weather_data.get("conditions", [])
        wind_entries = weather_data.get("winds", [])

        temp = self._roll_from_ranges(temp_entries, 12) or {
            "name": "Mild & Temperate", "desc": "Gentle, comfortable weather."
        }
        cond = self._roll_from_ranges(cond_entries, 12) or {
            "name": "Scattered Clouds", "desc": "Gentle cumulus clouds.", "travel_impact": "Normal speed"
        }
        wind = self._roll_from_ranges(wind_entries, 12) or {
            "name": "Gentle Breeze", "desc": "Pleasant rustling in the trees."
        }

        return {
            "temperature": temp.get("name"),
            "temp_desc": temp.get("desc"),
            "condition": cond.get("name"),
            "condition_desc": cond.get("desc"),
            "travel_impact": cond.get("travel_impact", "Normal speed"),
            "wind": wind.get("name"),
            "wind_desc": wind.get("desc"),
            "summary": f"{temp.get('name')}, {cond.get('name')}, with {wind.get('name').lower()} ({cond.get('travel_impact')})."
        }

    def _roll_from_ranges(self, entries: List[Dict[str, Any]], die_max: int) -> Optional[Dict[str, Any]]:
        if not entries:
            return None
        roll = random.randint(1, die_max)
        for e in entries:
            if e.get("min", 1) <= roll <= e.get("max", die_max):
                return e
        return entries[0]

    def roll_wilderness_encounter(self, biome: str) -> Dict[str, Any]:
        """Rolls a random encounter for the specified biome."""
        biomes_data = self.tables.tables.get("hex_biomes", {}).get("biomes", {})
        b_info = biomes_data.get(biome, biomes_data.get("Grassland", {}))
        encounters = b_info.get("encounters", [])

        # Roll 2d6
        r2d6 = random.randint(1, 6) + random.randint(1, 6)
        chosen = None
        for enc in encounters:
            if enc.get("min", 2) <= r2d6 <= enc.get("max", 12):
                chosen = enc
                break
        if not chosen and encounters:
            chosen = random.choice(encounters)

        creature = chosen.get("creature", "Wild Beasts") if chosen else "Wild Beasts"
        danger = chosen.get("danger", "Medium") if chosen else "Medium"

        activities = [
            "Prowling or foraging for food", "Resting or sleeping in the shade",
            "Defending territorial boundary marks", "Stalking prey silently",
            "Nursing injuries from a previous battle", "Migrating along ancient trails"
        ]

        return {
            "roll": r2d6,
            "creature": creature,
            "danger": danger,
            "activity": random.choice(activities),
            "biome": biome
        }

    def roll_landmark(self, category: Optional[str] = None) -> Dict[str, Any]:
        """Rolls a landmark from hex_landmarks.json (Natural, Artificial, or Magical)."""
        data = self.tables.tables.get("hex_landmarks", {}).get("categories", {})
        if not category or category not in data:
            d6 = random.randint(1, 6)
            if d6 <= 3:
                category = "Natural"
            elif d6 <= 5:
                category = "Artificial"
            else:
                category = "Magical"

        cat_info = data.get(category, {})
        subcats = cat_info.get("subcategories", {})
        if not subcats:
            return {"category": category, "subcategory": "Relief", "name": "Ancient Stone Monument"}

        subcat_name = random.choice(list(subcats.keys()))
        options = subcats[subcat_name]
        chosen_landmark = random.choice(options) if options else "Ancient Stone Monument"

        # Landmark situation / discovery
        content_roll = random.randint(1, 6)
        if content_roll <= 2:
            content_type = "Deserted & Serene"
            content_desc = "Silent and undisturbed by travelers."
        elif content_roll <= 4:
            content_type = "Sign of Lore / Inscription"
            spark = self.roll_knowledge_spark()
            content_desc = spark.get("prompt", "Faded markings on the stone.")
        else:
            quest = self.roll_special_quest()
            content_type = f"Local Trouble: {quest.get('category')}"
            content_desc = quest.get("hook", "A traveler requires aid.")

        return {
            "category": category,
            "subcategory": subcat_name,
            "name": chosen_landmark,
            "content_type": content_type,
            "content_desc": content_desc
        }

    def roll_knowledge_spark(self) -> Dict[str, Any]:
        """Rolls what can be learned or discovered in the hex (Sandbox Generator p. 22)."""
        sparks_data = self.tables.tables.get("hex_sparks", {})
        k_list = sparks_data.get("knowledge_tables", [])
        if not k_list:
            return {"type": "Local Lore", "prompt": "Clues regarding a nearby landmark."}
        d20 = random.randint(1, 20)
        for item in k_list:
            if item.get("min", 1) <= d20 <= item.get("max", 20):
                return item
        return random.choice(k_list)

    def roll_special_quest(self) -> Dict[str, Any]:
        """Rolls a special landmark opportunity or dilemma (Sandbox Generator p. 23)."""
        sparks_data = self.tables.tables.get("hex_sparks", {})
        quests = sparks_data.get("special_quests", {})
        if not quests:
            return {"category": "Mystery", "hook": "Unexplained glowing lights dancing over the rocks."}
        cat = random.choice(list(quests.keys()))
        items = quests[cat]
        hook = random.choice(items) if items else "A peculiar situation unfolds."
        return {
            "category": cat.replace("_", " ").title(),
            "hook": hook
        }

    def roll_hazard(self) -> Dict[str, Any]:
        """Rolls a wilderness hazard from hex_hazards.json (Sandbox Generator p. 22)."""
        hazards_data = self.tables.tables.get("hex_hazards", {})
        entries = hazards_data.get("entries", [])
        if not entries:
            return {"name": "Treacherous Footing", "effect": "Slippery scree slows progress.", "guidance": "Travel takes double time."}
        d20 = random.randint(1, 20)
        for h in entries:
            if h.get("min", 1) <= d20 <= h.get("max", 20):
                return h
        return random.choice(entries)

    def roll_settlement_name(self) -> str:
        """Generates a settlement name using prefixes and suffixes."""
        data = self.tables.tables.get("hex_settlements", {}).get("name_generators", {})
        prefixes = data.get("prefixes", ["Oakhaven", "Raven", "Stone", "High", "Deep", "Silver"])
        suffixes = data.get("suffixes", ["ford", "haven", "dale", "stead", "burg", "ton", "keep", "fell"])
        p = random.choice(prefixes)
        s = random.choice(suffixes)
        if p.endswith(s):
            return p
        return f"{p}{s}"

    def roll_settlement(self, s_type: Optional[str] = None) -> Dict[str, Any]:
        """Generates a detailed settlement (Sandbox Generator p. 27-58)."""
        settle_data = self.tables.tables.get("hex_settlements", {}).get("types", {})
        if not s_type or s_type not in settle_data:
            d12 = random.randint(1, 12)
            if d12 <= 3:
                s_type = "Hamlet"
            elif d12 <= 7:
                s_type = "Village"
            elif d12 <= 9:
                s_type = "Castle"
            elif d12 == 10:
                s_type = "Tower"
            elif d12 == 11:
                s_type = "Abbey"
            else:
                s_type = "City"

        spec = settle_data.get(s_type, {})
        name = self.roll_settlement_name()

        # Build contextual details based on settlement type
        details: Dict[str, Any] = {
            "type": s_type,
            "name": f"{s_type} of {name}",
            "population": spec.get("population", "Varied"),
            "description": spec.get("description", ""),
        }

        if s_type == "Hamlet":
            details["main_building"] = random.choice(spec.get("main_buildings", ["Wayside Tavern"]))
            details["secret"] = random.choice(spec.get("secrets", ["None of note"]))
        elif s_type == "Village":
            details["specialty"] = random.choice(spec.get("specialties", ["Farming"]))
            details["ruler"] = random.choice(spec.get("rulers", ["Village Elder"]))
            details["trouble"] = random.choice(spec.get("troubles", ["Bandit raids"]))
            details["tavern"] = random.choice(spec.get("tavern_names", ["The Rusty Horseshoe"]))
        elif s_type == "Castle":
            details["garrison"] = random.choice(spec.get("garrison", ["Men-at-Arms"]))
            details["defenses"] = random.choice(spec.get("defenses", ["Moat & Portcullis"]))
            details["ruler"] = random.choice(spec.get("rulers", ["Baron"]))
        elif s_type == "Tower":
            details["inhabitant"] = random.choice(spec.get("inhabitants", ["Reclusive Wizard"]))
            details["feature"] = random.choice(spec.get("features", ["Observatory"]))
        elif s_type == "Abbey":
            details["activity"] = random.choice(spec.get("activities", ["Illuminated manuscripts"]))
            details["relic"] = random.choice(spec.get("relics", ["Saint Relic"]))
        elif s_type == "City":
            details["district"] = random.choice(spec.get("districts", ["Market Quarter"]))
            details["ruler"] = random.choice(spec.get("rulers", ["Lord Mayor"]))

        return details

    def roll_lair(self, biome: str) -> Dict[str, Any]:
        """Generates a monster lair in the wilderness (Sandbox Generator p. 59-62)."""
        enc = self.roll_wilderness_encounter(biome)
        creature = enc.get("creature", "Beasts")

        lair_forms = [
            "Concealed natural cave behind a waterfall",
            "Excavated subterranean burrow in a ravine",
            "Overgrown mossy stone ruins",
            "Mound of bones and brush beneath a hollow oak",
            "Deep limestone sinkhole with hanging vines",
            "Crumbling ancient crypt threshold"
        ]

        defenses = [
            "Bone alarms and strung dried skulls",
            "Concealed deadfalls and sharpened stakes",
            "Vigilant sentries posted in the canopy",
            "Narrow choke point accessible only on hands and knees",
            "Camouflaged boulder blocking the inner chamber"
        ]

        treasures = [
            "A scatter of 3d10 loose silver and copper coins from prior victims",
            "A battered iron-banded chest containing 1d6x50 gold pieces",
            "A finely forged masterwork dagger and pouch of semi-precious quartz",
            "A traveler's leather pack holding rations, a map, and a silver ring",
            "A glittering gem hoard worth 2d6x100 coins guarded in the rear nest"
        ]

        return {
            "monster": creature,
            "danger": enc.get("danger", "Hard"),
            "lair_form": random.choice(lair_forms),
            "defenses": random.choice(defenses),
            "status": random.choice(["Alert and on guard", "Sleeping off a recent feast", "Squabbling over spoils", "Nursing wounds"]),
            "treasure": random.choice(treasures)
        }

    def roll_dungeon_entrance(self, biome: str) -> Dict[str, Any]:
        """Generates a subterranean dungeon entrance."""
        d_types = ["Cave", "Tomb", "Temple", "Ruins", "Fort", "Sewers"]
        chosen_type = random.choice(d_types)

        names_data = self.tables.tables.get("dungeon_names", {}).get("types", {})
        config = names_data.get(chosen_type, {})
        prefix = random.choice(config.get("prefixes", ["Ancient"]))
        suffix = random.choice(config.get("suffixes", ["Chamber"]))
        dungeon_name = f"{prefix} {suffix}"

        situations = [
            "Partially concealed behind hanging ivy on a sheer cliff face",
            "A collapsed stone archway half-buried beneath rubble",
            "An iron-studded door set into the hillside, bound in rusted chains",
            "A yawning black fissure exhaling chilled, foul-smelling subterranean air",
            "Submerged stone steps leading down into an underground cistern"
        ]

        accessibilities = [
            "Clear and unobstructed",
            "Blocked by heavy fallen stones (requires clearing)",
            "Secured by a rusted ancient lock or seal",
            "Guarded by territorial beasts nesting near the entrance"
        ]

        return {
            "dungeon_name": dungeon_name,
            "dungeon_type": chosen_type,
            "situation": random.choice(situations),
            "accessibility": random.choice(accessibilities),
            "theme_hint": f"A delve of {chosen_type.lower()} architecture awaiting explorers."
        }

    def roll_npc(self) -> Dict[str, Any]:
        """Generates a wandering wilderness NPC (Sandbox Generator p. 132-135)."""
        data = self.tables.tables.get("hex_npcs", {})
        first_names = data.get("first_names", ["Alden", "Bella", "Gareth", "Lyra"])
        surnames = data.get("surnames", ["Blackwood", "Flint", "Thorn", "Winter"])
        occupations = data.get("occupations", ["Mercenary", "Herbalist", "Hunter", "Scholar"])
        clothing = data.get("clothing", ["Traveler woolens", "Boiled leather"])
        particularities = data.get("particularities", ["None of note", "Facial claw scar"])
        attitudes = data.get("attitudes", ["Cautious", "Friendly", "Secretive"])
        dreams = data.get("dreams", ["Buying a homestead", "Exploring the wastes"])
        secrets = data.get("secrets", ["None", "Fleeing an arrest warrant"])

        name = f"{random.choice(first_names)} {random.choice(surnames)}"
        return {
            "name": name,
            "occupation": random.choice(occupations),
            "clothing": random.choice(clothing),
            "particularity": random.choice(particularities),
            "attitude": random.choice(attitudes),
            "dream": random.choice(dreams),
            "secret": random.choice(secrets)
        }

    def generate_single_hex(
        self,
        biome: Optional[str] = None,
        feature_type: Optional[str] = None,
        include_weather: bool = True
    ) -> HexCell:
        """Generates an independent single hex with complete tactical details."""
        b = biome if biome in BIOME_LIST else self.roll_starting_biome()

        if not feature_type or feature_type not in ["Wilds", "Landmark", "Settlement", "Lair", "Dungeon"]:
            d6 = random.randint(1, 6)
            if d6 <= 3:
                feature_type = "Wilds"
            elif d6 == 4:
                feature_type = "Landmark"
            elif d6 == 5:
                feature_type = "Settlement"
            else:
                feature_type = "Lair" if random.randint(1, 2) == 1 else "Dungeon"

        cell = HexCell(
            hex_index=1,
            q=0,
            r=0,
            biome=b,
            feature_type=feature_type
        )

        details: Dict[str, Any] = {}
        if include_weather:
            details["weather"] = self.roll_weather()
        details["encounter"] = self.roll_wilderness_encounter(b)

        if feature_type == "Wilds":
            hazard = self.roll_hazard()
            spark = self.roll_knowledge_spark()
            cell.title = f"The {b} Wilderness"
            cell.summary = f"Untamed {b.lower()} wilderness bearing subtle hazards and forgotten signs."
            details["hazard"] = hazard
            details["spark"] = spark

        elif feature_type == "Landmark":
            lm = self.roll_landmark()
            cell.title = lm.get("name", "Notable Landmark")
            cell.summary = f"A prominent {lm.get('category', '').lower()} landmark ({lm.get('subcategory', '')})."
            details["landmark"] = lm

        elif feature_type == "Settlement":
            settle = self.roll_settlement()
            cell.title = settle.get("name", "Frontier Settlement")
            cell.summary = f"A {settle.get('type', '').lower()} ({settle.get('population', '')})."
            details["settlement"] = settle

        elif feature_type == "Lair":
            lair = self.roll_lair(b)
            cell.title = f"{lair.get('monster')} Lair"
            cell.summary = f"A dangerous nesting ground occupied by {lair.get('monster', 'beasts').lower()}."
            details["lair"] = lair

        elif feature_type == "Dungeon":
            dungeon = self.roll_dungeon_entrance(b)
            cell.title = dungeon.get("dungeon_name", "Subterranean Delve")
            cell.summary = f"Concealed entrance to a {dungeon.get('dungeon_type', '').lower()} complex."
            details["dungeon"] = dungeon

        cell.details = details
        return cell

    def generate_region(
        self,
        name: str = "Uncharted Borderlands",
        layout_type: str = "cluster_19",
        starting_biome: Optional[str] = None
    ) -> HexRegion:
        """
        Generates a full regional sandbox map:
        - cluster_19: Center + 6-hex Ring 1 + 12-hex Ring 2 (Sandbox Generator p. 8-11)
        - cluster_7: Center + 6-hex Ring 1
        - single: 1 hex
        """
        center_biome = starting_biome if starting_biome in BIOME_LIST else self.roll_starting_biome()
        region_weather = self.roll_weather()

        num_hexes = 19 if layout_type == "cluster_19" else (7 if layout_type == "cluster_7" else 1)
        coords_slice = HEX_COORDINATES_19[:num_hexes]

        cells: List[HexCell] = []
        biome_map: Dict[Tuple[int, int], str] = {}

        for i, coord in enumerate(coords_slice, start=1):
            q, r = coord["q"], coord["r"]

            # Determine biome:
            # Hex 1 is center_biome.
            # Hexes 2..7 roll neighbor biome relative to Center (0, 0).
            # Hexes 8..19 roll neighbor biome relative to adjacent Ring 1 hex.
            if i == 1:
                hex_biome = center_biome
            elif i <= 7:
                hex_biome = self.roll_neighbor_biome(center_biome)
            else:
                parent_biome = biome_map.get((q // 2, r // 2), center_biome)
                hex_biome = self.roll_neighbor_biome(parent_biome)

            biome_map[(q, r)] = hex_biome

            # Determine feature:
            # Sandbox Generator p. 11:
            # Hex 1 is a village/settlement
            # Hex 2 is a dungeon
            # Other hexes roll standard feature distribution
            if i == 1:
                f_type = "Settlement"
            elif i == 2:
                f_type = "Dungeon"
            else:
                d6 = random.randint(1, 6)
                if d6 <= 3:
                    f_type = "Wilds"
                elif d6 == 4:
                    f_type = "Landmark"
                elif d6 == 5:
                    f_type = "Settlement"
                else:
                    f_type = "Lair" if random.randint(1, 2) == 1 else "Dungeon"

            cell = HexCell(
                hex_index=i,
                q=q,
                r=r,
                biome=hex_biome,
                feature_type=f_type
            )

            details: Dict[str, Any] = {
                "encounter": self.roll_wilderness_encounter(hex_biome),
                "weather": region_weather
            }

            if f_type == "Wilds":
                hazard = self.roll_hazard()
                spark = self.roll_knowledge_spark()
                cell.title = f"Hex {i}: {hex_biome} Expanse"
                cell.summary = f"Wild terrain ({hazard.get('name')})."
                details["hazard"] = hazard
                details["spark"] = spark

            elif f_type == "Landmark":
                lm = self.roll_landmark()
                cell.title = f"Hex {i}: {lm.get('name')}"
                cell.summary = f"{lm.get('category')} landmark ({lm.get('subcategory')})."
                details["landmark"] = lm

            elif f_type == "Settlement":
                # Make center a Village, others varied
                st = "Village" if i == 1 else None
                settle = self.roll_settlement(st)
                cell.title = f"Hex {i}: {settle.get('name')}"
                cell.summary = f"{settle.get('type')} ({settle.get('population')})."
                details["settlement"] = settle

            elif f_type == "Lair":
                lair = self.roll_lair(hex_biome)
                cell.title = f"Hex {i}: {lair.get('monster')} Lair"
                cell.summary = f"Nesting ground of {lair.get('monster').lower()}."
                details["lair"] = lair

            elif f_type == "Dungeon":
                dungeon = self.roll_dungeon_entrance(hex_biome)
                cell.title = f"Hex {i}: {dungeon.get('dungeon_name')}"
                cell.summary = f"Entrance to {dungeon.get('dungeon_type').lower()} delve."
                details["dungeon"] = dungeon

            cell.details = details
            cells.append(cell)

        return HexRegion(
            name=name,
            layout_type=layout_type,
            center_biome=center_biome,
            weather=region_weather,
            notes=f"Generated regional sandbox centered on {center_biome}.",
            cells=cells
        )
