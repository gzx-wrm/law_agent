from langchain_core.retrievers import BaseRetriever
from langchain_core.tools import Tool, tool

def get_law_documents_retriever_tool(retriever: BaseRetriever) -> Tool:
    @tool(name_or_callable="LegalRetriever",
          description="用于检索中国法律法规和条文。输入一个法律问题或关键词。")
    def law_retriever(query):
        # 基于向量相似度检索，并可利用元数据进行过滤
        docs = retriever.invoke(query)
        # docs = retriever.similarity_search(query, k=3)  # 检索最相关的5个片段
        return "\n\n".join([f"出处：{doc.metadata['book']}\n内容：{doc.page_content}" for doc in docs])

    return Tool(
        name="LegalRetriever",
        func=law_retriever,
        description="用于检索中国法律法规和条文。输入一个法律问题或关键词。"
    )
