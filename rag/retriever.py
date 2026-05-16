import chromadb
import os

def get_collection(repo_name: str, db_path="./rag/chroma_db"):
    """Get a ChromaDB collection for a repository."""
    client = chromadb.PersistentClient(path=db_path)
    collection_name = repo_name.replace("/", "_").replace("-", "_")
    try:
        return client.get_collection(name=collection_name)
    except Exception:
        print(f"Collection '{collection_name}' not found. Index the repo first.")
        return None


def retrieve_context(issue_text: str, repo_name: str, 
                     n_results=6, db_path="./rag/chroma_db") -> list[str]:
    """
    Retrieve the most relevant code chunks for a given issue description.
    Returns a list of code strings.
    """
    collection = get_collection(repo_name, db_path)
    if collection is None:
        return []

    results = collection.query(
        query_texts=[issue_text],
        n_results=min(n_results, collection.count())
    )

    chunks = results["documents"][0]
    metadatas = results["metadatas"][0]

    print(f"\nRetrieved {len(chunks)} chunks for query:")
    print(f"Query: {issue_text[:100]}...")
    print(f"\nRelevant files:")
    for meta in metadatas:
        print(f"  - {meta['file']} "
              f"(lines {meta['start_line']}-{meta['end_line']})")

    return chunks


def format_context(chunks: list[str]) -> str:
    """Format retrieved chunks into a single context string."""
    if not chunks:
        return ""
    
    context = "=== RELEVANT CODE CONTEXT ===\n\n"
    for i, chunk in enumerate(chunks):
        context += f"--- Chunk {i+1} ---\n"
        context += chunk
        context += "\n\n"
    context += "=== END CONTEXT ===\n"
    return context


if __name__ == "__main__":
    # Test retrieval on our test_repo
    test_query = "function that loads dataset and processes samples"
    chunks = retrieve_context(test_query, "test_repo")
    
    if chunks:
        print(f"\nFirst chunk preview:")
        print(chunks[0][:300])
        print("\nRetriever working correctly")
    else:
        print("No chunks retrieved")