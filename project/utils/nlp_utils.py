import re
import os
import json
import functools
import threading
import nltk
import requests

# ============================================================================
# CONFIGURATION — loaded from environment via config.py
# ============================================================================

# OpenRouter API settings (read from env; config.py loads these into Flask app config)
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', 'google/gemini-2.0-flash')
OPENROUTER_TIMEOUT = int(os.environ.get('OPENROUTER_TIMEOUT', '10'))
OPENROUTER_BATCH_SIZE = int(os.environ.get('OPENROUTER_BATCH_SIZE', '15'))
OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions'

# Local model paths
CUSTOM_MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "custom_model")
BASE_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"

# ============================================================================
# LAZY-LOADED LOCAL MODEL (only loads when API is unavailable)
# ============================================================================

_local_pipeline = None
_local_pipeline_lock = threading.Lock()
_local_pipeline_attempted = False


def _get_local_pipeline():
    """
    Lazy-loads the local Transformers sentiment pipeline on first call.
    Thread-safe via lock. Returns None if loading fails.
    This avoids loading ~2GB of torch/transformers at startup when the API is available.
    """
    global _local_pipeline, _local_pipeline_attempted

    if _local_pipeline is not None:
        return _local_pipeline

    if _local_pipeline_attempted:
        # Already tried and failed — don't retry every call
        return None

    with _local_pipeline_lock:
        # Double-check after acquiring lock
        if _local_pipeline is not None:
            return _local_pipeline
        if _local_pipeline_attempted:
            return None

        _local_pipeline_attempted = True

        try:
            import torch
            from transformers import pipeline

            device = 0 if torch.cuda.is_available() else -1

            if os.path.exists(CUSTOM_MODEL_DIR):
                print("[Fallback] Loading local CUSTOM fine-tuned model...")
                _local_pipeline = pipeline(
                    "sentiment-analysis",
                    model=CUSTOM_MODEL_DIR,
                    tokenizer=CUSTOM_MODEL_DIR,
                    device=device,
                    truncation=True,
                    max_length=512
                )
            else:
                print("[Fallback] Loading default HuggingFace model...")
                _local_pipeline = pipeline(
                    "sentiment-analysis",
                    model=BASE_MODEL,
                    device=device,
                    truncation=True,
                    max_length=512
                )
            print("[Fallback] Local AI engine loaded successfully.")
            return _local_pipeline

        except Exception as e:
            print(f"[Fallback] Failed to load local model: {e}")
            return None


# ============================================================================
# OPENROUTER API — Single Text Sentiment
# ============================================================================

_SYSTEM_PROMPT = (
    "You are a sentiment classifier. Classify the sentiment of the given text as exactly one of: "
    "Positive, Negative, or Neutral. Also provide a confidence score between 0.0 and 1.0. "
    "Respond ONLY with valid JSON in this exact format, no other text:\n"
    '{"sentiment": "Positive", "score": 0.85}'
)


def _call_openrouter_single(text):
    """
    Call OpenRouter API for a single text. Returns (sentiment, polarity) or None on failure.
    Scoped strictly to sentiment analysis — this is the ONLY function that calls the API.
    """
    if not OPENROUTER_API_KEY:
        return None

    # Skip empty or too-short text (optimization: don't waste tokens)
    if not text or len(text.strip()) < 3:
        return None

    try:
        response = requests.post(
            OPENROUTER_API_URL,
            headers={
                'Authorization': f'Bearer {OPENROUTER_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': OPENROUTER_MODEL,
                'messages': [
                    {'role': 'system', 'content': _SYSTEM_PROMPT},
                    {'role': 'user', 'content': text[:2000]}  # Truncate for safety
                ],
                'temperature': 0.0,  # Deterministic output for consistency
                'max_tokens': 50,    # JSON response is tiny
            },
            timeout=OPENROUTER_TIMEOUT
        )

        if response.status_code != 200:
            print(f"[OpenRouter] API returned status {response.status_code}")
            return None

        data = response.json()
        content = data['choices'][0]['message']['content'].strip()

        # Parse JSON response — handle markdown code blocks if model wraps output
        if content.startswith('```'):
            content = content.split('\n', 1)[-1].rsplit('```', 1)[0].strip()

        result = json.loads(content)
        sentiment = result.get('sentiment', 'Neutral')
        score = float(result.get('score', 0.5))

        # Normalize to standard format
        if sentiment not in ('Positive', 'Negative', 'Neutral'):
            sentiment = 'Neutral'

        if sentiment == 'Positive':
            polarity = score
        elif sentiment == 'Negative':
            polarity = -score
        else:
            polarity = 0.0

        return sentiment, polarity

    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"[OpenRouter] API call failed: {e}")
        return None


