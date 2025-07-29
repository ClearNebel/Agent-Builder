import os
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

PROVIDER_MAP = {
    'openai': ChatOpenAI,
    'google': ChatGoogleGenerativeAI,
}

def get_chat_model(provider_name, model_name, temperature, top_p):
    """
    Factory function to get an instance of a LangChain chat model.
    """
    if provider_name not in PROVIDER_MAP:
        raise ValueError(f"Provider '{provider_name}' is not supported.")

    model_class = PROVIDER_MAP[provider_name]
    
    chat_model = model_class(
        model=model_name,
        temperature=temperature,
        top_p=top_p
    )
    return chat_model

def invoke_llm_with_history(chat_model, prompt: str, history: list):
    """
    Invokes the given LangChain chat model with a prompt and formatted history.
    """
    messages = [SystemMessage(content="You are a helpful assistant.")]
    
    for msg in history:
        if msg['role'] == 'user':
            messages.append(HumanMessage(content=msg['content']))
        elif msg['role'] == 'assistant':
            messages.append(AIMessage(content=msg['content']))

    messages.append(HumanMessage(content=prompt))

    ai_response = chat_model.invoke(messages)

    return ai_response.content