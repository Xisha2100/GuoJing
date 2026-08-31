from guojing.application.help_requests.contracts import HELP_REQUEST_RESULT_SCHEMA_VERSION


def test_help_request_result_schema_is_explicitly_versioned() -> None:
    assert HELP_REQUEST_RESULT_SCHEMA_VERSION == "1.2"
