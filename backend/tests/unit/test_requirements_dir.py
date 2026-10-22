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


def test_method_moved_to_inherited_base_is_not_breaking():
    from app.watch.diff import diff_surfaces

    old = {
        "symbols": {
            "flask.Flask": {"kind": "class", "bases": ["_PackageBoundObject"], "params": None},
            "flask.Flask.register_blueprint": {"kind": "method", "params": [{"name": "blueprint", "kind": "pos", "default": None}]},
        }
    }
    new = {
        "symbols": {
            "flask.Flask": {"kind": "class", "bases": ["App"], "params": None},
            "flask.sansio.app.App": {"kind": "class", "bases": ["Scaffold"], "params": None},
            "flask.sansio.app.App.register_blueprint": {
                "kind": "method",
                "params": [{"name": "blueprint", "kind": "pos", "default": None}],
            },
        }
    }
    changes = diff_surfaces(old, new)
    assert not [c for c in changes if c["severity"] == "breaking"]
    # a genuinely unrelated class still reports a move
    new["symbols"]["flask.Flask"]["bases"] = ["object"]
    assert any(c["kind"] == "moved" for c in diff_surfaces(old, new))
