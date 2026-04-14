"""Entry point: TUI (default) or non-interactive CLI."""

import sys


def main():
    args = sys.argv[1:]

    if "--play" in args or "--new" in args or "--session" in args:
        # Non-interactive CLI mode
        from party_of_one.play import main as play_main
        play_main()
    else:
        # TUI mode (default)
        watch = "--watch" in args
        rounds = 0  # 0 = infinite
        for i, a in enumerate(args):
            if a == "--rounds" and i + 1 < len(args):
                rounds = int(args[i + 1])

        from party_of_one.cli import run_tui
        run_tui(watch=watch, rounds=rounds)


if __name__ == "__main__":
    main()
