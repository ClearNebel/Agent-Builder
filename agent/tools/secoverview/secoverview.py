import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

class Secoverview:
    secoverview_endpoint = os.getenv("SECOVERVIEW_ENDPOINT", "https://localhost")
    username = os.getenv("SECOVERVIEW_USERNAME", "username")
    password = os.getenv("SECOVERVIEW_PASSWORD", "password")
    update_cycle = int(os.getenv("SECOVERVIEW_PASSWORD_UPDATE_CYCLE", 23))
    access_token = None
    refresh_token = None
    last_token_update = None
    
    @property
    def headers(self):
        if self.access_token != None:
            return {"Authorization": f"Bearer {self.access_token}"}
        else:
            print("Warning: Access token is not set. Returning empty headers.")
            return None

    @staticmethod
    def _execute_before_task(pre_execution_method_name_str):
        """
        A decorator factory. Returns a decorator that will execute
        a specified instance method before the decorated method.
        """
        def decorator(target_method_func):
            """The actual decorator."""
            def wrapper(instance_self, *args, **kwargs):
                # 'instance_self' is the instance of MyTaskExecutor
                # Get the pre-execution method from the instance
                pre_exec_method = getattr(instance_self, pre_execution_method_name_str)

                print(f"--- Decorator in class: Calling '{pre_execution_method_name_str}' before '{target_method_func.__name__}' ---")
                pre_exec_method()  # Call the pre-execution method on the instance

                # Call the original target method
                result = target_method_func(instance_self, *args, **kwargs)
                return result
            return wrapper
        return decorator

    def _get_token(self):
        CREDENTIALS = {
            "username": self.username,
            "password": self.password
        }
        print(CREDENTIALS)
        response = self._post_request(urlendpoint="/api/token", json=CREDENTIALS, headers=False)
        if response.status_code == 200:
            tokens = response.json()
            print(tokens)
            self.access_token = tokens.get("access")
            self.refresh_token = tokens.get("refresh")
            self.last_token_update = datetime.now()
            print()
        else:
            print("Failed to get Secoverview token")
    
    def _refresh_access_token(self):
        REFRESH_DATA = {
            'refresh': self.refresh_token,
        }
        response = self._post_request(urlendpoint="/api/token/refresh", data=REFRESH_DATA, headers=False)
        if response.status_code == 200:
            tokens = response.json()
            self.access_token = tokens.get("access")
            self.last_token_update = datetime.now()
        else:
            print("Failed to Secoverview refresh access token.")

    def _token_validation(self):
        if datetime.now() - self.last_token_update > timedelta(hours=self.update_cycle) or self.access_token is None and self.refresh_token is not None:
            self._refresh_access_token()
            return True
        elif self.last_token_update == None or self.access_token == None or self.refresh_token == None:
            self._get_token()
            return True
        else:
            return True

    def _post_request(self, urlendpoint: str = "/", data=None, json=None, headers=True, timeout=30, verify=False):
        headers_set = self.headers if headers == True else None
        url = self.secoverview_endpoint + urlendpoint
        return requests.post(url=url, data=data, json=json, headers=headers_set, timeout=timeout, verify=verify)
    
    def _get_request(self, urlendpoint: str = "/", data=None, json=None, headers=True, timeout=30, verify=False):
        headers_set = self.headers if headers == True else None
        url = self.secoverview_endpoint + urlendpoint
        return requests.get(url=url, data=data, json=json, headers=headers_set, timeout=timeout, verify=verify)

    #@_execute_before_task('_token_validation')
    def nmap_scan(self, target: str, parameters: str = "-sV -T4") -> str:
        data = {"ip": target, "parameters": parameters}
        response = self._post_request(urlendpoint="/api/nmap/scan", data=data, timeout=300)
        return response.json()
    
    #@_execute_before_task('_token_validation')
    def get_crtsh_securityheaders_webtechfingerprinting(self, domain: str) -> str:
        response = self._get_request(urlendpoint=f"/api/web/all/get?q={domain}", timeout=300)
        return response.json()
    
    #@_execute_before_task('_token_validation')
    def get_ipinformation_reputation(self, ip: str) -> str:
        response = self._get_request(urlendpoint=f"/api/ipcheck/check?q={ip}", timeout=300)
        return response.json()


    def __init__(self):
        self._get_token()

