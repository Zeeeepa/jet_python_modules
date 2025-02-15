from typing import Callable, Optional, Any
import json
import os
from typing import Any, Callable, Literal, Optional
from jet.file.utils import load_file
from jet.llm.ollama.base import OllamaEmbedding
from jet.llm.ollama.constants import OLLAMA_SMALL_EMBED_MODEL, OLLAMA_SMALL_LLM_MODEL
from jet.llm.ollama.embeddings import get_ollama_embedding_function
from jet.llm.models import OLLAMA_HF_MODELS, OLLAMA_MODEL_EMBEDDING_TOKENS, OLLAMA_MODEL_NAMES
from jet.llm.query.cleaners import group_and_merge_texts_by_file_name
from jet.llm.query.splitters import split_heirarchical_nodes, split_markdown_header_nodes, split_sub_nodes
from jet.llm.retrievers.recursive import (
    initialize_summary_nodes_and_retrievers,
    query_nodes as query_nodes_recursive
)
from jet.llm import VectorSemanticSearch
from jet.token import filter_texts
from jet.token.token_utils import get_ollama_tokenizer
from jet.vectors.node_parser.hierarchical import JetHierarchicalNodeParser
from jet.vectors.utils import get_source_node_attributes
from llama_index.core.callbacks.base import CallbackManager
from llama_index.core.callbacks.schema import CBEventType
from llama_index.core.indices import vector_store
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, PromptTemplate
from llama_index.core.node_parser.relational.hierarchical import get_leaf_nodes
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.retrievers.fusion_retriever import FUSION_MODES
from llama_index.core.retrievers.recursive_retriever import RecursiveRetriever
from llama_index.core.schema import Document, NodeWithScore, BaseNode, TextNode, ImageNode
from jet.llm.utils import display_jet_source_nodes
from utils.data import generate_key
from jet.logger import logger
from jet.llm import call_ollama_chat
from jet.llm.llm_types import OllamaChatOptions
from jet.llm.ollama import initialize_ollama_settings
initialize_ollama_settings()


SYSTEM_MESSAGE = "You are a helpful AI Assistant."

PROMPT_TEMPLATE = PromptTemplate(
    """\
Context information are below.
---------------------
{context_str}
---------------------
Given the context information and not prior knowledge, answer the query.
Query: {query_str}
Answer: \
"""
)

DEFAULT_CHAT_OPTIONS: OllamaChatOptions = {
    "seed": 44,
    "num_ctx": 4096,
    "num_keep": 0,
    "num_predict": -1,
    "temperature": 0,
}


def setup_retrievers(index: VectorStoreIndex, initial_similarity_k: int, final_similarity_k: int) -> list[BaseRetriever]:
    from llama_index.retrievers.bm25 import BM25Retriever

    vector_retriever = index.as_retriever(
        similarity_top_k=initial_similarity_k,
    )

    bm25_retriever = BM25Retriever.from_defaults(
        docstore=index.docstore, similarity_top_k=final_similarity_k
    )

    return [vector_retriever, bm25_retriever]


def get_fusion_retriever(retrievers: list[BaseRetriever], fusion_mode: FUSION_MODES, final_similarity_k: int):

    retriever = QueryFusionRetriever(
        retrievers,
        retriever_weights=[0.6, 0.4],
        similarity_top_k=final_similarity_k,
        num_queries=1,  # set this to 1 to disable query generation
        mode=fusion_mode,
        use_async=False,
        verbose=True,

    )

    return retriever


def get_recursive_retriever(index: VectorStoreIndex, all_nodes: list[BaseNode], similarity_top_k: Optional[int] = None):
    vector_retriever_chunk = index.as_retriever(
        similarity_top_k=similarity_top_k)

    all_nodes_dict = {n.node_id: n for n in all_nodes}

    retriever = RecursiveRetriever(
        "vector",
        retriever_dict={"vector": vector_retriever_chunk},
        node_dict=all_nodes_dict,
        verbose=False,
    )

    return retriever

# Use in a Query Engine!
#
# Now, we can plug our retriever into a query engine to synthesize natural language responses.


