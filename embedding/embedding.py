from typing import List

import dashscope
from dashscope import TextEmbedding
from langchain_core.embeddings import Embeddings


class AliEmbeddings(Embeddings):
    def __init__(self, model_name: str = "text-embedding-v4", api_key: str = None):
        self.model_name = model_name
        dashscope.api_key = "sk-f1dc8b855d9747e1877fb393664b3335"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入文档列表"""
        batch = []
        res = []

        def batch_embedding(texts: List[str]) -> List[float]:
            response = TextEmbedding.call(
                model="text-embedding-v4",
                input=texts,
                # 仅 text-embedding-v3及 text-embedding-v4支持以下参数
                dimension=1024,  # 指定向量维度
                output_type="dense",  # 指定输出稠密向量（dense）/稀疏向量（sparse）/同时输出两种向量（dense&sparse）
                # 仅 text-embedding-v4支持以下参数
                instruct="Chinese Laws and Regulations"
            )

            if response.status_code == 200:
                embeddings = [embedding['embedding'] for embedding in response.output['embeddings']]
                return  embeddings
            else:
                raise Exception(f"Embedding failed: {response.message}")

        for text in texts:
            batch.append(text)
            if len(batch) == 10:
                res.extend(batch_embedding(batch))
                batch = []
        if len(batch) > 0:
            res.extend(batch_embedding(batch))
        return res

    def embed_query(self, text: str) -> List[float]:
        """嵌入查询文本"""
        if len(text) > 1000:
            text = text[:1000]
        response = TextEmbedding.call(
            model="text-embedding-v4",
            input=text,
            # 仅 text-embedding-v3及 text-embedding-v4支持以下参数
            dimension=1024,  # 指定向量维度
            output_type="dense",  # 指定输出稠密向量（dense）/稀疏向量（sparse）/同时输出两种向量（dense&sparse）
            # 仅 text-embedding-v4支持以下参数
            instruct="Chinese Laws and Regulations"
        )
        if response.status_code == 200:
            return response.output['embeddings'][0]['embedding']
        else:
            raise Exception(f"Embedding failed: {response.message}")