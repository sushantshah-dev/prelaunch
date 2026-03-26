from config import (
    FREE_PERSONAS_PER_TEST,
    PRO_PERSONAS_PER_TEST,
    STARTER_PERSONAS_PER_TEST,
)


PERSONA_SCHEMA = {
    "id": "Stable persona identifier",
    "display_name": "Human-readable persona name",
    "age_band": "Age range such as 18-24 or 35-44",
    "gender": "Self-described gender or gender context",
    "income_band": "Income or budget sensitivity band",
    "occupation": "Role or job title",
    "location_context": "Geography or market context",
    "household_context": "Family, dependents, living situation, or solo status",
    "lifecycle_stage": "Career or life stage relevant to buying behavior",
    "psychographic_traits": "Short list of beliefs, motivations, and anxieties",
    "behavioral_patterns": "How this person discovers, compares, and buys tools",
    "current_workaround": "What they do today instead",
    "pain_points": "Concrete frustrations tied to the problem",
    "budget_posture": "How they think about spend and ROI",
    "adoption_barriers": "What would make them say no",
}

PERSONA_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema":{
        "name": "personas",
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "A stable identifier for the persona, such as 'budget-conscious-millennial-freelancer'."},
                    "display_name": {"type": "string", "description": "A human-readable name for the persona, such as 'Budget-Conscious Millennial Freelancer'."},
                    "age_band": {"type": "string", "description": "The age range of the persona, such as '25-34'."},
                    "gender": {"type": "string", "description": "The self-described gender or gender context of the persona, such as 'female' or 'non-binary'."},
                    "income_band": {"type": "string", "description": "The income or budget sensitivity band of the persona, such as 'low-income' or 'budget-conscious'."},
                    "occupation": {"type": "string", "description": "The role or job title of the persona, such as 'freelance graphic designer'."},
                    "location_context": {"type": "string", "description": "The geography or market context of the persona, such as 'urban US' or 'Southeast Asia'."},
                    "household_context": {"type": "string", "description": "The family, dependents, living situation, or solo status of the persona, such as 'lives alone' or 'has two children'."},
                    "lifecycle_stage": {"type": "string", "description": "The career or life stage relevant to buying behavior of the persona, such as 'early career' or 'established professional'."},
                    "psychographic_traits": {"type": "string", "description": "A short list of beliefs, motivations, and anxieties of the persona, such as 'values affordability, motivated by desire to grow freelance business, anxious about overspending on tools'."},
                    "behavioral_patterns": {"type": "string", "description": "How this persona discovers, compares, and buys tools, such as 'follows influencers on social media, reads online reviews, prefers free trials'."},
                    "current_workaround": {"type": "string", "description": "What the persona currently does instead of using the product, such as 'uses a combination of free tools and manual workarounds'."},
                    "pain_points": {"type": "string", "description": "Concrete frustrations tied to the problem the product aims to solve, such as 'spends too much time switching between tools, struggles to find affordable options'."},
                    "budget_posture": {"type": "string", "description": "How the persona thinks about spend and ROI, such as 'wants to see clear value before paying, prefers monthly subscriptions to annual commitments'."},
                    "adoption_barriers": {"type": "string", "description": "What would make the persona say no to the product, such as 'concerned about learning curve, worried about hidden costs'."},
                },
                "required": ["id", "display_name", "age_band", "gender", "income_band", "occupation", "location_context", "household_context", "lifecycle_stage", "psychographic_traits", "behavioral_patterns", "current_workaround", "pain_points", "budget_posture", "adoption_barriers"],
            }
        }
    }
}

PERSONA_QUESTIONNAIRE = [
    "What do you think this product does after one read?",
    "Who do you think this is for?",
    "What problem does it seem to solve?",
    "What part feels most useful or compelling?",
    "What feels confusing, weak, or incomplete?",
    "What would make you trust this more?",
    "What risk or downside would hold you back?",
    "Would you try this or buy this? Why or why not?",
    "What price would feel reasonable?",
    "At what price would it feel too expensive?",
    "Does the value feel worth paying for right now?",
    "How would you describe this to someone else in one sentence?",
]

