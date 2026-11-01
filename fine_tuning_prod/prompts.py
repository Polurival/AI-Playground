"""Профили промпта на стороне сервиса. Копия констант из ../fine_tuning_my_dataset/common.py (День 7).

plain   — голый вопрос с вариантами: ровно то, на чём обучен тюн.
fewshot — системные правила + 3 примера: «проработанный промпт» для базовой модели.
Профиль привязан к модели в registry.json, поэтому откат модели откатывает и промпт.
"""

LETTERS = "ABCD"

SYSTEM_PROMPT = (
    "Eres un experto en historia, geografía y cultura de México que resuelve preguntas de opción múltiple.\n"
    "Reglas:\n"
    "1. Elige exactamente UNA opción: la correcta (A, B, C o D).\n"
    "2. Responde SOLO con una línea con este formato exacto: Respuesta: <LETRA>) <texto de la opción>\n"
    "3. No expliques, no añadas nada antes ni después, no uses negritas ni otro idioma que no sea español."
)
FEWSHOT = [
    ("¿En qué año se promulgó la Constitución vigente de México?",
     ["1810", "1917", "1857", "1960"], 1),
    ("¿Cuál es el río más largo que atraviesa la frontera norte de México?",
     ["Río Grijalva", "Río Lerma", "Río Bravo", "Río Papaloapan"], 2),
    ("¿Quién pintó el mural «Sueño de una tarde dominical en la Alameda Central»?",
     ["Diego Rivera", "David Alfaro Siqueiros", "José Clemente Orozco", "Rufino Tamayo"], 0),
]


def format_question(question, options):
    return question + "\n" + "\n".join(f"{LETTERS[i]}) {o}" for i, o in enumerate(options))


def format_answer(options, idx):
    return f"Respuesta: {LETTERS[idx]}) {options[idx]}"


def apply_profile(profile, messages):
    """messages — как пришли от клиента (system игнорируется: промпт принадлежит сервису)."""
    user = [m for m in messages if m["role"] != "system"]
    if profile == "plain":
        return user
    if profile == "fewshot":
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        for q, opts, idx in FEWSHOT:
            msgs += [{"role": "user", "content": format_question(q, opts)},
                     {"role": "assistant", "content": format_answer(opts, idx)}]
        return msgs + user
    raise ValueError(f"unknown prompt profile: {profile}")
