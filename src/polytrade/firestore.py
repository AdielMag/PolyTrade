from __future__ import annotations

from typing import Any

from google.cloud import firestore

from .config import settings


_client: firestore.Client | None = None


def get_client() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client(project=settings.gcp_project_id, database="polytrade")
    return _client


def get_doc(collection: str, doc_id: str) -> dict[str, Any] | None:
    doc = get_client().collection(collection).document(doc_id).get()
    return doc.to_dict() if doc.exists else None


def set_doc(collection: str, doc_id: str, data: dict[str, Any]) -> None:
    get_client().collection(collection).document(doc_id).set(data)


def add_doc(collection: str, data: dict[str, Any]) -> str:
    ref = get_client().collection(collection).add(data)[1]
    return ref.id


def query_collection(collection: str, limit: int = 50) -> list[dict[str, Any]]:
    snap = get_client().collection(collection).limit(limit).get()
    return [doc.to_dict() for doc in snap]


