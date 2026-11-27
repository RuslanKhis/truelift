"""The run gate (C1, C2, C3).

A run starts only for a DAG version that (a) the user confirmed, (b) passes identification and
(c) uses a confirmed mapping on the same data fingerprint, each checked by content hash. The
start-run route calls :func:`admit` under the project's lock; the worker calls it again on the
project folder before it fits anything, and refuses unless it admits exactly what the app
admitted (:func:`recheck`).

Read only: the gate never writes a project file, so the worker can call it safely.

Data files live in ``<project>/data/`` (design section 6, ``data/vN.csv``). A data fingerprint is
``sha256:<hex>`` of the file's bytes, and the gate finds the file by it, so a replaced or
edited file is refused rather than analysed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from truelift.causal.build import DagDraft
from truelift.causal.compile import CompileError, PipelineConfig, Profile, compile_config
from truelift.causal.identify import IdentifyInputError, identify
from truelift.causal.mapping import ColumnMapping, PanelSummary
from truelift.causal.rules import RuleSet
from truelift.store.errors import StoreError
from truelift.store.folder import ProjectFolder
from truelift.store.versions import VersionKind, VersionRecord, Versions, VersionStatus
from truelift.worker.layout import sha256_file

DATA_DIR = "data"


class GateRefused(Exception):
    """The run may not start. ``code`` is stable; ``message`` is a plain reason for the user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RunInputs:
    """What the gate admitted. Stored in ``run.json``; the worker must admit the same."""

    project_id: str
    profile: str
    dag_version: int
    dag_sha256: str
    mapping_version: int
    mapping_sha256: str
    data_fingerprint: str
    data_file: str
    config_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunInputs:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Admitted:
    config: PipelineConfig
    inputs: RunInputs


def data_fingerprint(path: Path) -> str:
    return "sha256:" + sha256_file(path)


def find_data_file(folder: ProjectFolder, fingerprint: str) -> Path | None:
    for path in sorted((folder.root / DATA_DIR).glob("*.csv")):
        if path.is_file() and data_fingerprint(path) == fingerprint:
            return path
    return None


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def admit(folder: ProjectFolder, dag_version: int, profile: Profile | str, rules: RuleSet) -> Admitted:
    """Admit a run of ``dag_version`` under ``profile``, or raise :class:`GateRefused`."""
    profile = Profile(profile)
    try:
        knowledge = folder.knowledge()
        knowledge.require_valid()  # a broken knowledge file is shown, never half-read (C11)
        facts = knowledge.facts
        dags = Versions(folder, VersionKind.dag)
        current = dags.current()
        if current is None:
            raise GateRefused(
                "dag_not_found", "There is no diagram yet. Finish the interview, then build it."
            )
        if dag_version != current:
            raise GateRefused(
                "stale_version", "The DAG changed since you opened it. Reload and review it again."
            )
        dag_record = dags.read(dag_version)
        dag_status = dags.status(dag_version, facts)
        if dag_status is VersionStatus.draft:
            raise GateRefused("dag_unconfirmed", "Review and confirm your DAG before running the analysis.")
        if dag_status is VersionStatus.stale:
            changed = dags.stale_facts(dag_version, facts)
            if changed:
                raise GateRefused(
                    "dag_stale",
                    f"Your DAG changed after you confirmed it: {_plural(len(changed), 'answer')} it "
                    "depends on changed. Review it and confirm it again.",
                )
            raise GateRefused(
                "dag_stale", "Your DAG file changed after you confirmed it. Review it and confirm it again."
            )

        mappings = Versions(folder, VersionKind.mapping)
        mapping_version = mappings.current()
        if mapping_version is None:
            raise GateRefused("mapping_needed", "Confirm your column roles first.")
        mapping_record = mappings.read(mapping_version)
        mapping_status = mappings.status(mapping_version, facts)
        if mapping_status is VersionStatus.draft:
            raise GateRefused("mapping_unconfirmed", "Confirm your column roles before running the analysis.")
        if mapping_status is VersionStatus.stale:
            raise GateRefused(
                "mapping_stale", "Your column roles changed after you confirmed them. Confirm them again."
            )
    except StoreError as exc:
        raise GateRefused(exc.code, str(exc)) from exc

    fingerprint = mapping_record.data_fingerprint
    if not fingerprint:
        raise GateRefused("data_needed", "Upload your data and confirm your column roles first.")
    if dag_record.data_fingerprint != fingerprint:
        raise GateRefused(
            "data_changed",
            "Your DAG was built for a different data file than your column roles. Build the DAG "
            "again and review it.",
        )
    data_file = find_data_file(folder, fingerprint)
    if data_file is None:
        raise GateRefused(
            "data_changed",
            "The data file you confirmed is missing or has changed. Upload it again and confirm "
            "your column roles.",
        )

    draft, mapping, panel = _parse(dag_record, mapping_record)
    try:
        ident = identify(draft.dag, mapping, panel, rules)
    except IdentifyInputError as exc:
        raise GateRefused(
            "mapping_mismatch", "The diagram and your column roles do not fit together."
        ) from exc
    if not ident.identified:
        raise GateRefused("not_identified", " ".join(b.message for b in ident.blocks))
    try:
        # The margin is not read from the knowledge files yet: 1.0, marked assumed (G09 ruling).
        config = compile_config(
            draft.dag, mapping, panel, rules, profile=profile, data_fingerprint=fingerprint, margin=None
        )
    except CompileError as exc:
        raise GateRefused(f"compile_{exc.code}", exc.message) from exc

    inputs = RunInputs(
        project_id=folder.id,
        profile=profile.value,
        dag_version=dag_version,
        dag_sha256=dag_record.sha256,
        mapping_version=mapping_version,
        mapping_sha256=mapping_record.sha256,
        data_fingerprint=fingerprint,
        data_file=data_file.relative_to(folder.root).as_posix(),
        config_sha256=config.sha256(),
    )
    return Admitted(config=config, inputs=inputs)


def recheck(folder: ProjectFolder, admitted: RunInputs, config_bytes: bytes, rules: RuleSet) -> Admitted:
    """The worker's check before fitting: the gate must still admit the same inputs, and the
    config on disk must be the one it compiles. Raises :class:`GateRefused` otherwise."""
    now = admit(folder, admitted.dag_version, admitted.profile, rules)
    if now.inputs != admitted or now.config.to_json() != config_bytes:
        raise GateRefused(
            "inputs_changed",
            "Your DAG, column roles or data changed after this run started. Review them and run again.",
        )
    return now


def _parse(
    dag_record: VersionRecord, mapping_record: VersionRecord
) -> tuple[DagDraft, ColumnMapping, PanelSummary]:
    try:
        draft = DagDraft.from_content(dag_record.content)
    except (ValueError, ValidationError) as exc:
        raise GateRefused("dag_invalid", f"Diagram version {dag_record.version} is not valid.") from exc
    content = mapping_record.content
    try:
        mapping = ColumnMapping.model_validate({"columns": content.get("columns")})
        panel_data = content.get("panel")
        if not panel_data:
            raise GateRefused(
                "profile_needed", "Upload your data again so we can check it before the analysis."
            )
        panel = PanelSummary.model_validate(panel_data)
    except ValidationError as exc:
        raise GateRefused("mapping_invalid", "Your column roles are not valid. Review them again.") from exc
    return draft, mapping, panel
