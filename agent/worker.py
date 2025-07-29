import os
import sys
import yaml
import json
import redis
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from providers.handler import get_chat_model, invoke_llm_with_history
import multiprocessing as mp
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from app.llm_inference import load_base_model_and_tokenizer
from app.router import route_request
from app.subagent_handler import handle_with_subagent, handle_with_subagent_stream
from app.llm_inference import generate_response, generate_response_stream
from safety.detector import SafetyDetector

print("--- [WORKER] Initializing ---")
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'configs/config.yaml')

with open(CONFIG_PATH, 'r') as f:
    CONFIG = yaml.safe_load(f)

MODEL = None
TOKENIZER = None
AGENTS_CONFIG = CONFIG.get('agents', {})
ALL_SYSTEM_AGENTS = list(AGENTS_CONFIG.keys())
SAFETY_DETECTOR = SafetyDetector(CONFIG.get('safety', {}))

def initialize_worker():
    """Loads the LLM model into the worker process's memory."""
    global MODEL, TOKENIZER
    if MODEL is None:
        worker_pid = os.getpid()
        print(f"--- [Worker PID: {worker_pid}] Loading model... ---")
        MODEL, TOKENIZER = load_base_model_and_tokenizer(CONFIG['base_model'])
        print(f"--- [Worker PID: {worker_pid}] Model loaded successfully. ---")

def process_job(job_data_str):
    """
    The main worker function, now capable of routing to local agents OR external providers.
    """
    job_data = json.loads(job_data_str)
    redis_pubsub_client = redis.Redis(decode_responses=True)
    print(f"[Worker] Processing job {job_data['job_id']}")
    
    user_query = job_data['user_query']
    chat_history_for_providers = job_data['chat_history_for_providers'] # A simple list of dicts
    chat_history_for_local = job_data['chat_history_for_local'] # A formatted string
    expert_settings = job_data['expert_settings']
    user_feature_flags = job_data.get('user_feature_flags', {})

    print(job_data['chat_history_for_local'])
    print(user_feature_flags)
    print(user_feature_flags.get('pii_force_local', False))
    print(SAFETY_DETECTOR.contains_pii(user_query))

    if user_feature_flags.get('block_dangerous_content', False) and SAFETY_DETECTOR.contains_dangerous_content(user_query):
        response = "This request has been blocked as it violates the content safety policy."
        display_name = "System Guardrail"
        return json.dumps({'status': 'complete', 'response': response, 'agent_name': display_name})

    selected_model_or_system = expert_settings.get('model_selection', 'local_system')
    
    if user_feature_flags.get('pii_force_local', False) and SAFETY_DETECTOR.contains_pii(user_query):
        print(f"[Worker Safety] PII detected in prompt for job {job_data['job_id']}. Forcing to local system.")
        selected_model_or_system = 'local_system'

    if selected_model_or_system == 'local_system':
        initialize_worker()
        worker_pid = os.getpid()
        print(f"--- [Worker PID: {worker_pid}] STARTING job {job_data['job_id']}. Re-using loaded model. ---")

        pubsub_channel = f"job_stream:{worker_pid}"
        user_query = job_data['user_query']
        user_available_agents = job_data['enabled_local_agents'] if not job_data['user_available_agents'] else job_data['user_available_agents']
        chat_history_context = list(job_data['chat_history_for_local'])
        expert_settings = job_data['expert_settings']

        generation_kwargs = {
            'temperature': expert_settings.get('temperature', 0.7),
            'top_p': expert_settings.get('top_p', 0.9)
        }

        router_adapter_path = os.path.join(PROJECT_ROOT, CONFIG['router']['model_path'])
        chosen_agent = route_request(MODEL, TOKENIZER, user_query, user_available_agents, router_adapter_path, **generation_kwargs)

        if chosen_agent and chosen_agent in user_available_agents:
            agent_config = AGENTS_CONFIG[chosen_agent]
            final_agent_config = {
                'prompt_file': os.path.join(PROJECT_ROOT, agent_config['prompt_file']),
                'model_path': os.path.join(PROJECT_ROOT, agent_config['model_path']),
                'tools_whitelist': agent_config.get('tools_whitelist', [])
            }
            response = handle_with_subagent(MODEL, TOKENIZER, agent_name=chosen_agent, user_query=user_query, prompt_history=chat_history_context, agent_config=final_agent_config, **generation_kwargs) # without streaming funcitonality use handle_with_subagent

            display_name = chosen_agent.capitalize()
        else:
            response = generate_response(MODEL, TOKENIZER, user_query=user_query, **generation_kwargs) # without streaming use generate_response
            display_name = "Assistant"
        
        print(f"[Worker PID: {worker_pid}] Finished job {job_data['job_id']}")

        #for token in response_stream:
        #        if token:
        #            response += token
        #            payload = json.dumps({'type': 'token', 'content': token})
        #            redis_pubsub_client.publish(pubsub_channel, payload)

    else:
        provider_name, provider_model_name = selected_model_or_system.split(':')
        provider_config = CONFIG['providers'][provider_name]
        model_details = next((m for m in provider_config['models'] if m['id'] == provider_model_name), None)
        
        if model_details:
            display_name = f"{provider_config['display_name']}: {model_details['display_name']}"
        else:
            display_name = f"{provider_name.capitalize()}: {provider_model_name}"
        print(f"[Worker] Calling LangChain provider: {display_name}")

        try:
            chat_model = get_chat_model(
                provider_name=provider_name,
                model_name=provider_model_name,
                temperature=job_data['expert_settings'].get('temperature', 0.7),
                top_p=job_data['expert_settings'].get('top_p', 0.9)
            )
            
            response = invoke_llm_with_history(
                chat_model=chat_model,
                prompt=job_data['user_query'],
                history=job_data['chat_history_for_providers']
            )
        except Exception as e:
            response = f"Error calling LangChain provider '{provider_name}': {e}"

    if user_feature_flags.get('block_dangerous_content', False) and SAFETY_DETECTOR.contains_dangerous_content(response):
        response = "The generated response was blocked as it was found to contain potentially harmful content."
        display_name = "System Guardrail"

    result = {
        'status': 'complete',
        'response': response,
        'agent_name': display_name
    }

    return json.dumps(result)



