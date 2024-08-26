import argparse
import sys

from wayland import get_package_root
from wayland.log import log
from wayland.parser import WaylandParser

if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description="Process Wayland protocols.")
    argparser.add_argument(
        "--no-minimise",
        default=True,
        action="store_false",
        help="Disable the minimisation of protocol files.",
    )
    argparser.add_argument(
        "--download",
        default=False,
        action="store_true",
        help=(
            "Do not use the locally installed protocol definitions, instead"
            "download the latest available protocol definitions."
        ),
    )
    argparser.add_argument(
        "--verbose",
        default=False,
        action="store_true",
        help=("Verbose output when processing Wayland protocol files."),
    )
    argparser.add_argument(
        "--compare",
        default=False,
        action="store_true",
        help=(
            "Output a report comparing the local protocol files with "
            "the latest online versions. Only interfaces and there "
            "version numbers are compared, not any variances in specific "
            "requests or events."
        ),
    )
    args = argparser.parse_args()

    if args.verbose:
        log.enable()
        log.info("Starting Wayland protocol update.")

    # Compare protocol files if requested
    if args.compare:
        local_interfaces = {}
        remote_interfaces = {}

        print(
            "Comparing locally installed and latest official protocol definitions. Please wait."
        )

        # Get local protocols
        parser = WaylandParser()
        local_uris = parser.get_local_files()
        if local_uris:
            for i, protocol in enumerate(local_uris):
                log.info(
                    f"Parsing local protocol definition {i+1} of {len(local_uris)}"
                )
                parser.parse(protocol)
            # Extract interfaces and versions
            for interface, details in parser.interfaces.items():
                local_interfaces[interface] = details["version"]

        # Remote interfaces
        parser = WaylandParser()
        remote_uris = parser.get_remote_uris()
        if remote_uris:
            for i, protocol in enumerate(remote_uris):
                log.info(
                    f"Parsing remote protocol definition {i+1} of {len(local_uris)}"
                )
                parser.parse(protocol)
            # Extract interfaces and versions
            for interface, details in parser.interfaces.items():
                remote_interfaces[interface] = details["version"]

        # Compare
        changed_interfaces = {}
        for interface, local_version in local_interfaces.items():
            remote_version = remote_interfaces.get(interface)
            if remote_version is not None and local_version != remote_version:
                changed_interfaces[interface] = (local_version, remote_version)

        only_remote = {}
        for interface, remote_version in remote_interfaces.items():
            if interface not in local_interfaces:
                only_remote[interface] = remote_version

        only_local = {}
        for interface, local_version in local_interfaces.items():
            if interface not in remote_interfaces:
                only_local[interface] = local_version

        # Print the report
        print("\nProtocol definitions which have been updated:\n")
        for interface, versions in changed_interfaces.items():
            print(
                f"{interface}: local version {versions[0]}, remote version {versions[1]}"
            )

        print("\nAvailable remote protocol definitions, but not installed locally:\n")
        for interface, version in only_remote.items():
            print(f"{interface}: version {version}")

        print(
            "\nProtocol definitions installed locally but not in official stable or staging repositories:\n"
        )
        for interface, version in only_local.items():
            print(f"{interface}: version {version}")

        sys.exit(0)

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
