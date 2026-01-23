"""Google Gemini service via Vertex AI."""
import logging
from typing import Optional

import vertexai
from vertexai.generative_models import GenerativeModel
from config import config

logger = logging.getLogger(__name__)


class GeminiService:
    """Service for Google Gemini via Vertex AI."""

    def __init__(self):
        # Initialize Vertex AI
        vertexai.init(project=config.project_id, location=config.vertex_ai_region)
        self.model = GenerativeModel("gemini-2.0-flash-001")

    def generate_memo(self, company: str, domain: str, research_context: str = None, custom_prompt: Optional[str] = None) -> str:
        """Generate investment memo content using Gemini. Returns markdown text."""
        if custom_prompt:
            # Substitute placeholders in custom prompt
            prompt = custom_prompt.replace('{company}', company).replace('{domain}', domain)
            logger.info(f"Using custom prompt for {company}")
        else:
            # Build context section if research data is available
            context_section = ""
            if research_context:
                context_section = f"""
IMPORTANT: Use the following research data to write an accurate memo. This is real data gathered from the company's website, Google search results, and LinkedIn. Base your analysis on this information - do not make up facts.

{research_context}

---

"""

            prompt = f"""You are a research analyst. Compile a factual research brief on the company below. Do NOT provide opinions, assessments, or recommendations. Only include verified facts.

Company: {company}
Website: {domain if domain and domain != 'Unknown' else 'Not provided'}
{context_section}
IMPORTANT: If the research data above is limited or empty, use your training knowledge about this company to fill in factual information. Many companies have public information available - use what you know. Only state "Not found" if you genuinely have no information about a topic.

Create a factual research brief with the following structure:

# {company} — Research Brief

## Company Overview
- **What they do:** Clear, factual description of the product/service
- **Website:** {domain}
- **Founded:** Year and location (only if found in research)
- **Headquarters:** Location (only if found in research)
- **Company size:** Employee count or range (only if found in research)

## Founders & Team
For each founder/key executive found in the research data:
- **[Name]** - [Title]
  - Background: [Education, previous companies, roles - only verified facts]
  - LinkedIn: [Include URL if provided in research data]

List only people confirmed in the research data. Do not invent team members.

## Product & Service
- Factual description of what the product does
- Key features mentioned on website or in articles
- Target customers/users (if stated)
- Pricing information (if publicly available)

## Traction & Metrics
Only include metrics that are explicitly stated in the research:
- User counts, customer numbers, or revenue figures
- Growth statistics
- Named customers or partnerships
- Funding raised (amount, date, investors)

If no traction data is available, state "No public traction data found."

## Online Presence & Discussion
- Social media following (if found)
- Press coverage or articles (list sources)
- Product Hunt, Reddit, Hacker News, or forum discussions
- App store ratings/reviews (if applicable)

## Background & Context
- Company history and timeline
- Notable news or announcements
- Industry or sector classification
- Any publicly stated company mission or vision

## Additional Information
- Known investors or advisors
- Notable partnerships or integrations
- Awards or recognition
- Any other relevant factual information

---

CRITICAL INSTRUCTIONS:
- Output ONLY facts. Do NOT provide opinions, analysis, or recommendations.
- Do NOT discuss market size, TAM, or growth potential.
- Do NOT assess the company's prospects or give investment advice.
- Use the research data above FIRST, then supplement with your training knowledge about the company.
- Only state "Not found" if you have NO information from either source.
- Start directly with: # {company} — Research Brief
- Include LinkedIn URLs for founders when available.
- Use markdown formatting with headers, bullet points, and bold text.
- Cite sources where helpful (e.g., "According to TechCrunch...")."""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 8192,
                    "temperature": 0.3,
                }
            )

            content = response.text.strip()
            logger.info(f"Generated memo for {company} ({len(content)} chars)")
            return content

        except Exception as e:
            logger.error(f"Error generating memo with Gemini: {e}", exc_info=True)
            raise
