"""F08 input wiring only: this is not an implementation of nine reports."""

from typing import Literal

from pydantic import model_validator

from seshat.corpus import (
    CorpusSelectionSpec, CorpusSpaceSnapshot, FrozenModel, _digest, public_selection_digest,
)


class CorpusReportInput(FrozenModel):
    report_id: Literal["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"]
    selection: CorpusSelectionSpec
    corpus: CorpusSpaceSnapshot
    source_regime: Literal["SRC-B"] = "SRC-B"
    content_state: Literal["METADATA_ONLY_NOT_REPORT_EVIDENCE"] = (
        "METADATA_ONLY_NOT_REPORT_EVIDENCE")

    @model_validator(mode="after")
    def matching_selection(self):
        if self.corpus.selection_digest != public_selection_digest(self.selection):
            raise ValueError("REPORT_SELECTION_MISMATCH")
        if self.corpus.snapshot_digest != _digest(self.corpus.model_dump(
                mode="json", exclude={"snapshot_digest"})):
            raise ValueError("REPORT_SNAPSHOT_MISMATCH")
        return self
