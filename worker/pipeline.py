import json
from dataclasses import dataclass, field

from openai import OpenAI

from spec import (
    IDEA_EVALUATION_FIELDS,
    IDEA_RESPONSE_SCHEMA,
    PERSONA_QUESTIONNAIRE,
    PERSONA_RESPONSE_SCHEMA,
    PERCEPTION_HIGHLIGHT_RESPONSE_SCHEMA,
    PERCEPTION_FIELDS,
    WORD_OF_MOUTH_FIELDS,
    pipeline_baseline_for_plan,
)
from config import (
    OPENROUTER_ANALYSIS_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_APP_NAME,
    OPENROUTER_APP_URL,
    OPENROUTER_BASE_URL,
)
from db import db_connection


client = OpenAI(
    base_url=OPENROUTER_BASE_URL,
    api_key=OPENROUTER_API_KEY or None,
)


def _pending_field(value):
    return {"status": "pending", "value": value}


def _completed_field(value, *, source="worker"):
    return {"status": "completed", "value": value, "source": source}


def get_response(messages, model, response_format=None):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("Missing OPENROUTER_API_KEY for analysis worker.")

    headers = {}
    if OPENROUTER_APP_URL:
        headers["HTTP-Referer"] = OPENROUTER_APP_URL
    if OPENROUTER_APP_NAME:
        headers["X-OpenRouter-Title"] = OPENROUTER_APP_NAME

    response = client.chat.completions.create(
        extra_headers=headers,
        messages=messages,
        model=model,
        response_format=response_format,
    ) if response_format else client.chat.completions.create(
        extra_headers=headers,
        messages=messages,
        model=model,
    )
    return response.choices[0].message.content.strip()


@dataclass
class Persona:
    persona_key: str
    display_name: str = ""
    profile: dict = field(default_factory=dict)
    chat_history: list = field(default_factory=list)

    @classmethod
    def from_record(cls, record):
        return cls(
            persona_key=record.get("persona_key") or record.get("id") or "",
            display_name=record.get("display_name") or "",
            profile=record.get("profile") or {
                key: value
                for key, value in record.items()
                if key not in {"persona_key", "id", "display_name", "chat_history"}
            },
            chat_history=record.get("chat_history") or [],
        )

    def to_record(self):
        return {
            "id": self.persona_key,
            "persona_key": self.persona_key,
            "display_name": self.display_name,
            **self.profile,
            "chat_history": self.chat_history,
        }


