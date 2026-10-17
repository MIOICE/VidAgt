from pydantic import BaseModel, Field, HttpUrl


class UploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    mime_type: str = Field(default="application/octet-stream", max_length=128)
    fingerprint: str = Field(min_length=8, max_length=128)


class UploadCreated(BaseModel):
    upload_id: str
    part_size: int
    part_count: int
    parallelism: int


class PartSignRequest(BaseModel):
    part_numbers: list[int] = Field(min_length=1, max_length=100)


class SignedPart(BaseModel):
    part_number: int
    url: str


class PartSignResponse(BaseModel):
    parts: list[SignedPart]
    expires_in: int


class CompletedPart(BaseModel):
    part_number: int = Field(ge=1)
    etag: str = Field(min_length=1)


class UploadCompleteRequest(BaseModel):
    parts: list[CompletedPart] = Field(min_length=1)


class UploadStatusResponse(BaseModel):
    upload_id: str
    status: str
    completed_parts: list[CompletedPart]
    missing_parts: list[int]


class ImportUrlRequest(BaseModel):
    url: HttpUrl
    title: str | None = Field(default=None, max_length=255)

