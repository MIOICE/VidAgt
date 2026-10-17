from enum import StrEnum


class SourceType(StrEnum):
    UPLOAD = "UPLOAD"
    URL = "URL"


class UploadStatus(StrEnum):
    CREATED = "CREATED"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class VideoStatus(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProcessingStage(StrEnum):
    QUEUED = "QUEUED"
    IMPORTING = "IMPORTING"
    PROBING = "PROBING"
    HASHING = "HASHING"
    TRANSCODING = "TRANSCODING"
    AUDIO = "AUDIO"
    ASR = "ASR"
    KEYFRAMES = "KEYFRAMES"
    VISION = "VISION"
    FUSION = "FUSION"
    INDEXING = "INDEXING"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"


class AnalysisStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

