from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.outputs import ChatResult, ChatGeneration

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("Please install google-genai package: pip install google-genai")

class CustomGeminiAdapter(BaseChatModel):
    client: Any = None
    model_name: str
    temperature: float = 0

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-pro", temperature: float = 0, **kwargs):
        super().__init__(model_name=model_name, temperature=temperature, **kwargs)
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.temperature = temperature

    @property
    def _llm_type(self) -> str:
        return "google-genai-custom"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        
        # Convert LangChain messages to Google GenAI format
        # This is a simplified converter
        prompt_text = ""
        system_instruction = None
        
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_instruction = msg.content
            elif isinstance(msg, HumanMessage):
                prompt_text += f"\nUser: {msg.content}"
            elif isinstance(msg, AIMessage):
                prompt_text += f"\nModel: {msg.content}"
            else:
                prompt_text += f"\n{msg.content}"

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            candidate_count=1,
            stop_sequences=stop,
            system_instruction=system_instruction
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt_text.strip(),
                config=config
            )
            
            content = response.text
            
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=content))]
            )
        except Exception as e:
            # Fallback for error handling or different model names
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=f"Error: {str(e)}"))]
            )
