import sys
import xml.etree.ElementTree as ET


def coverage_percent(xml_path: str) -> float:
    root = ET.parse(xml_path).getroot()
    return float(root.attrib["line-rate"]) * 100


def main(xml_path: str, threshold_path: str) -> int:
    measured = coverage_percent(xml_path)
    with open(threshold_path) as f:
        threshold = float(f.read().strip())
    print(f"Couverture mesurée : {measured:.2f}% (seuil : {threshold:.2f}%)")
    if measured < threshold:
        print(f"ÉCHEC : couverture {measured:.2f}% < seuil {threshold:.2f}%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
