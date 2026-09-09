import json

hex_hazards = {
  "name": "hex_hazards",
  "dice": "d20",
  "entries": [
    {"min": 1, "max": 1, "name": "Acid Pools", "effect": "Corrosive steaming pools eat through boots and gear.", "guidance": "Navigate single-file with caution or suffer gear degradation."},
    {"min": 2, "max": 2, "name": "Allergenic & Poisonous Plants", "effect": "Pungent pollen causes burning eyes, coughing fits, and rash.", "guidance": "Cover face with dampened cloth or suffer -1 on checks."},
    {"min": 3, "max": 3, "name": "Ancient Dormant Sickness", "effect": "Plague-bearing mist or mold in old hollows.", "guidance": "Test constitution or contract shivering ague."},
    {"min": 4, "max": 4, "name": "Lurking Curse", "effect": "An invisible hex clings to trespassers.", "guidance": "Spurs misfortune on the next critical encounter."},
    {"min": 5, "max": 5, "name": "Treacherous Footing", "effect": "Slippery shale, boggy moss, or loose scree slows progress to a crawl.", "guidance": "Travel takes double time or risk sprained ankles."},
    {"min": 6, "max": 6, "name": "Disorienting Terrain", "effect": "Confusing ridgelines or identical copses make it easy to get lost.", "guidance": "Navigation check required or lose half a day doubling back."},
    {"min": 7, "max": 7, "name": "Blinding Fog", "effect": "Dense white pea-soup mist blankets the entire hex.", "guidance": "Visibility reduced to 10 paces; surprise checks are at disadvantage."},
    {"min": 8, "max": 8, "name": "Noxious Fumes", "effect": "Volcanic sulfur or decaying peat gas chokes the lungs.", "guidance": "Hasten through the area or suffer fatigue."},
    {"min": 9, "max": 9, "name": "Restless Hauntings", "effect": "Spirits of massacred wanderers follow with chilling wails.", "guidance": "Interrupts restful sleep; camping here grants no recovery."},
    {"min": 10, "max": 10, "name": "Hallucinogenic Spores", "effect": "Puffball mushrooms burst into vibrant psychedelic clouds.", "guidance": "Visions, disorientation, and paranoia plague the party."},
    {"min": 11, "max": 11, "name": "Concealed Natural Pits", "effect": "Deep fissures overgrown with brambles and vines.", "guidance": "Front scout must test alertness to avoid tumbling 20 feet."},
    {"min": 12, "max": 12, "name": "Old Hunting Traps", "effect": "Rusted iron wolf traps and deadfalls set by poachers.", "guidance": "Careful search required to avoid severe leg wound."},
    {"min": 13, "max": 13, "name": "Eldritch Taint", "effect": "Warped mutations, violet grass, and reversed shadows.", "guidance": "Prolonged exposure risks strange cosmetic or behavioral afflictions."},
    {"min": 14, "max": 14, "name": "Outbreak / Contaminated Water", "effect": "The streams and ponds are tainted with rotting carcasses.", "guidance": "Drinking unboiled water causes debilitating cramps."},
    {"min": 15, "max": 15, "name": "Quicksand / Mud Sink", "effect": "Firm-looking ground gives way into a sucking mire.", "guidance": "Requires rope and teamwork to extract trapped pack beasts."},
    {"min": 16, "max": 16, "name": "Arcane Radiation", "effect": "Faint blue hum warms metal armor and sickens creatures.", "guidance": "Iron grows hot to the touch; spellcasting causes unpredictable surges."},
    {"min": 17, "max": 17, "name": "Sabotaged Trail", "effect": "Felled timber and booby-trapped ropes placed by bandits.", "guidance": "Ambush is likely if the trap is triggered."},
    {"min": 18, "max": 18, "name": "Unstable Cliff / Overhang", "effect": "Cracking rock ledges liable to shear off under pack weight.", "guidance": "Tether party members together while traversing heights."},
    {"min": 19, "max": 19, "name": "Venomous Swarm", "effect": "Nests of red hornets, vipers, or black scorpions.", "guidance": "Scout ahead with smoke or detour around nesting grounds."},
    {"min": 20, "max": 20, "name": "Active Thermal Vent", "effect": "Superheated geysers and spurts of scalding mud.", "guidance": "Listen for rumbling ground to avoid scalding eruptions."}
  ]
}

