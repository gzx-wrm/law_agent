from typing import List

from langchain.agents import initialize_agent, AgentType
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import Tool

from model.model import get_model_ali


class LegalAgent:
    def __init__(self, model: BaseChatModel, tools: List[Tool]):
        # 初始化原有的工具和Agent
        self.tools = tools
        self.llm = model
        # self.memory = ConversationBufferWindowMemory(k=3)

        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            # memory=self.memory,
            handle_parsing_errors=True,
        )
