import hashlib
import json
import os
import re
import shutil
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypedDict, TypeVar, Unpack, overload


class Ansi:
    BOLD = '\033[1m'
    ITALIC = '\033[3m'
    YELLOW_FG = '\033[33m'
    RED_FG = '\033[31m'
    WARN = YELLOW_FG+BOLD
    ERROR = RED_FG+BOLD
    RESET = '\033[0m'

def check_packwiz() -> Path:
    """Get the current packwiz executable"""
    packwiz = env("PACKWIZ", default="packwiz")
    if p := shutil.which(packwiz):
        return Path(p)
    else:
        raise RuntimeError(f"!!! Couldn't find packwiz (looked for '{packwiz}'). Please put packwiz on your path or set the PACKWIZ environment variable to a packwiz executable")

def check_java() -> Path:
    """Get the current java executable"""
    java = "java"
    if "JAVA_HOME" in os.environ:
        java_p = Path(os.environ["JAVA_HOME"]) / "bin/java"
        if not java_p.exists():
            raise RuntimeError(f"!!! JAVA_HOME is invalid. {java} does not exist")
        return java_p
    else:
        if resolved_java := shutil.which("java"):
            return Path(resolved_java)
        else:
            raise RuntimeError(f"!!! Couldn't find java on path. Please add it or set JAVA_HOME")

def get_repo_root() -> Path:
    # This file should be located in <repo_root>/scripts/common.py, so the root
    # is one directory up from this one
    return Path(os.path.join(os.path.dirname(__file__), '..'))

def get_generated_dir() -> Path:
    dir = env("OUTPUT_DIR", default=(get_repo_root() / "generated"))
    dir = Path(dir)
    if not dir.exists():
        dir.mkdir(exist_ok=True, parents=True)
    return dir

def read_file(path: os.PathLike) -> str:
    with open(path, "r") as f:
        return f.read()

def fix_packwiz_pack(pack_toml: Path):
    data = tomllib.loads(read_file(pack_toml))
    index = pack_toml.parent / data["index"]["file"]
    if not index.exists():
        index.touch()

class JSONWithCommentsDecoder(json.JSONDecoder):
    def __init__(self, **kw):
        super().__init__(**kw)

    def decode(self, s):
        s = '\n'.join(l if not l.lstrip().startswith('//') else '' for l in s.split('\n'))
        return super().decode(s)

def jsonc_at_home(input: str | bytes) -> Any:
    return json.loads(input, cls=JSONWithCommentsDecoder)

def hash(values: list[str]) -> str:
    hasher = hashlib.sha256()
    for value in values:
        hasher.update(value.encode("UTF-8"))
    return hasher.hexdigest()

# overloads for proper type checking
T = TypeVar('T')
@overload
def env(env: str, *, default: None = None) -> None | str: ...
@overload
def env(env: str, *, default: T) -> T | str: ...

def env(env: str, *, default: Any = None) -> Any | str:
    if env in os.environ:
        return os.environ[env]
    else:
        return default

class Constants(TypedDict):
    colours: dict[str, str]

def get_colour(parsed_constants: Constants, key: str) -> str:
    """Given a parsed constants.jsonc, retrieves a colour by key. Returns a value in the form of #FFFFFF"""
    if not key.startswith("_"):
        raise RuntimeError("Scripts should only depend on colour keys starting with an underscore")
    def get_inner(k):
        v = parsed_constants["colours"].get(k)
        if v is None:
            return None
        elif v.startswith("."):
            return get_inner(v[1:])
        elif v.startswith("#"):
            return v
        else:
            raise RuntimeError(f"Invalid colour definition for {k}. Should start with # or .")
    return get_inner(key)

class Ratelimiter:
    def __init__(self, time: float):
        # Time is given in seconds, convert to nanoseconds
        self.wait_time = time
        self.last_action: float = 0
    
    def limit(self):
        time.sleep(max(0, self.wait_time - (time.time() - self.last_action)))
        self.last_action = time.time()

@dataclass
class PackwizPackInfo:
    name: str | None
    author: str | None
    pack_version: str | None
    minecraft_version: str
    loader: str
    loader_version: str

    def safe_name(self) -> str:
        assert self.name is not None
        return re.sub("[^a-zA-Z0-9]+", "-", self.name)

def parse_packwiz(pack_toml_file: Any) -> PackwizPackInfo:
    pack_toml = tomllib.loads(read_file(pack_toml_file))
    
    version_data = pack_toml["versions"]
    if not "minecraft" in version_data:
        raise Exception("pack.toml doesn't define a minecraft version")

    # detect loader
    supported_loaders = ["fabric", "neoforge"]
    loaders = {k:v for k, v in version_data.items() if k in supported_loaders}
    if len(loaders) >= 2:
        raise Exception("pack is using multiple loaders, unsure which one to use: ["+", ".join(loaders.keys())+"]")
    if len(loaders) == 0:
        raise Exception("pack does not seem to define a loader")

    loader = list(loaders.keys())[0]
    loader_version = list(loaders.values())[0]

    for v in version_data:
        if v not in ["minecraft", "unsup"] and v not in supported_loaders:
            raise Exception(f"pack is using unsupported software: {v}")

    return PackwizPackInfo(
        pack_toml.get("name"),
        pack_toml.get("author"),
        pack_toml.get("version"),
        version_data["minecraft"],
        loader,
        loader_version
    )
