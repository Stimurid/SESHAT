"""Owner-admitted scientific prose. This module composes, never infers, claims."""
from __future__ import annotations

from datetime import date
from html import escape
import hashlib
from typing import Literal

from pydantic import Field, model_validator

from seshat.corpus import FrozenModel, MemberPin


class AnchoredClaim(FrozenModel):
    stage: Literal["E1_OBSERVATION", "E2_RECONSTRUCTION", "E3_CONTRAST",
                   "E4_CRITERIA", "E5_PROPOSAL"]
    subassembly_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    carrier_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int = Field(ge=1)
    # A page is a locator, not a claim that the composer read the page.


class Subassembly(FrozenModel):
    subassembly_id: str = Field(min_length=1)
    functional_object: str = Field(min_length=1)
    method: str = Field(min_length=1)
    material: str = Field(min_length=1)
    result: str = Field(min_length=1)
    counterexample_or_unknown: str = Field(min_length=1)
    claims: tuple[AnchoredClaim, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def own_claims(self):
        if any(c.subassembly_id != self.subassembly_id for c in self.claims):
            raise ValueError("CLAIM_OBJECT_COLLAPSE")
        return self


class ScientificReportAsset(FrozenModel):
    """Passed by the authenticated owner, never supplied in a report request."""
    object_id: str
    caller_id: str
    rights_scope: str
    producer_id: str = Field(min_length=1)
    rights_basis: str = Field(min_length=1)
    currentness_as_of: date
    source_member: MemberPin
    method_body_version: str = Field(min_length=1)
    method_body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    analytic_state_version: str = Field(min_length=1)
    review_status: Literal["OWNER_AUTHORED_UNREVIEWED"] = "OWNER_AUTHORED_UNREVIEWED"
    research_problem: str = Field(min_length=1)
    author_scope: str = Field(min_length=1)
    evidence_subassembly_ids: tuple[str, ...] = Field(min_length=1)
    subassemblies: tuple[Subassembly, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_objects(self):
        ids = [s.subassembly_id for s in self.subassemblies]
        if (len(ids) != len(set(ids))
                or len(self.evidence_subassembly_ids) != len(set(self.evidence_subassembly_ids))
                or set(ids) != set(self.evidence_subassembly_ids)):
            raise ValueError("CLAIM_OBJECT_COLLAPSE")
        return self


def validate_asset(asset: ScientificReportAsset, member: MemberPin,
                   source_contents: dict[str, bytes],
                   method_bodies: dict[str, bytes]) -> None:
    if asset.source_member != member or asset.object_id != member.object_id:
        raise ValueError("SCIENTIFIC_SOURCE_CHANGED")
    body = method_bodies.get(asset.method_body_version)
    if body is None or hashlib.sha256(body).hexdigest() != asset.method_body_sha256:
        raise ValueError("SCIENTIFIC_METHOD_UNREADABLE")
    carriers = {c.carrier_id: c for c in member.carriers}
    for sub in asset.subassemblies:
        for claim in sub.claims:
            carrier = carriers.get(claim.carrier_id)
            if (carrier is None or carrier.version != claim.source_version
                    or carrier.sha256 != claim.source_sha256):
                raise ValueError("SCIENTIFIC_SOURCE_CHANGED")
            content = source_contents.get(claim.carrier_id)
            if content is None or hashlib.sha256(content).hexdigest() != claim.source_sha256:
                raise ValueError("SCIENTIFIC_SOURCE_UNREADABLE")
            if content.startswith(b"SYNTHETIC PAGE 1:") and (
                    f"SYNTHETIC PAGE {claim.page}:".encode() not in content):
                raise ValueError("SCIENTIFIC_PAGE_UNAVAILABLE")


def render_markdown(asset: ScientificReportAsset) -> str:
    def plain(value: str) -> str:
        value = " ".join(value.split())
        for char in "\\`*_{}[]()<>!#|":
            value = value.replace(char, "\\" + char)
        return value

    lines = ["# Исследовательская деятельность: аналитический отчёт", "",
             f"Статус: {asset.review_status}. Научная приёмка определяется отдельно.",
             f"Автор аналитического состояния: {plain(asset.producer_id)}. "
             f"Право использования: {plain(asset.rights_basis)}.",
             f"Актуальность проверялась владельцем: {asset.currentness_as_of}.",
             f"Метод: {plain(asset.method_body_version)} / {asset.method_body_sha256}.",
             f"Версия аналитического состояния: {plain(asset.analytic_state_version)}.", "",
             "## Исследовательская проблема", "", plain(asset.research_problem), "",
             "## Границы атрибуции", "", plain(asset.author_scope), ""]
    for index, sub in enumerate(asset.subassemblies, 1):
        lines += [f"## {index}. {plain(sub.functional_object)}", "",
                  f"Материал: {plain(sub.material)}", "", f"Метод и операции: {plain(sub.method)}", "",
                  f"Результат: {plain(sub.result)}", "",
                  f"Контрпример или неизвестное: {plain(sub.counterexample_or_unknown)}", "",
                  "### Утверждения и опоры", ""]
        for claim in sub.claims:
            lines.append(f"- {claim.stage}: {plain(claim.text)} "
                         f"[источник {plain(claim.carrier_id)}@{plain(claim.source_version)}, "
                         f"с. {claim.page}, sha256:{claim.source_sha256}]")
        lines.append("")
    lines += ["## Provenance и неизвестное", "",
              "Текст составлен только из отдельно переданного аналитического состояния. "
              "Адрес страницы не удостоверяет чтение исходного документа этим композитором. "
              "E5 означает предложение, а не подтверждённую внешнюю новизну.", ""]
    return "\n".join(lines)


def render_html(asset: ScientificReportAsset) -> str:
    def e(value):
        return escape(str(value), quote=True)
    parts = ["<!doctype html><html lang=\"ru\"><meta charset=\"utf-8\">",
             "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
             "style-src 'unsafe-inline'\">",
             "<title>Научный отчёт</title><style>body{font:17px/1.6 system-ui;"
             "max-width:52em;margin:2em auto;padding:0 1em}h2{margin-top:2em}"
             "li{margin:.7em 0}code{overflow-wrap:anywhere}</style><body>",
             "<h1>Исследовательская деятельность: аналитический отчёт</h1>",
             f"<p><strong>Статус:</strong> {e(asset.review_status)}. "
             "Научная приёмка определяется отдельно.</p>",
             f"<p>Автор аналитического состояния: {e(asset.producer_id)}. "
             f"Право использования: {e(asset.rights_basis)}. "
             f"Актуальность: {e(asset.currentness_as_of)}.</p>",
             f"<p>Метод: {e(asset.method_body_version)} "
             f"<code>{e(asset.method_body_sha256)}</code>. "
             f"Состояние: {e(asset.analytic_state_version)}.</p>",
             f"<h2>Исследовательская проблема</h2><p>{e(asset.research_problem)}</p>",
             f"<h2>Границы атрибуции</h2><p>{e(asset.author_scope)}</p>"]
    for index, sub in enumerate(asset.subassemblies, 1):
        parts.extend((f"<h2>{index}. {e(sub.functional_object)}</h2>",
                      f"<p><strong>Материал:</strong> {e(sub.material)}</p>",
                      f"<p><strong>Метод и операции:</strong> {e(sub.method)}</p>",
                      f"<p><strong>Результат:</strong> {e(sub.result)}</p>",
                      "<p><strong>Контрпример или неизвестное:</strong> "
                      f"{e(sub.counterexample_or_unknown)}</p>",
                      "<h3>Утверждения и опоры</h3><ul>"))
        for claim in sub.claims:
            parts.append(f"<li><strong>{e(claim.stage)}</strong>: {e(claim.text)} "
                         f"[источник {e(claim.carrier_id)}@{e(claim.source_version)}, "
                         f"с. {claim.page}, <code>sha256:{claim.source_sha256}</code>]</li>")
        parts.append("</ul>")
    parts.append("<h2>Provenance и неизвестное</h2><p>Текст составлен только из "
                 "отдельно переданного аналитического состояния. Адрес страницы "
                 "не удостоверяет чтение страницы этим композитором. E5 означает "
                 "предложение, а не подтверждённую внешнюю новизну.</p></body></html>")
    return "\n".join(parts)
