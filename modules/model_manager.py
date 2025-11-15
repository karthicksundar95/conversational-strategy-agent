import os
import json
import yaml
import requests
from pathlib import Path
from google import genai
from openai import OpenAI
from openai import APIError, AuthenticationError
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
MODELS_JSON = ROOT / "config" / "models.json"
PROFILE_YAML = ROOT / "config" / "profiles.yaml"

class ModelManager:
    def __init__(self):
        self.config = json.loads(MODELS_JSON.read_text())
        self.profile = yaml.safe_load(PROFILE_YAML.read_text())

        self.text_model_key = self.profile["llm"]["text_generation"]
        self.model_info = self.config["models"][self.text_model_key]
        self.model_type = self.model_info["type"]

        # ✅ Gemini initialization (your style)
        if self.model_type == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            self.client = genai.Client(api_key=api_key)
        
        # ✅ OpenAI initialization
        elif self.model_type == "openai":
            api_key_env = self.model_info.get("api_key_env", "OPENAI_API_KEY")
            api_key = os.getenv(api_key_env)
            if not api_key:
                raise ValueError(
                    f"❌ OpenAI API Key Missing: {api_key_env} environment variable not set. "
                    f"Please set it in your .env file or environment. "
                    f"Get your key at: https://platform.openai.com/account/api-keys"
                )
            self.client = OpenAI(api_key=api_key)

    async def generate_text(self, prompt: str) -> str:
        if self.model_type == "gemini":
            return self._gemini_generate(prompt)

        elif self.model_type == "ollama":
            return self._ollama_generate(prompt)
        
        elif self.model_type == "openai":
            return self._openai_generate(prompt)

        raise NotImplementedError(f"Unsupported model type: {self.model_type}")

    def _gemini_generate(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model_info["model"],
            contents=prompt
        )

        # ✅ Safely extract response text
        try:
            return response.text.strip()
        except AttributeError:
            try:
                return response.candidates[0].content.parts[0].text.strip()
            except Exception:
                return str(response)

    def _ollama_generate(self, prompt: str) -> str:
        response = requests.post(
            self.model_info["url"]["generate"],
            json={"model": self.model_info["model"], "prompt": prompt, "stream": False}
        )
        response.raise_for_status()
        return response.json()["response"].strip()

    def _openai_generate(self, prompt: str) -> str:
        """Generate text using OpenAI API."""
        temperature = self.model_info.get("temperature", 0.7)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_info["model"],
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature
            )
            
            # ✅ Safely extract response text
            try:
                return response.choices[0].message.content.strip()
            except (AttributeError, IndexError, KeyError) as e:
                # Fallback: try to get any available text from response
                try:
                    if response.choices and len(response.choices) > 0:
                        return str(response.choices[0])
                    return str(response)
                except Exception:
                    return f"[OpenAI Response Parse Error: {str(e)}]"
        
        except AuthenticationError as e:
            # API key is invalid or missing
            error_msg = str(e)
            if "api key" in error_msg.lower() or "401" in error_msg:
                raise ValueError(
                    f"❌ OpenAI API Key Error: Invalid or missing API key. "
                    f"Please check your OPENAI_API_KEY environment variable. "
                    f"Get your key at: https://platform.openai.com/account/api-keys"
                ) from e
            raise
        
        except APIError as e:
            # Other API errors (rate limits, server errors, etc.)
            error_msg = str(e)
            raise ValueError(
                f"❌ OpenAI API Error: {error_msg}. "
                f"Please check your API key and account status."
            ) from e
        
        except Exception as e:
            # Unexpected errors
            raise ValueError(
                f"❌ OpenAI Request Error: {str(e)}"
            ) from e
