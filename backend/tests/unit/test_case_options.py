import pytest

from app.config import Settings, effective_settings
from app.schemas.investigation import InvestigationCreate
from app.services.investigation_service import InvestigationService


def test_effective_settings_applies_case_choices():
    base = Settings(dry_run=True, skopeo_sandbox_execution=False)
    eff = effective_settings(base, {"dry_run": False, "sandbox_execution": True})
    assert eff.dry_run is False and eff.skopeo_sandbox_execution is True
    assert base.dry_run is True and base.skopeo_sandbox_execution is False
    assert effective_settings(base, {}) is base


def test_case_execution_needs_server_permission():
    svc = InvestigationService(Settings(skopeo_allow_case_execution=False))
    req = InvestigationCreate(repository_url="https://github.com/o/r", sandbox_execution=True)
    with pytest.raises(ValueError):
        svc.create(req)


def test_case_options_are_stored_and_used():
    svc = InvestigationService(Settings(skopeo_allow_case_execution=True))
    iid = svc.create(InvestigationCreate(repository_url="https://github.com/o/r", sandbox_execution=True, dry_run=False))
    opts = svc.store.get_investigation(iid).execution_summary["options"]
    assert opts["sandbox_execution"] is True and opts["dry_run"] is False
    assert svc._services(iid).settings.skopeo_sandbox_execution is True
