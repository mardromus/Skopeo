from pathlib import Path

from shopfront.config import load_credentials

FIXTURE = Path(__file__).parent / "fixtures" / "example_credentials.txt"


def test_load_credentials_reads_default_profile():
    creds = load_credentials(FIXTURE)
    assert creds["access_key_id"].startswith("AKIA")
    assert creds["secret_access_key"]
