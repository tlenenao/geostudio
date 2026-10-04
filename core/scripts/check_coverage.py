import os
import sys
import xml.etree.ElementTree as ET


def coverage_percent(xml_path: str) -> float:
    root = ET.parse(xml_path).getroot()
    return float(root.attrib["line-rate"]) * 100


def package_rates(xml_path: str) -> list[tuple[str, float]]:
    """REV-281a : couverture par module (<package> Cobertura), la plus basse d'abord."""
    root = ET.parse(xml_path).getroot()
    rates = [(p.attrib["name"], float(p.attrib["line-rate"]) * 100) for p in root.iter("package")]
    return sorted(rates, key=lambda r: r[1])


def report(rates: list[tuple[str, float]]) -> str:
    rows = [f"| {name} | {rate:.1f} % |" for name, rate in rates]
    return "\n".join(["| Module | Couverture |", "|---|---|", *rows])


def main(xml_path: str, threshold_path: str) -> int:
    measured = coverage_percent(xml_path)
    with open(threshold_path) as f:
        threshold = float(f.read().strip())
    print(f"Couverture mesurée : {measured:.2f}% (seuil : {threshold:.2f}%)")
    rates = package_rates(xml_path)
    if rates:
        table = report(rates)
        print(table)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as f:
                f.write(f"### Couverture du cœur par module\n\n{table}\n")
    if measured < threshold:
        print(f"ÉCHEC : couverture {measured:.2f}% < seuil {threshold:.2f}%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
