import hashlib
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Common tracking parameters to remove
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 
    'utm_term', 'utm_content', 'fbclid', 'gclid',
    '_hsenc', '_hsmi', 'mc_cid', 'mc_eid'
}

def normalize_url(url: str) -> str:
    """
    Deterministically normalizes a URL by:
    - Lowercasing scheme and hostname
    - Removing fragments (#)
    - Removing common tracking query parameters
    - Stripping trailing slashes from the path (if path is not just '/')
    """
    if not url:
        return ""
        
    try:
        parsed = urlparse(url)
        
        # Lowercase scheme and netloc
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        
        # Strip trailing slash from path, but keep it if it's just '/'
        path = parsed.path
        if len(path) > 1 and path.endswith('/'):
            path = path.rstrip('/')
            
        # Process query params
        query = parsed.query
        if query:
            # Parse query parameters keeping the order (parse_qsl preserves order, but we sort it to be deterministic)
            params = parse_qsl(query, keep_blank_values=True)
            # Filter out tracking params
            filtered_params = [(k, v) for k, v in params if k.lower() not in TRACKING_PARAMS]
            # Sort to ensure deterministic URL structure regardless of parameter order
            filtered_params.sort(key=lambda x: x[0])
            query = urlencode(filtered_params)
            
        # Reconstruct URL (omitting fragment)
        normalized = urlunparse((scheme, netloc, path, parsed.params, query, ''))
        return normalized
    except Exception:
        # If parsing fails entirely, return original
        return url

import re

def normalize_title(title: str) -> str:
    """
    Normalizes article titles for clustering comparison:
    - Lowercases text
    - Removes common publication suffixes (e.g. " | TechCrunch")
    - Normalizes whitespace
    - Removes punctuation while preserving version numbers (like GPT-4.5)
    """
    if not title:
        return ""
        
    t = title.lower()
    
    # Remove common publication suffixes
    # Matches patterns like " - TechCrunch", " | The Verge", " — OpenAI"
    t = re.sub(r'\s+[-|—]\s+(?:techcrunch|the verge|wired|openai|venturebeat|nvidia)\s*$', '', t)
    
    # Replace non-word characters with space, EXCEPT dots and hyphens that are surrounded by word chars
    # We want to preserve things like GPT-4, Llama-3, v2.5
    # First, replace punctuation that is DEFINITELY not part of a version number
    t = re.sub(r'[\'\"\[\]\{\}\(\)\,\!\?\:\;]', ' ', t)
    
    # Split by spaces and only keep hyphens/dots if they are internal to a token
    tokens = t.split()
    cleaned_tokens = []
    for token in tokens:
        # strip dots/hyphens from start and end of token
        token = token.strip('.-')
        if token:
            cleaned_tokens.append(token)
            
    # Re-join with single space
    return " ".join(cleaned_tokens)

def generate_article_hash(url: str, title: str) -> str:
    """
    Generates a deterministic hash for an article to detect exact duplicates.
    It uses the normalized URL and a heavily normalized title.
    """
    normalized_url = normalize_url(url)
    safe_title = normalize_title(title)
    safe_url = (normalized_url or "").strip()
    
    hash_input = f"{safe_url}|{safe_title}"
    return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