def load_documents(
    data_dir: str,
    extensions: Optional[list[str]] = None,
    json_attributes: Optional[list[str]] = None,
):
    arg = {}

    is_file = os.path.isfile(data_dir)
    if is_file:
        arg['input_files'] = [data_dir]
    else:
        arg['input_dir'] = data_dir

    is_json = is_file and data_dir.endswith('.json')

    if is_json:
        # Load JSON file
        with open(data_dir, "r", encoding="utf-8") as f:
            json_data = json.load(f)

        # Convert each item in the JSON into a Document
        documents = []
        for item in json_data:
            # Use all attributes if json_attributes is empty or None
            if json_attributes:
                text_parts = [str(item[attr])
                              for attr in json_attributes if attr in item]
            else:
                # Use all attributes
                text_parts = [str(value) for key, value in item.items()]

            text_content = "\n".join(text_parts) if text_parts else ""

            documents.append(Document(
                text=text_content,
                metadata={
                    key: item[key] for key in item if key not in json_attributes
                }))
    else:
        documents = SimpleDirectoryReader(
            **arg, required_exts=extensions, recursive=True
        ).load_data()

    return documents


def setup_semantic_search(
    path_or_docs: str | list[Document],
    *,
    extensions: Optional[list[str]] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: int = 40,
    sub_chunk_sizes: Optional[list[int]] = None,
    with_hierarchy: Optional[bool] = None,
    embed_model: Optional[str] = OLLAMA_SMALL_EMBED_MODEL,
    mode: Optional[Literal["faiss", "graph_nx"]] = "faiss",
    split_mode: Optional[list[Literal["markdown", "hierarchy"]]] = [],
    json_attributes: Optional[list[str]] = [],
    **kwargs
):
    documents: list[Document]
    if type(path_or_docs) == str:
        documents = load_documents(path_or_docs, extensions, json_attributes)
    elif isinstance(path_or_docs, list):
        documents = path_or_docs
    else:
        raise ValueError(f"'data_dir' must be of type str | list[Document]")

    final_chunk_size: int = chunk_size if isinstance(
        chunk_size, int) else OLLAMA_MODEL_EMBEDDING_TOKENS[embed_model]

    splitter = SentenceSplitter(
        chunk_size=final_chunk_size,
        chunk_overlap=chunk_overlap,
        tokenizer=get_ollama_tokenizer(embed_model).encode
    )
    all_nodes = splitter.get_nodes_from_documents(
        documents, show_progress=True)

    texts = [node.text for node in all_nodes]
    node_lookup = {node.text: node.metadata for node in all_nodes}

    search = VectorSemanticSearch(texts)

    def search_func(
        query: str,
        threshold: float = 0.0,
        top_k: Optional[int] = None,
    ):
        if mode == "graph_nx":
            results = search.graph_based_search([query])
        else:
            results = search.faiss_search([query])

        search_results = results[query]

        logger.info(
            f"\n({mode.capitalize()}) Search Results ({len(search_results)}):")

        logger.newline()
        logger.info("Query:")
        logger.debug(query)
        for result in search_results:
            logger.log(f"{result['text'][:50]}:", f"{
                result['score']:.4f}", colors=["DEBUG", "SUCCESS"])

        retrieved_nodes: list[NodeWithScore] = [
            NodeWithScore(
                node=TextNode(
                    text=result['text'],
                    metadata=node_lookup.get(result['text'], {})
                ),
                score=float(result['score'])
            )
            for result in search_results]

        filtered_nodes: list[NodeWithScore] = [
            node for node in retrieved_nodes if node.score > threshold]

        filtered_nodes = filtered_nodes[:top_k]

        texts = [node.text for node in filtered_nodes]

        result = {
            "nodes": filtered_nodes,
            "texts": texts,
        }

        return result

    return search_func


_active_search_wrappers = {}


def get_file_timestamp(file_path: str) -> Optional[float]:
    """Get the last modified time of a file."""
    if os.path.isfile(file_path):
        return os.path.getmtime(file_path)
    return None


