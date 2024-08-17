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
    parser.add_argument(
        "--download",
        default=False,
        action="store_true",
        help=(
            "Do not use the locally installed protocol definitions, instead"
            "download the latest available protocol definitions."
        ),
    )
    args = parser.parse_args()

    parser = WaylandParser()

    # Try to parse local protocol files
    if not args.download:
        uris = parser.get_local_files()

    # Download protocol definitions if no local one or explicitly requested
    if args.download or not uris:
        uris = parser.get_remote_uris()

    for i, protocol in enumerate(uris):
        log.info(f"Parsing protocol definition {i+1} of {len(uris)}")
        parser.parse(protocol)

    parser.create_type_hinting(parser.interfaces, get_package_root())
    log.info("Created type hinting file.")

    protocols = parser.to_json(minimise=args.no_minimise)
    filepath = f"{get_package_root()}/protocols.json"
    with open(filepath, "w", encoding="utf-8") as outfile:
        outfile.write(protocols)
    log.info("Created protocol database: " + filepath)
