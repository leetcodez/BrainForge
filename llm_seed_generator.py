import logging
import os
import time
import json
import google.generativeai as genai
import config
from typing import List, Dict

logger = logging.getLogger(__name__)

class LLMSeedGenerator:
    def __init__(self):
        self.model_name = config.LLM_MODEL
        genai.configure(api_key=config.GEMINI_API_KEY)

        self.base_prompt = (
            "You are a world-class quantitative analyst creating alphas for WorldQuant Brain using FastExpr. "
            "Your output must ONLY be a raw JSON array of strings, where each string is a distinct FastExpr mathematical formula template. "
            "Use {FIELD}, {LOOKBACK_SHORT}, and {LOOKBACK_LONG} placeholders. "
            "Focus on generating structural diversity (momentum, volatility-adjusted mean-reversion, statistical arbitrage). "
            "Available Operators: ts_mean, ts_rank, ts_std_dev, ts_zscore, ts_decay_linear, ts_sum, ts_product, rank, zscore. "
            "Do NOT use group operators like group_neutralize; they will be applied automatically by the orchestrator. "
            "Ensure the formulas are syntactically valid and mathematically sound."
        )

        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=self.base_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.8,
                response_mime_type="application/json"
            )
        )

    def generate_seed_alphas(self, count: int, experience_memory: List[str] = None) -> List[str]:
        prompt = f"Generate an array of {count} highly distinct FastExpr templates. Return STRICTLY a JSON list of strings."

        if experience_memory:
            prompt += "\n\nCRITICAL EXPERIENCE MEMORY:\n"
            for thought in experience_memory[-10:]:
                prompt += f"- {thought}\n"
            prompt += "\nDo NOT generate structures that resemble the specific failures listed above. Pivot to uncorrelated mathematical anomalies."

        for attempt in range(3):
            try:
                logger.info(f"Requesting bulk batch of {count} templates from Gemini (Attempt {attempt+1}/3)...")
                response = self.model.generate_content(prompt)

                if response.text:
                    raw_text = response.text.strip()
                    try:
                        seeds = json.loads(raw_text)
                        if isinstance(seeds, list):
                            logger.info(f"Successfully generated {len(seeds)} templates.")
                            time.sleep(4.5) 
                            return seeds
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON response: {e}")

            except Exception as e:
                logger.error(f"Gemini Generation failed: {e}")
                if "429" in str(e) or "Quota exceeded" in str(e):
                    logger.warning("Rate limit hit. Applying exponential backoff (30 seconds)...")
                    time.sleep(30)
                else:
                    time.sleep(5)

        logger.warning("Failed to generate seeds from LLM after 3 attempts.")
        return []