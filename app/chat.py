from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding


@dataclass(frozen=True)
class ChatSource:
    path: str
    score: Optional[float]
    snippet: Optional[str]


def build_index(
    files: List[Path],
    *,
    model: str,
    embed_model: Optional[str] = None,
) -> VectorStoreIndex:
    api_key = str(os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing OPENROUTER_API_KEY for chat RAG")

    base_url = str(os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip()

    Settings.llm = OpenAI(
        model=model,
        api_key=api_key,
        api_base=base_url,
    )
    embed_name = (embed_model or "text-embedding-3-small").strip()
    if "/" in embed_name:
        embed_name = embed_name.rsplit("/", 1)[-1].strip() or embed_name

    Settings.embed_model = OpenAIEmbedding(
        model=embed_name,
        api_key=api_key,
        api_base=base_url,
    )

    reader = SimpleDirectoryReader(input_files=[str(p) for p in files])
    docs = reader.load_data()
    return VectorStoreIndex.from_documents(docs)


def run_chat_query(
    *,
    files: List[Path],
    query: str,
    model: str,
    embed_model: Optional[str] = None,
    top_k: int = 4,
) -> Dict[str, Any]:
    index = build_index(files, model=model, embed_model=embed_model)
    engine = index.as_query_engine(similarity_top_k=top_k)
    response = engine.query(query)

    sources: List[ChatSource] = []
    for sn in getattr(response, "source_nodes", []) or []:
        node = getattr(sn, "node", None)
        meta = getattr(node, "metadata", {}) or {}
        file_path = meta.get("file_path") or meta.get("filename") or meta.get("path")
        if not file_path:
            file_path = ""
        text = getattr(node, "get_content", None)
        snippet = None
        if callable(text):
            snippet = str(text())[:500]
        sources.append(
            ChatSource(
                path=str(file_path),
                score=getattr(sn, "score", None),
                snippet=snippet,
            )
        )

    return {
        "answer": str(response),
        "sources": [s.__dict__ for s in sources],
    }