# ============================================================================
# OPENROUTER API — Batch Sentiment (for bulk CSV uploads)
# ============================================================================

_BATCH_SYSTEM_PROMPT = (
    "You are a sentiment classifier. For each numbered text below, classify sentiment as exactly "
    "Positive, Negative, or Neutral with a confidence score (0.0-1.0). "
    "Respond ONLY with a valid JSON array, no other text. Example:\n"
    '[{"sentiment": "Positive", "score": 0.85}, {"sentiment": "Negative", "score": 0.72}]'
)


def analyze_sentiment_batch(texts):
    """
    Batch-analyze multiple texts in a single API call.
    Returns list of (sentiment, polarity) tuples matching input order.
    Falls back to individual analysis if batch parsing fails.
    
    Args:
        texts: List of raw feedback strings
    Returns:
        List of (sentiment_category, polarity_score) tuples
    """
    if not OPENROUTER_API_KEY or not texts:
        # No API key — fall back to individual analysis
        return [analyze_sentiment(t) for t in texts]

    # Filter out empty texts but keep track of indices
    valid_indices = []
    valid_texts = []
    for i, text in enumerate(texts):
        if text and len(text.strip()) >= 3:
            valid_indices.append(i)
            valid_texts.append(text[:2000])  # Truncate per text

    if not valid_texts:
        return [('Neutral', 0.0)] * len(texts)

    # Build numbered prompt
    numbered_lines = []
    for idx, text in enumerate(valid_texts, 1):
        numbered_lines.append(f"{idx}. {text}")
    user_content = '\n'.join(numbered_lines)

    try:
        response = requests.post(
            OPENROUTER_API_URL,
            headers={
                'Authorization': f'Bearer {OPENROUTER_API_KEY}',
                'Content-Type': 'application/json',
            },
            json={
                'model': OPENROUTER_MODEL,
                'messages': [
                    {'role': 'system', 'content': _BATCH_SYSTEM_PROMPT},
                    {'role': 'user', 'content': user_content}
                ],
                'temperature': 0.0,
                'max_tokens': len(valid_texts) * 60,  # ~60 tokens per result
            },
            timeout=OPENROUTER_TIMEOUT + (len(valid_texts) * 2)  # Scale timeout with batch size
        )

        if response.status_code != 200:
            print(f"[OpenRouter Batch] API returned status {response.status_code}, falling back to individual")
            return [analyze_sentiment(t) for t in texts]

        data = response.json()
        content = data['choices'][0]['message']['content'].strip()

        # Handle markdown code blocks
        if content.startswith('```'):
            content = content.split('\n', 1)[-1].rsplit('```', 1)[0].strip()

        results_raw = json.loads(content)

        if not isinstance(results_raw, list) or len(results_raw) != len(valid_texts):
            print(f"[OpenRouter Batch] Expected {len(valid_texts)} results, got {len(results_raw) if isinstance(results_raw, list) else 'non-list'}")
            return [analyze_sentiment(t) for t in texts]

        # Build full results array (including empty text slots)
        full_results = [('Neutral', 0.0)] * len(texts)

        for array_idx, original_idx in enumerate(valid_indices):
            r = results_raw[array_idx]
            sentiment = r.get('sentiment', 'Neutral')
            score = float(r.get('score', 0.5))

            if sentiment not in ('Positive', 'Negative', 'Neutral'):
                sentiment = 'Neutral'

            if sentiment == 'Positive':
                polarity = score
            elif sentiment == 'Negative':
                polarity = -score
            else:
                polarity = 0.0

            # Apply complaint-override layer on API results too
            final_sentiment, final_polarity = _apply_complaint_override(
                texts[original_idx], sentiment, polarity, score
            )
            full_results[original_idx] = (final_sentiment, final_polarity)

        return full_results

    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"[OpenRouter Batch] Failed: {e}, falling back to individual analysis")
        return [analyze_sentiment(t) for t in texts]