class SearchWrapper:
    def __init__(self, path_or_docs, setup_index_func, search_func, **kwargs):
        self.path_or_docs = path_or_docs
        self.setup_index_func = setup_index_func
        self.search_func = search_func
        self.kwargs = kwargs
        self.last_modified = get_file_timestamp(
            path_or_docs) if isinstance(path_or_docs, str) else None

    def reload_if_needed(self):
        if isinstance(self.path_or_docs, str):
            current_modified = get_file_timestamp(self.path_or_docs)
            if current_modified and self.last_modified and current_modified > self.last_modified:
                print("File has changed, reloading index...")
                self.search_func = self.setup_index_func(
                    self.path_or_docs, **self.kwargs).search_func
                self.last_modified = current_modified

    def __call__(self, query: str, *args, **kwargs):
        self.reload_if_needed()
        return self.search_func(query, *args, **kwargs)


def setup_index(
    path_or_docs: str | list[Document],
    *,
    extensions: Optional[list[str]] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: int = 40,
    sub_chunk_sizes: Optional[list[int]] = None,
    with_hierarchy: Optional[bool] = None,
    embed_model: Optional[str] = OLLAMA_SMALL_EMBED_MODEL,
    mode: Optional[Literal["fusion", "hierarchy", "deeplake"]] = "fusion",
    split_mode: Optional[list[Literal["markdown", "hierarchy"]]] = [],
    json_attributes: Optional[list[str]] = [],
    **kwargs
) -> SearchWrapper:
    global _active_search_wrappers

    if isinstance(path_or_docs, str):
        # Generate hash for the current set of arguments
        cache_values = [
            path_or_docs,
            mode,
            embed_model,
            json_attributes,
            chunk_size,
            chunk_overlap,
        ]
        current_hash_key = generate_key(*cache_values)

    if isinstance(path_or_docs, str) and current_hash_key in _active_search_wrappers:
        return _active_search_wrappers[current_hash_key]

    documents: list[Document]
    if isinstance(path_or_docs, str):
        documents = load_documents(path_or_docs, extensions, json_attributes)
    elif isinstance(path_or_docs, list):
        documents = path_or_docs
    else:
        raise ValueError("'data_dir' must be of type str | list[Document]")

    final_chunk_size: int = chunk_size if isinstance(
        chunk_size, int) else OLLAMA_MODEL_EMBEDDING_TOKENS[embed_model]

    if split_mode:
        if "markdown" in split_mode:
            all_nodes = split_markdown_header_nodes(documents)
    else:
        splitter = SentenceSplitter(
            chunk_size=final_chunk_size,
            chunk_overlap=chunk_overlap,
            tokenizer=get_ollama_tokenizer(embed_model).encode
        )
        all_nodes = splitter.get_nodes_from_documents(
            documents, show_progress=True)

    if with_hierarchy or mode == 'hierarchy' or (split_mode and "hierarchy" in split_mode):
        if not sub_chunk_sizes:
            sub_chunk_sizes = [final_chunk_size]
        other_args = {"chunk_overlap": chunk_overlap} if chunk_overlap else {}
        sub_nodes = split_heirarchical_nodes(
            all_nodes, sub_chunk_sizes, **other_args)
        jet_node_parser = JetHierarchicalNodeParser(sub_nodes, sub_chunk_sizes)
        all_nodes = get_leaf_nodes(jet_node_parser.all_nodes)

    if mode == "hierarchy":
        index = VectorStoreIndex(
            all_nodes,
            show_progress=True,
            embed_model=OllamaEmbedding(model_name=embed_model),
        )

        def search_hierarchy_func(
            query: str,
            threshold: float = 0.0,
            top_k: Optional[int] = None,
            **kwargs
        ):
            # First, we create our retrievers. Each will retrieve the top-10 most similar nodes.
            similarity_top_k = top_k if top_k and top_k < len(
                all_nodes) else len(all_nodes)
            combined_retriever = get_recursive_retriever(
                index, all_nodes, similarity_top_k=similarity_top_k)
            # else:
            # initial_similarity_k = len(documents)
            # final_similarity_k = len(all_nodes)

            retrieved_nodes: list[NodeWithScore] = combined_retriever.retrieve(
                query)

            filtered_nodes: list[NodeWithScore] = [
                node for node in retrieved_nodes if node.score > threshold]

            texts = [node.text for node in filtered_nodes]

            # contexts = clean_texts(filtered_nodes)

            result = {
                "nodes": filtered_nodes,
                "texts": texts,
                # "contexts": contexts,
            }

            return result

        wrapper = SearchWrapper(path_or_docs, setup_index,
                                search_hierarchy_func, **kwargs)

    elif mode == "deeplake":
        store_path = kwargs["store_path"]
        embedding_function = get_ollama_embedding_function(embed_model)
        vector_store = load_or_create_deeplake_vector_store(
            store_path=store_path,
            texts=[node.text for node in all_nodes],
            metadata=[node.metadata for node in all_nodes],
            embedding_function=embedding_function,
            overwrite=kwargs.get("overwrite", True),
            verbose=kwargs.get("verbose", False),
        )

        def search_deeplake_func(
            query: str,
            threshold: float = 0.0,
            top_k: Optional[int] = None,
            **kwargs
        ):
            similarity_top_k = top_k if top_k and top_k < len(
                all_nodes) else len(all_nodes)
            results = vector_store.search(
                embedding_data=query,
                k=similarity_top_k,
            )
            results["text"] = [str(text) for text in results["text"]]

            # Process search results into NodeWithScore format
            nodes_with_scores = [
                NodeWithScore(
                    node=TextNode(text=str(text), metadata=metadata),
                    score=extract_score(score)
                )
                for text, metadata, score in zip(results["text"], results["metadata"], results["score"])
            ]

            # contexts = clean_texts(nodes_with_scores)

            result = {
                "nodes": nodes_with_scores,
                "texts": results["text"],
                # "contexts": contexts,
            }

            return result

        wrapper = SearchWrapper(path_or_docs, setup_index,
                                search_deeplake_func, **kwargs)

    else:
        index = VectorStoreIndex(
            all_nodes,
            show_progress=True,
            embed_model=OllamaEmbedding(model_name=embed_model),
        )

        def search_fusion_func(
            query: str,
            threshold: float = 0.0,
            top_k: Optional[int] = None,
            fusion_mode: FUSION_MODES = FUSION_MODES.RELATIVE_SCORE,
            **kwargs
        ):

            initial_similarity_k = top_k if top_k and top_k < len(
                all_nodes) else len(all_nodes)
            final_similarity_k = top_k if top_k and top_k < len(
                all_nodes) else len(all_nodes)
            retrievers = setup_retrievers(
                index, initial_similarity_k, final_similarity_k)
            combined_retriever = get_fusion_retriever(
                retrievers, fusion_mode, top_k)

            retrieved_nodes: list[NodeWithScore] = combined_retriever.retrieve(
                query)

            filtered_nodes: list[NodeWithScore] = [
                node for node in retrieved_nodes if node.score > threshold]
            if top_k:
                filtered_nodes = filtered_nodes[:top_k]

            texts = [node.text for node in filtered_nodes]

            # contexts = clean_texts(filtered_nodes)

            result = {
                "nodes": filtered_nodes,
                "texts": texts,
                # "contexts": contexts,
            }

            return result

        wrapper = SearchWrapper(path_or_docs, setup_index,
                                search_fusion_func, **kwargs)

    if isinstance(path_or_docs, str):
        _active_search_wrappers[current_hash_key] = wrapper

    return wrapper


