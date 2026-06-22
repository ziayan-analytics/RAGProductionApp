import pydantic


class RAGChunkAndSrc(pydantic.BaseModel):
    chunks: list[str]
    source_id: str = None


class RAGUpsertResult(pydantic.BaseModel):
    ingested: int


class RAGSearchResult(pydantic.BaseModel):
    contexts: list[str]
    sources: list[str]


class RAGQueryResult(pydantic.BaseModel):
    answer: str
    sources: list[str]
    num_contexts: int


class WarehouseChunk(pydantic.BaseModel):
    id: str
    text: str
    source_id: str
    metadata: dict = pydantic.Field(default_factory=dict)


class WarehouseChunkBatch(pydantic.BaseModel):
    chunks: list[WarehouseChunk]


class WarehouseSyncResult(pydantic.BaseModel):
    ingested: int
    source_id: str
