from llama_index.core import VectorStoreIndex, StorageContext, Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.lancedb import LanceDBVectorStore
from openai import OpenAI as PerplexityClient
from llama_index.core.vector_stores import MetadataFilters, MetadataFilter, FilterOperator
import lancedb
import pyarrow as pa
import os
from datetime import datetime

# Initialize Perplexity Sonar client
sonar_client = PerplexityClient(
    api_key=os.environ["PERPLEXITY_API_KEY"],
    base_url="https://api.perplexity.ai"
)

# Define explicit schema matching metadata structure
schema = pa.schema([
    pa.field("id", pa.string()),
    pa.field("text", pa.string()),
    pa.field("metadata", pa.map_(pa.string(), pa.string())),  # Store metadata as key-value map
    pa.field("embedding", pa.list_(pa.float32(), 768))  # Match your embedding dimension
])

# Initialize persistent vector store with clean slate
lancedb_uri = "./lancedb"
if os.path.exists(lancedb_uri):
    import shutil
    shutil.rmtree(lancedb_uri)
    
db = lancedb.connect(lancedb_uri)
vector_store = LanceDBVectorStore(uri=lancedb_uri, table_name="chat_history")
storage_context = StorageContext.from_defaults(vector_store=vector_store)

# Configure node parser with metadata support
node_parser = SentenceSplitter(
    chunk_size=1024,
    chunk_overlap=100,
    include_metadata=True
)

def initialize_chat_session():
    """Create new session with proper schema"""
    return VectorStoreIndex(
        [],
        storage_context=storage_context,
        node_parser=node_parser
    )

def chat_with_persistence(user_query: str, index: VectorStoreIndex):
    # Store user query
    user_doc = Document(
        text=user_query,
        metadata={
            "role": "user",
            "timestamp": datetime.now().isoformat()
        }
    )
    index.insert_nodes(node_parser.get_nodes_from_documents([user_doc]))
    
    # Retrieve context nodes
    retriever = index.as_retriever(similarity_top_k=3)
    context_nodes = retriever.retrieve(user_query)
    
    # Ensure context relevance by filtering for recent queries
    context_text = "\n".join([
        f"{n.metadata['role'].title()}: {n.text}" 
        for n in context_nodes if n.metadata["role"] == "user"
    ])
    
    # Generate Sonar API request
    messages = [
        {
            "role": "system",
            "content": f"Conversation History:\n{context_text}\n\nAnswer the latest query using this context."
        },
        {"role": "user", "content": user_query}
    ]
    
    response = sonar_client.chat.completions.create(
        model="sonar-pro",
        messages=messages,
        temperature=0.3
    )
    
    assistant_response = response.choices[0].message.content
    
    # Store assistant response
    assistant_doc = Document(
        text=assistant_response,
        metadata={
            "role": "assistant",
            "timestamp": datetime.now().isoformat()
        }
    )
    index.insert_nodes(node_parser.get_nodes_from_documents([assistant_doc]))
    
    # Persist conversation state
    storage_context.persist(persist_dir="./chat_store")
    return assistant_response

# Usage
if __name__ == "__main__":
    index = initialize_chat_session()
    print("Response:", chat_with_persistence("What's the current weather in London?", index))
    print("Follow-up:", chat_with_persistence("What about tomorrow's forecast?", index))