def get_relative_path(abs_path: str, partial_path: str) -> str:
    """
    Extracts the relative path from the absolute path using the given partial path as the starting point.

    :param abs_path: The absolute path to process.
    :param partial_path: The partial path to locate within the absolute path.
    :return: The resulting relative path starting from the partial path.
    """
    if partial_path in abs_path:
        start_index = abs_path.index(partial_path)
        return abs_path[start_index:]
    else:
        raise ValueError(f"Partial path '{
                         partial_path}' not found in the absolute path '{abs_path}'.")


def clean_texts(nodes: list[NodeWithScore]) -> list[str]:
    grouped_texts = group_and_merge_texts_by_file_name(nodes)
    contexts = [f"File: {file_name}\n\n{
        content}" for file_name, content in grouped_texts.items()]
    return contexts


def query_llm(
    query: str,
    contexts: list[str],
    model: Optional[OLLAMA_MODEL_NAMES] = OLLAMA_SMALL_LLM_MODEL,
    options: OllamaChatOptions = {},
    system: Optional[str] = None,
    template: PromptTemplate = PROMPT_TEMPLATE,
    max_tokens: Optional[int | float] = None,
    # retriever: QueryFusionRetriever,
    **kwargs,
):
    # query_engine = RetrieverQueryEngine.from_args(retriever, text_qa_template=)
    # response = query_engine.query(query)
    # return response

    if not system:
        system = SYSTEM_MESSAGE

    filtered_texts = filter_texts(
        contexts, model, max_tokens=max_tokens)
    context = "\n\n".join(filtered_texts)
    prompt = template.format(
        context_str=context, query_str=query
    )
    options = {**options, **DEFAULT_CHAT_OPTIONS}

    yield from call_ollama_chat(
        prompt,
        stream=True,
        model=model,
        system=system,
        options=options,
        # track={
        #     "repo": "~/aim-logs",
        #     "experiment": "RAG Retriever Test",
        #     "run_name": "Run Fusion Relative Score",
        #     "metadata": {
        #         "type": "rag_retriever",
        #     }
        # }
        **kwargs,
    )


