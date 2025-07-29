import re

class SafetyDetector:
    def __init__(self, config):
        """
        Initializes the detector with rules from the config file.
        :param config: The 'safety' section of the config.yaml.
        """
        self.pii_config = config.get('force_local_on_pii', {})
        self.danger_config = config.get('block_on_dangerous_content', {})

        self.pii_patterns = []
        if self.pii_config.get('enabled', False):
            for item in self.pii_config.get('patterns', []):
                self.pii_patterns.append(re.compile(item['regex']))

        self.danger_keywords = []
        if self.danger_config.get('enabled', False):
            self.danger_keywords = [kw.lower() for kw in self.danger_config.get('keywords', [])]

    def contains_pii(self, text: str) -> bool:
        """Checks if the text contains any configured PII patterns."""
        if not self.pii_config.get('enabled', False):
            return False
        
        for pattern in self.pii_patterns:
            if re.search(pattern, text):
                return True
        return False

    def contains_dangerous_content(self, text: str) -> bool:
        """Checks if the text contains any configured dangerous keywords."""
        if not self.danger_config.get('enabled', False):
            return False
        
        lower_text = text.lower()
        for keyword in self.danger_keywords:
            if keyword in lower_text:
                return True
        return False