"""Revalidate the independent reader's URL; never pass arbitrary vendor links."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit


def original_link(value, report_id):
    if not isinstance(value, str) or not value or len(value) > 4096 or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", report_id):
        return None
    if any(ord(character) <= 32 or ord(character) == 127 or character == "\\" for character in value):
        return None
    try:
        parsed = urlsplit(value)
        route, separator, query = parsed.fragment.partition("?")
        if (parsed.scheme != "https" or parsed.netloc != "yk.qianmaitcm.com" or
                parsed.path != "/print_smart_healthcare/" or parsed.query or
                route != "/discriminateRingReport" or not separator or
                parse_qsl(query, keep_blank_values=True, strict_parsing=True) != [("reportId", report_id)]):
            return None
    except ValueError:
        return None
    return "https://yk.qianmaitcm.com/print_smart_healthcare/#/discriminateRingReport?" + urlencode({"reportId": report_id})
