# Copyright (c) 2024 Graham R King
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so,enum subject to
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
            keys_to_remove = ["description", "signature", "summary"]
            for protocol in protocols.values():
                self._remove_keys(protocol, keys_to_remove)

        return json.dumps(protocols, indent=1)

    def _remove_keys(self, obj, keys):
        if isinstance(obj, dict):
            for key in keys:
                obj.pop(key, None)
            for value in obj.values():
                self._remove_keys(value, keys)
        elif isinstance(obj, list):
            for item in obj:
                self._remove_keys(item, keys)

    def add_request(self, interface, request):
        # Check for python keyword collision
        if keyword.iskeyword(request["name"]):
            request["name"] = request["name"] + "_"
            log.info(f"Renamed {self.protocol_name}.{interface}.{request['name']}")
        if interface not in self.interfaces:
            self.interfaces[interface] = {"events": [], "requests": [], "enums": []}
        requests = self.interfaces.get(interface, {}).get("requests", [])
        request["opcode"] = len(requests)
        requests.append(request)

    def parse_value(self, value):
        if value.startswith("0b"):  # binary
            return int(value, 2)
        if value.startswith("0x"):  # hexadecimal
            return int(value, 16)

        return int(value)

    def add_enum(self, interface, enum):
        # Check for python keyword collision
        if keyword.iskeyword(enum["name"]):
            enum["name"] = enum["name"] + "_"
            log.info(f"Renamed {self.protocol_name}.{interface}.{enum['name']}")

        if interface not in self.interfaces:
            self.interfaces[interface] = {"events": [], "requests": [], "enums": []}

        enums = self.interfaces.get(interface, {}).get("enums", [])
        enums.append(enum)

    def add_event(self, interface, event):
        # Check for python keyword collision
        if keyword.iskeyword(event["name"]):
            event["name"] = event["name"] + "_"
            log.info(f"Renamed {self.protocol_name}.{interface}.{event['name']}")
        if interface not in self.interfaces:
            self.interfaces[interface] = {"events": [], "requests": [], "enums": []}
        events = self.interfaces.get(interface, {}).get("events", [])
        event["opcode"] = len(events)
        # Check for name collision
        requests = [x["name"] for x in self.interfaces[interface]["requests"]]
        if event["name"] in requests:
            msg = f"Event {event['name']} collides with request of the same name."
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

        self.parse_xml(tree, "/protocol/interface/request")
        self.parse_xml(tree, "/protocol/interface/event")
        self.parse_xml(tree, "/protocol/interface/enum")

    def get_description(self, description):
        doc = ""
        if description is not None:
            summary = dict(description.items())["summary"]
            if description.text:
                text = [x.strip() for x in description.text.split("\n")]
                doc = f"{summary.strip()}\n{'\n'.join(text)}"
            else:
                doc = f"{summary.strip()}"
        return doc

    def parse_xml(self, tree, xpath):
        all_elements = tree.xpath(xpath)

        for node in all_elements:
            interface_name = node.getparent().get("name")
            object_type = node.tag
            object_name = node.get("name")
            log.info(f"    ({object_type}) {interface_name}.{object_name}")

            wayland_object = dict(node.items())

            # Read the interface
            interface = dict(node.getparent().items())

            # Get arguments
            params = (
                node.findall("arg") if object_type != "enum" else node.findall("entry")
            )
            description = self.get_description(node.find("description"))

            args = [dict(x.items()) for x in params]
            args = self.fix_arguments(args, object_type)
            signature_args = [f"{x.get('name')}: {x.get('type')}" for x in args]

            # signature
            signature = f"{interface_name}.{object_name}({', '.join(signature_args)})"

            wayland_object["args"] = args
            wayland_object["description"] = description
            wayland_object["signature"] = signature

            if object_type == "request":
                self.add_request(interface_name, wayland_object)
            elif object_type == "event":
                self.add_event(interface_name, wayland_object)
            elif object_type == "enum":
                self.add_enum(interface_name, wayland_object)

            # Add the interface details
            if not self.interfaces.get(interface_name, {}).get("version"):
                # Interface version
                self.interfaces[interface_name]["version"] = interface.get(
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
                self.interfaces[interface_name]["description"] = interface_description

    def fix_arguments(self, original_args, item_type):
        new_args = []
        for arg in original_args:
            # Rename python keyword collisions with wayland arguments
            if keyword.iskeyword(arg["name"]):
                arg["name"] = arg["name"] + "_"
                log.info(
                    f"Renamed request/event argument to {arg['name']} in protocol {self.protocol_name}"
                )

            if arg.get("type") == "new_id":
                interface = arg.get("interface", None)

                if not interface:
                    # Not expecting this for events
                    if item_type == "event":
                        msg = "Event with dynamic new_id not supported"
                        raise NotImplementedError(msg)
                    # Creating a new instance of an unknown interface
                    # so the caller must pass the details, we dynamically
                    # adjust the args here
                    new_args.extend([{"name": "interface", "type": "string"}])
                    new_args.extend([{"name": "version", "type": "uint"}])

            new_args.extend([arg])

        return new_args
