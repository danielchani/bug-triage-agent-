from bug_triage.models import BugReportInput
from bug_triage.preprocess import preprocess


def test_preserves_original_text():
    report = BugReportInput(raw_text="Hello\nworld")
    pre = preprocess(report)
    assert pre.original_text == "Hello\nworld"


def test_masks_and_extracts_email():
    report = BugReportInput(raw_text="Please contact me at jane.doe@example.com for details.")
    pre = preprocess(report)
    assert pre.extracted_email == "jane.doe@example.com"
    assert "jane.doe@example.com" not in pre.sanitized_text
    assert "[EMAIL]" in pre.sanitized_text


def test_no_email_present():
    report = BugReportInput(raw_text="The app crashes on launch.")
    pre = preprocess(report)
    assert pre.extracted_email is None
    assert pre.sanitized_text == report.raw_text


def test_extracts_hash_style_issue_id():
    report = BugReportInput(raw_text="This is the same as ticket #4821, please check.")
    pre = preprocess(report)
    assert pre.extracted_issue_id == "#4821"


def test_extracts_project_style_issue_id():
    report = BugReportInput(raw_text="Duplicate of BUG-1234, already fixed in staging.")
    pre = preprocess(report)
    assert pre.extracted_issue_id == "BUG-1234"


def test_no_issue_id_present():
    report = BugReportInput(raw_text="The app crashes on launch.")
    pre = preprocess(report)
    assert pre.extracted_issue_id is None


def test_extracts_v_prefixed_version():
    report = BugReportInput(raw_text="Happens on v2.3.1 of the API.")
    pre = preprocess(report)
    assert pre.extracted_version == "2.3.1"


def test_extracts_version_keyword():
    report = BugReportInput(raw_text="Running version 1.2.3 on the server.")
    pre = preprocess(report)
    assert pre.extracted_version == "1.2.3"


def test_no_version_present():
    report = BugReportInput(raw_text="The app crashes on launch.")
    pre = preprocess(report)
    assert pre.extracted_version is None


def test_extracts_windows_os():
    report = BugReportInput(raw_text="Tested on Windows 11, Chrome 125.")
    pre = preprocess(report)
    assert pre.extracted_os == "Windows"


def test_extracts_macos_os():
    report = BugReportInput(raw_text="Reproduced on macOS Sonoma.")
    pre = preprocess(report)
    assert pre.extracted_os == "macOS"


def test_extracts_linux_os():
    report = BugReportInput(raw_text="Running on Linux containers in production.")
    pre = preprocess(report)
    assert pre.extracted_os == "Linux"


def test_extracts_ios_os():
    report = BugReportInput(raw_text="iOS app v6.2.0, iPhone 14.")
    pre = preprocess(report)
    assert pre.extracted_os == "iOS"


def test_extracts_android_os():
    report = BugReportInput(raw_text="Crashes on Android 14 devices.")
    pre = preprocess(report)
    assert pre.extracted_os == "Android"


def test_no_os_present():
    report = BugReportInput(raw_text="The app crashes on launch.")
    pre = preprocess(report)
    assert pre.extracted_os is None


def test_detects_stack_trace():
    report = BugReportInput(
        raw_text=(
            "It fails with:\n"
            "Traceback (most recent call last):\n"
            '  File "reports/export.py", line 42, in export_csv\n'
            "    writer.writerow(row)\n"
        )
    )
    pre = preprocess(report)
    assert pre.has_stack_trace is True


def test_no_stack_trace_present():
    report = BugReportInput(raw_text="The app just crashes sometimes, no error message shown.")
    pre = preprocess(report)
    assert pre.has_stack_trace is False
