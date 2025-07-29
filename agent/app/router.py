from app.llm_inference import generate_response
from transformers import AutoModelForCausalLM, AutoTokenizer
import os
import re

def _parse_agent(response: str):
    """Parses the LLM response to find a tool call."""
    match = re.search(r'</think>\s*(.*)', response, re.DOTALL)
    if '<think>' in response and match:
        after_think = match.group(1).strip()
        return after_think
    else:
        return response

def route_request(
    model: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    user_query: str,
    agents: list,
    router_adapter_path: str,
    **kwargs
) -> str:
    """Analyzes the user query using the shared model with router adapters."""
    agent_list_str = ", ".join(agents)
    
    prompt = f"""Given the user's query, determine which of the following agents is best suited to respond. If no agent is clearly suitable, select the default agent: general_agent. 

The available agents are: [{agent_list_str}].

Respond with ONLY the name of the selected agent in the exact format: 
AGENT_NAME

Only replace AGENT_NAME with the chosen agent.

User Query: "{user_query}"
Agent:"""

    print(prompt)
    print(f"\n[Router] Determining best agent for query: '{user_query}'")

    adapter_loaded = False
    if os.path.isdir(router_adapter_path):
        try:
            print(f"[Router] Loading adapter from: {router_adapter_path}")
            model.load_adapter(router_adapter_path, adapter_name="router")
            model.set_adapter("router")
            adapter_loaded = True
        except Exception as e:
            print(f"[Router] ERROR: Failed to load adapter from '{router_adapter_path}'. Error: {e}")
            print("[Router] Using base model for routing instead.")
    else:
        print(f"[Router] WARNING: Router adapter not found at '{router_adapter_path}'. Using base model for routing.")

    chosen_agent = generate_response(
        model=model,
        tokenizer=tokenizer,
        prompt_text=prompt,
        max_new_tokens=1024
    )
    
    print(chosen_agent)

    if adapter_loaded:
        print("[Router] Unloading adapter.")
        model.delete_adapter("router")

    chosen_agent = _parse_agent(chosen_agent)
    print(chosen_agent)

    chosen_agent = chosen_agent.strip().replace('.', '')

    if chosen_agent in agents:
        print(f"[Router] Decision: Route to '{chosen_agent}' agent.")
        return chosen_agent
    else:
        print(f"[Router] Warning: Model returned an invalid agent '{chosen_agent}'.")
        return None
