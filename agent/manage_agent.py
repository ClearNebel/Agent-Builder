import argparse
import os
import sys
import yaml
import subprocess
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'configs/config.yaml')
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), 'configs/prompts')
TRAINING_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), 'training/train_sft.py')
DPO_TRAINING_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), 'training/train_dpo.py')
MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')
ADMIN_AGENT_BASE_MODEL_ID = "google/gemma-3-4b-it"

ADMIN_MODEL = None
ADMIN_TOKENIZER = None

def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f: return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found at {CONFIG_PATH}"); sys.exit(1)

def save_config(config_data):
    try:
        with open(CONFIG_PATH, 'w') as f: yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
        print(f"✅ Configuration saved to {CONFIG_PATH}")
    except Exception as e:
        print(f"Error: Could not save config. {e}"); sys.exit(1)

def load_admin_llm():
    """Loads the base LLM for the admin agent's tasks."""
    global ADMIN_MODEL, ADMIN_TOKENIZER
    if ADMIN_MODEL is not None: return

    print(f"--- Loading Admin Agent LLM ({ADMIN_AGENT_BASE_MODEL_ID}) ---")
    print("This may take a moment...")
    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

    quantization_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=compute_dtype, bnb_4bit_use_double_quant=False,)
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[LLM Inference] Using device: {device}")
    attn_implementation = "sdpa"
    try:
        ADMIN_TOKENIZER = AutoTokenizer.from_pretrained(ADMIN_AGENT_BASE_MODEL_ID)
        ADMIN_MODEL = AutoModelForCausalLM.from_pretrained(
            ADMIN_AGENT_BASE_MODEL_ID,
            device_map=device,
            quantization_config=quantization_config,
            attn_implementation=attn_implementation,
            torch_dtype=compute_dtype
        )
        print("--- LLM Loaded Successfully ---")
    except Exception as e:
        print(f"FATAL: Could not load the language model. Error: {e}"); sys.exit(1)

def generate_prompt_from_description(persona_description: str) -> str:
    """Uses the LLM to generate a structured system prompt."""
    load_admin_llm()
    system_prompt = """You are an expert Prompt Engineer. Your task is to create a high-quality, structured system prompt for a new AI agent based on a user's description.
The system prompt you generate MUST follow this structure:
1.  **Introduction:** A clear, one-sentence declaration of the agent's name and primary purpose.
2.  **Capabilities:** A bulleted list detailing what the agent CAN and SHOULD do.
3.  **Constraints:** A bulleted list detailing what the agent CANNOT or MUST NOT do.
4.  **Output Formatting (Optional):** Define any specific output formatting rules.

Now, based on the following user description, generate the complete system prompt for the new agent."""
    user_request = f"User's description of the new agent: '{persona_description}'"
    full_prompt_for_llm = f"{system_prompt}\n\n{user_request}\n\nGenerated System Prompt:"
    
    print("\n>>> Generating structured prompt... Please wait.")
    
    inputs = ADMIN_TOKENIZER(full_prompt_for_llm, return_tensors="pt").to(ADMIN_MODEL.device)
    outputs = ADMIN_MODEL.generate(**inputs, max_new_tokens=1024, temperature=0.7, do_sample=True)
    response = ADMIN_TOKENIZER.decode(outputs[0][len(inputs.input_ids[0]):], skip_special_tokens=True)
    return response.strip()

def handle_config_show(args):
    """Shows the current configuration."""
    config = load_config()
    print("--- Current config.yaml ---")
    print(yaml.dump(config, default_flow_style=False, sort_keys=False))

def handle_config_set_base_model(args):
    """Sets the base model in the configuration."""
    config = load_config()
    old_model = config.get('base_model', 'N/A')
    config['base_model'] = args.model_id
    save_config(config)
    print(f"Base model changed from '{old_model}' to '{args.model_id}'.")
    print("NOTE: You may need to re-train your adapters with this new base model.")

def handle_agents_list(args):
    """Lists all configured agents."""
    config = load_config()
    agents = config.get('agents', {})
    if not agents:
        print("No agents found in the configuration.")
        return
    print("--- Configured Agents ---")
    for name, details in agents.items():
        desc = details.get('description', 'No description.')
        print(f"- {name}: {desc}")

def handle_agents_create(args):
    """Creates a new agent entry in the config and an empty prompt file."""
    agent_name = args.name.lower().replace(" ", "_")
    print(f"Creating new agent scaffolding: '{agent_name}'")
    
    config = load_config()
    if agent_name in config.get('agents', {}):
        print(f"Error: An agent with the name '{agent_name}' already exists.")
        return

    description = input("Enter a short description for the agent: ")
    prompt_filename = f"{agent_name}.txt"
    prompt_filepath_relative = f"configs/prompts/{prompt_filename}"
    prompt_filepath_absolute = os.path.join(PROMPTS_DIR, prompt_filename)

    if not os.path.exists(prompt_filepath_absolute):
        open(prompt_filepath_absolute, 'a').close()
        print(f"✅ Empty prompt file created at {prompt_filepath_absolute}")
    
    if 'agents' not in config: config['agents'] = {}
    
    config['agents'][agent_name] = {
        'description': description,
        'prompt_file': prompt_filepath_relative,
        'model_path': f"models/{agent_name}_agent",
        'tools_whitelist': []
    }
    save_config(config)
    print(f"\nAgent '{agent_name}' added to config.yaml.")
    print("Next, use the 'agents create-prompt' command to generate its system prompt.")

