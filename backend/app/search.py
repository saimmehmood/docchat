from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

from .config import Settings


def build_index(settings: Settings) -> SearchIndex:
    return SearchIndex(
        name=settings.azure_search_index,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="page", type=SearchFieldDataType.Int32),
            SimpleField(name="chunk", type=SearchFieldDataType.Int32),
            SearchField(
                name="embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=settings.embedding_dimensions,
                vector_search_profile_name="default",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
            profiles=[VectorSearchProfile(name="default", algorithm_configuration_name="hnsw")],
        ),
    )


class SearchStore:
    def __init__(self, settings: Settings):
        credential = AzureKeyCredential(settings.azure_search_api_key)
        self.settings = settings
        self.index_client = SearchIndexClient(settings.azure_search_endpoint, credential)
        self.client = SearchClient(settings.azure_search_endpoint, settings.azure_search_index, credential)

    def ensure_index(self) -> None:
        try:
            self.index_client.get_index(self.settings.azure_search_index)
        except ResourceNotFoundError:
            self.index_client.create_index(build_index(self.settings))

    def delete_source(self, source: str) -> None:
        """Remove previously indexed chunks of a file so re-uploads don't duplicate."""
        escaped = source.replace("'", "''")
        results = self.client.search(search_text="*", filter=f"source eq '{escaped}'", select=["id"], top=1000)
        ids = [{"id": r["id"]} for r in results]
        if ids:
            self.client.delete_documents(ids)

    def upload(self, docs: list[dict]) -> None:
        # Azure AI Search accepts at most 1000 documents per batch.
        for i in range(0, len(docs), 500):
            self.client.upload_documents(docs[i : i + 500])

    def hybrid_search(self, query: str, vector: list[float], k: int) -> list[dict]:
        results = self.client.search(
            search_text=query,
            vector_queries=[VectorizedQuery(vector=vector, k_nearest_neighbors=k, fields="embedding")],
            select=["content", "source", "page", "chunk"],
            top=k,
        )
        return [dict(r) for r in results]
