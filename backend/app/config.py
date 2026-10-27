from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Azure AI Foundry (Azure OpenAI-compatible endpoint)
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = "gpt-4.1-mini"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Azure AI Search
    azure_search_endpoint: str
    azure_search_api_key: str
    azure_search_index: str = "docchat"

    # Retrieval / chunking
    chunk_size: int = 1200
    chunk_overlap: int = 200
    top_k: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
