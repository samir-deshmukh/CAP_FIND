from backend.admin.resolver import valid_url, verify_url


def test_valid_url_normalizes_safe_http_urls():
    assert valid_url("example.edu") == "https://example.edu/"
    assert valid_url("HTTP://example.edu/path") == "http://example.edu/path"


def test_valid_url_rejects_local_and_invalid_targets():
    assert valid_url("ftp://example.edu") is None
    assert valid_url("http://127.0.0.1:8000") is None
    assert valid_url("http://localhost") is None
    assert valid_url("") is None


def test_verify_url_rejects_invalid_url_without_network():
    result = verify_url("localhost", "Example College")
    assert result["ok"] is False
    assert result["note"] == "Invalid URL"


def test_valid_url_rejects_private_ip_and_credentials():
    assert valid_url("http://192.168.1.10/admin") is None
    assert valid_url("http://169.254.169.254/latest/meta-data") is None
    assert valid_url("http://user:pass@example.edu") is None


def test_verify_url_rejects_private_dns_result(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.4", 443))],
    )
    result = verify_url("https://example.edu", "Example College")
    assert result["ok"] is False
    assert "non-public" in result["note"]


def test_infer_city_from_name_uses_whole_phrase_and_longest_match():
    from backend.admin.resolver import infer_city_from_name
    cities = ["Pune", "Navi Mumbai", "Mumbai", "Nashik"]
    assert infer_city_from_name("Navi Mumbai Institute of Technology", cities) == "Navi Mumbai"
    assert infer_city_from_name("College of Engineering, Pune", cities) == "Pune"
    assert infer_city_from_name("Institute of Technology", cities) is None


def test_infer_city_from_name_does_not_match_short_substrings():
    from backend.admin.resolver import infer_city_from_name
    assert infer_city_from_name("Mumbaiwala Institute", ["Mumbai"]) is None
    assert infer_city_from_name("Vidarbha College", ["Nagpur", "Vidarbha"]) is None


def test_gemini_search_uses_cap_code_and_grounded_location_requirements(monkeypatch):
    import io
    import json
    from backend.admin import resolver

    captured = {}
    response_data = {
        "candidates": [{"content": {"parts": [{"text": json.dumps({
            "official_url": None, "city": "Pune", "address": None,
            "confidence": 0.8, "evidence_urls": ["https://example.edu/contact"],
            "note": "Official contact page",
        })}]}}]
    }

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response(json.dumps(response_data).encode())

    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-key")
    monkeypatch.setattr(resolver.urllib.request, "urlopen", fake_urlopen)
    result, _ = resolver.gemini_find(
        "Example College of Engineering", institution_code="1234567"
    )

    prompt = captured["payload"]["contents"][0]["parts"][0]["text"]
    assert "1234567" in prompt
    assert "Do not infer a city from the college name alone" in prompt
    assert result["city"] is None  # A model assertion without Google citations is not trusted.


def test_gemini_results_expose_only_provider_grounding_as_evidence(monkeypatch):
    import io
    import json
    from backend.admin import resolver

    response_data = {
        "candidates": [{
            "content": {"parts": [{"text": json.dumps({
                "official_url": "https://college.example.edu",
                "city": "Pune",
                "evidence_urls": ["https://invented.example/source"],
            })}]},
            "groundingMetadata": {
                "groundingChunks": [{"web": {
                    "uri": "https://cetcell.example.gov.in/institute/1234",
                    "title": "Official institute profile",
                }}],
                "groundingSupports": [{
                    "segment": {"text": "Official website college.example.edu, Pune campus"},
                    "groundingChunkIndices": [0],
                }],
            },
        }]
    }

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-key")
    monkeypatch.setattr(
        resolver.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(json.dumps(response_data).encode()),
    )
    result, _ = resolver.gemini_find("Example College", institution_code="1234")
    assert result["evidence_urls"] == ["https://cetcell.example.gov.in/institute/1234"]
    assert result["model_evidence_urls"] == ["https://invented.example/source"]
    assert resolver._grounding_supports_site(
        "https://college.example.edu", result["grounding_evidence"]
    )
    assert result["city"] == "Pune"


def test_verification_requires_matching_grounded_site_or_explicit_official_link():
    from backend.admin.resolver import _grounding_supports_site

    candidate = "https://college.example.edu"
    assert not _grounding_supports_site(candidate, [{
        "url": "https://unrelated.example.edu/",
        "title": "Example College",
        "supporting_text": [],
    }])
    assert not _grounding_supports_site("https://college.edu.in", [{
        "url": "https://other.edu.in/",
        "title": "Other College",
        "supporting_text": ["https://college.edu.in.fake.example"],
    }])
    assert not _grounding_supports_site(candidate, [{
        "url": "https://directory.example/listing",
        "title": "College Directory: college.example.edu",
        "supporting_text": [],
    }])
    assert _grounding_supports_site(candidate, [{
        "url": "https://cetcell.example.gov.in/institute/1234",
        "title": "Official institute profile",
        "supporting_text": ["Official website: college.example.edu"],
    }])


def test_json_parser_handles_braces_inside_strings_and_surrounding_text():
    from backend.admin.resolver import _json_object_from_text

    assert _json_object_from_text('Result: {"note":"value with } brace", "ok":true} tail') == {
        "note": "value with } brace",
        "ok": True,
    }


def test_city_must_appear_in_a_grounded_response_segment():
    from backend.admin.resolver import _grounding_supports_value

    assert _grounding_supports_value("Navi Mumbai", [{
        "supporting_text": ["The official campus is in Navi Mumbai."],
    }])
    assert not _grounding_supports_value("Mumbai", [{
        "supporting_text": ["The institute is in Navi Mumbai."],
    }])


def test_institute_resolution_treats_blank_metadata_as_missing():
    from backend.admin.resolver import _update_institute_resolution

    class FakeConnection:
        statement = None

        def execute(self, query, params):
            self.statement = (query, params)

    conn = FakeConnection()
    _update_institute_resolution(conn, "1234", city="Pune", source="gemini_google_search")

    query, params = conn.statement
    assert "NULLIF(TRIM(city),'')" in query
    assert params[:2] == ("Pune", "Pune")


def test_import_name_recovery_uses_real_staged_names_not_codes():
    import json
    from backend.admin.resolver import _import_names_for_codes

    class FakeResult:
        def fetchall(self):
            return [
                {"normalized_json": json.dumps({"institution_code": "1234", "institution_name": "Example Institute of Technology"})},
                {"normalized_json": json.dumps({"institution_code": "5678", "institution_name": "5678"})},
            ]

    class FakeConnection:
        def execute(self, query, params):
            assert "import_staging_records" in query
            assert params == ("1234", "5678")
            return FakeResult()

    assert _import_names_for_codes(FakeConnection(), ["1234", "5678"]) == {
        "1234": "Example Institute of Technology"
    }


def test_import_name_recovery_skips_query_when_no_codes():
    from backend.admin.resolver import _import_names_for_codes

    class FakeConnection:
        def execute(self, *args):
            raise AssertionError("Should not query without missing names")

    assert _import_names_for_codes(FakeConnection(), []) == {}
