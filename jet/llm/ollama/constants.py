"""Set of constants."""

DEFAULT_TEMPERATURE = 0.1
DEFAULT_CONTEXT_WINDOW = 3900  # tokens
DEFAULT_NUM_OUTPUTS = 256  # tokens
DEFAULT_NUM_INPUT_FILES = 10  # files
DEFAULT_REQUEST_TIMEOUT = 300.0

DEFAULT_EMBED_BATCH_SIZE = 32

DEFAULT_SIMILARITY_TOP_K = 2
DEFAULT_IMAGE_SIMILARITY_TOP_K = 2

# NOTE: for text-embedding-ada-002
DEFAULT_EMBEDDING_DIM = 1536

# context window size for llm predictor
COHERE_CONTEXT_WINDOW = 2048
AI21_J2_CONTEXT_WINDOW = 8192


TYPE_KEY = "__type__"
DATA_KEY = "__data__"
VECTOR_STORE_KEY = "vector_store"
IMAGE_STORE_KEY = "image_store"
GRAPH_STORE_KEY = "graph_store"
INDEX_STORE_KEY = "index_store"
DOC_STORE_KEY = "doc_store"
PG_STORE_KEY = "property_graph_store"

# llama-cloud constants
DEFAULT_PIPELINE_NAME = "default"
DEFAULT_PROJECT_NAME = "Default"
DEFAULT_BASE_URL = "https://api.cloud.llamaindex.ai"
DEFAULT_APP_URL = "https://cloud.llamaindex.ai"

# Ollama constants
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_BASE_EMBED_URL = "http://localhost:11434"
OLLAMA_SMALL_LLM_MODEL = "llama3.2"
OLLAMA_LARGE_LLM_MODEL = "llama3.1"
DEFAULT_OLLAMA_MODEL = OLLAMA_LARGE_LLM_MODEL

OLLAMA_SMALL_EMBED_MODEL = "nomic-embed-text"
OLLAMA_SMALL_CHUNK_SIZE = 768  # tokens
OLLAMA_SMALL_CHUNK_OVERLAP = 50  # tokens

OLLAMA_LARGE_EMBED_MODEL = "mxbai-embed-large"
OLLAMA_LARGE_CHUNK_SIZE = 1024  # tokens
OLLAMA_LARGE_CHUNK_OVERLAP = 100  # tokens