def handle_agents_create_prompt(args):
    """Interactively creates the prompt content for an existing agent."""
    agent_name = args.name
    config = load_config()
    if agent_name not in config.get('agents', {}):
        print(f"Error: Agent '{agent_name}' not found in config.yaml.")
        print("Please create the agent first using 'agents create'.")
        return

    print(f"--- Generating prompt for agent: '{agent_name}' ---")
    persona_desc = input(f"\nDescribe the '{agent_name}' agent's persona and main goal in one or two sentences:\n> ")
    if not persona_desc:
        print("Error: Description cannot be empty."); return

    generated_prompt = generate_prompt_from_description(persona_desc)
    
    prompt_filepath_absolute = os.path.join(os.path.dirname(__file__), config['agents'][agent_name]['prompt_file'])

    while True:
        print("\n--- Generated System Prompt ---\n")
        print(generated_prompt)
        print("\n-------------------------------\n")
        action = input("Save this prompt, (r)egenerate, or (q)uit? [S/r/q]: ").lower()

        if action == 'r':
            generated_prompt = generate_prompt_from_description(persona_desc)
        elif action == 'q':
            print("Quitting without saving."); return
        else:
            try:
                with open("." + prompt_filepath_absolute, 'w', encoding='utf-8') as f:
                    f.write(generated_prompt)
                print(f"\n✅ Prompt successfully saved to {prompt_filepath_absolute}")
                return
            except Exception as e:
                print(f"Error saving file: {e}"); return
            
def handle_agents_delete(args):
    """Deletes an agent."""
    agent_name = args.name
    print(f"Attempting to delete agent: '{agent_name}'")
    
    config = load_config()
    agents = config.get('agents', {})
    
    if agent_name not in agents:
        print(f"Error: Agent '{agent_name}' not found.")
        return

    confirm = input(f"Are you sure you want to delete the agent '{agent_name}' and its prompt file? [y/N]: ")
    if confirm.lower() != 'y':
        print("Deletion cancelled.")
        return

    prompt_file_path = agents[agent_name].get('prompt_file')
    if prompt_file_path:
        prompt_filepath_absolute = os.path.join(os.path.dirname(__file__), prompt_file_path)
        if os.path.exists(prompt_filepath_absolute):
            os.remove(prompt_filepath_absolute)
            print(f"✅ Deleted prompt file: {prompt_filepath_absolute}")

    del config['agents'][agent_name]
    save_config(config)
    print(f"Agent '{agent_name}' removed from configuration.")

def handle_train_run(args):
    """Runs the training script for a specific agent or the router."""
    target = args.target
    config = load_config()
    base_model = config.get('base_model')

    if not base_model:
        print("Error: `base_model` not set in config.yaml. Please set it using `python manage_agent.py config set-base-model ...`")
        return

    print(f"--- Starting training for '{target}' ---")
    
    if target == 'router':
        dataset_path = 'data/agents/router_sft_data.jsonl'
        output_dir = 'models/router'
        is_chat_format = False
    elif target in config.get('agents', {}):
        dataset_path = f'data/agents/{target}_sft_data.jsonl'
        output_dir = f'models/{target}_agent'
        is_chat_format = True
    else:
        print(f"Error: Target '{target}' is not a valid agent or 'router'.")
        return
        
    if not os.path.exists(dataset_path):
        print(f"Error: Training dataset not found at '{dataset_path}'. Please create it first.")
        return

    command = [
        sys.executable,
        TRAINING_SCRIPT_PATH,
        '--model_id', base_model,
        '--dataset_path', dataset_path,
        '--output_dir', output_dir,
        '--epochs', str(args.epochs),
        '--batch_size', str(args.batch_size),
        '--learning_rate', str(args.learning_rate)
    ]
    if is_chat_format:
        command.append('--is_chat_format')

    print("\nExecuting command:")
    print(" ".join(command) + "\n")
    
    try:
        subprocess.run(command, check=True)
        print(f"\n✅ Training for '{target}' completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Training for '{target}' failed with exit code {e.returncode}.")

