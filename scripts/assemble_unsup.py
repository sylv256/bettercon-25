#!/usr/bin/env python3
import io
import json
import re
import sys
import urllib.request
import zipfile
from typing import Any
from zipfile import ZipFile

import common
from common import Ansi


def main():
    repo_root = common.get_repo_root()
    constants_file = repo_root / "constants.jsonc"
    pack_toml_file = repo_root / "pack" / "pack.toml"
    generated_dir = common.get_generated_dir()

    url = common.env("URL")
    if url is None:
        print(f"{Ansi.ERROR}Please set the URL environment variable to the public url for this pack{Ansi.RESET}")
        sys.exit(1)
    if not url.endswith("pack.toml"):
        print(f"{Ansi.WARN}URL does not end with \"pack.toml\", please make sure it's correct{Ansi.RESET}")
    unsup_v = common.env("UNSUP_VERSION", default="1.0-rc2")

    print(f"Using unsup version {unsup_v}")
    
    packwiz_info = common.parse_packwiz(pack_toml_file)
    constants = common.jsonc_at_home(common.read_file(constants_file))

    # Download unsup jar
    unsup_jar_file = generated_dir / "cache" / f"unsup-{unsup_v}.jar"
    if not unsup_jar_file.exists():
        unsup_jar_file.parent.mkdir(exist_ok=True, parents=True)
        print(f"Downloading unsup to {unsup_jar_file.relative_to(repo_root)}")
        urllib.request.urlretrieve(
            f"https://repo.sleeping.town/com/unascribed/unsup/{unsup_v}/unsup-{unsup_v}.jar",
            unsup_jar_file
        )

    # Create prism zip
    prism = generated_dir / f"{packwiz_info.name}.zip"
    with ZipFile(prism, "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
        icon_key = packwiz_info.safe_name()

        with output_zip.open("instance.cfg", mode="w") as cfg:
            cfg.write(create_instance_config(packwiz_info, icon_key).encode("utf-8"))

        with output_zip.open("mmc-pack.json", mode="w") as packjson:
            packjson.write(create_mmc_meta(packwiz_info, unsup_v).encode("utf-8"))
        
        art_id = constants["art_id"]
        with urllib.request.urlopen(f'https://github.com/ModFest/art/blob/v2/icon/64w/{art_id}/transparent.png?raw=true') as icon:
            with output_zip.open(f"{icon_key}.png", mode="w") as icon_out:
                icon_out.write(icon.read())

        with output_zip.open("patches/com.unascribed.unsup.json", mode="w") as patch:
            patch.write(create_unsup_patch(unsup_v).encode("utf-8"))

        with output_zip.open(".minecraft/unsup.jar", mode="w") as unsup_out:
            with open(unsup_jar_file, "rb") as unsup_src:
                unsup_out.write(unsup_src.read())

        with output_zip.open(".minecraft/unsup.ini", mode="w") as unsupini:
            unsupini.write(create_unsup_ini(url, constants).encode("utf-8"))
    print(f"Wrote to \"{prism.relative_to(generated_dir)}\"")

    server_zip = generated_dir / f"{packwiz_info.safe_name()}-server.zip"
    with ZipFile(server_zip, "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
        if packwiz_info.loader == "fabric":
            print(f"{Ansi.WARN}Fabric server zips are not supported yet{Ansi.RESET}")
        elif packwiz_info.loader == "neoforge":
            with output_zip.open("user_jvm_args.txt", mode="w") as jvm_args:
                jvm_args.write("-javaagent:unsup.jar".encode("utf-8"))

        with output_zip.open("unsup.jar", mode="w") as unsup_out:
            with open(unsup_jar_file, "rb") as unsup_src:
                unsup_out.write(unsup_src.read())

        with output_zip.open("unsup.ini", mode="w") as unsupini:
            unsupini.write(create_unsup_ini(url, constants).encode("utf-8"))
    print(f"Wrote to \"{server_zip.relative_to(generated_dir)}\"")

# Creates a patch file which tells prism to
# load unsup as an agent
def create_unsup_patch(unsup_version):
    patch = {
        "formatVersion": 1,
        "name": "Una's Simple Updater",
        "uid": "com.unascribed.unsup",
        "version": unsup_version,
        "+agents": [
            {
                "name": f"com.unascribed:unsup:{unsup_version}",
                "url": "https://repo.sleeping.town"
            }
        ]
    }
    return json.dumps(patch)

# Creates the mmc-pack.json file, which stores "dependency" information for prism/multimc
# The most important thing is that it defines the minecraft version and launcher used
def create_mmc_meta(packwiz_info, unsup_version):
    meta: Any = {}
    meta["formatVersion"] = 1
    
    components = []
    # Add mc component
    components.append({
            "important": True,
            "uid": "net.minecraft",
            "version": packwiz_info.minecraft_version
        })
    
    # Add unsup component
    components.append({
            "cachedName": "Una's Simple Updater",
            "cachedVersion": unsup_version,
            "uid": "com.unascribed.unsup"
        })
    
    # Add loader component
    if packwiz_info.loader == "neoforge":
        components.append({
            "uid": "net.neoforged",
            "version": packwiz_info.loader_version
        })
    elif packwiz_info.loader == "fabric":
        components.append({
            "uid": "net.fabricmc.fabric-loader",
            "version": packwiz_info.loader_version
        })
    else:
        raise RuntimeError(f"Unknown loader {packwiz_info.loader}")

    meta["components"] = components
    return json.dumps(meta)

# Creates the instance.cfg, which defines basic information about the pack
# to prism/multimc
def create_instance_config(packwiz_info, icon_name):
    return instance_cfg_template.replace("{iconKey}", icon_name).replace("{name}", packwiz_info.name)

# Creates the unsup config file, which tells unsup where
# to download mods from
def create_unsup_ini(url: str, constants):
    colour_entries = []
    for colour_key in unsup_colours:
        colour_value = common.get_colour(constants, "_unsup_"+colour_key)
        if colour_value:
            colour_value = colour_value.replace("#", "")
            colour_entries.append(f"{colour_key}={colour_value}")
    return unsup_ini_template.replace("{url}", url).replace("{colours}", "\n".join(colour_entries))

instance_cfg_template = """
[General]
ConfigVersion=1.2
iconKey={iconKey}
name={name}
InstanceType=OneSix
""".strip()

unsup_colours = [
    "background",
    "title",
    "subtitle",
    "progress",
    "progress_track",
    "dialog",
    "button",
    "button_text",
]

unsup_ini_template = """
version=1
source_format=packwiz
source={url}
preset=minecraft
[colors]
{colours}
""".strip()

if __name__ == "__main__":
    main()
