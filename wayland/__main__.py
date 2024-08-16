import argparse

from wayland import get_package_root
from wayland.log import log
from wayland.parser import WaylandParser

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process Wayland protocols.")
    parser.add_argument(
        "--no-minimise",
        default=True,
        action="store_false",
        help="Disable the minimisation of protocol files.",
    )
    args = parser.parse_args()

    with open(f"{get_package_root()}/cache/sources.txt", encoding="utf-8") as outfile:
        sources = [x.strip() for x in outfile]

    parser = WaylandParser(use_cache=True)
    for source in sources:
        parser.load_file(source)

    parser.create_type_hinting(parser.interfaces, get_package_root())
    log.warning("Created type hinting file.")

    protocols = parser.to_json(minimise=args.no_minimise)
    filepath = f"{get_package_root()}/cache/protocols.json"
    with open(filepath, "w", encoding="utf-8") as outfile:
        outfile.write(protocols)
    log.warning("Created protocol database: " + filepath)
