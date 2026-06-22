import datetime
import logging
import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI
import inngest
import inngest.fast_api
from inngest.experimental import ai

from custom_types import (
    RAGChunkAndSrc,
    RAGSearchResult,
    RAGUpsertResult,
    WarehouseChunkBatch,
    WarehouseSyncResult,
)
from data_loader import embed_texts, load_and_chunk_pdf
from vector_db import QdrantStorage
from warehouse_loader import load_and_chunk_warehouse

load_dotenv()

inngest_client = inngest.Inngest(
    app_id="ragproductionapp",
    logger=logging.getLogger("uvicorn"),
    is_production=False,
    serializer=inngest.PydanticSerializer(),
)


@inngest_client.create_function(
    fn_id="RAG: Ingest PDF",
    trigger=inngest.TriggerEvent(event="rag/ingest-pdf"),
)
async def rag_ingest_pdf(ctx: inngest.Context):
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        pdf_path = ctx.event.data["pdf_path"]
        source_id = ctx.event.data.get("source_id", pdf_path)

        chunks = load_and_chunk_pdf(pdf_path)

        return RAGChunkAndSrc(
            chunks=chunks,
            source_id=source_id,
        )

    def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks = chunks_and_src.chunks
        source_id = chunks_and_src.source_id

        if not chunks:
            return RAGUpsertResult(ingested=0)

        vecs = embed_texts(chunks)

        ids = [
            str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{source_id}:{i}",
                )
            )
            for i in range(len(chunks))
        ]

        payloads = [
            {
                "source": source_id,
                "source_type": "pdf",
                "text": chunks[i],
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        QdrantStorage().upsert(ids, vecs, payloads)

        return RAGUpsertResult(ingested=len(chunks))

    chunks_and_src = await ctx.step.run(
        "load-and-chunk",
        lambda: _load(ctx),
        output_type=RAGChunkAndSrc,
    )

    ingested = await ctx.step.run(
        "embed-and-upsert",
        lambda: _upsert(chunks_and_src),
        output_type=RAGUpsertResult,
    )

    return ingested.model_dump()


@inngest_client.create_function(
    fn_id="RAG: Sync Warehouse",
    trigger=inngest.TriggerEvent(event="rag/sync-warehouse"),
)
async def rag_sync_warehouse(ctx: inngest.Context):
    def _load() -> WarehouseChunkBatch:
        data = ctx.event.data or {}
        chunks = load_and_chunk_warehouse(
            query=data.get("query"),
            source_id=data.get("source_id"),
            primary_key_columns=data.get("primary_key_columns"),
            text_columns=data.get("text_columns"),
            metadata_columns=data.get("metadata_columns"),
        )
        return WarehouseChunkBatch(chunks=chunks)

    def _upsert(batch: WarehouseChunkBatch) -> WarehouseSyncResult:
        chunks = batch.chunks
        source_id = chunks[0].source_id if chunks else (ctx.event.data or {}).get("source_id", "warehouse")

        if not chunks:
            return WarehouseSyncResult(ingested=0, source_id=source_id)

        texts = [chunk.text for chunk in chunks]
        vecs = embed_texts(texts)
        ids = [chunk.id for chunk in chunks]
        payloads = [
            {
                **chunk.metadata,
                "source": chunk.source_id,
                "source_type": "warehouse",
                "text": chunk.text,
                "synced_at": datetime.datetime.utcnow().isoformat(),
            }
            for chunk in chunks
        ]

        QdrantStorage().upsert(ids, vecs, payloads)

        return WarehouseSyncResult(ingested=len(chunks), source_id=source_id)

    batch = await ctx.step.run(
        "load-warehouse-rows",
        _load,
        output_type=WarehouseChunkBatch,
    )

    result = await ctx.step.run(
        "embed-and-upsert-warehouse",
        lambda: _upsert(batch),
        output_type=WarehouseSyncResult,
    )

    return result.model_dump()


@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai"),
)
async def rag_query_pdf_ai(ctx: inngest.Context):
    def _search(question: str, top_k: int = 5, filters: dict | None = None) -> RAGSearchResult:
        query_vec = embed_texts([question])[0]

        store = QdrantStorage()
        found = store.search(query_vec, top_k, filters=filters)

        return RAGSearchResult(
            contexts=found["contexts"],
            sources=found["sources"],
        )

    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))
    filters = ctx.event.data.get("filters")

    found = await ctx.step.run(
        "embed-and-search",
        lambda: _search(question, top_k, filters),
        output_type=RAGSearchResult,
    )

    context_block = "\n\n".join(f"- {c}" for c in found.contexts)

    user_content = (
        "Use the following context to answer the question.\n\n"
        f"Context:\n{context_block}\n\n"
        f"Question: {question}\n"
        "Answer concisely using the context above."
    )

    adapter = ai.openai.Adapter(
        auth_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini",
    )

    res = await ctx.step.ai.infer(
        "llm-answer",
        adapter=adapter,
        body={
            "max_tokens": 1024,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": "You answer questions using only the provided context.",
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
        },
    )

    answer = res["choices"][0]["message"]["content"].strip()

    return {
        "answer": answer,
        "sources": found.sources,
        "num_contexts": len(found.contexts),
    }


app = FastAPI()

inngest.fast_api.serve(
    app,
    inngest_client,
    functions=[rag_ingest_pdf, rag_sync_warehouse, rag_query_pdf_ai],
)