def main():
    try:
        mp.set_start_method("spawn", force=True)
        print("--- [Orchestrator] Multiprocessing start method set to 'spawn'. ---")
    except RuntimeError:
        pass

    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        db=int(os.getenv('REDIS_DB', 0)),
        password=os.getenv('REDIS_PASSWORD'), 
        decode_responses=True
    )
    try:
        redis_client.ping()
        print(f"--- [Orchestrator] Successfully connected to Redis at {redis_host}. ---")
    except redis.exceptions.ConnectionError as e:
        print(f"--- [Orchestrator] FATAL: Could not connect to Redis at {redis_host}. Error: {e}")
        sys.exit(1)

    NUM_WORKERS = int(os.getenv("NUM_WORKERS", 1))
    print(f"--- [Orchestrator] Starting worker pool with {NUM_WORKERS} workers. ---")

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        active_futures = {}

        print("--- [Orchestrator] Starting main processing loop... ---")
        
        while True:
            completed_job_ids = []
            for job_id, future in active_futures.items():
                if future.done():
                    try:
                        result_str = future.result()
                        redis_client.set(f"result:{job_id}", result_str, ex=300)
                        print(f"[Orchestrator] Job {job_id} completed successfully.")
                    except Exception as exc:
                        print(f"[Orchestrator] Job {job_id} failed with an exception: {exc}")
                        error_result = json.dumps({'status': 'error', 'response': str(exc)})
                        redis_client.set(f"result:{job_id}", error_result, ex=300)
                    
                    completed_job_ids.append(job_id)

            for job_id in completed_job_ids:
                del active_futures[job_id]

            if len(active_futures) < NUM_WORKERS:
                job_tuple_str = redis_client.lpop("job_queue")
                if job_tuple_str:
                    job_id, job_data_str = json.loads(job_tuple_str)
                    print(f"[Orchestrator] Submitting job {job_id} to worker pool.")
                    future = executor.submit(process_job, job_data_str)
                    active_futures[job_id] = future
            
            time.sleep(0.1)

if __name__ == "__main__":
    main()