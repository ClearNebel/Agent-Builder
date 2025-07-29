import requests 
import json
import re
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple

SEARXNG_INSTANCE_URL = "http://localhost:8080"

# Usage:
# self.searcher = SearxNGSearcher(SEARXNG_INSTANCE_URL)
# self.content_fetcher = BasicWebContentFetcher()

class SearxNGSearcher():
    def __init__(self, instance_url: str):
        self.base_url = instance_url.rstrip('/')
        if not self.base_url.startswith(("http://", "https://")):
            self.base_url = "http://" + self.base_url

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        params = {"time_range": "month", "q": query, "format": "json"}
        search_results = []
        try:
            # print(f"SearxNG: Searching for '{query}'") # Debug
            response = requests.get(f"{self.base_url}/search", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            for item in data.get("results", []):
                if len(search_results) < num_results:
                    if item.get("url") and item.get("title"):
                        if not any(item['url'].lower().endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.ppt']):
                            search_results.append({
                                "title": item["title"],
                                "url": item["url"],
                                "publishedDate": item.get("publishedDate")
                            })
                else:
                    break
        except requests.RequestException as e:
            print(f"Error searching with SearxNG for '{query}': {e}")
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from SearxNG for '{query}': {e}")
        return search_results

class BasicWebContentFetcher():
    def fetch_text(self, url: str) -> Optional[str]:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        try:
            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            response.raise_for_status()
            if 'text/html' not in response.headers.get('Content-Type', '').lower():
                # print(f"Skipping non-HTML content at {url}") # Debug
                return None
            soup = BeautifulSoup(response.content, 'html.parser')
            article_body = soup.find('article') or soup.find('main') or \
                           soup.find(class_=re.compile(r'(article|post|content|entry|main|body)')) or \
                           soup.find(id=re.compile(r'(article|post|content|entry|main|body)'))
            text_elements = (article_body.find_all(['p', 'h1', 'h2', 'h3', 'li'])
                             if article_body else soup.find_all('p'))
            text_content = "\n".join(element.get_text(separator=' ', strip=True) for element in text_elements)
            text_content = re.sub(r'\s{2,}', ' ', text_content)
            text_content = re.sub(r'\n{2,}', '\n', text_content)
            return text_content if len(text_content) > 100 else None
        except requests.RequestException as e:
            print(f"Error fetching URL {url}: {e}")
        except Exception as e:
            print(f"Error parsing content from {url}: {e}")
        return None


