from langchain.chat_models import init_chat_model
from langchain_community.chat_models import ChatOpenAI
from langchain_core.callbacks import Callbacks


def get_model_ali(
        model: str = "qwen-plus",
        streaming: bool = True,
        callbacks: Callbacks = None) -> ChatOpenAI:
    model = ChatOpenAI(api_key="sk-f1dc8b855d9747e1877fb393664b3335",
                       base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                       model="qwen-plus", streaming=streaming, callbacks=callbacks)
    return model

def get_langgraph_model():
    return init_chat_model(api_key="sk-f1dc8b855d9747e1877fb393664b3335",
                       base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                       model="openai:qwen-plus", streaming=True, callbacks=None)