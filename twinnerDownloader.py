#!/usr/bin/python
# -*- coding: utf-8 -*-
import argparse
import json
import math
import os
import re
from os.path import exists
from tempfile import gettempdir

import requests
from PIL import Image
from bs4 import BeautifulSoup
from tqdm import tqdm

__author__ = "Michael Pekar"
__version__ = "1.0"
__license__ = "MIT"


class Folder:
    def __init__(self, path, width, height, tile_size, format, force_download):
        self.path = path
        self.tile_size = tile_size
        self.format = format
        self.force_download = force_download
        # calculate level sizes
        self.levels = []
        while width > 1 or height > 1:
            self.levels.append({"width": width, "height": height})
            width = math.ceil(width * 0.5)
            height = math.ceil(height * 0.5)
        self.levels.reverse()

    def download(self, level_index, image_folder):
        level = self.levels[level_index]
        columns = math.ceil(level["width"] / self.tile_size)
        rows = math.ceil(level["height"] / self.tile_size)

        session = requests.Session()
        for x in tqdm(range(columns), desc="Downloading"):
            for y in tqdm(range(rows), leave=False):
                url = "{}/{}/{}_{}.{}".format(
                    self.path, level_index + 1, x, y, self.format
                )
                outPath = os.path.join(
                    image_folder, "{}_{}.{}".format(x, y, self.format)
                )
                if not exists(outPath) or self.force_download:
                    blob = session.get(url).content
                    with open(outPath, "wb") as file:
                        file.write(blob)

    def join_tiles(self, level_index, image_folder):
        level = self.levels[level_index]
        columns = math.ceil(level["width"] / self.tile_size)
        rows = math.ceil(level["height"] / self.tile_size)

        result = Image.new("RGB", (level["width"], level["height"]))
        for x in tqdm(range(columns), desc="Joining"):
            for y in tqdm(range(rows), leave=False):
                out_path = os.path.join(
                    image_folder, "{}_{}.{}".format(x, y, self.format)
                )
                with Image.open(out_path) as src_image:
                    result.paste(src_image, (x * self.tile_size, y * self.tile_size))
        return result


def do_item_folder(args, widget_url, metadata, folder_name):
    if args.name is not None and folder_name.casefold().find(args.name.casefold()) == -1:
        if args.verbose:
            print("Skipping {} because folder name filter".format(folder_name))
        return

    folder_url = widget_url + folder_name
    folder = Folder(
        folder_url,
        metadata["width"],
        metadata["height"],
        metadata["tileSize"],
        metadata["format"],
        args.forceDownload is True,
    )
    format = args.format if args.format is not None else folder.format
    level_index = args.level if args.level is not None else len(folder.levels) - 1

    out_file_name = (
        folder_name.replace("_files", "").replace("/", "_") + "_LVL" + str(level_index)
    )
    temp_dir = gettempdir()
    temp_dir = os.path.join(temp_dir, "twinnerdl", out_file_name)

    print()
    print("Folder: " + folder_name)

    if args.verbose:
        print("FolderUrl: " + folder_url)
        print("Using format: " + format)
        print("Using level: " + str(level_index))
        print("Cache directory: " + temp_dir)
        print("Metadata: " + json.dumps(metadata))

    try:
        os.makedirs(temp_dir)
    except FileExistsError:
        pass

    folder.download(level_index, temp_dir)

    out = os.path.join(args.out, "{}.{}".format(out_file_name, format))
    image = folder.join_tiles(level_index, temp_dir)
    image.save(out, quality=90, optimize=True)

    if args.verbose:
        print("Wrote joined image to: " + out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Twinner image downloader v" + __version__)
    parser.add_argument(
        "url",
        help="target twinner url (twinner0produc0mytwinn.blob.core.windows.net/...)",
    )
    parser.add_argument("out", help="output directory")
    parser.add_argument(
        "-f", "--format", help="output image format (default: use source format)"
    )
    parser.add_argument(
        "-n", "--name", help="filter images by folder name"
    )
    parser.add_argument(
        "-l",
        "--level",
        help="resolution level (default: use the largest level)",
        type=int,
    )
    parser.add_argument(
        "-d",
        "--forceDownload",
        help="force downloading of image tiles (ignore cache)",
        action="store_true",
    )
    parser.add_argument(
        "-v", "--verbose", help="increase output verbosity", action="store_true"
    )
    args = parser.parse_args()

    # find script tag that contains the widgetUrl
    soup = BeautifulSoup(requests.get(args.url).text, "html.parser")
    script = soup.find(lambda tag: tag.name == "script" and "widgetUrl" in tag.text)
    if script is not None:
        match = re.search("widgetUrl:'(\S+)'", script.text, re.IGNORECASE)
    else:
        match = None

    if match is not None:
        widget_url = match.group(1)
        sceneconfig_text = requests.get(match.group(1) + "sceneconfig.json").text
        sceneconfig = json.loads(sceneconfig_text)

        for item in sceneconfig["viewModes"]["items"]:
            metadata = item["pyramidMetadata"]
            if "pageFolders" in item:
                for folder_name in item["pageFolders"]:
                    do_item_folder(args, widget_url, metadata, folder_name)
            else:
                do_item_folder(args, widget_url, metadata, item["pyramidFolder"])
    else:
        print("ERROR! Couldn't find widgetUrl (pease verify input url)")
