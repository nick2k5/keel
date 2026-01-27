"""Google Gemini service via Vertex AI."""
import logging
from typing import Optional, Dict, Any

import vertexai
from vertexai.generative_models import GenerativeModel, Tool, grounding
from config import config

logger = logging.getLogger(__name__)


class GeminiService:
    """Service for Google Gemini via Vertex AI."""

    def __init__(self):
        # Initialize Vertex AI
        vertexai.init(project=config.project_id, location=config.vertex_ai_region)
        self.model = GenerativeModel("gemini-2.0-flash-001")

        # Google Search grounding tool for research
        self.search_tool = Tool.from_google_search_retrieval(
            grounding.GoogleSearchRetrieval()
        )

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

    def research_company(self, company: str, domain: str = '', source: str = '') -> Dict[str, Any]:
        """Research a company using Google Search grounding.

        This uses Gemini with Google Search retrieval to gather information
        about a company, replacing the manual web scraping approach.

        Args:
            company: Company name
            domain: Company website domain (optional)
            source: Source hint like 'W26' for YC batch (optional)

        Returns:
            Dict with 'content' (research text) and 'sources' (list of URLs)
        """
        logger.info(f"Researching {company} ({domain or 'no domain'}) with Gemini Grounding")

        # Build context for the search
        context_parts = [f"Research the company {company}"]
        if domain:
            context_parts.append(f"(website: {domain})")
        if source and source.upper().startswith(('W', 'S')):
            context_parts.append(f"- this is a Y Combinator {source} batch company")

        prompt = f"""{' '.join(context_parts)}

Find comprehensive information about this company for investment due diligence:

1. **Company Overview**
   - What they do (product, service, technology)
   - Business model
   - Founded date and location

2. **Founders & Team**
   - Founder names and backgrounds
   - Education and prior companies
   - LinkedIn profiles if available

3. **Funding & Investors**
   - Total funding raised
   - Funding rounds with dates and amounts
   - Notable investors

4. **Traction & Metrics**
   - Revenue or ARR if available
   - User/customer numbers
   - Growth rates
   - Notable customers or partnerships

5. **Market & Competition**
   - Industry/sector
   - Main competitors
   - Market positioning

6. **Recent News**
   - Latest announcements
   - Press coverage
   - Product launches

Be thorough and cite your sources. Include URLs where possible."""

        try:
            response = self.model.generate_content(
                prompt,
                tools=[self.search_tool],
                generation_config={
                    "max_output_tokens": 4096,
                    "temperature": 0.2,
                }
            )

            content = response.text.strip()

            # Extract grounding metadata if available
            sources = []
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    metadata = candidate.grounding_metadata
                    if hasattr(metadata, 'grounding_chunks'):
                        for chunk in metadata.grounding_chunks:
                            if hasattr(chunk, 'web') and chunk.web:
                                sources.append({
                                    'url': chunk.web.uri,
                                    'title': chunk.web.title if hasattr(chunk.web, 'title') else ''
                                })

            logger.info(f"Research complete for {company}: {len(content)} chars, {len(sources)} sources")

            return {
                'company': company,
                'domain': domain,
                'source': source,
                'content': content,
                'sources': sources
            }

        except Exception as e:
            logger.error(f"Error researching company with Gemini: {e}", exc_info=True)
            return {
                'company': company,
                'domain': domain,
                'source': source,
                'content': '',
                'sources': [],
                'error': str(e)
            }

    def format_research_context(self, research: Dict[str, Any],
                                yc_data: Dict[str, Any] = None,
                                relationship_data: Dict[str, Any] = None) -> str:
        """Format research data into context string for memo generation.

        Args:
            research: Research data from research_company()
            yc_data: Optional YC company data from Bookface
            relationship_data: Optional relationship data from forwarded emails

        Returns:
            Formatted context string
        """
        parts = []

        company = research.get('company', 'Unknown')
        domain = research.get('domain', 'no website')
        source = research.get('source', '')

        # Header
        header = f"=== RESEARCH DATA FOR {company} ({domain}) ==="
        if source:
            header += f"\nSource: {source}"
            if source.upper().startswith(('W', 'S')) and len(source) <= 4:
                header += " (Y Combinator batch)"
        parts.append(header + "\n")

        # Relationship data (highest priority - personal context)
        if relationship_data:
            parts.append("\n=== RELATIONSHIP HISTORY ===")

            if relationship_data.get('introducer'):
                intro = relationship_data['introducer']
                parts.append(f"\n**Introducer:** {intro.get('name', 'Unknown')}")
                if intro.get('email'):
                    parts.append(f"  Email: {intro['email']}")
                if intro.get('context'):
                    parts.append(f"  Context: {intro['context']}")

            if relationship_data.get('contacts'):
                parts.append("\n**Key Contacts:**")
                for contact in relationship_data['contacts']:
                    info = f"- {contact.get('name', 'Unknown')}"
                    if contact.get('email'):
                        info += f" ({contact['email']})"
                    if contact.get('role'):
                        info += f" - {contact['role']}"
                    parts.append(info)

            if relationship_data.get('summary'):
                parts.append(f"\n**Relationship Summary:**\n{relationship_data['summary']}")

        # YC Bookface data
        if yc_data:
            if yc_data.get('founders'):
                parts.append("\n=== YC FOUNDERS ===")
                for founder in yc_data['founders']:
                    info = f"- {founder.get('name', 'Unknown')}"
                    if founder.get('email'):
                        info += f" ({founder['email']})"
                    parts.append(info)

            if yc_data.get('posts'):
                parts.append("\n=== YC BOOKFACE POSTS ===")
                for i, post in enumerate(yc_data['posts'][:3]):
                    if post.get('title'):
                        parts.append(f"\n**Post {i+1}: {post['title']}**")
                    if post.get('body'):
                        parts.append(post['body'][:1500])

        # Main research content
        content = research.get('content', '')
        if content:
            parts.append("\n=== RESEARCH FINDINGS ===")
            parts.append(content)

        # Sources
        sources = research.get('sources', [])
        if sources:
            parts.append("\n=== SOURCES ===")
            for i, src in enumerate(sources[:15], 1):
                if isinstance(src, dict):
                    url = src.get('url', '')
                    title = src.get('title', url)
                    parts.append(f"{i}. [{title}]({url})")
                else:
                    parts.append(f"{i}. {src}")

        # Error handling
        if research.get('error'):
            parts.append(f"\n=== RESEARCH ERROR ===")
            parts.append(f"Error: {research['error']}")

        return '\n'.join(parts)