hex_sparks = {
  "name": "hex_sparks",
  "knowledge_tables": [
    {"min": 1, "max": 5, "type": "Monster Lore", "prompt": "Clues regarding a nearby beast or faction: territorial boundary marks, favored prey, or a vulnerability."},
    {"min": 6, "max": 6, "type": "Alchemy Formula", "prompt": "An etched recipe on stone or bark revealing how to distill local flora into an antitoxin or poultice."},
    {"min": 7, "max": 7, "type": "Curative Spring or Herb", "prompt": "The specific location of a mineral spring or root with potent rejuvenating properties."},
    {"min": 8, "max": 8, "type": "Settlement Directions", "prompt": "A blazed trail or traveler marker pointing toward the nearest refuge, ford, or trading post."},
    {"min": 9, "max": 9, "type": "Dungeon Entrance Location", "prompt": "A carved map or cryptic riddle disclosing the concealed entrance to a subterranean crypt or ruin."},
    {"min": 10, "max": 10, "type": "Prophesied Event", "prompt": "A dire omen or astrological alignment heralding an impending raid, eclipse, or calamity."},
    {"min": 11, "max": 11, "type": "Historic Chronicle", "prompt": "A commemorative inscription recounting a decisive battle or treaty between ancient factions."},
    {"min": 12, "max": 12, "type": "Myth & Local Folklore", "prompt": "A folk ballad or fireside legend hinting at an ancient guardian and the tribute it demands."},
    {"min": 13, "max": 13, "type": "Regional Custom & Taboo", "prompt": "Knowledge of a sacred boundary or sign of peace recognized by the local inhabitants."},
    {"min": 14, "max": 14, "type": "Password / Phrase", "prompt": "A cipher word that pacifies an enchanted ward, sentry construct, or smuggler post."},
    {"min": 15, "max": 15, "type": "Secret Route / Shortcut", "prompt": "A camouflaged goat path cutting straight through impassable terrain, halving travel time."},
    {"min": 16, "max": 16, "type": "Spell Scroll or Ritual Fragment", "prompt": "Vellum scrap or engraved slate holding the words to an obscure cantrip or minor ritual."},
    {"min": 17, "max": 17, "type": "Legend of a Relic", "prompt": "Tale of a hero's lost blade, staff, or ring buried nearby with clues to its resting place."},
    {"min": 18, "max": 18, "type": "Toxicity / Edibility Insight", "prompt": "Clear signs distinguishing which local berries and mushrooms are nourishing versus fatal."},
    {"min": 19, "max": 19, "type": "Upcoming Weather Signs", "prompt": "Atmospheric pressure, cloud shapes, and bird flight indicating severe storms or unseasonal warmth."},
    {"min": 20, "max": 20, "type": "Monster Language Vocabulary", "prompt": "Crucial phrases in Goblin, Orcish, or Draconic enabling parley rather than immediate bloodshed."}
  ],
  "special_quests": {
    "Disputes": [
      "Adultery or broken family honor between two influential clans",
      "Broken trade charter over grain tariffs and smuggled salt",
      "Contested inheritance of a deceased merchant estate",
      "Murder investigation with contradictory alibis and tainted evidence",
      "Disputed territorial boundary marker moved in the dead of night",
      "Impending execution trial where the accused claims divine innocence"
    ],
    "Threats": [
      "Fanatical cultists preparing a blood ritual at the next moonrise",
      "Impending flash flood threatening to wash away the river crossing",
      "Stampeding herd of panicked beasts fleeing a worse terror",
      "Creeping magical blight withering crops and poisoning wells",
      "Virulent pestilence spreading from an unburied mass grave",
      "Uncontrolled wildfire raging across the dry prairie or forest"
    ],
    "Mysteries": [
      "Unexplained nighttime abductions leaving only claw marks",
      "A weeping phantom wandering the crossroads pleading for burial",
      "Ancestral curse that strikes the firstborn of every generation",
      "A sudden miraculous healing spring drawing desperate pilgrims",
      "Bizarre mutations appearing among newborn livestock",
      "Enigmatic glowing lights dancing above the marshes at midnight"
    ],
    "NPC_In_Need": [
      "Wounded traveler stricken with amnesia clutching a bloody signet",
      "Desperate merchant fleeing pursuing outlaws across the rocks",
      "Weeping parent whose child vanished near the barrow mounds",
      "Exhausted pilgrims on the verge of dying from hunger and thirst",
      "Escaped captive in iron manacles being tracked by hunting hounds",
      "Injured knight trapped beneath a dead warhorse in a ravine"
    ]
  }
}

