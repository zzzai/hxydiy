"""Run the standalone source reader's HTTP/privacy contracts in backend CI."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.integrations.tcm.test_readonly_reports import (
    reports,
    test_read_credentials_minimal_list_owner_detail_and_probe_exclusion,
    test_public_ip_spoofed_forward_header_and_invalid_query_rejected,
    test_missing_or_reused_privileged_credential_disables_reader,
)