def handle_train_dpo(args):
    """Runs the DPO training script for a specific agent."""
    target_agent = args.target
    config = load_config()
    
    if target_agent not in config.get('agents', {}):
        print(f"Error: Target agent '{target_agent}' is not a valid agent.")
        return

    print(f"--- Starting DPO training for agent '{target_agent}' ---")
    
    sft_model_path = config['agents'][target_agent].get('model_path')
    if not os.path.isdir(sft_model_path):
        print(f"Error: SFT-tuned model not found at '{sft_model_path}'.")
        print(f"Please run 'train run {target_agent}' first to create a base SFT model.")
        return
        
    dataset_path = args.dataset_path or f'data/{target_agent}_dpo_data.jsonl'
    if not os.path.exists(dataset_path):
        print(f"Error: DPO preference dataset not found at '{dataset_path}'.")
        print("Please run the Django 'export_feedback_data' command first.")
        return
        
    output_dir = f"{sft_model_path}"
    
    command = [
        sys.executable,
        DPO_TRAINING_SCRIPT_PATH,
        '--model_id', sft_model_path,
        '--dataset_path', dataset_path,
        '--output_dir', output_dir,
        '--epochs', str(args.epochs),
        '--batch_size', str(args.batch_size),
        '--learning_rate', str(args.learning_rate)
    ]

    print("\nExecuting command:")
    print(" ".join(command) + "\n")
    
    try:
        subprocess.run(command, check=True)
        print(f"\n✅ DPO training for '{target_agent}' completed successfully.")
        print(f"New adapters saved to '{output_dir}'.")
        print(f"To use them, update 'model_path' for '{target_agent}' in config.yaml to point to this new directory.")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ DPO training for '{target_agent}' failed with exit code {e.returncode}.")


def main():
    parser = argparse.ArgumentParser(description="Admin CLI for the Gemma Multi-Agent System.")
    subparsers = parser.add_subparsers(dest='command', required=True, help='Main command')


    parser_config = subparsers.add_parser('config', help='Manage config.yaml')
    config_subparsers = parser_config.add_subparsers(dest='subcommand', required=True)
    
    config_subparsers.add_parser('show', help='Show current config').set_defaults(func=handle_config_show)
    
    parser_set_model = config_subparsers.add_parser('set-base-model', help='Set the base model ID')
    parser_set_model.add_argument('model_id', type=str, help='e.g., google/gemma-2-9b-it')
    parser_set_model.set_defaults(func=handle_config_set_base_model)


    parser_agents = subparsers.add_parser('agents', help='Manage agents')
    agents_subparsers = parser_agents.add_subparsers(dest='subcommand', required=True)
    
    agents_subparsers.add_parser('list', help='List all agents').set_defaults(func=handle_agents_list)
    
    parser_create_agent = agents_subparsers.add_parser('create', help='Create agent scaffolding (config entry and empty prompt file)')
    parser_create_agent.add_argument('name', type=str, help='Name of the new agent')
    parser_create_agent.set_defaults(func=handle_agents_create)

    parser_create_prompt = agents_subparsers.add_parser('create-prompt', help='Use AI to generate the prompt content for an agent')
    parser_create_prompt.add_argument('name', type=str, help='Name of the agent whose prompt you want to create')
    parser_create_prompt.set_defaults(func=handle_agents_create_prompt)

    parser_delete_agent = agents_subparsers.add_parser('delete', help='Delete an existing agent')
    parser_delete_agent.add_argument('name', type=str, help='Name of the agent to delete')
    parser_delete_agent.set_defaults(func=handle_agents_delete)

    parser_train = subparsers.add_parser('train', help='Train models using SFT or DPO')
    train_subparsers = parser_train.add_subparsers(dest='subcommand', required=True)

    parser_run_sft = train_subparsers.add_parser('run', help='Run a Supervised Fine-Tuning (SFT) job')
    parser_run_sft.add_argument('target', type=str, help="The agent name to train, or 'router'")
    parser_run_sft.add_argument('--epochs', type=int, default=1, help='Number of training epochs')
    parser_run_sft.add_argument('--batch_size', type=int, default=1, help='Training batch size')
    parser_run_sft.add_argument('--learning_rate', type=float, default=5e-5, help='Learning rate')
    parser_run_sft.set_defaults(func=handle_train_run)
    
    parser_run_dpo = train_subparsers.add_parser('dpo', help='Run a Direct Preference Optimization (DPO) job on an existing agent')
    parser_run_dpo.add_argument('target', type=str, help="The agent name to refine with DPO")
    parser_run_dpo.add_argument('--dataset_path', type=str, help="(Optional) Path to the preference dataset. Defaults to data/<target>_dpo_data.jsonl")
    parser_run_dpo.add_argument('--epochs', type=int, default=1, help='Number of training epochs')
    parser_run_dpo.add_argument('--batch_size', type=int, default=1, help='Training batch size')
    parser_run_dpo.add_argument('--learning_rate', type=float, default=1e-5, help='DPO learning rate')
    parser_run_dpo.set_defaults(func=handle_train_dpo)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()