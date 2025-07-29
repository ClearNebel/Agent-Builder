import yaml
import os
import torch
from app.router import route_request
from app.subagent_handler import handle_with_subagent
from app.llm_inference import load_base_model_and_tokenizer, generate_response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))

def load_config(config_path=os.path.join(BASE_DIR, '../configs/config.yaml')):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def main():
    config = load_config()
    base_model_id = config['base_model']
    
    model, tokenizer = load_base_model_and_tokenizer(base_model_id)
    
    print("\nWelcome to the Gemma Multi-Agent System (Optimized)!")
    print("Type 'exit' or 'quit' to end the session.")
    
    agents_config = config['agents']
    available_agents = list(agents_config.keys())
    
    while True:
        try:
            user_query = input("\nYou: ")
            if user_query.lower() in ['exit', 'quit']:
                break

            router_adapter_path = os.path.join(BASE_DIR, '..', config['router']['model_path'])
            chosen_agent_name = route_request(
                model, tokenizer, user_query, available_agents, router_adapter_path
            )

            if chosen_agent_name and chosen_agent_name in agents_config:
                agent_config = agents_config[chosen_agent_name]
                print((agent_config['prompt_file']))
                print((agent_config))
                final_agent_config = {
                    'prompt_file': (PROJECT_ROOT + agent_config['prompt_file']),
                    'model_path': os.path.join(PROJECT_ROOT, agent_config['model_path']),
                    'tools_whitelist': agent_config.get('tools_whitelist', [])
                }
                
                response = handle_with_subagent(
                    model, tokenizer, chosen_agent_name, user_query, final_agent_config
                )
                display_name = chosen_agent_name.capitalize()
            else:
                print("[System] Routing failed or uncertain. Using general base model.")
                response = generate_response(model, tokenizer, user_query)
                display_name = "Assistant"

            print(f"\n{display_name}: {response}")

        except KeyboardInterrupt:
            print("\nExiting session.")
            break
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
            torch.cuda.empty_cache()
            continue

if __name__ == "__main__":
    main()