import os, re
from app.llm_inference import generate_response, generate_response_stream
from transformers import AutoModelForCausalLM, AutoTokenizer
from tools.tool_registry import TOOL_REGISTRY

def _format_tool_prompt(allowed_tools: list) -> str:
    """Formats the tool descriptions for the LLM prompt."""
    if not allowed_tools:
        return ""

    prompt_lines = [
    "You are ONLY allowed to call a tool if ALL the following conditions are met:",
    "1. You are 100% certain you HAVE TO USE the tool and it will provide the correct and needed information.",
    "2. The tool is currently available (from the provided list).",
    "3. You only use tools when absolutely necessary — rely on your own knowledge when appropriate.",
    "To call a tool, respond ONLY with the tool function call, wrapped **exactly** like this:",
    "<tool_code>tool_function(arguments)</tool_code>",
    "Do not include any extra explanation or response outside the <tool_code> tags.",
    "Example:",
    "<tool_code>get_current_date()</tool_code>",
    "Now, here are the available tools you may call:",
    "\nAvailable Tools:"
    ]
    for tool_name in allowed_tools:
        if tool_name in TOOL_REGISTRY:
            prompt_lines.append(f"- {TOOL_REGISTRY[tool_name]['schema']}")
    
    prompt_lines.append("Always remember: if you're not absolutely certain a tool is required **and available**, do not call it. If a Tool was called once your prohibited to recall it!")

    return "\n".join(prompt_lines)

def _parse_tool_call(response: str):
    """Parses the LLM response to find a tool call."""
    match = re.search(r"<tool_code>(.*?)</tool_code>", response)
    if match:
        call_str = match.group(1).strip()
        print(f"[Subagent Handler] Parsed tool call: {call_str}")
        return call_str
    return None

def _execute_tool(call_str: str) -> str:
    """Executes a tool call string and returns the result."""
    try:
        tool_name = call_str.split('(')[0]
        if tool_name not in TOOL_REGISTRY:
            return f"Error: Tool '{tool_name}' not found."
        
        args_str = call_str[len(tool_name)+1:-1]
        values = [arg.strip() for arg in args_str.split(',') if arg.strip()]
        args = [arg.split("=", 1)[1].strip("'").strip('"') for arg in values]
        

        parsed_args = []
        for arg in args:
            try: parsed_args.append(float(arg))
            except ValueError: parsed_args.append(arg)

        print(parsed_args)
        func = TOOL_REGISTRY[tool_name]['function']
        print(func)
        result = func(*parsed_args)
        return str(result)
    except Exception as e:
        return f"Error executing tool '{call_str}': {e}"

