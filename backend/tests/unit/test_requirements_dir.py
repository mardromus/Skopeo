from app.tools.manifests import detect_ecosystems, is_requirements_file
from app.watch.usage import find_pinned_version


def test_requirements_directory_files_are_manifests():
    assert is_requirements_file("requirements.txt")
    assert is_requirements_file("deploy/requirements-dev.txt")
    assert is_requirements_file("requirements/common.txt")
    assert is_requirements_file("requirements/dev.txt")
    assert not is_requirements_file("docs/notes.txt")
    assert not is_requirements_file("requirements/README.md")
    assert detect_ecosystems(["requirements/common.txt"]) == ["PyPI"]


def test_pin_found_in_requirements_directory():
    files = [
        ("requirements/dev.txt", "-r common.txt\nfaker==0.7.18\n"),
        ("requirements/common.txt", "Flask==0.12.2\nitsdangerous==0.24\nFlask-SQLAlchemy==2.2\n"),
    ]
    pin = find_pinned_version(files, "itsdangerous", "PyPI")
    assert pin and pin["version"] == "0.24" and pin["manifest"] == "requirements/common.txt"
    pin = find_pinned_version(files, "flask_sqlalchemy", "PyPI")
    assert pin and pin["version"] == "2.2"
