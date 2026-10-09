import importlib.util
from pathlib import Path

from seshat.contracts import EvidenceAccessProfile, RawAccessPolicy


def _load_operations_module():
    path = (
        Path(__file__).parents[1]
        / "profiles"
        / "sechenovka_authorabstract"
        / "operations.py"
    )
    spec = importlib.util.spec_from_file_location("sechenovka_ops", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_object_and_method_require_full_source_and_mutually_constrain() -> None:
    mod = _load_operations_module()
    obj = mod.OBJECT_OPERATION
    method = mod.METHOD_OPERATION

    assert obj.raw_access_policy is RawAccessPolicy.FULL_REQUIRED
    assert method.raw_access_policy is RawAccessPolicy.FULL_REQUIRED
    assert obj.evidence_access_profile is EvidenceAccessProfile.FULL_WITH_STATE
    assert method.evidence_access_profile is EvidenceAccessProfile.FULL_WITH_STATE
    assert method.operation_id in obj.dependency_ids
    assert obj.operation_id in method.dependency_ids
