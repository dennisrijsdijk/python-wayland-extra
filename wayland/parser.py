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

from __future__ import annotations

import json
import keyword
import os
from copy import deepcopy

import requests
from lxml import etree

from wayland.log import log


class WaylandParser:
    def __init__(self):
        self.interfaces: dict[str, dict] = {}
        self.protocol_name: str = ""

    def get_remote_uris(self) -> list[str]:
        base_url = "https://gitlab.freedesktop.org/api/v4/projects/wayland%2Fwayland-protocols/repository/"
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
                response = requests.get(f"{base_url}/tree", params=params, timeout=30)
                response.raise_for_status()

                if not response.json():
                    break

                xml_uris.extend(
                    f"{base_url}/blobs/{x['id']}/raw"
                    for x in response.json()
                    if x["path"].endswith(".xml")
                )
                page += 1

        xml_uris.insert(
            0,
            "https://gitlab.freedesktop.org/wayland/wayland/-/raw/main/protocol/wayland.xml",
        )
        return xml_uris

    def get_local_files(self) -> list[str]:
        protocol_dirs = ["/usr/share/wayland", "/usr/share/wayland-protocols"]
        return [
            os.path.join(root, file)
            for directory in protocol_dirs
            for root, _, files in os.walk(directory)
            for file in files
            if file.endswith(".xml")
        ]

    def to_json(self, *, minimise=True) -> str:
        protocols = deepcopy(self.interfaces)
        if minimise:
            self._remove_keys(protocols, ["description", "signature", "summary"])
        return json.dumps(protocols, indent=1)

    @staticmethod
    def _remove_keys(obj: dict | list, keys: list[str]):
        if isinstance(obj, dict):
            for key in keys:
                obj.pop(key, None)
            for value in obj.values():
                WaylandParser._remove_keys(value, keys)
        elif isinstance(obj, list):
            for item in obj:
                WaylandParser._remove_keys(item, keys)

    def _add_interface_item(self, interface: str, item_type: str, item: dict):
        if keyword.iskeyword(item["name"]):
            item["name"] += "_"
            log.info(f"Renamed {self.protocol_name}.{interface}.{item['name']}")

        if interface not in self.interfaces:
            self.interfaces[interface] = {"events": [], "requests": [], "enums": []}

        items = self.interfaces[interface][f"{item_type}s"]
        if item_type != "enum":
            item["opcode"] = len(items)

        if item_type == "event":
            requests = [x["name"] for x in self.interfaces[interface]["requests"]]
            if item["name"] in requests:
                msg = f"Event {item['name']} collides with request of the same name."
                raise ValueError(msg)

        items.append(item)

    def add_request(self, interface: str, request: dict):
        self._add_interface_item(interface, "request", request)

    def add_enum(self, interface: str, enum: dict):
        self._add_interface_item(interface, "enum", enum)

    def add_event(self, interface: str, event: dict):
        self._add_interface_item(interface, "event", event)

    def parse(self, path: str):
        if not path.strip():
            return

        if path.startswith("http"):
            response = requests.get(path, timeout=20)
            response.raise_for_status()
            tree = etree.fromstring(response.content)
        else:
            tree = etree.parse(path)

        if isinstance(tree, etree._Element):
            self.protocol_name = tree.attrib["name"]
        else:
            tree.getroot().attrib.get("name")

        for xpath in [
            "/protocol/interface/request",
            "/protocol/interface/event",
            "/protocol/interface/enum",
        ]:
            self.parse_xml(tree, xpath)

    @staticmethod
    def get_description(description: etree.Element) -> str:
        if description is None:
            return ""
        summary = description.attrib.get("summary", "").strip()
        text = "\n".join(
            line.strip()
            for line in (description.text or "").split("\n")
            if line.strip()
        )
        return f"{summary}\n{text}" if text else summary

    def parse_xml(self, tree: etree.ElementTree, xpath: str):
        for node in tree.xpath(xpath):
            interface_name = node.getparent().attrib["name"]
            object_type = node.tag
            object_name = node.attrib["name"]
            log.info(f"    ({object_type}) {interface_name}.{object_name}")

            wayland_object = dict(node.attrib)
            interface = dict(node.getparent().attrib)

            params = node.findall("arg" if object_type != "enum" else "entry")
            description = self.get_description(node.find("description"))

            args = self.fix_arguments([dict(x.attrib) for x in params], object_type)
            signature = f"{interface_name}.{object_name}({', '.join(f'{x['name']}: {x.get('type','')}' for x in args)})"

            wayland_object.update(
                {"args": args, "description": description, "signature": signature}
            )

            getattr(self, f"add_{object_type}")(interface_name, wayland_object)

            if (
                interface_name not in self.interfaces
                or "version" not in self.interfaces[interface_name]
            ):
                self.interfaces[interface_name].update(
                    {
                        "version": interface.get("version", "1"),
                        "description": self.get_description(
                            node.getparent().find("description")
                        ),
                    }
                )

    def fix_arguments(self, original_args: list[dict], item_type: str) -> list[dict]:
        new_args = []
        for arg in original_args:
            if keyword.iskeyword(arg["name"]):
                arg["name"] += "_"
                log.info(
                    f"Renamed request/event argument to {arg['name']} in protocol {self.protocol_name}"
                )

            if arg.get("type") == "new_id" and not arg.get("interface"):
                if item_type == "event":
                    msg = "Event with dynamic new_id not supported"
                    raise NotImplementedError(msg)
                new_args.extend(
                    [
                        {"name": "interface", "type": "string"},
                        {"name": "version", "type": "uint"},
                    ]
                )

            new_args.append(arg)

        return new_args
