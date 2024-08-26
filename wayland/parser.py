# Copyright (c) 2024 Graham R King
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice (including the
# next paragraph) shall be included in all copies or substantial
# portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT.  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import json
import keyword
import os
from copy import deepcopy

import requests
from lxml import etree

from wayland.log import log


class WaylandParser:
    def __init__(self):
        self.interfaces = {}
        self.headers = []
        self.protocol_name = ""

    def get_remote_uris(self):
        # Download the latest protocols
        domain = "https://gitlab.freedesktop.org"
        project = "projects/wayland%2Fwayland-protocols"
        url = f"{domain}/api/v4/{project}/repository/"
        paths = ["staging", "stable"]
        xml_uris = []
        for path in paths:
            log.info(f"Searching for {path} Wayland protocol definitions")
            page = 1
            while True:
                params = {
                    "per_page": 100,
                    "page": page,
                    "path": path,
                    "recursive": True,
                }

                # Get all objects
                response = requests.get(url=f"{url}/tree", params=params, timeout=30)
                if not response.ok:
                    response.raise_for_status()

                # If nothing we are done
                if not len(response.json()):
                    break

                page += 1

                # Add xml files to our list
                xml_uris.extend(
                    [
                        f"{url}/blobs/{x['id']}/raw"
                        for x in response.json()
                        if os.path.splitext(x["path"])[-1] == ".xml"
                    ]
                )

        xml_uris.insert(
            0,
            "https://gitlab.freedesktop.org/wayland/wayland/-/raw/main/protocol/wayland.xml",
        )

        return xml_uris

    def get_local_files(self):
        # XXX: Not sure this assumption holds everywhere?
        protocol_dirs = [
            "/usr/share/wayland",
            "/usr/share/wayland-protocols",
        ]
        xml_files = []
        for directory in protocol_dirs:
            log.info(f"Searching for local files in {directory}")
            for root, _, files in os.walk(directory):
                xml_files.extend(
                    [os.path.join(root, x) for x in files if x.endswith(".xml")]
                )
        return xml_files

    def to_json(self, *, minimise=True):
        protocols = deepcopy(self.interfaces)

        if minimise:
            # Remove descriptions to save space in runtime version
            for protocol in protocols.values():
                for items in protocol.values():
                    for method in items:
                        if "description" in method:
                            del method["description"]
                        if "signature" in method:
                            del method["signature"]
                        if "args" in method:
                            for arg in method["args"]:
                                if "summary" in arg:
                                    del arg["summary"]
        return json.dumps(protocols, indent=1)

    def add_method(self, interface, method):
        # Check for python keyword collision
        if keyword.iskeyword(method["name"]):
            method["name"] = method["name"] + "_"
            log.info(f"Renamed {self.protocol_name}.{interface}.{method['name']}")
        if interface not in self.interfaces:
            self.interfaces[interface] = {"events": [], "methods": []}
        methods = self.interfaces.get(interface, {}).get("methods", [])
        method["opcode"] = len(methods)
        methods.append(method)

    def add_event(self, interface, event):
        # Check for python keyword collision
        if keyword.iskeyword(event["name"]):
            event["name"] = event["name"] + "_"
            log.info(f"Renamed {self.protocol_name}.{interface}.{event['name']}")
        if interface not in self.interfaces:
            self.interfaces[interface] = {"events": [], "methods": []}
        events = self.interfaces.get(interface, {}).get("events", [])
        event["opcode"] = len(events)
        # Check for name collision
        methods = [x["name"] for x in self.interfaces[interface]["methods"]]
        if event["name"] in methods:
            msg = f"Event {event['name']} collides with method of the same name."
            raise ValueError(msg)
        events.append(event)

    def parse(self, path):
        if not path.strip():
            return
        if path.startswith("http"):
            response = requests.get(path, timeout=20)
            if response.ok:
                tree = etree.fromstring(response.content)
            else:
                response.raise_for_status()
        else:
            tree = etree.parse(path)

        try:
            self.protocol_name = tree.getroot().attrib["name"]
        except AttributeError:
            self.protocol_name = tree.attrib["name"]

        self.parse_xml(tree, "/protocol/interface/request", self.add_method)
        self.parse_xml(tree, "/protocol/interface/event", self.add_event)

    def parse_xml(self, tree, xpath, add_item_func):
        all_elements = tree.xpath(xpath)

        for node in all_elements:
            request = dict(node.items())

            # Read the interface
            interface = dict(node.getparent().items())

            # Get request arguments
            params = node.findall("arg")
            description = node.find("description")
            doc = ""
            if description is not None:
                summary = dict(description.items())["summary"]
                if description.text:
                    text = [x.strip() for x in description.text.split("\n")]
                    doc = f"{summary.strip()}\n{'\n'.join(text)}"
                else:
                    doc = f"{summary.strip()}"
            args = [dict(x.items()) for x in params]

            args = self.manipulate_args(args, add_item_func)

            fargs = [f"{x['name']}: {x['type']}" for x in args]

            # method signature
            signature = f"{interface['name']}.{request['name']}({', '.join(fargs)})"
            method = request
            method["args"] = args
            method["description"] = doc
            method["signature"] = signature
            add_item_func(interface["name"], method)

            # Add the interface details
            if not self.interfaces.get(interface["name"], {}).get("version"):
                # Interface version
                self.interfaces[interface["name"]]["version"] = interface.get(
                    "version", "1"
                )
                # Interface description
                idescnode = node.getparent().find("description")
                interface_description = ""
                if idescnode is not None:
                    summary = dict(idescnode.items()).get("summary", "").strip()
                    if idescnode.text:
                        text = [x.strip() for x in idescnode.text.split("\n")]
                        interface_description = f"{summary}\n{'\n'.join(text)}"
                    else:
                        interface_description = summary
                self.interfaces[interface["name"]]["description"] = (
                    interface_description
                )

    def manipulate_args(self, original_args, item_type):
        new_args = []
        for arg in original_args:
            # Rename python keyword collisions with wayland arguments
            if keyword.iskeyword(arg["name"]):
                arg["name"] = arg["name"] + "_"
                log.info(
                    f"Renamed request/event argument to {arg['name']} in protocol {self.protocol_name}"
                )

            if arg["type"] == "new_id":
                interface = arg.get("interface", None)

                if not interface:
                    # Not expecting this for events
                    if item_type is self.add_event:
                        msg = "Event with dynamic new_id not supported"
                        raise NotImplementedError(msg)
                    # Creating a new instance of an unknown interface
                    # so the caller must pass the details, we dynamically
                    # adjust the args here
                    new_args.extend([{"name": "interface", "type": "string"}])
                    new_args.extend([{"name": "version", "type": "uint"}])

            new_args.extend([arg])

        return new_args

    @classmethod
    def indent(cls, input_string, indent_columns, *, comment=True):
        indent = " " * indent_columns
        indented_string = "\n".join(indent + line for line in input_string.splitlines())
        if comment:
            indented_string = f'{indent}"""\n{indented_string}\n{indent}"""\n'
        return indented_string

    def create_type_hinting(self, structure, path):
        file_name = f"{path}/__init__.pyi"

        self.headers = [
            "# DO NOT EDIT this file, it is automatically generated.",
            "# ",
            "# This file is only used as a code completion helper",
            "# for editors, it is not used at runtime.",
            "",
            "from typing import TypeAlias, Annotated",
            "new_id: TypeAlias = int",
            "object: TypeAlias = int",
            "uint: TypeAlias = int",
            "string: TypeAlias = str",
            "fd: TypeAlias = int",
            "array: TypeAlias = list",
            "fixed: TypeAlias = float",
            "",
        ]
        self.headers = [x + "\n" for x in self.headers]
        class_definitions = []

        # Iterate the entire wayland protocol structure
        for class_name, details in structure.items():
            # Describe each class
            class_declaration = f"class {class_name}:\n"
            iface_desc = details["description"]
            class_declaration += self.indent(iface_desc, 4, comment=True)
            class_declaration += (
                f"    object_id = 0\n    version = {details['version']}\n\n"
            )

            # Add requests and events
            class_body = ""
            class_body += self.process_members(details.get("methods", []))
            class_events_declaration = "    class events:\n"
            class_events = self.process_members(details.get("events", []), events=True)
            if not class_events:
                class_events_declaration = ""  # no events? don't create events class
            else:
                class_body += class_events_declaration + class_events

            class_definitions.append(class_declaration + class_body)

        class_definitions = self.headers + class_definitions

        with open(file_name, "w", encoding="utf-8") as outfile:
            for class_def in class_definitions:
                outfile.write(class_def)

    def process_members(self, members, *, events=False):
        if events:
            indent_declaration = 8
            indent_body = 12
        else:
            indent_declaration = 4
            indent_body = 8

        pad = " " * indent_declaration
        pad_body = " " * indent_body

        definitions = ""

        for member in members:
            # Check if this creates a new object of a known type
            original_args = deepcopy(member["args"])
            new_args = []
            return_type = None

            for arg in original_args:
                # new_id arg types are converted to their object types if possible
                if arg["type"] == "new_id":
                    interface = arg.get("interface")
                    if interface and not events:
                        # we don't need new_id in requests if we know the object type
                        return_type = interface
                        continue
                    if interface and events:
                        # use the object type as the arg type instead of new_id
                        arg["type"] = interface

                new_args.append(arg)

            method_signature = f"# opcode {member['opcode']}\n"
            method_signature += f"{pad}@staticmethod\n"
            method_signature += f"{pad}def {member['name']}("
            method_signature += ", ".join(
                f"{arg['name']}: {arg['type']}" for arg in new_args
            )
            if return_type:
                method_signature += f") -> {return_type}:\n"
            else:
                method_signature += ") -> None:\n"

            method_signature += self.indent(member["description"], indent_body)
            method_signature += f"{pad_body}...\n\n"
            definitions += f"{pad}{method_signature}"

            if not definitions:
                definitions = f"{pad_body}..."

        return definitions
