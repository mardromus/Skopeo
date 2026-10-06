"""Configuration loading."""

import configparser
from pathlib import Path


def load_credentials(path: Path, profile: str = "default") -> dict:
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if profile not in parser:
        raise KeyError(profile)
    section = parser[profile]
    return {
        "access_key_id": section.get("aws_access_key_id", ""),
        "secret_access_key": section.get("aws_secret_access_key", ""),
    }
