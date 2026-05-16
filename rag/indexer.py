import chromadb
import os
from pathlib import Path

def get_client(db_path="./rag/chroma_db"):
    """Get a persistent ChromaDB client."""
    os.makedirs(db_path, exist_ok=True)
    return chromadb.PersistentClient(path=db_path)

def chunk_python_file(file_path: str) -> list[dict]:
    """Split a Python file into function-level chunks."""
    chunks = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        lines = content.split("\n")
        current_chunk = []
        current_start = 0
        chunk_id = 0

        for i, line in enumerate(lines):
            # start of a new function or class
            if (line.startswith("def ") or line.startswith("class ") or
                line.startswith("    def ")):
                if current_chunk and len("\n".join(current_chunk)) > 50:
                    chunks.append({
                        "id":      f"{file_path}_{chunk_id}",
                        "text":    "\n".join(current_chunk),
                        "file":    file_path,
                        "start_line": current_start,
                        "end_line": i,
                    })
                    chunk_id += 1
                current_chunk = [line]
                current_start = i
            else:
                current_chunk.append(line)

        # add final chunk
        if current_chunk:
            chunks.append({
                "id":      f"{file_path}_{chunk_id}",
                "text":    "\n".join(current_chunk),
                "file":    file_path,
                "start_line": current_start,
                "end_line": len(lines),
            })

    except Exception as e:
        print(f"Error chunking {file_path}: {e}")

    return chunks


def index_repo(repo_path: str, repo_name: str, db_path="./rag/chroma_db"):
    """Index all Python files in a repository into ChromaDB."""
    client = get_client(db_path)

    # get or create collection for this repo
    collection = client.get_or_create_collection(
        name=repo_name.replace("/", "_").replace("-", "_"),
        metadata={"repo": repo_name}
    )

    print(f"Indexing {repo_name}...")
    all_chunks = []

    for py_file in Path(repo_path).rglob("*.py"):
        chunks = chunk_python_file(str(py_file))
        all_chunks.extend(chunks)

    if not all_chunks:
        print(f"No Python files found in {repo_path}")
        return

    print(f"Found {len(all_chunks)} chunks from {repo_name}")

    # add in batches of 100
    batch_size = 100
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        collection.add(
            documents=[c["text"] for c in batch],
            ids=[c["id"][:512] for c in batch],
            metadatas=[{
                "file":       c["file"],
                "start_line": c["start_line"],
                "end_line":   c["end_line"],
            } for c in batch]
        )
        print(f"  Indexed batch {i//batch_size + 1} "
              f"({min(i+batch_size, len(all_chunks))}/{len(all_chunks)} chunks)")

    print(f"Done indexing {repo_name}")
    return collection


if __name__ == "__main__":
    # Test with a small local Python folder first
    # We will use actual SWE-bench repos in Week 2
    print("Indexer starting...")
    test_path = "./agent"
    index_repo(test_path, "test_repo")
    print("\nIndexer working correctly")