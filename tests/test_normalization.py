from app.services.normalization import normalize_url, generate_article_hash

def test_normalize_url():
    # Test tracking params removal
    assert normalize_url("https://example.com/article?utm_source=twitter&utm_medium=social") == "https://example.com/article"
    assert normalize_url("https://example.com/article?fbclid=12345&gclid=67890") == "https://example.com/article"
    
    # Test keeping important params
    assert normalize_url("https://example.com/article?id=42&utm_campaign=sale") == "https://example.com/article?id=42"
    
    # Test ordering (deterministic query string)
    assert normalize_url("https://example.com/article?z=1&a=2") == "https://example.com/article?a=2&z=1"
    
    # Test trailing slash and fragments
    assert normalize_url("https://example.com/article/#comments") == "https://example.com/article"
    assert normalize_url("https://example.com/article/?a=1#section") == "https://example.com/article?a=1"
    
    # Test scheme and hostname casing
    assert normalize_url("HTTPS://Example.COM/Article") == "https://example.com/Article"

def test_generate_article_hash():
    hash1 = generate_article_hash("https://example.com/article", "My Test Article")
    hash2 = generate_article_hash("https://example.com/article", "my test article ")
    
    assert hash1 == hash2
    
    hash3 = generate_article_hash("https://example.com/article", "Different Title")
    assert hash1 != hash3
    
    hash4 = generate_article_hash("https://example.com/article-2", "My Test Article")
    assert hash1 != hash4
