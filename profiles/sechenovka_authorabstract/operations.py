"""SESHAT operation declarations for the Sechenovka authorabstract profile.

This module encodes methodological access requirements only.  It does not
reproduce or invent the historical prompts themselves.
"""

from seshat.contracts import (
    AnalyticObjectSpec,
    EvidenceAccessProfile,
    OperationSpec,
    RawAccessPolicy,
)


OBJECT_OPERATION = OperationSpec(
    operation_id="sechenovka.authorabstract.object",
    name="Research object reconstruction",
    target=AnalyticObjectSpec(
        object_type="research_object_reconstruction",
        object_class="distributed_latent_relational",
        description=(
            "Formal object, material, functional object, problem scene, "
            "object-method-result coherence and alternative objectifications."
        ),
        distributed=True,
    ),
    methodological_frame="AGENT_OBJECT_CORE",
    evidence_access_profile=EvidenceAccessProfile.FULL_WITH_STATE,
    raw_access_policy=RawAccessPolicy.FULL_REQUIRED,
    dependency_ids=["sechenovka.authorabstract.method"],
    input_types=["ResearchObject", "SourceCarrier", "Observation", "DerivedObject"],
    output_type="sechenovka.object_reconstruction",
    applicability_conditions=[
        "full source carrier is addressable",
        "cross-section evidence may be inspected",
    ],
    acceptance_right="sechenovka_profile_owner",
    implementation_ref=(
        "Drive:1zzxvEy88Fz61rMJAyUZEr9R3pvIQiCxcHn2ubPS_Pt8"
    ),
)


METHOD_OPERATION = OperationSpec(
    operation_id="sechenovka.authorabstract.method",
    name="Research method reconstruction",
    target=AnalyticObjectSpec(
        object_type="research_method_reconstruction",
        object_class="distributed_relational",
        description=(
            "Objects, procedures, instruments, measurements, transformations, "
            "statistics and analytical sequence reconstructed across the source."
        ),
        distributed=True,
    ),
    methodological_frame="AGENT_0_METHOD_SECTION_EXTRACTOR",
    evidence_access_profile=EvidenceAccessProfile.FULL_WITH_STATE,
    raw_access_policy=RawAccessPolicy.FULL_REQUIRED,
    dependency_ids=["sechenovka.authorabstract.object"],
    input_types=["ResearchObject", "SourceCarrier", "Observation", "DerivedObject"],
    output_type="sechenovka.method_reconstruction",
    applicability_conditions=[
        "full source carrier is addressable",
        "method evidence may occur outside named method sections",
    ],
    acceptance_right="sechenovka_profile_owner",
    implementation_ref=(
        "Drive:1LLKU0nC6sVBc34dR_wJSCQF2JCckI2x5oOoo-oN6PdE"
    ),
)


OPERATIONS = {
    OBJECT_OPERATION.operation_id: OBJECT_OPERATION,
    METHOD_OPERATION.operation_id: METHOD_OPERATION,
}
