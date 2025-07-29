# tools/tool_registry.py
from tools.basic_tools import get_current_date, calculate_simple_interest, nmap_scan, get_crtsh_securityheaders_webtechfingerprinting, get_ipinformation_reputation, secoverview
from rag.rag_handler import query_knowledge_base

# The master dictionary of all available tools in the system
TOOL_REGISTRY = {
    "get_current_date": {
        "function": get_current_date,
        "schema": "get_current_date() -> str: Returns the current date in YYYY-MM-DD format."
    },
    "calculate_simple_interest": {
        "function": calculate_simple_interest,
        "schema": "calculate_simple_interest(principal: float, rate: float, time: float) -> float: Calculates simple interest."
    },
    "query_knowledge_base": {
        "function": query_knowledge_base,
        "schema": "query_knowledge_base(query: str) -> str: Searches the knowledge base for specific topics like 'Quantum Computing' or 'Photosynthesis'."
    },
}

if secoverview != None:
    TOOL_REGISTRY.update({     
        "nmap_scan": {
            "function": nmap_scan,
            "schema": "nmap_scan(target: str, parameters: str = '-sV -T4') -> str: Executes NMAP-Scan on Target with the Provided Scan parameters."
        },
        "get_crtsh_securityheaders_webtechfingerprinting": {
            "function": get_crtsh_securityheaders_webtechfingerprinting,
            "schema": "get_crtsh_securityheaders_webtechfingerprinting(domain: str) -> str: Get Crtsh infos, secuirtyheaders and web tech fingerprinting."
        },
        "get_ipinformation_reputation": {
            "function": get_ipinformation_reputation,
            "schema": "get_ipinformation_reputation(ip: str) -> str: Get IP BGP information, AbuseIPDB information and MISP information if available"
        },
    })