def read_file(file_path, start_index=None, end_index=None):
    with open(file_path, 'r') as file:
        if not any([start_index, end_index]):
            content = file.read()
        else:
            file.seek(start_index)  # Move to the start index
            # Read only up to the end index
            content = file.read(end_index - start_index)
    return content


def setup_recursive_query(
    *args,
    chunk_size: int = 256,
    chunk_overlap: int = 20,
    **kwargs,
):
    splitter = SentenceSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    summary_nodes, vector_retrievers = initialize_summary_nodes_and_retrievers(
        *args,  transformations=[splitter], **kwargs)

    def query_nodes_func(
        query: str,
        threshold: float = 0.0,
        top_k: int = 4,
    ):
        retrieved_nodes = query_nodes_recursive(
            query,
            summary_nodes,
            vector_retrievers,
            transformations=[splitter],
            similarity_top_k=top_k,
        )

        filtered_nodes: list[NodeWithScore] = [
            node for node in retrieved_nodes if node.score > threshold]

        texts = [node.text for node in filtered_nodes]

        result = {
            "nodes": filtered_nodes,
            "texts": texts,
        }

        return result

    return query_nodes_func


def setup_deeplake_query(
    data_dir: str | list[Document],
    store_path: str,
    *,
    embed_model: str = OLLAMA_SMALL_EMBED_MODEL,
    chunk_size: Optional[int] = None,
    chunk_overlap: int = 40,
    overwrite=True,
    **kwargs,
):
    final_chunk_size: int = chunk_size if isinstance(
        chunk_size, int) else OLLAMA_MODEL_EMBEDDING_TOKENS[embed_model]
    # Define file and vector store paths
    documents: list[Document]
    if type(data_dir) == str:
        documents = SimpleDirectoryReader(data_dir).load_data()
    elif isinstance(data_dir, list):
        documents = data_dir
    else:
        raise ValueError(f"'data_dir' must be of type str | list[Document]")
    splitter = SentenceSplitter(
        chunk_size=final_chunk_size,
        chunk_overlap=chunk_overlap,
        tokenizer=get_ollama_tokenizer(embed_model).encode
    )
    all_nodes = splitter.get_nodes_from_documents(
        documents, show_progress=True)

    texts = [node.text for node in all_nodes]
    metadata = [node.metadata for node in all_nodes]

    embedding_function = get_ollama_embedding_function(embed_model)

    # Create a VectorStore instance
    vector_store = load_or_create_deeplake_vector_store(
        store_path,
        texts=texts,
        metadata=metadata,
        embedding_function=embedding_function,
        overwrite=overwrite,
        verbose=True,
    )

    def query_nodes_func(
        query: str,
        threshold: float = 0.0,
        top_k: int = 4,
    ):
        search_results = search_deeplake_store(
            query, store_path, top_k=top_k, embedding_function=embedding_function)

        texts = [node.text for node in search_results]

        result = {
            "nodes": search_results,
            "texts": texts,
        }

        return result

    return query_nodes_func