hex_settlements = {
  "name": "hex_settlements",
  "types": {
    "Hamlet": {
      "population": "10-30 inhabitants",
      "description": "A quiet cluster of thatched huts around a single central trade or farmstead.",
      "main_buildings": [
        "Cider Brewery & Orchard", "Wayside Stone Chapel", "Goat & Dairy Ranch",
        "Water Mill on the Creek", "Tannery & Smokehouse", "Timber Logging Yard",
        "Peat Cutter Hovel", "Potter Kiln Workshop", "Herbalist Drying Barn", "Charcoal Burner Camp"
      ],
      "secrets": [
        "None (honest, weary folk)",
        "The elders practice blood offerings at midnight for good harvest",
        "Harboring an exiled prince or wanted fugitive in the attic",
        "Several villagers have been replaced by dopplegangers or mimics",
        "The hamlet hides a curse: lycanthropy runs through the bloodline",
        "A hidden smuggler cellar beneath the chapel stores contraband silver"
      ]
    },
    "Village": {
      "population": "50-250 inhabitants",
      "description": "A fortified rural settlement with communal square, tavern, and craft shops.",
      "specialties": [
        "Iron mining & master smithing", "Fine wool weavers & dye pits", "Vineyards & cask vintners",
        "Horse breeding for heavy cavalry", "River fishing & salt curing", "Timber milling & carpentry",
        "Stone quarrying & masonry", "Apiaries & aromatic candle-wax"
      ],
      "rulers": [
        "Elected village bailiff / alderman", "Hereditary landed knight", "Venerable high priest / druid elder",
        "Wealthy guild factor / merchant mayor", "Council of matriarchs", "Stern militia captain"
      ],
      "troubles": [
        "Demanding tithes from an extortionate neighboring robber-baron",
        "Lurking pack of worgs picking off lone shepherds at twilight",
        "Severe water contamination caused by a poisoned upstream spring",
        "A sharp dispute between the smithing guild and the church elders",
        "Famine reserves running dangerously low before winter sets in",
        "Corrupt bailiff skimming the kingdom tax collector ledger"
      ],
      "tavern_names": [
        "The Silver Sturgeon", "The Drunken Griffin", "The Rusty Horseshoe", "The Maiden & Wheel",
        "The Boar & Flagon", "The Weeping Willow Taproom", "The Golden Anvil", "The Black Ram Tavern"
      ]
    },
    "City": {
      "population": "1,000-10,000+ inhabitants",
      "description": "Sprawling fortified metropolis ringed with stone walls, crowded markets, and bustling guilds.",
      "districts": [
        "High Merchant Quarter", "The Harbor Docks & Warehouses", "The Grand Cathedral Plaza",
        "The Artisan Guildhall Ward", "The Warrens & Beggar Slums", "The Citadel Barracks"
      ],
      "rulers": [
        "Lord Mayor and Guild Council", "High Prince or Duchess", "Archbishop of the Holy Synod",
        "Military Governor under martial decree", "Oligarchy of Grand Merchants"
      ]
    },
    "Castle": {
      "population": "100-500 garrison & court",
      "description": "A formidable fortress of high stone curtain walls, dry moats, and iron-toothed portcullises.",
      "garrison": [
        "Knight-Commander & Men-at-Arms", "Mercenary Halberdiers", "Longbow Archers on the Ramparts",
        "Heavy Armored Shock Cavalry", "Castle Crossbowmen"
      ],
      "defenses": [
        "Deep dry moat spanned by counterweighted drawbridge",
        "Machicolations and murder holes pouring boiling pitch",
        "Massive concentric curtain walls with square bastions",
        "Heavy iron portcullises and reinforced oak gates"
      ],
      "rulers": [
        "Baron / Earl of the border marches", "Fierce veteran warlord", "Solemn hereditary castellan",
        "Ruthless noble scheming to seize the provincial throne"
      ]
    },
    "Tower": {
      "population": "5-25 acolytes & guards",
      "description": "A lone, imposing stone spire rising above the wilderness, humming with dormant arcane power.",
      "inhabitants": [
        "Reclusive Astrologer observing the night sky", "Elementalist Wizard experimenting with alchemy",
        "Eccentric Illusionist paranoid of visitors", "Necromancer studying forbidden tomes",
        "Clockwork Artificer attended by bronze automata"
      ],
      "features": [
        "Rooftop observatory with giant bronze astrolabe",
        "Subterranean alchemy laboratory with bubbling alembics",
        "Labyrinthine library lined with trapped spellbooks",
        "Enchanted gargoyles perched on the parapets serving as sentries"
      ]
    },
    "Abbey": {
      "population": "30-150 monks or nuns",
      "description": "A tranquil monastic sanctuary enclosed within high stone perimeter walls.",
      "activities": [
        "Viticulture and fine herbal liqueurs", "Copying ancient manuscripts in the scriptorium",
        "Herbal healing, infirmary care, and alchemy", "Breeding warhorses and draft oxen",
        "Guarding a revered saint relic in the crypt"
      ],
      "relics": [
        "The Silver Fingerbone of Saint Geffrey", "The Weeping Icon of the Blessed Mother",
        "The Unbroken Lance of the Martyr Knight", "The Sun-Gold Chalice of Deliverance"
      ]
    }
  },
  "name_generators": {
    "prefixes": [
      "Oakhaven", "Stone", "Raven", "Iron", "High", "Deep", "Silver", "Cold", "Black",
      "Green", "White", "Fair", "Wolf", "Barrow", "Crest", "Red", "Sun", "Ash", "Storm", "Shadow"
    ],
    "suffixes": [
      "ford", "haven", "dale", "stead", "burg", "ton", "mill", "cross", "bridge",
      "wick", "hollow", "fell", "glen", "mere", "keep", "crest", "marsh", "hall", "vale", "port"
    ]
  }
}

