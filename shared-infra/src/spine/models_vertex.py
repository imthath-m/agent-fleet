"""Real Gemini-on-Vertex adapter implementing ``ModelClient``.

The ``google-genai`` SDK is imported lazily inside methods so the SDK-free
core (models.py, agent.py, fake client) never depends on it and tests run
without GCP credentials. Construct this only in an environment with Vertex AI
access; ``generate`` performs a live API call.
"""

from __future__ import annotations

from spine.models import DEFAULT_CONFIG, ModelConfig, ModelResponse


class VertexModelClient:
    """``ModelClient`` backed by Gemini on Vertex AI via ``google-genai``."""

    def __init__(
        self,
        *,
        project: str,
        location: str = "us-central1",
        config: ModelConfig = DEFAULT_CONFIG,
    ) -> None:
        self._project = project
        self._location = location
        self._config = config
        self._client = None  # created lazily on first use

    def _get_client(self):
        if self._client is None:
            # Lazy import: keeps the SDK optional for the core package.
            from google import genai

            self._client = genai.Client(
                vertexai=True,
                project=self._project,
                location=self._location,
            )
        return self._client

    def generate(self, prompt: str, **params: object) -> ModelResponse:
        from google.genai import types

        client = self._get_client()
        gen_config = types.GenerateContentConfig(
            temperature=float(params.get("temperature", self._config.temperature)),
            max_output_tokens=int(
                params.get("max_output_tokens", self._config.max_output_tokens)
            ),
        )
        result = client.models.generate_content(
            model=self._config.model,
            contents=prompt,
            config=gen_config,
        )

        usage = getattr(result, "usage_metadata", None)
        return ModelResponse(
            text=result.text or "",
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            model=self._config.model,
        )