def load_or_create_deeplake_vector_store(
    store_path: str,
    texts: list[str],
    metadata: Optional[list[str]] = None,
    embedding_function: Optional[Callable] = None,
    overwrite: bool = False,
    **kwargs
):
    from deeplake.core.vectorstore import VectorStore
    logger.log("Vector store path:", os.path.realpath(store_path),
               colors=["GRAY", "BRIGHT_DEBUG"])

    os.makedirs(store_path, exist_ok=True)

    # Create a VectorStore instance
    vector_store = VectorStore(
        path=store_path,
        embedding_function=embedding_function,
        overwrite=overwrite,
        **kwargs
    )

    if overwrite:
        # Add text chunks to the vector store with embeddings
        vector_store.add(
            text=texts,
            embedding_function=embedding_function,
            embedding_data=texts,
            metadata=metadata,
        )

    return vector_store


def search_deeplake_store(
    prompt: str,
    store_path: str,
    top_k=4,
    embedding_function: Optional[Callable] = None,
) -> list[NodeWithScore]:
    from deeplake.core.vectorstore import VectorStore
    vector_store = VectorStore(
        path=store_path, embedding_function=embedding_function)

    results = vector_store.search(
        embedding_data=prompt,
        k=top_k,
    )
    results["text"] = [str(text) for text in results["text"]]

    # Process search results into NodeWithScore format
    nodes_with_scores = [
        NodeWithScore(
            node=TextNode(text=str(text), metadata=metadata),
            score=extract_score(score)
        )
        for text, metadata, score in zip(results["text"], results["metadata"], results["score"])
    ]
    return nodes_with_scores


def extract_score(score) -> float:
    # Check if score is a tensor and convert it to float
    if hasattr(score, 'item'):  # e.g., if it's a tensor
        return score.item()
    elif isinstance(score, list) and len(score) == 1:
        # If it's a list with a single score, convert to float
        return float(score[0])
    return float(score)  # If it's already a float, return it directly


if __name__ == "__main__":
    system = (
        "You are a job applicant providing tailored responses during an interview.\n"
        "Always answer questions using the provided context as if it is your resume, "
        "and avoid referencing the context directly.\n"
        "Some rules to follow:\n"
        "1. Never directly mention the context or say 'According to my resume' or similar phrases.\n"
        "2. Provide responses as if you are the individual described in the context, focusing on professionalism and relevance."
    )

    prompt_template = PromptTemplate(
        """\
    Resume details are below.
    ---------------------
    {context_str}
    ---------------------
    Given the resume details and not prior knowledge, respond to the question.
    Question: {query_str}
    Response: \
    """
    )

    data_dir = "/Users/jethroestrada/Desktop/External_Projects/Jet_Projects/JetScripts/data/jet-resume/data"
    rag_dir = "/Users/jethroestrada/Desktop/External_Projects/Jet_Projects/JetScripts/data/jet-resume/data"
    extensions = [".md"]

    sample_query = "Tell me about yourself."

    documents = SimpleDirectoryReader(
        rag_dir, required_exts=extensions).load_data()

    query_nodes = setup_index(documents)

    # logger.newline()
    # logger.info("RECIPROCAL_RANK: query...")
    # response = query_nodes(sample_query, FUSION_MODES.RECIPROCAL_RANK)

    # logger.newline()
    # logger.info("DIST_BASED_SCORE: query...")
    # response = query_nodes(sample_query, FUSION_MODES.DIST_BASED_SCORE)

    logger.newline()
    logger.info("RELATIVE_SCORE: sample query...")
    result = query_nodes(
        sample_query, FUSION_MODES.RELATIVE_SCORE, threshold=0.2)
    logger.info(f"RETRIEVED NODES ({len(result["nodes"])})")
    display_jet_source_nodes(sample_query, result["nodes"])

    response = query_llm(sample_query, result['texts'])
    # logger.info("QUERY RESPONSE:")
    # logger.success(response)

    # Run app
    while True:
        # Continuously ask user for queries
        try:
            query = input("Enter your query (type 'exit' to quit): ").strip()
            if query.lower() == "exit":
                print("Exiting query loop.")
                break

            result = query_nodes(query, FUSION_MODES.RELATIVE_SCORE)
            logger.info(f"RETRIEVED NODES ({len(result["nodes"])})")
            display_jet_source_nodes(query, result["nodes"])

            response = query_llm(query, result['texts'])
            # logger.info("QUERY RESPONSE:")
            # logger.success(response)

        except KeyboardInterrupt:
            print("\nExiting query loop.")
            break
        except Exception as e:
            logger.error(f"Error while processing query: {e}")

    logger.info("\n\n[DONE]", bright=True)