# ============================================================================
# LOCAL MODEL — Single Text Fallback
# ============================================================================

def _analyze_local(text):
    """
    Run sentiment analysis using the lazy-loaded local Transformers model.
    Returns (sentiment, polarity) or ('Neutral', 0.0) if model unavailable.
    """
    pipeline_fn = _get_local_pipeline()
    if not pipeline_fn:
        return 'Neutral', 0.0

    try:
        safe_text = text[:2000]
        result = pipeline_fn(safe_text)[0]
        label = result['label'].lower()
        score = result['score']

        if label in ('positive', 'label_2'):
            return 'Positive', float(score)
        elif label in ('negative', 'label_0'):
            return 'Negative', -float(score)
        else:
            return 'Neutral', 0.0

    except Exception as e:
        print(f"[Local Model] Error: {e}")
        return 'Neutral', 0.0


# ============================================================================
# TEXT PREPROCESSING (UNCHANGED)
# ============================================================================

# Basic stop words fallback if NLTK fails to load
FALLBACK_STOPWORDS = {"i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself", "they", "them", "their", "theirs", "themselves", "what", "which", "who", "whom", "this", "that", "these", "those", "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having", "do", "does", "did", "doing", "a", "an", "the", "and", "but", "if", "or", "because", "as", "until", "while", "of", "at", "by", "for", "with", "about", "against", "between", "into", "through", "during", "before", "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "so", "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now"}

# Attempt to load NLTK corpora gracefully
stop_words = FALLBACK_STOPWORDS
use_nltk_tokenize = False

try:
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', quiet=True)
    from nltk.corpus import stopwords
    stop_words = set(stopwords.words('english'))
    
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
        nltk.download('punkt_tab', quiet=True)
    use_nltk_tokenize = True
except Exception as e:
    print(f"NLTK initialization encountered an error: {e}. Falling back to basic tokenization.")


def preprocess_text(text):
    """
    Cleans text by removing punctuation, converting to lowercase, 
    and removing stopwords. Used for TF-IDF keyword extraction and storage.
    NOTE: This is NOT used for sentiment analysis — the model receives
    the original text for better accuracy.
    """
    if not isinstance(text, str):
        return ""
        
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    
    if use_nltk_tokenize:
        try:
            from nltk.tokenize import word_tokenize
            tokens = word_tokenize(text)
        except Exception:
            tokens = text.split()
    else:
        tokens = text.split()
        
    filtered_tokens: list[str] = [str(w) for w in tokens if w not in stop_words]
    return ' '.join(filtered_tokens)


# ============================================================================
# COMPLAINT-AWARE OVERRIDE LAYER (UNCHANGED)
# ============================================================================

COMPLAINT_KEYWORDS = frozenset({
    'dirty', 'filthy', 'unclean', 'stinking', 'smelly', 'smells', 'stink',
    'broken', 'damaged', 'defective', 'faulty', 'malfunctioning',
    'poor', 'worst', 'terrible', 'horrible', 'awful', 'pathetic', 'useless',
    'bad', 'worse', 'disappointing', 'disgusting', 'unbearable', 'miserable',
    'rude', 'arrogant', 'unfriendly', 'unhelpful', 'disrespectful', 'harsh',
    'unfair', 'biased', 'partial', 'unjust', 'favouritism', 'favoritism',
    'overcrowded', 'congested', 'cramped', 'noisy', 'chaotic',
    'delayed', 'late', 'slow', 'irregular', 'unpunctual',
    'expensive', 'overpriced', 'overcharged',
    'unsafe', 'insecure', 'dangerous', 'risky',
    'inadequate', 'insufficient', 'lacking', 'shortage', 'scarce',
    'neglected', 'ignored', 'unattended', 'unmaintained',
    'outdated', 'old', 'obsolete', 'worn',
    'not working', 'doesn\'t work', 'don\'t work', 'never works',
    'not available', 'not clean', 'not safe', 'not good', 'not enough',
    'no water', 'no fan', 'no wifi', 'no internet', 'no light',
    'no response', 'no action', 'no improvement',
    'complaint', 'complain', 'complained', 'issue', 'problem', 'problems',
    'concern', 'concerns', 'dissatisfied', 'frustrated', 'angry', 'annoyed',
    'fed up', 'sick of', 'tired of', 'unhappy', 'unsatisfied',
    'fail', 'failed', 'failing', 'failure',
})

_NEGATION_PATTERNS = re.compile(
    r'\b(?:not|no|never|doesn\'t|don\'t|isn\'t|aren\'t|wasn\'t|weren\'t|can\'t|cannot|won\'t|hardly|barely|scarcely)\b'
    r'(?:\s+\w+){0,4}\s+'
    r'(?:working|available|clean|safe|good|enough|functional|proper|adequate|maintained|helpful|responsive|fair|satisfactory|accessible|provided|present)',
    re.IGNORECASE
)


def _apply_complaint_override(text, sentiment, polarity, score):
    """
    Complaint-aware override layer. Runs AFTER both API and local model results.
    When the model says Neutral (or low-confidence Positive), checks for complaint
    language and overrides to Negative if found.
    
    Returns (final_sentiment, final_polarity).
    """
    if sentiment == 'Neutral' or (sentiment == 'Positive' and score < 0.70):
        text_lower = text.lower() if isinstance(text, str) else ''

        # Check negation phrases first (highest signal)
        if _NEGATION_PATTERNS.search(text_lower):
            return 'Negative', -0.75

        # Check individual complaint keywords
        words = set(re.findall(r'\b\w+\b', text_lower))
        complaint_matches = words & COMPLAINT_KEYWORDS
        if len(complaint_matches) >= 1:
            severity = min(0.60 + (len(complaint_matches) * 0.08), 0.95)
            return 'Negative', -severity

    return sentiment, polarity


# ============================================================================
# MAIN SENTIMENT ANALYSIS — Hybrid: API Primary → Local Fallback
# ============================================================================

@functools.lru_cache(maxsize=10000)
def analyze_sentiment(text):
    """
    Multi-layer hybrid sentiment analysis pipeline:
    
    1. Check LRU cache (automatic via decorator)
    2. Try OpenRouter API (primary — fast, accurate, no local RAM)
    3. If API fails → lazy-load local Transformers model (fallback)
    4. Apply complaint-aware override layer (always, regardless of source)
    
    Returns (sentiment_category, polarity_score)
    """
    if not text:
        return 'Neutral', 0.0

    # === Layer 1: OpenRouter API (Primary) ===
    api_result = _call_openrouter_single(text)
    
    if api_result is not None:
        sentiment, polarity = api_result
        score = abs(polarity) if polarity != 0.0 else 0.5
        # Apply complaint override on API results
        return _apply_complaint_override(text, sentiment, polarity, score)

    # === Layer 2: Local Model (Fallback) ===
    print("[Sentiment] API unavailable, using local model fallback...")
    sentiment, polarity = _analyze_local(text)
    score = abs(polarity) if polarity != 0.0 else 0.5
    # Apply complaint override on local results
    return _apply_complaint_override(text, sentiment, polarity, score)


# ============================================================================
# COLLEGE CONTEXT VALIDATION (UNCHANGED)
# ============================================================================

COLLEGE_KEYWORDS = frozenset({
    'college', 'university', 'school', 'institute', 'institution', 'academy',
    'student', 'students', 'teacher', 'teachers', 'professor', 'professors',
    'hod', 'staff', 'faculty', 'lecturer', 'lecturers', 'instructor', 'instructors',
    'principal', 'dean', 'director', 'vice-principal', 'chairman', 'trustee',
    'admin', 'administration', 'management', 'warden', 'librarian', 'peon',
    'clerk', 'registrar', 'coordinator', 'mentor', 'counselor', 'counsellor',
    'class', 'classes', 'classroom', 'classrooms', 'course', 'courses',
    'subject', 'subjects', 'exam', 'exams', 'examination', 'examinations',
    'grade', 'grades', 'marks', 'result', 'results', 'cgpa', 'gpa', 'percentage',
    'assignment', 'assignments', 'homework', 'project', 'projects',
    'lecture', 'lectures', 'tutorial', 'tutorials', 'practicals',
    'lab', 'labs', 'laboratory', 'laboratories',
    'library', 'reading', 'textbook', 'textbooks', 'syllabus', 'curriculum',
    'degree', 'diploma', 'certificate', 'graduate', 'undergraduate', 'postgraduate', 'phd',
    'semester', 'term', 'paper', 'papers', 'presentation', 'viva',
    'academic', 'academics', 'study', 'studying', 'education', 'learning', 'teaching',
    'attendance', 'absent', 'present', 'book', 'books', 'notes',
    'scholar', 'scholarship', 'topper', 'backlog', 'revaluation',
    'campus', 'hostel', 'hostels', 'dormitory', 'dorm',
    'canteen', 'cafeteria', 'mess', 'food', 'lunch', 'breakfast', 'dinner', 'snacks',
    'toilet', 'toilets', 'restroom', 'restrooms', 'washroom', 'washrooms', 'bathroom', 'bathrooms', 'lavatory',
    'ground', 'grounds', 'playground', 'playgrounds', 'field', 'fields', 'court', 'courts',
    'sports', 'sport', 'game', 'games', 'gym', 'gymnasium', 'fitness',
    'parking', 'vehicle', 'bike', 'cycle', 'scooter',
    'transport', 'bus', 'buses', 'van', 'shuttle', 'route',
    'corridor', 'corridors', 'hallway', 'hallways', 'lobby', 'entrance', 'exit', 'gate',
    'staircase', 'stairs', 'elevator', 'lift',
    'building', 'buildings', 'block', 'wing', 'floor', 'room', 'rooms',
    'auditorium', 'hall', 'seminar', 'conference',
    'wifi', 'internet', 'network', 'computer', 'computers', 'projector', 'projectors',
    'fan', 'fans', 'ac', 'aircon', 'ventilation', 'light', 'lights', 'lighting',
    'water', 'drinking', 'cooler', 'purifier', 'ro',
    'generator', 'power', 'electricity', 'ups', 'inverter',
    'bench', 'benches', 'desk', 'desks', 'chair', 'chairs', 'furniture',
    'board', 'whiteboard', 'blackboard', 'smartboard',
    'garden', 'lawn', 'tree', 'trees', 'greenery', 'landscape',
    'fence', 'wall', 'roof', 'ceiling', 'window', 'windows', 'door', 'doors',
    'cctv', 'camera', 'cameras', 'surveillance',
    'admission', 'admissions', 'fee', 'fees', 'placement', 'placements',
    'internship', 'internships', 'recruitment', 'interview', 'interviews',
    'event', 'events', 'club', 'clubs', 'society', 'societies',
    'facility', 'facilities', 'infrastructure', 'amenity', 'amenities',
    'department', 'departments', 'office', 'offices',
    'notice', 'notices', 'circular', 'announcement',
    'id', 'card', 'uniform', 'dress', 'code',
    'tournament', 'competition', 'fest', 'festival', 'cultural', 'technical',
    'symposium', 'webinar', 'workshop', 'training', 'orientation',
    'skill', 'skills', 'industry', 'visit', 'tour', 'trip', 'picnic', 'excursion',
    'holiday', 'vacation', 'leave', 'permission',
    'guard', 'security', 'safe', 'safety', 'rule', 'rules', 'regulation', 'regulations',
    'strict', 'discipline', 'fine', 'penalty', 'punishment', 'reward',
    'ragging', 'bullying', 'harassment', 'complaint',
    'clean', 'cleaning', 'cleanliness', 'dirty', 'maintenance', 'repair', 'renovation',
    'hygiene', 'sanitation', 'garbage', 'dustbin', 'waste', 'disposal',
    'pest', 'mosquito', 'mosquitoes', 'rat', 'rats', 'cockroach', 'insects',
})


def is_college_context(text):
    """
    Fast heuristic to check if feedback is related to institutional context.
    Returns True if at least one institutional keyword is found.
    """
    if not isinstance(text, str) or not text.strip():
        return False
        
    text_lower = text.lower()
    words = set(re.findall(r'\b\w+\b', text_lower))
    
    if words & COLLEGE_KEYWORDS:
        return True
    
    phrase_patterns = [
        'class room', 'play ground', 'wash room', 'rest room',
        'drinking water', 'sports ground', 'parking lot', 'parking area',
        'common room', 'computer lab', 'science lab', 'physics lab',
        'chemistry lab', 'seminar hall', 'exam hall', 'reading room',
        'staff room', 'faculty room', 'principal office',
    ]
    for phrase in phrase_patterns:
        if phrase in text_lower:
            return True
            
    return False


# ============================================================================
# RISK / SENSITIVE CONTENT DETECTION (UNCHANGED)
# ============================================================================

RISK_CATEGORIES = {
    'Bullying & Ragging': frozenset({
        'bully', 'bullied', 'bullying', 'bullies',
        'ragging', 'ragged', 'rag', 'rags',
        'torment', 'tormented', 'tormenting',
        'intimidate', 'intimidated', 'intimidation', 'intimidating',
        'humiliate', 'humiliated', 'humiliation', 'humiliating',
        'tease', 'teased', 'teasing', 'mocking', 'mocked', 'ridiculed',
        'cyberbully', 'cyberbullying', 'trolling', 'trolled',
    }),
    'Harassment & Abuse': frozenset({
        'harass', 'harassed', 'harassment', 'harassing',
        'abuse', 'abused', 'abusing', 'abusive',
        'molest', 'molested', 'molesting', 'molestation',
        'exploit', 'exploited', 'exploitation', 'exploiting',
        'inappropriate', 'inappropriately',
        'misconduct', 'misbehave', 'misbehaved', 'misbehaviour', 'misbehavior',
        'touch', 'touched', 'grope', 'groped', 'groping',
    }),
    'Violence & Assault': frozenset({
        'assault', 'assaulted', 'assaulting',
        'violence', 'violent', 'violently',
        'attack', 'attacked', 'attacking',
        'hit', 'hitting', 'beaten', 'beat', 'beating',
        'slap', 'slapped', 'punch', 'punched', 'kick', 'kicked',
        'fight', 'fighting', 'fights',
        'weapon', 'knife', 'gun',
    }),
    'Safety & Threats': frozenset({
        'unsafe', 'danger', 'dangerous', 'risky',
        'threat', 'threaten', 'threatened', 'threatening', 'threats',
        'scared', 'frightened', 'terrified', 'afraid', 'fear', 'fearful',
        'stalking', 'stalked', 'stalker', 'following',
        'kidnap', 'kidnapped', 'abduct', 'abducted',
        'emergency', 'sos',
    }),
    'Mental Health & Self-Harm': frozenset({
        'suicide', 'suicidal',
        'selfharm', 'self-harm', 'cutting', 'hurt myself',
        'depressed', 'depression', 'depressing',
        'anxiety', 'anxious', 'panic',
        'mental', 'mentally', 'breakdown',
        'hopeless', 'helpless', 'worthless',
        'lonely', 'loneliness', 'isolated', 'isolation',
        'trauma', 'traumatic', 'traumatized', 'ptsd',
        'stress', 'stressed', 'distress', 'distressed',
        'cry', 'crying', 'tears',
    }),
    'Discrimination': frozenset({
        'discriminate', 'discriminated', 'discrimination', 'discriminating',
        'racist', 'racism', 'racial',
        'sexist', 'sexism',
        'casteism', 'caste', 'castist',
        'communal', 'communalism',
        'bias', 'biased', 'prejudice', 'prejudiced',
        'xenophobia', 'xenophobic',
        'homophobia', 'homophobic',
        'marginalized', 'excluded', 'exclusion',
    }),
    'Corruption & Misconduct': frozenset({
        'bribe', 'bribery', 'bribing', 'corrupt', 'corruption',
        'illegal', 'fraud', 'fraudulent', 'scam',
        'cheat', 'cheating', 'cheated', 'malpractice',
        'nepotism', 'favouritism', 'favoritism',
        'blackmail', 'blackmailed', 'extort', 'extortion',
        'leak', 'leaked', 'leaking',
    }),
}

_RISK_WORD_TO_CATEGORY = {}
for _cat, _words in RISK_CATEGORIES.items():
    for _w in _words:
        _RISK_WORD_TO_CATEGORY[_w] = _cat

_RISK_PHRASE_PATTERNS = re.compile(
    r'\b(?:'
    r'self[- ]?harm|hurt myself|kill myself|end my life|want to die'
    r'|behave[sd]? inappropriately|inappropriate behavi(?:our|or)'
    r'|sexual(?:ly)? harass(?:ed|ment|ing)?'
    r'|feel(?:s|ing)? unsafe|not safe|don\'t feel safe'
    r'|mental(?:ly)? (?:disturbed|broken|tortured|stressed|unwell)'
    r'|drug(?:s| abuse| dealing| addict)'
    r'|substance abuse|alcohol'
    r')\b',
    re.IGNORECASE
)


def detect_risk_content(text):
    """
    Detects sensitive/high-risk content independently of sentiment classification.
    Returns a list of matched risk categories, or empty list if no risk detected.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    
    text_lower = text.lower()
    matched_categories = set()
    
    words = re.findall(r'\b\w+\b', text_lower)
    for word in words:
        cat = _RISK_WORD_TO_CATEGORY.get(word)
        if cat:
            matched_categories.add(cat)
    
    phrase_matches = _RISK_PHRASE_PATTERNS.findall(text_lower)
    if phrase_matches:
        for phrase in phrase_matches:
            pl = phrase.lower()
            if any(w in pl for w in ('self harm', 'hurt myself', 'kill myself', 'end my life', 'want to die')):
                matched_categories.add('Mental Health & Self-Harm')
            elif any(w in pl for w in ('inappropriat', 'sexual')):
                matched_categories.add('Harassment & Abuse')
            elif any(w in pl for w in ('unsafe', 'not safe', 'don\'t feel safe')):
                matched_categories.add('Safety & Threats')
            elif any(w in pl for w in ('mental',)):
                matched_categories.add('Mental Health & Self-Harm')
            elif any(w in pl for w in ('drug', 'substance', 'alcohol')):
                matched_categories.add('Corruption & Misconduct')
    
    return sorted(matched_categories)


# ============================================================================
# BACKWARD-COMPATIBLE WRAPPERS (UNCHANGED)
# ============================================================================

def is_critical_sentiment(text, sentiment=None, score=None):
    """
    Backward-compatible wrapper. Triggers on risk keywords regardless
    of sentiment label.
    """
    risk_categories = detect_risk_content(text)
    return len(risk_categories) > 0