IDEA_EVALUATION_FIELDS = [
    "audience",
    "perception_cue",
    "trust_signal",
    "risk_signal",
    "signal_summary",
    "what_to_do_next",
    "focus_area",
]

IDEA_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema":{
        "name": "idea_evaluation",
        "schema": {
            "type": "object",
            "properties": {
                "perception_cue": {"type": "string", "description": "The specific aspect of the product that most strongly influences the persona's perception, such as 'affordability' or 'ease of use'."},
                "trust_signal": {"type": "string", "description": "The strongest signal that would increase the persona's trust in the product, such as 'positive reviews from similar users' or 'transparent pricing'."},
                "risk_signal": {"type": "string", "description": "The strongest signal that would increase the persona's perception of risk or downside, such as 'concern about data privacy' or 'fear of hidden costs'."},
                "signal_summary": {"type": "string", "description": "A concise summary of the key factors influencing the persona's perception and trust, such as 'sees value in features but worried about cost and learning curve'."},
                "what_to_do_next": {"type": "string", "description": "The most important next step to take based on this evaluation, such as 'clarify pricing structure' or 'highlight ease of use in marketing materials'."},
                "focus_area": {"type": "string", "description": "The single area that would have the biggest impact on improving the persona's perception and likelihood to buy, such as 'demonstrating clear ROI' or 'providing social proof from similar users'."},
            },
            "required": ["audience", "perception_cue", "trust_signal", "risk_signal", "signal_summary", "what_to_do_next", "focus_area"],
        }
    }
}

PERCEPTION_HIGHLIGHT_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema":{
        "name": "perception_highlights",
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "a short tag identifying the demographic trait, behavior, or other aspect of the persona that this highlight relates to, such as 'budget-conscious' or 'Founder, 24F'."},
                    "highlight": {"type": "string", "description": "The exact text from the persona's responses that is the most striking signal related to this tag."},
                },
                "required": ["tag", "highlight"],
            }
        }
    }
}

PERCEPTION_FIELDS = [
    "would_use_or_buy",
    "why_or_why_not",
    "expected_price",
    "too_expensive_price",
    "worth_it_assessment",
]

WORD_OF_MOUTH_FIELDS = [
    "persona_id",
    "received_message",
    "retold_gist",
    "clarity_shift",
    "novelty_shift",
    "trust_shift",
]

LIVE_SIGNAL_SOURCES = [
    "reddit",
    "x",
    "youtube",
    "tiktok",
    "search",
    "forums",
    "product_communities",
]

PIPELINE_STEPS = [
    "Identify the target audience from the prompt.",
    "Generate personas using the shared schema, varying by age, gender, income group, and adjacent context.",
    "Ask the questionnaire to each persona.",
    "Use persona responses to evaluate idea-level fields.",
    "Use buy/price/value answers to produce perception outputs.",
    "Scramble persona order and run a word-of-mouth chain with gist compression between hops.",
    "Use a tool-calling model to discover live signals across social and search surfaces.",
]


def persona_count_for_plan(plan):
    if plan == "Starter":
        return STARTER_PERSONAS_PER_TEST
    if plan == "Pro":
        return PRO_PERSONAS_PER_TEST
    return FREE_PERSONAS_PER_TEST


def pipeline_baseline_for_plan(plan):
    return {
        "persona_count_per_test": persona_count_for_plan(plan),
        "persona_schema": PERSONA_SCHEMA,
        "questionnaire": PERSONA_QUESTIONNAIRE,
        "idea_evaluation_fields": IDEA_EVALUATION_FIELDS,
        "perception_fields": PERCEPTION_FIELDS,
        "word_of_mouth_fields": WORD_OF_MOUTH_FIELDS,
        "live_signal_sources": LIVE_SIGNAL_SOURCES,
        "steps": PIPELINE_STEPS,
    }