hex_weather = {
  "name": "hex_weather",
  "temperatures": [
    {"min": 1, "max": 2, "name": "Freezing", "desc": "Bone-chilling frost; water freezes solid; hypothermia risk without warm furs."},
    {"min": 3, "max": 5, "name": "Cold & Crisp", "desc": "Brisk autumn chill; breath mists in the air; pleasant for fast marching."},
    {"min": 6, "max": 8, "name": "Mild & Temperate", "desc": "Gentle, comfortable weather ideal for cross-country travel."},
    {"min": 9, "max": 11, "name": "Warm & Humid", "desc": "Heavy warmth; pack beasts tire quickly; requires frequent hydration."},
    {"min": 12, "max": 12, "name": "Sweltering Heat", "desc": "Blistering scorching sun; mirages on the horizon; heat exhaustion risk."}
  ],
  "conditions": [
    {"min": 1, "max": 2, "name": "Clear Blue Skies", "desc": "Unobscured sun and unlimited visibility to the horizon.", "travel_impact": "Full travel speed."},
    {"min": 3, "max": 4, "name": "Scattered Clouds", "desc": "Gentle, rolling cumulus clouds offering intermittent shade.", "travel_impact": "Full travel speed."},
    {"min": 5, "max": 6, "name": "Overcast & Gloomy", "desc": "Lead-grey cloud blanket muting light and casting dreary shadows.", "travel_impact": "Full travel speed."},
    {"min": 7, "max": 7, "name": "Creeping Mist / Fog", "desc": "Ground-level fog obscuring distant landmarks.", "travel_impact": "Slowed pace; navigation checks at -1."},
    {"min": 8, "max": 9, "name": "Light Rain / Drizzle", "desc": "Steady, damp drizzle soaking clothes and softening the soil.", "travel_impact": "Normal pace; campsite prep requires dry timber."},
    {"min": 10, "max": 10, "name": "Heavy Downpour", "desc": "Torrents of blinding rain churning roads into thick mud.", "travel_impact": "Movement halved; small brooks swell into torrents."},
    {"min": 11, "max": 11, "name": "Raging Thunderstorm", "desc": "Crashing lightning, deafening thunderclaps, and howling squalls.", "travel_impact": "Travel dangerous; open terrain risks lightning strikes."},
    {"min": 12, "max": 12, "name": "Blinding Snow / Sleet", "desc": "Howling blizzard and zero visibility.", "travel_impact": "Parties must seek shelter or become hopelessly lost."}
  ],
  "winds": [
    {"min": 1, "max": 4, "name": "Calm Air", "desc": "Still, motionless leaves and smoke rising straight up."},
    {"min": 5, "max": 8, "name": "Gentle Breeze", "desc": "Pleasant rustling in the treetops, carrying scents."},
    {"min": 9, "max": 11, "name": "Stiff Wind", "desc": "Buffeting gusts that tear at cloaks and rattle branches."},
    {"min": 12, "max": 12, "name": "Howling Gale", "desc": "Violent squalls that snap boughs and whip dust into eyes."}
  ]
}

