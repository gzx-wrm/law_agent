from typing import List

from elasticsearch import Elasticsearch
from langchain_community.vectorstores import ElasticsearchStore
from langchain_core.documents import Document

from embedding.embedding import AliEmbeddings
from embedding.loader import LawLoader
from embedding.splitter import LawSplitter


class LawDocumentStore:
    def __init__(self, es_client=None):
        self.es_client = es_client or Elasticsearch(
            hosts=["http://localhost:9200"],
            # 如果有认证信息
            http_auth=('elastic', '123456')
        )
        self.embeddings = AliEmbeddings()

    def store_documents(self, split_documents: List[Document], index_name: str = "law_documents"):
        """
        将切分后的法律文档存储到Elasticsearch
        """
        # 创建向量存储
        vectorstore = ElasticsearchStore(
            es_connection=self.es_client,
            index_name=index_name,
            embedding=self.embeddings,
            strategy=ElasticsearchStore.ApproxRetrievalStrategy()  # 或者 DenseVectorStrategy
        )

        # 添加文档
        vectorstore.add_documents(split_documents)

        return vectorstore

    def create_index_mapping(self, index_name: str = "law_documents"):
        """
        创建优化的索引mapping
        """
        mapping = {
            "mappings": {
                "properties": {
                    "text": {"type": "text"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": 1024,
                        "index": True,
                        "similarity": "cosine"
                    },
                    "book": {"type": "keyword"},
                    "header1": {"type": "keyword"},
                    "header2": {"type": "keyword"},
                    "header3": {"type": "keyword"},
                    "header4": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "page": {"type": "integer"},
                    # 其他metadata字段
                    "metadata": {
                        "type": "object",
                        "enabled": True
                    }
                }
            }
        }

        # 创建索引
        if not self.es_client.indices.exists(index=index_name):
            self.es_client.indices.create(index=index_name, body=mapping)

if __name__ == '__main__':
    text_splitter = LawSplitter.from_tiktoken_encoder(
        chunk_size=100, chunk_overlap=20
    )
    docs = LawLoader("../Law-Book").load_and_split(text_splitter=text_splitter)

    # print(len(docs))
    document_store = LawDocumentStore()
    document_store.store_documents(docs)