class LLMPipeline:
    def __init__(self, job):
        self.job = job or {}
        self.prompt = self.job["prompt"]
        self.target_type = self.job["target_type"]
        self.target_id = self.job["target_id"]
        self.plan = self.job["plan"]
        self.mode = self.job["mode"]
        self.context_label = self.job["context_label"]
        self.baseline = pipeline_baseline_for_plan(self.plan)
        self.project_id = self._resolve_project_id()
        # Load latest payload from DB if exists
        self._load_progress_from_db()

    def _load_progress_from_db(self):
        self.personas = None
        self.target_audience = ""
        self.questionnaire_responses = []
        self.idea_review = {field: "" for field in IDEA_EVALUATION_FIELDS}
        self.perception = {"responses": [], "summary": ""}
        self.word_of_mouth = {"order": [], "chain": [], "summary": ""}
        self.live_signals = None
        # Try to load existing payload from DB
        table_name = self._target_table_name()
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT analysis_payload FROM {table_name} WHERE id = %s",
                    (self.target_id,)
                )
                row = cur.fetchone()
        payload = row[0] if row and row[0] else {}
        # Restore step results if present and completed
        if payload:
            # Target audience
            ta = payload.get("target_audience", {})
            if ta.get("status") == "completed":
                self.target_audience = ta.get("value", "")
            # Personas
            personas_field = payload.get("personas", {})
            if personas_field.get("status") == "completed":
                self.personas = [Persona.from_record(p) for p in personas_field.get("value", [])]
            elif self.project_id is not None:
                self.personas = self._load_existing_personas()
            # Questionnaire responses
            qres = payload.get("questionnaire_responses", {})
            if qres.get("status") == "completed":
                self.questionnaire_responses = qres.get("value", [])
            # Idea review
            idea = payload.get("idea_review", {})
            if idea.get("status") == "completed":
                self.idea_review = idea.get("value", {field: "" for field in IDEA_EVALUATION_FIELDS})
            # Perception
            perception = payload.get("perception", {})
            if perception.get("status") == "completed":
                self.perception = perception.get("value", {"responses": [], "summary": ""})
            # Word of mouth
            wom = payload.get("word_of_mouth", {})
            if wom.get("status") == "completed":
                self.word_of_mouth = wom.get("value", {"order": [], "chain": [], "summary": ""})
            # Live signals
            ls = payload.get("live_signals", {})
            if ls.get("status") == "completed":
                self.live_signals = ls.get("value", None)

    def run(self):
        print(f"Starting LLM pipeline for job {self.job['id']} with target_type {self.target_type} and target_id {self.target_id}")
        # Step 1: Identify target audience (skip if already completed)
        if not self.target_audience:
            self.identify_target_audience()
            self._checkpoint_step("target_audience", _completed_field(self.target_audience))
        else:
            print("Target audience already completed, skipping.")
        print(f"Identified target audience: {self.target_audience}")
        # TODO: Repeat this pattern for all subsequent steps
        # Step 2: Generate personas
        if not self.personas:
            self.generate_personas()
            self._checkpoint_step("personas", _completed_field([p.to_record() for p in self.personas], source="project_memory"))
        else:
            print("Personas already completed, skipping.")
        print(f"Generated {len(self.personas) if self.personas is not None else 0} personas")

        # Step 3: Ask persona questionnaire
        if not self.questionnaire_responses:
            self.ask_persona_questionnaire()
            # Convert Persona objects in responses to dicts for storage
            def serialize_response(resp):
                return {
                    **resp,
                    "persona": resp["persona"].to_record() if hasattr(resp["persona"], "to_record") else resp["persona"]
                }
            q_responses = [serialize_response(r) for r in self.questionnaire_responses]
            self._checkpoint_step("questionnaire_responses", _completed_field(q_responses))
        else:
            print("Questionnaire responses already completed, skipping.")
        print(f"Collected questionnaire responses for {len(self.questionnaire_responses)} personas")

        # Step 4: Aggregate idea evaluation
        if not (self.idea_review and any(self.idea_review.values())):
            self.aggregate_idea_evaluation()
            self._checkpoint_step("idea_review", _completed_field(self.idea_review))
        else:
            print("Idea evaluation already completed, skipping.")
        print(f"Aggregated idea evaluation")

        # Step 5: Analyze perception
        if not (self.perception and (self.perception.get("responses") or self.perception.get("summary"))):
            self.analyze_perception()
            self._checkpoint_step("perception", _completed_field(self.perception))
        else:
            print("Perception analysis already completed, skipping.")
        print(f"Analyzed perception")

        # Step 6: Run word of mouth chain
        if not (self.word_of_mouth and (self.word_of_mouth.get("order") or self.word_of_mouth.get("chain") or self.word_of_mouth.get("summary"))):
            self.run_word_of_mouth_chain()
            self._checkpoint_step("word_of_mouth", _completed_field(self.word_of_mouth))
        else:
            print("Word of mouth chain already completed, skipping.")
        print(f"Ran word of mouth chain")

        # Step 7: Discover live signals
        if self.live_signals is None:
            self.discover_live_signals()
            self._checkpoint_step("live_signals", _completed_field(self.live_signals))
        else:
            print("Live signals already completed, skipping.")
        print(f"Discovered live signals")

        payload = self._build_payload()
        print(f"Built payload for job {self.job['id']}")
        self._write_payload(payload)
        self._persist_project_personas(self.personas)

    def _checkpoint_step(self, field, value):
        # Write a single step's result to the DB payload
        table_name = self._target_table_name()
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {table_name} SET analysis_payload = COALESCE(analysis_payload, '{{}}'::jsonb) || %s::jsonb WHERE id = %s",
                    (json.dumps({field: value}), self.target_id),
                )

    def identify_target_audience(self):
        self.target_audience = get_response([
            {
                "role": "system",
                "content": ("You are an assistant for a product founder. Your task is to identify the target audience for the product based on the founder's description and prompt. "
                            "Provide a concise description of the ideal customer profile, including demographics, interests, and pain points. "
                            "Focus on who would benefit most from this product and why. Return a 1-2 sentence summary of the target audience, without any additional text or formatting.")
            },
            {
                "role": "user",
                "content": self.prompt
            }
        ], OPENROUTER_ANALYSIS_MODEL)


    def generate_personas(self):
        if self.personas:
            return
        n = 5 if self.plan == "Free" else 10 if self.plan == "Starter" else 20
        personas_response = get_response([
            {
                "role": "system",
                "content": (f"You are an assistant for a product founder. Your task is to generate {n} distinct customer personas based on the founder's description and prompt. "
                            "The personas should represent different segments of the target audience that would benefit from the product.")
            },
            {
                "role": "user",
                "content": self.target_audience
            }
        ], OPENROUTER_ANALYSIS_MODEL, PERSONA_RESPONSE_SCHEMA)
        print(f"Received personas response: {personas_response}")
        try:
            personas_data = json.loads(personas_response)
            self.personas = [Persona.from_record(record) for record in personas_data]
        except json.JSONDecodeError:
            self.personas = []
            print(f"Failed to parse personas response as JSON: {personas_response}")

    def ask_persona_questionnaire(self):
        if not self.personas:
            self.questionnaire_responses = []
            return

        import concurrent.futures
        def ask_one_and_write(persona):
            response = get_response([
                {
                    "role": "system",
                    "content": (f"You are a customer that matches the following persona: {persona.to_record()}.")
                },
                {
                    "role": "user",
                    "content": (f"Based on the product description: {self.prompt}, answer the following questionnaire: {PERSONA_QUESTIONNAIRE}. Provide detailed and thoughtful responses that reflect the perspective of the persona. Return your answers in a JSON format with keys corresponding to the questionnaire fields and values containing your responses. Strict JSON output, no additional text.")
                }
            ], OPENROUTER_ANALYSIS_MODEL, {"type": "json_object"})
            result = {
                "persona": persona.to_record(),
                "responses": json.loads(response) if response else {},
            }
            # Write partial result to DB
            partial_responses = self.questionnaire_responses + [result]
            payload = self._build_payload()
            self._write_payload(payload)
            return result

        with concurrent.futures.ThreadPoolExecutor() as executor:
            self.questionnaire_responses = []
            futures = [executor.submit(ask_one_and_write, persona) for persona in self.personas]
            for future in concurrent.futures.as_completed(futures):
                self.questionnaire_responses.append(future.result())

    def aggregate_idea_evaluation(self):
        self.idea_review = {field: "" for field in IDEA_EVALUATION_FIELDS}
        response = get_response([
            {
                "role": "system",
                "content": ("You are an assistant for a product founder. Your task is to evaluate the founder's product idea based on the personas and their questionnaire responses. "
                            "Consider the strengths and weaknesses of the product idea, how well it addresses the needs of the personas, and any potential risks or blind spots. "
                            "Provide a detailed evaluation of the product idea, organized by the following fields: " + ", ".join(IDEA_EVALUATION_FIELDS) + ". "
                            "Return your evaluation in a JSON format with keys corresponding to the evaluation fields and values containing your analysis. Strict JSON output, no additional text.")
            },
            {
                "role": "user",
                "content": (f"Product description: {self.prompt}\n\nPersonas and questionnaire responses: {self.questionnaire_responses}")
            }
        ], OPENROUTER_ANALYSIS_MODEL, IDEA_RESPONSE_SCHEMA)
        try:
            self.idea_review = json.loads(response) if response else {field: "" for field in IDEA_EVALUATION_FIELDS}
            self.idea_review['audience'] = self.target_audience
        except json.JSONDecodeError:
            self.idea_review = {field: "" for field in IDEA_EVALUATION_FIELDS}
            print(f"Failed to parse idea evaluation response as JSON: {response}")


    def analyze_perception(self):
        if not self.personas:
            self.perception = {"responses": [], "summary": ""}
            return

        response = get_response([ # Identify the most important perception cues from the persona responses, such as specific likes, dislikes, concerns, or desires related to the product. Then analyze the overall perception of the product based on these cues, looking for common themes and insights across the different personas. Finally, provide a summary of the product's perception that highlights key takeaways and actionable insights for the founder.
            {
                "role": "system",
                "content": ("You are an assistant for a product founder. Your task is to analyze the perception of the founder's product idea based on the personas and their questionnaire responses. "
                            "First, identify the most important perception cues from the persona responses, such as specific likes, dislikes, concerns, or desires related to the product. Then analyze the overall perception of the product based on these cues, looking for common themes and insights across the different personas. Finally, provide a summary of the product's perception that highlights key takeaways and actionable insights for the founder. ")
            },
            {
                "role": "user",
                "content": (f"Product description: {self.prompt}\n\nPersonas and questionnaire responses: {self.questionnaire_responses}\n\nIdea evaluation: {self.idea_review}")
            }
        ], OPENROUTER_ANALYSIS_MODEL, PERCEPTION_HIGHLIGHT_RESPONSE_SCHEMA)
        try:
            perception_data = json.loads(response)
            self.perception = {
                "responses": perception_data.get("responses", []),
                "summary": perception_data.get("summary", ""),
            }
        except json.JSONDecodeError:
            self.perception = {"responses": [], "summary": ""}
            print(f"Failed to parse perception analysis response as JSON: {response}")

    def run_word_of_mouth_chain(self):
        if not self.personas:
            self.word_of_mouth = {"order": [], "chain": [], "summary": ""}
            return

        self.word_of_mouth = {
            "order": [persona.persona_key for persona in self.personas],
            "chain": [
                {
                    "persona_id": persona.persona_key,
                    **{field: "" for field in WORD_OF_MOUTH_FIELDS if field != "persona_id"},
                }
                for persona in self.personas
            ],
            "summary": "",
        }

    def discover_live_signals(self):
        self.live_signals = None

    def _build_payload(self):
        if self.personas is None:
            personas_field = None
        elif self.personas:
            personas_field = _completed_field([persona.to_record() for persona in self.personas], source="project_memory")
        else:
            personas_field = _pending_field([])

        # Convert Persona objects in questionnaire_responses to dicts
        def serialize_response(resp):
            return {
                **resp,
                "persona": resp["persona"].to_record() if hasattr(resp["persona"], "to_record") else resp["persona"]
            }
        q_responses = [serialize_response(r) for r in self.questionnaire_responses]

        return {
            "status": "processing",
            "job": {
                "id": self.job["id"],
                "status": "processing",
                "attempts": self.job.get("attempts"),
                "worker_id": self.job.get("worker_id"),
                "target_type": self.target_type,
                "target_id": self.target_id,
                "plan": self.plan,
                "mode": self.mode,
                "context_label": self.context_label,
            },
            "input": {
                "prompt": self.prompt,
                "plan": self.plan,
                "mode": self.mode,
                "context_label": self.context_label,
            },
            "personas": personas_field,
            "target_audience": _pending_field(self.target_audience),
            "questionnaire_responses": _pending_field(q_responses),
            "idea_review": _pending_field(self.idea_review),
            "perception": _pending_field(self.perception),
            "word_of_mouth": _pending_field(self.word_of_mouth),
            "scores": _pending_field(
                {
                    "idea_score": None,
                    "perception_score": None,
                    "spread_score": None,
                }
            ),
            "summaries": _pending_field(
                {
                    "idea_summary": "",
                    "perception_summary": "",
                    "spread_summary": "",
                }
            ),
            "live_signals": _pending_field(self.live_signals),
        }

    def _write_payload(self, payload):
        table_name = self._target_table_name()
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {table_name}
                    SET analysis_payload = %s::jsonb
                    WHERE id = %s
                    """,
                    (json.dumps(payload), self.target_id),
                )

    def _target_table_name(self):
        if self.target_type == "project_material":
            return "project_materials"
        if self.target_type == "one_off_test":
            return "one_off_tests"
        raise ValueError(f"Unsupported analysis job target_type: {self.target_type}")

    def _resolve_project_id(self):
        if self.target_type != "project_material":
            return None

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT project_id
                    FROM project_materials
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (self.target_id,),
                )
                row = cur.fetchone()
        return row[0] if row else None

    def _load_existing_personas(self):
        if not self.project_id:
            return None

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT persona_key, display_name, profile, chat_history
                    FROM personas
                    WHERE project_id = %s
                    ORDER BY created_at ASC
                    """,
                    (self.project_id,),
                )
                rows = cur.fetchall()
        return [
            Persona(
                persona_key=row[0],
                display_name=row[1] or "",
                profile=row[2] or {},
                chat_history=row[3] or [],
            )
            for row in rows
        ]

    def _persist_project_personas(self, personas):
        if not self.project_id or not personas:
            return

        with db_connection() as conn:
            with conn.cursor() as cur:
                for persona in personas:
                    cur.execute(
                        """
                        INSERT INTO personas (
                            project_id,
                            persona_key,
                            display_name,
                            profile,
                            chat_history,
                            updated_at
                        )
                        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, NOW())
                        ON CONFLICT (project_id, persona_key)
                        DO UPDATE SET
                            display_name = EXCLUDED.display_name,
                            profile = EXCLUDED.profile,
                            chat_history = EXCLUDED.chat_history,
                            updated_at = NOW()
                        """,
                        (
                            self.project_id,
                            persona.persona_key,
                            persona.display_name,
                            json.dumps(persona.profile),
                            json.dumps(persona.chat_history),
                        ),
                    )
