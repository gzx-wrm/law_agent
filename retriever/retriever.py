from elasticsearch import Elasticsearch
from langchain.chains.llm import LLMChain
from langchain.retrievers.multi_query import LineListOutputParser, MultiQueryRetriever
from langchain_community.vectorstores import ElasticsearchStore
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import VectorStore
from pydantic import BaseModel

from embedding.embedding import AliEmbeddings
from prompt.prompt import MULTI_QUERY_PROMPT_TEMPLATE


def get_es_retriever(index_name: str, embedding: Embeddings) -> BaseRetriever:
    es_client = Elasticsearch(
        hosts=["http://localhost:9200"],
        # 如果有认证信息
        http_auth=('elastic', '123456')
    )

    vectorstore = ElasticsearchStore(
        es_connection=es_client,
        index_name="law_documents",
        embedding=embedding,
        strategy=ElasticsearchStore.ApproxRetrievalStrategy()  # 或者 DenseVectorStrategy
    )

    return vectorstore.as_retriever(search_kwargs={"k": 3, })

def get_multi_query_retriever(retriever: BaseRetriever, model: BaseModel) -> BaseRetriever:
    output_parser = LineListOutputParser()

    llm_chain = LLMChain(llm=model, prompt=MULTI_QUERY_PROMPT_TEMPLATE, output_parser=output_parser)

    retriever = MultiQueryRetriever(
        retriever=retriever, llm_chain=llm_chain, parser_key="lines"
    )

    return retriever