hex_npcs = {
  "name": "hex_npcs",
  "first_names": [
    "Alden", "Arthur", "Bella", "Brant", "Cecilia", "David", "Dina", "Eliza", "Finn", "Georg",
    "Hank", "Helen", "Ingol", "John", "Kaelen", "Lilly", "Mona", "Olov", "Sophie", "Thomas",
    "Tisha", "Vaughn", "Will", "Yvaine", "Bram", "Cora", "Eamon", "Gareth", "Lyra", "Rowan"
  ],
  "surnames": [
    "Briggs", "Burrows", "Button", "Cray", "Flint", "Gibbs", "Griffith", "Hartley", "Head", "Hook",
    "Lloyd", "Moore", "Poole", "Powell", "Quinn", "Robinson", "Shaw", "Smith", "Taylor", "Wright",
    "Blackwood", "Stone", "Miller", "Fletcher", "Thorn", "Hawthorne", "Rivers", "Winter", "Vane", "Frost"
  ],
  "occupations": [
    "Alchemist", "Apothecary", "Armorer", "Bounty Hunter", "Cartographer", "Deserter",
    "Diplomat", "Falconer", "Fence / Dealer", "Fugitive Outlaw", "Guard / Sentry", "Herbalist",
    "Hunter / Trapper", "Inquisitor", "Knight Errant", "Locksmith", "Mercenary Veteran", "Merchant",
    "Minstrel", "Monk / Pilgrim", "Peasant Farmer", "Priest", "Scavenger", "Scholar / Sage",
    "Smuggler", "Soldier", "Spy", "Tavernkeeper", "Wandering Druid", "Witch Doctor"
  ],
  "clothing": [
    "Tattered, mud-spattered rags", "Threadbare traveler woolens and patched boots",
    "Sturdy boiled leather and oiled canvas cloak", "Clean, finely tailored linen and velvet trim",
    "Flamboyant dyed silks, feathered hat, and silver buckles", "Dull camouflaged hunter leathers and hood"
  ],
  "particularities": [
    "None of note", "Prominent facial scar from an old claw wound", "Uncanny mismatched eyes (one blue, one gold)",
    "Intricate tribal or arcane tattoos on neck and arms", "Multiple silver ear and nose piercings",
    "Missing two fingers on the left hand", "Raspy, whispered voice due to an old injury",
    "Peculiar habit of whistling jaunty funeral tunes", "Constantly checks behind shoulders for pursuers"
  ],
  "attitudes": [
    "Aggressive and quick to draw steel", "Cautious, suspicious, and keeping distance",
    "Warm, jovial, and eager to share fireside tales", "Aloof, condescending, and disdainful of commoners",
    "Anxious, skittish, and trembling at loud noises", "Secretive, choosing words with deliberate care",
    "Weary, fatalistic, and resigned to bad luck", "Calculating, always looking for financial profit"
  ],
  "dreams": [
    "Buying a modest homestead and hanging up weapons forever",
    "Avenging a fallen sibling slain by a monstrous warlord",
    "Uncovering a fabled lost relic to win royal favor",
    "Paying off an extortionate debt to a ruthless crime boss",
    "Exploring the unexplored wastes beyond the map borders",
    "Writing the definitive compendium of regional beasts"
  ],
  "secrets": [
    "None", "Carrying stolen guild gems hidden inside the hollow hilt of a weapon",
    "Fleeing a arranged marriage or royal arrest warrant", "Afflicted with a dormant lycanthrope bite",
    "Secretly an agent of an enemy faction gathering regional intelligence",
    "Stole the identity and papers of a dead traveler found along the road",
    "Suffering from a slow magical poison and desperately seeking a cure"
  ]
}

with open("data/hex_hazards.json", "w", encoding="utf-8") as f:
    json.dump(hex_hazards, f, indent=2)

with open("data/hex_sparks.json", "w", encoding="utf-8") as f:
    json.dump(hex_sparks, f, indent=2)

with open("data/hex_settlements.json", "w", encoding="utf-8") as f:
    json.dump(hex_settlements, f, indent=2)

with open("data/hex_weather.json", "w", encoding="utf-8") as f:
    json.dump(hex_weather, f, indent=2)

with open("data/hex_npcs.json", "w", encoding="utf-8") as f:
    json.dump(hex_npcs, f, indent=2)

print("All hex data files created successfully!")
