"""Prompts for the sales-brief feature.

Prompts live in their own module, versioned, for the same reason SQL does not
live inside route handlers: they are a dependency you will change, and changes
need to be traceable. `PROMPT_VERSION` is stored on every `ai_runs` row, so a
drop in brief quality can be attributed to a specific edit rather than guessed
at.

What this prompt deliberately does NOT ask for: a score. Scoring is a
deterministic business rule that must stay explainable and reproducible. The
model is given the score as *context* so its narrative agrees with the number a
salesperson can already see, and is told explicitly not to dispute it.
"""

#: Bump on any change to the text below.
PROMPT_VERSION = "sales_brief_v1"

SYSTEM_PROMPT = """\
You are a senior sales strategist at Fluxframe Media, a content and social media \
agency that helps service businesses grow through short-form video, social media \
management, content strategy, paid social and creator campaigns.

You read an inbound lead's enquiry and produce a short, practical brief that \
prepares a salesperson for a first call.

Rules you must follow:

1. Work only from the information given. Do not invent facts about the company, \
   its revenue, its competitors or its history. If the enquiry is vague, say so \
   and set confidence to "low".
2. A deterministic scoring system has already rated this lead. That score is \
   authoritative and is not yours to dispute or restate. Your job is to explain \
   the human context behind it.
3. Be concrete and specific. "They want more leads" is useless. "They have a new \
   location opening in six weeks with no content plan" is useful.
4. Write in plain British English. No marketing jargon, no filler, no hype.
5. suggested_service must be one of: short_form_video, social_media_management, \
   content_strategy, paid_social, creator_campaigns.
6. urgency must be one of: high, medium, low.
7. confidence must be one of: high, medium, low, and should reflect how much the \
   prospect actually told you — a one-line enquiry cannot support high confidence.
"""

USER_PROMPT_TEMPLATE = """\
Prepare a sales brief for this inbound lead.

Company:            {company_name}
Industry:           {industry}
Monthly revenue:    {monthly_revenue}
Marketing budget:   {marketing_budget}
Content volume:     {content_volume} videos per month
Primary goal:       {primary_goal}
Wants to start:     {start_timeline}

Deterministic lead score: {deterministic_score}/100 ({deterministic_temperature})

What they wrote:
\"\"\"
{message}
\"\"\"

Use the submit_sales_brief tool to return your answer.
"""

#: The structured-output contract. Giving the model a tool with a JSON Schema is
#: what turns "please reply in JSON" (unreliable, needs parsing and repair) into
#: a typed response the API itself validates the shape of. We still validate
#: again on our side — never trust a shape you did not check.
SALES_BRIEF_TOOL = {
    "name": "submit_sales_brief",
    "description": "Submit the structured sales brief for this lead.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "Two or three sentences on who this prospect is and what they appear to need."
                ),
            },
            "pain_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Between one and four specific problems, drawn from what they actually wrote."
                ),
            },
            "urgency": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "How time-pressured this prospect appears to be.",
            },
            "suggested_service": {
                "type": "string",
                "enum": [
                    "short_form_video",
                    "social_media_management",
                    "content_strategy",
                    "paid_social",
                    "creator_campaigns",
                ],
                "description": "The Fluxframe service to lead the call with.",
            },
            "opening_line": {
                "type": "string",
                "description": (
                    "One sentence the salesperson can open the call with, "
                    "referencing something specific the prospect said."
                ),
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "How much the enquiry actually supports this brief.",
            },
        },
        "required": [
            "summary",
            "pain_points",
            "urgency",
            "suggested_service",
            "opening_line",
            "confidence",
        ],
    },
}

NO_MESSAGE_PLACEHOLDER = (
    "(The prospect did not leave a message. Base the brief only on their "
    "structured answers, and set confidence to low.)"
)
