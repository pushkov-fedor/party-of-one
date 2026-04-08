"""Simple input/print loop for testing the game flow."""

from party_of_one.agents.companion import load_companion_profiles
from party_of_one.config import load_config
from party_of_one.logger import setup_logging
from party_of_one.orchestrator import Orchestrator


def main():
    config = load_config()
    setup_logging(log_file=config.logging.file, level=config.logging.level)

    print("=" * 60)
    print("  Party of One — Solo RPG")
    print("=" * 60)
    print()

    # Character creation
    name = input("Имя персонажа: ").strip() or "Герой"
    print("\nАрхетипы: Воин, Следопыт, Маг, Плут")
    class_ = input("Архетип: ").strip() or "Воин"

    # Companion selection
    profiles = load_companion_profiles(config.game.companion_profiles_path)
    print("\nВыбери двух компаньонов:")
    for i, p in enumerate(profiles):
        print(f"  {i + 1}. {p.name} ({p.class_}) — {p.traits[0] if p.traits else ''}")

    comp_input = input("\nНомера двух компаньонов (через пробел, напр. '1 3'): ").strip()
    try:
        indices = [int(x) - 1 for x in comp_input.split()][:2]
        if len(indices) < 2:
            indices = [0, 1]
    except ValueError:
        indices = [0, 1]

    chosen = [profiles[i] for i in indices]
    print(f"\nКомпаньоны: {chosen[0].name} ({chosen[0].class_}), {chosen[1].name} ({chosen[1].class_})")

    # Setting
    print()
    setting = input("Опиши сеттинг (свободный текст): ").strip()
    if not setting:
        setting = "Мрачное средневековое фэнтези. Тёмный лес, заброшенные руины, опасные твари."
    print()

    # Initialize
    print("DM готовит начальную сцену...\n")
    orch = Orchestrator(config)
    opening = orch.init_game(name, class_, setting, indices)
    print(f"DM: {opening}\n")

    # Game loop
    while not orch.is_ended:
        print("=" * 60)
        action = input("\n> ").strip()

        if not action:
            continue
        if action.lower() in ("/quit", "/exit"):
            print("\nСессия завершена.")
            break

        results = orch.process_round(action)

        for r in results:
            role = r["role"]
            if role == "dm":
                print(f"\nDM: {r['narrative']}")
            elif "companion" in role:
                print(f"\n  {r['narrative']}")
            print()

    orch.db.close()


if __name__ == "__main__":
    main()
