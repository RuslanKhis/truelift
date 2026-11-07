"""Upload, data profile and column mapping. Stub (G02); G07 replaces it (C12, SB11).

The fake upload does not parse the file. It rejects a non-``.csv`` name, an empty file, and a
file whose stem equals an ``IntakeErrorCode`` (``duplicate_keys.csv``), so the interface can show
every rejection reason. The size cap is enforced before the body is read (413).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from truelift.api.errors import ApiError, error_responses
from truelift.api.fakes import check_role
from truelift.api.routes import DemoProject, Fakes
from truelift.api.schemas import (
    DataProfile,
    DataVersion,
    IntakeErrorCode,
    Mapping,
    MappingIn,
    MappingStatus,
    VersionIn,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["intake"])

_REJECTIONS = {
    IntakeErrorCode.not_csv: "Only .csv files can be uploaded.",
    IntakeErrorCode.empty_file: "The file is empty.",
    IntakeErrorCode.missing_date: "No column holds dates. truelift needs one row per week and region.",
    IntakeErrorCode.not_weekly: "The dates are not weekly. truelift needs one row per week and region.",
    IntakeErrorCode.duplicate_keys: "Some week and region pairs appear more than once.",
    IntakeErrorCode.malformed_rows: "Some rows could not be read.",
}


def _reject(code: IntakeErrorCode) -> ApiError:
    return ApiError(422, code.value, _REJECTIONS[code])


@router.post(
    "/data",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(404, 413),
)
async def upload_data(
    project_id: DemoProject,
    fakes: Fakes,
    file: Annotated[UploadFile, File(description="A weekly panel as CSV.")],
) -> DataVersion:
    name = (file.filename or "").rsplit("/", 1)[-1][:200]
    stem, dot, ext = name.rpartition(".")
    if not dot or ext.lower() != "csv":
        raise _reject(IntakeErrorCode.not_csv)
    size = 0
    while chunk := await file.read(1 << 16):
        size += len(chunk)
    if size == 0:
        raise _reject(IntakeErrorCode.empty_file)
    if stem in IntakeErrorCode.__members__:
        raise _reject(IntakeErrorCode(stem))
    return fakes.upload(name, size)


@router.get("/data/profile", responses=error_responses(404))
def get_profile(project_id: DemoProject, fakes: Fakes) -> DataProfile:
    return fakes.profile()


@router.get("/mapping", responses=error_responses(404))
def get_mapping(project_id: DemoProject, fakes: Fakes) -> Mapping:
    return fakes.mapping


@router.put("/mapping", responses=error_responses(404, 409))
def put_mapping(project_id: DemoProject, body: MappingIn, fakes: Fakes) -> Mapping:
    if body.expected_version != fakes.mapping.version:
        raise ApiError(409, "stale_version", "The mapping changed since you opened it. Reload and try again.")
    fakes.mapping = Mapping(
        version=fakes.mapping.version + 1,
        status=MappingStatus.proposed,
        data_fingerprint=fakes.mapping.data_fingerprint,
        roles=[check_role(a) for a in body.roles],
    )
    return fakes.mapping


@router.post("/mapping/confirm", responses=error_responses(404, 409))
def confirm_mapping(project_id: DemoProject, body: VersionIn, fakes: Fakes) -> Mapping:
    if body.version != fakes.mapping.version:
        raise ApiError(409, "stale_version", "The mapping changed since you opened it. Reload and try again.")
    if not all(r.ok for r in fakes.mapping.roles):
        raise ApiError(422, "mapping_invalid", "Fix the columns marked in red before confirming.")
    fakes.mapping = fakes.mapping.model_copy(update={"status": MappingStatus.confirmed})
    return fakes.mapping
