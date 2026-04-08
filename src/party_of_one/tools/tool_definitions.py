"""OpenAI function-calling tool definitions for the DM agent."""

TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "roll_dice",
            "description": "Roll dice. Result from RNG, not AI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sides": {"type": "integer", "enum": [4, 6, 8, 10, 12, 20]},
                    "count": {"type": "integer", "minimum": 1, "maximum": 10, "default": 1},
                },
                "required": ["sides"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity",
            "description": "Get full entity record from World State.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["character", "location", "quest"]},
                    "id": {"type": "string"},
                },
                "required": ["type", "id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "damage_character",
            "description": "Deal damage to character (after armor reduction). HP->STR cascade.",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                    "amount": {"type": "integer", "minimum": 1},
                },
                "required": ["character_id", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "heal_character",
            "description": "Restore HP (capped at max_hp). Fails if deprived.",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                    "amount": {"type": "integer", "minimum": 1},
                },
                "required": ["character_id", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "damage_stat",
            "description": "Direct stat damage (STR=0->death, DEX=0->paralysis, WIL=0->delirium).",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                    "stat": {"type": "string", "enum": ["strength", "dexterity", "willpower"]},
                    "amount": {"type": "integer", "minimum": 1},
                },
                "required": ["character_id", "stat", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restore_stat",
            "description": "Restore stat (capped at max). Fails if deprived.",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                    "stat": {"type": "string", "enum": ["strength", "dexterity", "willpower"]},
                    "amount": {"type": "integer", "minimum": 1},
                },
                "required": ["character_id", "stat", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_character",
            "description": "Update character field: status, disposition, location_id or notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                    "field": {"type": "string", "enum": ["status", "disposition", "location_id", "notes"]},
                    "value": {"type": "string"},
                },
                "required": ["character_id", "field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_entity",
            "description": "Move character to an adjacent location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "location_id": {"type": "string"},
                },
                "required": ["entity_id", "location_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_item",
            "description": "Add item to inventory. Checks 10-slot limit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                    "item": {"type": "string", "maxLength": 100},
                    "bulky": {"type": "boolean", "default": False},
                },
                "required": ["character_id", "item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_item",
            "description": "Remove item from inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                    "item": {"type": "string"},
                },
                "required": ["character_id", "item"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_fatigue",
            "description": "Add fatigue (spell, exhaustion). Takes 1 inventory slot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                },
                "required": ["character_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_fatigue",
            "description": "Remove one fatigue (after safe rest).",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                },
                "required": ["character_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_gold",
            "description": "Change gold (positive=gain, negative=spend).",
            "parameters": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                    "amount": {"type": "integer"},
                },
                "required": ["character_id", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_event",
            "description": "Record event to timeline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "maxLength": 200},
                    "event_type": {"type": "string", "enum": ["combat", "dialogue", "discovery", "quest", "death"]},
                },
                "required": ["description", "event_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_quest",
            "description": "Update quest status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "quest_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["active", "completed", "failed"]},
                },
                "required": ["quest_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_location",
            "description": "Update location description, connections or discovered status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_id": {"type": "string"},
                    "field": {"type": "string", "enum": ["description", "connected_to", "discovered"]},
                    "value": {"type": "string"},
                },
                "required": ["location_id", "field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_character",
            "description": "Create new character (NPC, companion). max_hp=hp, max_stats=stats on creation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": 100},
                    "role": {"type": "string", "enum": ["npc", "companion"]},
                    "class_": {"type": "string", "maxLength": 100},
                    "description": {"type": "string", "maxLength": 500},
                    "disposition": {"type": "string", "enum": ["friendly", "neutral", "hostile"]},
                    "location_id": {"type": "string"},
                    "strength": {"type": "integer"},
                    "dexterity": {"type": "integer"},
                    "willpower": {"type": "integer"},
                    "hp": {"type": "integer"},
                    "armor": {"type": "integer", "default": 0, "maximum": 3},
                    "gold": {"type": "integer", "default": 0},
                },
                "required": ["name", "role", "class_", "disposition", "location_id",
                             "strength", "dexterity", "willpower", "hp"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_quest",
            "description": "Create new quest.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 200},
                    "description": {"type": "string", "maxLength": 500},
                    "giver_character_id": {"type": "string"},
                },
                "required": ["title", "description", "giver_character_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_location",
            "description": "Create new location. Connections are bidirectional.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": 100},
                    "description": {"type": "string", "maxLength": 500},
                    "connected_to": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                },
                "required": ["name", "description", "connected_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_rules",
            "description": "Поиск правил Cairn по запросу. Используй когда нужны правила боя, спасбросков, магии, снаряжения.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос на русском языке"},
                },
                "required": ["query"],
            },
        },
    },
]
