"""Demo runnable : Red -> Blue -> Green sur le catalogue d'attaques (Phase 10).

Usage : python scripts/red_blue_green_demo.py
Sortie ASCII (console Windows-safe) : pour chaque cas, le signal Blue, la reponse Green,
et la mise en quarantaine.
"""

from sandbox.security import RED_CASES, triage


def main() -> None:
    header = f"{'CAS':<26}{'VECTEUR':<22}{'SIGNAL (Blue)':<20}{'REPONSE (Green)':<28}QUARANTAINE"
    print(header)
    print("-" * len(header))
    for c in RED_CASES:
        d = triage(c.action)
        flag = "OUI" if d.quarantined else "non"
        print(f"{c.id:<26}{c.vector:<22}{str(d.signal):<20}{d.response:<28}{flag}")


if __name__ == "__main__":
    main()
