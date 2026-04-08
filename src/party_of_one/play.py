"""CLI for Party of One — interactive and non-interactive modes.

Usage:
    # Interactive:
    python -m party_of_one.play

    # Non-interactive (new game):
    python -m party_of_one.play --new --name "Hero" --class_ "Warrior" --companions "Бранка,Тихомир" --setting "Тёмные пещеры"

    # Non-interactive (continue):
    python -m party_of_one.play --session <session_id> --action "Осматриваюсь"
"""

from __future__ import annotations

import argparse
import sys

from party_of_one.agents.companion import load_companion_profiles
from party_of_one.config import load_config
from party_of_one.logger import setup_logging
from party_of_one.orchestrator import Orchestrator


def main():
    parser = argparse.ArgumentParser(description="Party of One")
    parser.add_argument("--new", action="store_true", help="Start a new game (non-interactive)")
    parser.add_argument("--session", type=str, help="Session ID to continue (non-interactive)")
    parser.add_argument("--name", type=str, default="Герой", help="Player name")
    parser.add_argument("--class_", type=str, default="Воин", help="Player class")
    parser.add_argument("--companions", type=str, help="Companion names (comma separated)")
    parser.add_argument("--setting", type=str, help="Setting description")
    parser.add_argument("--action", type=str, help="Player action (non-interactive)")
    args = parser.parse_args()

    config = load_config()
    setup_logging(log_file=config.logging.file, level=config.logging.level)

    if args.new:
        _new_game(config, args)
    elif args.session and args.action:
        _continue_game(config, args)
    else:
        _interactive(config, args)


# ── Interactive mode ───────────────────────────────────────────────────────

def _interactive(config, args):
    print("╔══════════════════════════════════════╗")
    print("║        Party of One — RPG Cairn      ║")
    print("╚══════════════════════════════════════╝")
    print()

    # Загрузить доступных компаньонов
    profiles = load_companion_profiles(config.game.companion_profiles_path)

    # Проверить, есть ли сессия для продолжения
    session_id = args.session
    if session_id:
        orch = Orchestrator(config, session_id=session_id)
        if not orch.db.characters.list(role="player"):
            print(f"Сессия '{session_id}' не найдена.")
            orch.db.close()
            session_id = None
        else:
            print(f"Продолжаем сессию: {session_id}")
            print()
            print(orch.db.snapshot())
            print()

    if not session_id:
        # Новая игра
        name = input("Имя персонажа [Герой]: ").strip() or "Герой"

        archetypes = ["Воин", "Следопыт", "Маг", "Плут"]
        print("\nДоступные классы:")
        for i, a in enumerate(archetypes, 1):
            print(f"  {i}. {a}")
        class_input = input("Выбери класс (номер) [1]: ").strip() or "1"
        class_ = archetypes[int(class_input) - 1] if class_input.isdigit() else class_input

        print("\nДоступные компаньоны:")
        for i, p in enumerate(profiles, 1):
            print(f"  {i}. {p.name} ({p.class_}) — {p.personality.traits[0]}")

        comp_input = input("\nВыбери двух (номера через пробел) [1 2]: ").strip() or "1 2"
        indices = [int(x) - 1 for x in comp_input.split()][:2]
        if len(indices) < 2:
            indices = [0, 1]
        companion_names = [profiles[i].name for i in indices]

        setting = input("Описание сеттинга [Мрачное средневековое фэнтези]: ").strip()
        setting = setting or "Мрачное средневековое фэнтези"

        print("\nСоздаю игру...")
        orch = Orchestrator(config)
        session_id = orch.session_id

        dm_response = orch.init_game(
            player_name=name,
            player_archetype=class_,
            companion_choices=companion_names,
            setting_description=setting,
        )

        print(f"\nСессия: {session_id}")
        print("─" * 40)
        print(dm_response.narrative)
        print("─" * 40)
        print()
        print(orch.db.snapshot())

    # Игровой цикл
    print("\nВведи действие (или /quit для выхода):\n")
    while not orch.is_ended:
        try:
            action = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nСохранено. До встречи!")
            break

        if not action:
            continue
        if action.lower() in ("/quit", "/exit", "/q"):
            print("Сохранено. До встречи!")
            break

        print()
        result = orch.process_round(action)

        role_labels = {
            "player": "Игрок",
            "companion_a": "Компаньон A",
            "companion_b": "Компаньон B",
        }
        for actor_role, dm_resp in zip(result.actor_roles, result.dm_responses):
            role_val = actor_role.value
            label = role_labels.get(role_val, role_val)

            if role_val in result.companion_texts:
                print(f"── {label} ──")
                print(result.companion_texts[role_val])
                print()

            print(f"── DM (→ {label}) ──")
            print(dm_resp.narrative)
            print()

        if result.session_ended:
            print(f"═══ СЕССИЯ ЗАВЕРШЕНА ({result.end_reason}) ═══")
            break

        print(orch.db.snapshot())
        print()

    orch.db.close()


# ── Non-interactive modes ──────────────────────────────────────────────────

def _new_game(config, args):
    companion_names = [n.strip() for n in (args.companions or "Бранка,Тихомир").split(",")][:2]

    orch = Orchestrator(config)
    print(f"SESSION_ID={orch.session_id}")
    print()

    dm_response = orch.init_game(
        player_name=args.name,
        player_archetype=args.class_,
        companion_choices=companion_names,
        setting_description=args.setting or "Мрачное средневековое фэнтези",
    )

    print("=== INIT ===")
    print(f"DM: {dm_response.narrative}")
    print()
    print("=== WORLD STATE ===")
    print(orch.db.snapshot())
    orch.db.close()


def _continue_game(config, args):
    orch = Orchestrator(config, session_id=args.session)

    if not orch.db.characters.list(role="player"):
        print(f"ERROR: Сессия '{args.session}' не найдена", file=sys.stderr)
        sys.exit(1)

    print(f"SESSION_ID={args.session}")
    print(f"ROUND={orch.round_number + 1}")
    print()

    result = orch.process_round(args.action)

    role_labels = {"player": "Игрок", "companion_a": "Компаньон A", "companion_b": "Компаньон B"}
    for actor_role, dm_resp in zip(result.actor_roles, result.dm_responses):
        role_val = actor_role.value
        label = role_labels.get(role_val, role_val)

        if role_val in result.companion_texts:
            print(f"=== {label} ===")
            print(result.companion_texts[role_val])
            print()

        print(f"=== DM (→ {label}) ===")
        print(dm_resp.narrative)
        print()

    if result.session_ended:
        print(f"=== SESSION ENDED ({result.end_reason}) ===")

    print("=== WORLD STATE ===")
    print(orch.db.snapshot())
    orch.db.close()


if __name__ == "__main__":
    main()
