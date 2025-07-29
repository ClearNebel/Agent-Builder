# tools/basic_tools.py
import datetime
from .secoverview.secoverview import Secoverview

try:
    secoverview = Secoverview()
except:
    secoverview = None


def get_current_date() -> str:
    """Returns the current date in YYYY-MM-DD format."""
    return datetime.datetime.now().strftime("%Y-%m-%d")

def calculate_simple_interest(principal: float, rate: float, time: float) -> float:
    """
    Calculates simple interest.
    :param principal: The initial amount of money.
    :param rate: The annual interest rate as a decimal (e.g., 0.05 for 5%).
    :param time: The time period in years.
    """
    return principal * rate * time

def nmap_scan(target: str, parameters: str = "-sV -T4"):
    """
    Creates simple nmap scan.
    :param target: IP/IP-Range of Scan Target.
    :param parameters: NMAP Scan parameters.
    """
    return str(secoverview.nmap_scan(target=target, parameters=parameters))

def get_crtsh_securityheaders_webtechfingerprinting(domain: str):
    """
    Get crtsh infos, scurityheaders info, web tech fingerprinting.
    :param domain: Target Domain.
    """
    return str(secoverview.get_crtsh_securityheaders_webtechfingerprinting(domain=domain))

def get_ipinformation_reputation(ip: str):
    """
    Get IP BGP info, AbuseIPDB and MISP information.
    :param ip: Target Domain.
    """
    return str(secoverview.get_ipinformation_reputation(ip=ip))