from dataclasses import dataclass


@dataclass
class OllamaConfig:
    host: str = "http://localhost:11434"
    model: str = "llama3.2:3b"
    timeout_seconds: float = 300.0

    def __post_init__(self):
        if not self.host or not self.host.strip():
            raise ValueError("Host cannot be empty")
        if not self.model or not self.model.strip():
            raise ValueError("Model cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("Timeout must be > 0")

        # Normalize host to not have a trailing slash
        self.host = self.host.rstrip("/")