def handle_with_subagent(
    model: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    agent_name: str,
    user_query: str,
    prompt_history: list,
    agent_config: dict,
    max_loops: int = 10,
    **kwargs
) -> str:
    """Handles the user query with the specified subagent using dynamic adapters."""
    adapter_path = agent_config['model_path']
    allowed_tools = agent_config.get('tools_whitelist', [])

    adapter_loaded = False
    if os.path.isdir(adapter_path):
        print(f"[{agent_name.capitalize()} Agent] Loading adapter from: {adapter_path}")
        model.load_adapter(adapter_path, adapter_name=agent_name)
        model.set_adapter(agent_name)
        adapter_loaded = True
    else:
        print(f"[{agent_name.capitalize()} Agent] Warning: Adapter not found at '{adapter_path}'. Using base model.")

    print(os.getcwd())
    print('../agent' + agent_config['prompt_file'])
    try:
        with open('../agent' + agent_config['prompt_file'], 'r') as f:
            master_prompt = f.read().strip()
    except FileNotFoundError:
        try:
            with open(agent_config['prompt_file'], 'r') as f:
                master_prompt = f.read().strip()
        except FileNotFoundError:
            return f"Error: Prompt file not found."

    tool_prompt = _format_tool_prompt(allowed_tools)
    
    master_prompt = f"{master_prompt}\n{tool_prompt}"
    
    print(master_prompt)

    for i in range(max_loops):
        
        print(f"\n--- [Loop {i+1}] Sending prompt to LLM ---")
        print(prompt_history)
        llm_response = generate_response(
            model=model,
            tokenizer=tokenizer,
            prompt_text=user_query,
            prompt_history=prompt_history,
            prompt_master_prompt=master_prompt,
            **kwargs
        )
        print(f"--- [Loop {i+1}] LLM Raw Response: {llm_response} ---")

        tool_call_str = _parse_tool_call(llm_response)

        print(llm_response)

        if tool_call_str:
            print(f"[Subagent Handler] Agent wants to call tool: {tool_call_str}")
            
            tool_name = tool_call_str.split('(')[0]
            if tool_name not in allowed_tools:
                result = f"Error: You are not permitted to use the tool '{tool_name}'."
            else:
                result = _execute_tool(tool_call_str)
            
            print(f"[Subagent Handler] Tool result: {result}")
            
            master_prompt = master_prompt + f"\nObservation: <tool_called>{tool_call_str}</tool_called>\n <tool_result>{result}</tool_result>"
            user_query = f"Now, provide a final answer to the user based on the tool's result. Initial Question to Awnser: {user_query}"
        else:
            if adapter_loaded:
                print(f"[{agent_name.capitalize()} Agent] Unloading adapter.")
                model.delete_adapter(agent_name)
            return llm_response 
    
    final_answer = "The agent could not determine a final answer after using its tools."
    if adapter_loaded:
        model.delete_adapter(agent_name)
    return final_answer

def handle_with_subagent_stream(
    model,
    tokenizer,
    agent_name: str,
    user_query_with_history: str,
    agent_config: dict,
    generation_kwargs: dict,
    max_loops: int = 3
) -> iter:
    """
    Handles the user query with a subagent, supports tool use, and STREAMS the final response.
    This is now a generator function.
    """
    adapter_path = agent_config['model_path']
    allowed_tools = agent_config.get('tools_whitelist', [])
    
    adapter_loaded = False
    if os.path.isdir(adapter_path):
        print(f"[{agent_name.capitalize()} Agent] Loading adapter from: {adapter_path}")
        model.load_adapter(adapter_path, adapter_name=agent_name)
        model.set_adapter(agent_name)
        adapter_loaded = True
    else:
        print(f"[{agent_name.capitalize()} Agent] Warning: Adapter not found at '{adapter_path}'. Using base model.")

    try:
        with open('../agent' + agent_config['prompt_file'], 'r') as f:
            master_prompt = f.read().strip()
    except FileNotFoundError:
        return f"Error: Prompt file not found."

    try:
        tool_prompt = _format_tool_prompt(allowed_tools)
        
        initial_context = [
            master_prompt,
            tool_prompt,
            f"\n{user_query_with_history}"
        ]
        
        conversation_history = list(initial_context)

        for i in range(max_loops):
            full_prompt = "\n".join(conversation_history)

            from .llm_inference import generate_response
            llm_decision = generate_response(
                model=model,
                tokenizer=tokenizer,
                prompt_text=full_prompt,
                max_new_tokens=256,
                **generation_kwargs
            )
            
            tool_call_str = _parse_tool_call(llm_decision)

            if tool_call_str:
                result = _execute_tool(tool_call_str)
                synthesis_prompt = f"""
Observation: <tool_result>{result}</tool_result>
Thought: Now I have the result. I will use it to form the final answer.
Final Answer:"""
                conversation_history.append(synthesis_prompt)
            else:
                final_prompt_for_streaming = f"{full_prompt}\nAssistant: {llm_decision}"
                
                print(f"[Subagent Handler] Streaming final answer for agent '{agent_name}'.")
                yield from generate_response_stream(model, tokenizer, final_prompt_for_streaming, **generation_kwargs) # handle without stream generate_response
                
                break
    finally:
        if adapter_loaded:
            print(f"[{agent_name.capitalize()} Agent] Unloading adapter.")
            model.delete_adapter(agent_name)